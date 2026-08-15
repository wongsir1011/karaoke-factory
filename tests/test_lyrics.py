from __future__ import annotations

import re

import pytest

from karaoke_maker.lyrics import (
    LyricLine,
    build_ass,
    karaoke_override_text,
    lyrics_from_text,
    parse_lrc,
    to_traditional_chinese,
)


def test_parse_lrc_supports_offsets_and_multiple_timestamps() -> None:
    lrc = """[offset:500]
[00:01.00][00:03.00]你好
[00:05.25]世界
"""
    assert parse_lrc(lrc) == [
        LyricLine(1.5, "你好"),
        LyricLine(3.5, "你好"),
        LyricLine(5.75, "世界"),
    ]


def test_plain_lyrics_are_marked_as_estimated() -> None:
    lines, estimated = lyrics_from_text("第一句\n第二句\n第三句", 60)
    assert estimated is True
    assert len(lines) == 3
    assert lines == sorted(lines)


def test_simplified_lyrics_are_always_converted_to_hk_traditional() -> None:
    assert to_traditional_chinese("爱你一万年，头发里面，后台干活。") == "愛你一萬年，頭髮裏面，後台幹活。"

    lines = parse_lrc("[00:01.00]爱你一万年\n[00:03.00]头发里面")
    assert [line.text for line in lines] == ["愛你一萬年", "頭髮裏面"]


def test_karaoke_timing_fills_requested_duration() -> None:
    output = karaoke_override_text("Hello 世界", 3.25)
    timings = [int(value) for value in re.findall(r"\\kf(\d+)", output)]
    assert sum(timings) == 325
    assert len(timings) >= 3


def test_build_ass_has_two_rows_and_karaoke_effects() -> None:
    result = build_ass(
        [LyricLine(1.0, "第一句"), LyricLine(4.0, "第二句")],
        video_duration=8.0,
        highlight_color="#112233",
    )
    assert "Style: KaraokeBottom" in result
    assert "Style: KaraokeTop" in result
    assert "&H00332211" in result
    assert r"{\kf" in result
    assert result.count("Dialogue:") >= 3


def test_build_ass_rejects_empty_lyrics() -> None:
    with pytest.raises(ValueError, match="No timed lyric"):
        build_ass([], video_duration=20)
