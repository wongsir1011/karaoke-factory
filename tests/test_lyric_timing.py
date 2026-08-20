from __future__ import annotations

import math

from karaoke_maker.lyric_timing import (
    SuggestedLyricLine,
    TranscriptToken,
    align_lyrics_to_transcript,
    plain_lyric_lines,
    suggested_lines_to_lrc,
    transcript_tokens_from_segments,
    validate_manual_lines,
)
from karaoke_maker.lyrics import LyricLine


def test_plain_lyric_lines_remove_metadata_and_convert_traditional() -> None:
    text = "[ti:測試]\n[00:01.00]爱你一万年\n\n头发里面"

    assert plain_lyric_lines(text) == ["愛你一萬年", "頭髮裏面"]


def test_transcript_segments_prefer_word_timestamps() -> None:
    tokens = transcript_tokens_from_segments(
        [
            {
                "start": 1.0,
                "end": 4.0,
                "text": "不應使用呢個整段時間",
                "words": [
                    {"start": 1.0, "end": 2.0, "word": "今天"},
                    {"start": 3.0, "end": 4.0, "word": "看雪"},
                ],
            }
        ]
    )

    assert [token.text for token in tokens] == list("今天看雪")
    assert tokens[0].start == 1.0
    assert tokens[2].start == 3.0


def test_align_exact_lyrics_to_noisy_transcript_and_interpolate_missing_line() -> None:
    transcript = [
        TranscriptToken("今", 10.0, 10.2),
        TranscriptToken("天", 10.2, 10.4),
        TranscriptToken("看", 10.4, 10.6),
        TranscriptToken("雪", 10.6, 10.8),
        TranscriptToken("仍", 20.0, 20.2),
        TranscriptToken("然", 20.2, 20.4),
        TranscriptToken("熱", 20.4, 20.6),
        TranscriptToken("愛", 20.6, 20.8),
    ]

    aligned = align_lyrics_to_transcript(
        "今天看雪\n模型漏咗呢句\n仍然熱愛",
        transcript,
        duration=30.0,
    )

    assert [line.text for line in aligned] == ["今天看雪", "模型漏咗呢句", "仍然熱愛"]
    assert aligned[0].start == 10.0
    assert 10.0 < aligned[1].start < 20.0
    assert aligned[1].confidence == 0.0
    assert aligned[2].start == 20.0
    assert aligned[0].confidence == 1.0


def test_repeated_chorus_keeps_monotonic_matches() -> None:
    transcript = [
        TranscriptToken(char, start, start + 0.1)
        for char, start in zip("愛你愛你", [5.0, 5.2, 12.0, 12.2], strict=True)
    ]

    aligned = align_lyrics_to_transcript("愛你\n愛你", transcript, duration=20.0)

    assert [line.start for line in aligned] == [5.0, 12.0]


def test_lrc_export_uses_centiseconds() -> None:
    output = suggested_lines_to_lrc(
        [SuggestedLyricLine(65.234, "第一句", 0.8)]
    )

    assert output == "[01:05.23]第一句\n"


def test_manual_lines_must_be_strictly_increasing_and_within_duration() -> None:
    assert validate_manual_lines(
        [LyricLine(1.0, "第一句"), LyricLine(2.0, "第二句")],
        10.0,
    ) == ""
    assert "遲過上一句" in validate_manual_lines(
        [LyricLine(2.0, "第一句"), LyricLine(2.0, "第二句")],
        10.0,
    )
    assert "介乎" in validate_manual_lines([LyricLine(11.0, "第一句")], 10.0)
    assert "有效秒數" in validate_manual_lines(
        [LyricLine(math.nan, "第一句")],
        10.0,
    )
