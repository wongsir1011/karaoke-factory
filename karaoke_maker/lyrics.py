from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from opencc import OpenCC


TIMESTAMP_RE = re.compile(r"\[(\d{1,3}):(\d{1,2}(?:\.\d{1,3})?)\]")
OFFSET_RE = re.compile(r"\[offset:([+-]?\d+)\]", re.IGNORECASE)
METADATA_RE = re.compile(r"^\[(?:ar|al|ti|by|length|re|ve):.*?\]$", re.IGNORECASE)
TOKEN_RE = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]"
    r"|[^\W_]+(?:['’][^\W_]+)*"
    r"|[^\w\s]"
    r"|\s+",
    re.UNICODE,
)


@dataclass(frozen=True, order=True)
class LyricLine:
    start: float
    text: str


@lru_cache(maxsize=1)
def _traditional_converter() -> OpenCC:
    return OpenCC("s2hk")


def to_traditional_chinese(text: str) -> str:
    """Normalize Simplified or mixed Chinese lyrics to Hong Kong Traditional."""
    return _traditional_converter().convert(text)


def has_lrc_timestamps(text: str) -> bool:
    return TIMESTAMP_RE.search(text) is not None


def parse_lrc(text: str, extra_offset_ms: int = 0) -> list[LyricLine]:
    """Parse standard LRC, including multiple timestamps on one line."""
    text = text.lstrip("\ufeff")
    embedded_offset = 0
    match = OFFSET_RE.search(text)
    if match:
        embedded_offset = int(match.group(1))

    total_offset = (embedded_offset + extra_offset_ms) / 1000.0
    parsed: list[LyricLine] = []

    for raw_line in text.splitlines():
        raw_line = raw_line.strip()
        timestamps = list(TIMESTAMP_RE.finditer(raw_line))
        if not timestamps:
            continue

        lyric = to_traditional_chinese(TIMESTAMP_RE.sub("", raw_line).strip())
        if not lyric or METADATA_RE.match(lyric):
            continue

        for timestamp in timestamps:
            minutes = int(timestamp.group(1))
            seconds = float(timestamp.group(2))
            start = max(0.0, minutes * 60 + seconds + total_offset)
            parsed.append(LyricLine(start=start, text=lyric))

    # Some LRC files repeat identical time/text pairs. Keep the first copy.
    unique = {(round(item.start, 3), item.text): item for item in parsed}
    return sorted(unique.values())


def time_plain_lyrics(
    text: str,
    duration: float,
    extra_offset_ms: int = 0,
) -> list[LyricLine]:
    """Create estimated timestamps for plain lyrics as a useful fallback."""
    lines = [
        to_traditional_chinese(line.strip())
        for line in text.lstrip("\ufeff").splitlines()
        if line.strip()
    ]
    if not lines:
        return []

    offset = extra_offset_ms / 1000.0
    usable_start = max(0.0, min(8.0, duration * 0.05) + offset)
    usable_end = max(usable_start + 1.0, duration - min(5.0, duration * 0.03))
    step = max(0.5, (usable_end - usable_start) / len(lines))
    return [
        LyricLine(start=max(0.0, usable_start + index * step), text=line)
        for index, line in enumerate(lines)
    ]


def lyrics_from_text(
    text: str,
    duration: float,
    extra_offset_ms: int = 0,
) -> tuple[list[LyricLine], bool]:
    """Return lyric lines and whether their timing had to be estimated."""
    if has_lrc_timestamps(text):
        return parse_lrc(text, extra_offset_ms), False
    return time_plain_lyrics(text, duration, extra_offset_ms), True


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, int(round(seconds * 100)))
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    secs, cs = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _escape_ass(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\n", r"\N")
    )


def _karaoke_units(text: str) -> list[str]:
    raw = TOKEN_RE.findall(text)
    units: list[str] = []
    for token in raw:
        if token.isspace() and units:
            units[-1] += token
        elif token:
            units.append(token)
    return units or [text]


