from __future__ import annotations

import re
import unicodedata
import math
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable, Mapping, Sequence

from .lyrics import LyricLine, METADATA_RE, TIMESTAMP_RE, to_traditional_chinese


ALIGNMENT_CHAR_RE = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]|[a-z0-9]",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TranscriptToken:
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class SuggestedLyricLine:
    start: float
    text: str
    confidence: float


def plain_lyric_lines(text: str) -> list[str]:
    """Return display-ready lyric lines without LRC metadata or timestamps."""
    lines: list[str] = []
    for raw_line in text.lstrip("\ufeff").splitlines():
        stripped = TIMESTAMP_RE.sub("", raw_line).strip()
        if not stripped or METADATA_RE.match(stripped):
            continue
        converted = to_traditional_chinese(stripped)
        if converted:
            lines.append(converted)
    return lines


def _alignment_chars(text: str) -> list[str]:
    normalised = to_traditional_chinese(unicodedata.normalize("NFKC", text)).casefold()
    return ALIGNMENT_CHAR_RE.findall(normalised)


def _spread_token(token: TranscriptToken) -> list[TranscriptToken]:
    chars = _alignment_chars(token.text)
    if not chars:
        return []
    duration = max(0.02, token.end - token.start)
    step = duration / len(chars)
    return [
        TranscriptToken(
            text=char,
            start=token.start + index * step,
            end=token.start + (index + 1) * step,
        )
        for index, char in enumerate(chars)
    ]


def transcript_tokens_from_segments(
    segments: Iterable[Mapping[str, object]],
) -> list[TranscriptToken]:
    """Convert Whisper-style segments into timestamped alignment characters."""
    tokens: list[TranscriptToken] = []
    for segment in segments:
        words = segment.get("words")
        if isinstance(words, Sequence) and not isinstance(words, (str, bytes)):
            word_tokens: list[TranscriptToken] = []
            for word in words:
                if not isinstance(word, Mapping):
                    continue
                try:
                    start = float(word.get("start", 0.0))
                    end = float(word.get("end", start + 0.02))
                except (TypeError, ValueError):
                    continue
                word_tokens.extend(
                    _spread_token(
                        TranscriptToken(str(word.get("word") or ""), start, end)
                    )
                )
            if word_tokens:
                tokens.extend(word_tokens)
                continue

        try:
            start = float(segment.get("start", 0.0))
            end = float(segment.get("end", start + 0.02))
        except (TypeError, ValueError):
            continue
        tokens.extend(
            _spread_token(
                TranscriptToken(str(segment.get("text") or ""), start, end)
            )
        )
    return sorted(tokens, key=lambda item: (item.start, item.end))


def _interpolate_missing_starts(
    starts: list[float | None],
    duration: float,
) -> list[float]:
    count = len(starts)
    anchors = [index for index, value in enumerate(starts) if value is not None]
    if not anchors:
        usable_start = min(8.0, max(0.0, duration * 0.05))
        usable_end = max(usable_start + 0.5, duration - min(5.0, duration * 0.03))
        step = max(0.1, (usable_end - usable_start) / max(1, count))
        return [min(duration, usable_start + index * step) for index in range(count)]

    output = [float(value) if value is not None else -1.0 for value in starts]
    first = anchors[0]
    if first:
        first_time = output[first]
        interval = min(5.0, first_time / (first + 1))
        for index in range(first - 1, -1, -1):
            output[index] = max(0.0, first_time - interval * (first - index))

    for left, right in zip(anchors, anchors[1:], strict=False):
        if right - left <= 1:
            continue
        span = output[right] - output[left]
        step = max(0.05, span / (right - left))
        for index in range(left + 1, right):
            output[index] = output[left] + step * (index - left)

    last = anchors[-1]
    if last < count - 1:
        remaining = count - last - 1
        available = max(0.1, duration - output[last])
        interval = min(5.0, available / (remaining + 1))
        for index in range(last + 1, count):
            output[index] = output[last] + interval * (index - last)

    previous = -0.05
    for index, value in enumerate(output):
        clamped = max(0.0, min(max(0.0, duration - 0.05), value))
        clamped = max(clamped, previous + 0.05)
        output[index] = min(duration, clamped)
        previous = output[index]
    return output


def align_lyrics_to_transcript(
    lyric_text: str,
    transcript_tokens: Sequence[TranscriptToken],
    duration: float,
) -> list[SuggestedLyricLine]:
    """Align exact lyric lines to noisy ASR output while preserving line order."""
    lines = plain_lyric_lines(lyric_text)
    if not lines:
        return []

    lyric_chars: list[str] = []
    lyric_char_lines: list[int] = []
    line_char_counts: list[int] = []
    for line_index, line in enumerate(lines):
        chars = _alignment_chars(line)
        line_char_counts.append(len(chars))
        lyric_chars.extend(chars)
        lyric_char_lines.extend([line_index] * len(chars))

    if not lyric_chars or not transcript_tokens:
        starts = _interpolate_missing_starts([None] * len(lines), duration)
        return [
            SuggestedLyricLine(start=start, text=line, confidence=0.0)
            for start, line in zip(starts, lines, strict=True)
        ]

    transcript_chars = [token.text for token in transcript_tokens]
    matcher = SequenceMatcher(None, lyric_chars, transcript_chars, autojunk=False)
    matches_by_line: list[list[int]] = [[] for _ in lines]
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            lyric_index = block.a + offset
            transcript_index = block.b + offset
            matches_by_line[lyric_char_lines[lyric_index]].append(transcript_index)

    starts: list[float | None] = []
    confidences: list[float] = []
    for line_index, matched_indices in enumerate(matches_by_line):
        char_count = line_char_counts[line_index]
        confidence = len(set(matched_indices)) / char_count if char_count else 0.0
        confidences.append(max(0.0, min(1.0, confidence)))
        if matched_indices:
            starts.append(transcript_tokens[min(matched_indices)].start)
        else:
            starts.append(None)

    interpolated = _interpolate_missing_starts(starts, duration)
    return [
        SuggestedLyricLine(start=start, text=line, confidence=confidence)
        for start, line, confidence in zip(
            interpolated,
            lines,
            confidences,
            strict=True,
        )
    ]


def suggested_lines_to_lrc(lines: Iterable[SuggestedLyricLine | LyricLine]) -> str:
    output: list[str] = []
    for line in lines:
        centiseconds = max(0, int(round(float(line.start) * 100)))
        minutes, remainder = divmod(centiseconds, 6_000)
        seconds, fraction = divmod(remainder, 100)
        output.append(f"[{minutes:02d}:{seconds:02d}.{fraction:02d}]{line.text}")
    return "\n".join(output) + ("\n" if output else "")


def validate_manual_lines(
    lines: Sequence[LyricLine],
    duration: float,
) -> str:
    if not lines:
        return "歌詞列表係空白。"
    previous = -1.0
    for index, line in enumerate(lines, start=1):
        if not line.text.strip():
            return f"第 {index} 句歌詞係空白。"
        if not math.isfinite(line.start):
            return f"第 {index} 句開始時間必須係有效秒數。"
        if line.start < 0 or line.start > duration:
            return f"第 {index} 句開始時間必須介乎 0 至 {duration:.1f} 秒。"
        if line.start <= previous:
            return f"第 {index} 句開始時間必須遲過上一句。"
        previous = line.start
    return ""
