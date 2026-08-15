from __future__ import annotations

import subprocess
from pathlib import Path

from karaoke_maker.lyrics import LyricLine, write_ass
from karaoke_maker.pipeline import (
    _center_channel_remove,
    _extract_audio,
    _ffmpeg_path,
    _filter_escape,
    _render_video,
    _safe_filename,
    _validate_youtube_url,
)


def test_youtube_url_validation() -> None:
    _validate_youtube_url("https://youtu.be/abcdefghijk")
    _validate_youtube_url("https://www.youtube.com/watch?v=abcdefghijk")


def test_safe_filename_removes_windows_characters() -> None:
    assert _safe_filename('A/B: C*D? "Live"') == "A B C D Live"


def test_ffmpeg_filter_escape_handles_windows_drive() -> None:
    escaped = _filter_escape(Path("C:/Music/lyrics.ass"))
    assert "\\:" in escaped


def test_fast_mode_and_subtitle_render_end_to_end(tmp_path: Path) -> None:
    ffmpeg = str(_ffmpeg_path())
    source = tmp_path / "source.mp4"
    mixture = tmp_path / "mixture.wav"
    instrumental = tmp_path / "instrumental.wav"
    subtitles = tmp_path / "karaoke.ass"
    output = tmp_path / "karaoke.mp4"

    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x243447:s=640x360:d=2:r=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
    )
    _extract_audio(source, mixture)
    _center_channel_remove(mixture, instrumental)
    write_ass(
        subtitles,
        [LyricLine(0.1, "測試字幕"), LyricLine(1.0, "Karaoke")],
        2.0,
    )
    _render_video(source, instrumental, subtitles, output)

    assert output.exists()
    assert output.stat().st_size > 1_000