def karaoke_override_text(text: str, duration: float) -> str:
    r"""Create ASS \kf timing, weighted across words or CJK characters."""
    units = _karaoke_units(text)
    total_cs = max(len(units), int(round(max(0.1, duration) * 100)))
    weights = [max(1, len(re.sub(r"\s", "", unit))) for unit in units]
    weight_sum = sum(weights)

    # Give every unit one centisecond, then apportion the remainder. This
    # guarantees that the override timings add up exactly to the line length.
    remaining = total_cs - len(units)
    shares = [remaining * weight / weight_sum for weight in weights]
    extras = [math.floor(share) for share in shares]
    spare = remaining - sum(extras)
    order = sorted(
        range(len(units)),
        key=lambda index: shares[index] - extras[index],
        reverse=True,
    )
    for index in order[:spare]:
        extras[index] += 1
    timings = [1 + extra for extra in extras]

    return "".join(
        f"{{\\kf{timing}}}{_escape_ass(unit)}"
        for timing, unit in zip(timings, units, strict=True)
    )


def _hex_to_ass_bgr(color: str) -> str:
    match = re.fullmatch(r"#?([0-9a-fA-F]{6})", color.strip())
    if not match:
        raise ValueError("Highlight colour must be a six-digit hex colour")
    rgb = match.group(1).upper()
    return f"&H00{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}"


def _dialogue(
    layer: int,
    start: float,
    end: float,
    style: str,
    text: str,
) -> str:
    return (
        f"Dialogue: {layer},{_ass_time(start)},{_ass_time(end)},"
        f"{style},,0,0,0,,{text}"
    )


def build_ass(
    lines: Iterable[LyricLine],
    video_duration: float,
    *,
    font_name: str = "Microsoft JhengHei",
    font_size: int = 64,
    highlight_color: str = "#FFC928",
) -> str:
    """Build two-row, word/character-highlighting ASS karaoke subtitles."""
    items = [line for line in sorted(lines) if line.text and line.start < video_duration]
    if not items:
        raise ValueError("No timed lyric lines fall inside the video")

    primary = _hex_to_ass_bgr(highlight_color)
    safe_font = font_name.replace(",", " ").strip() or "Arial"
    preview_size = max(36, int(font_size * 0.86))

    header = f"""[Script Info]
Title: Karaoke subtitles
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
PlayResX: 1920
PlayResY: 1080
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: KaraokeBottom,{safe_font},{font_size},{primary},&H00FFFFFF,&H00101010,&H64000000,-1,0,0,0,100,100,1,0,1,4,1,2,80,80,72,1
Style: KaraokeTop,{safe_font},{font_size},{primary},&H00FFFFFF,&H00101010,&H64000000,-1,0,0,0,100,100,1,0,1,4,1,2,80,80,168,1
Style: PreviewBottom,{safe_font},{preview_size},&H00E4E4E4,&H00E4E4E4,&H00101010,&H64000000,-1,0,0,0,100,100,1,0,1,3,1,2,80,80,72,1
Style: PreviewTop,{safe_font},{preview_size},&H00E4E4E4,&H00E4E4E4,&H00101010,&H64000000,-1,0,0,0,100,100,1,0,1,3,1,2,80,80,168,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events: list[str] = []

    # Show the opening line shortly before it begins.
    if items[0].start > 0.25:
        preview_start = max(0.0, items[0].start - 7.0)
        events.append(
            _dialogue(
                0,
                preview_start,
                items[0].start,
                "PreviewBottom",
                _escape_ass(items[0].text),
            )
        )

    for index, line in enumerate(items):
        next_start = items[index + 1].start if index + 1 < len(items) else video_duration
        natural_duration = max(0.5, next_start - line.start)
        active_duration = min(natural_duration, 12.0)
        active_end = min(video_duration, line.start + active_duration)
        row = "Bottom" if index % 2 == 0 else "Top"
        effect = r"{\fad(90,160)}" + karaoke_override_text(line.text, active_duration)
        events.append(
            _dialogue(1, line.start, active_end, f"Karaoke{row}", effect)
        )

        if index + 1 < len(items):
            upcoming = items[index + 1]
            preview_row = "Top" if row == "Bottom" else "Bottom"
            preview_start = max(line.start, upcoming.start - 7.0)
            if upcoming.start - preview_start >= 0.2:
                events.append(
                    _dialogue(
                        0,
                        preview_start,
                        upcoming.start,
                        f"Preview{preview_row}",
                        _escape_ass(upcoming.text),
                    )
                )

    return header + "\n".join(events) + "\n"


def write_ass(
    path: Path,
    lines: Iterable[LyricLine],
    video_duration: float,
    **kwargs: object,
) -> None:
    path.write_text(
        build_ass(lines, video_duration, **kwargs),
        encoding="utf-8-sig",
    )
