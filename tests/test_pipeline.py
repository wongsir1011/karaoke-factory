from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import karaoke_maker.pipeline as pipeline
from karaoke_maker.lyrics import LyricLine, write_ass
from karaoke_maker.pipeline import (
    JobSettings,
    LyricsLookup,
    PipelineError,
    _KugeciCandidate,
    _YoutubeLogger,
    _center_channel_remove,
    _extract_audio,
    _ffmpeg_filter_available,
    _ffmpeg_path,
    _filter_escape,
    _render_video,
    _safe_filename,
    _select_kugeci_candidate,
    _validate_youtube_url,
    _youtube_options,
    _youtube_pipeline_error,
    lookup_synced_lyrics,
    run_pipeline,
)


def test_youtube_url_validation() -> None:
    _validate_youtube_url("https://youtu.be/abcdefghijk")
    _validate_youtube_url("https://www.youtube.com/watch?v=abcdefghijk")


def test_safe_filename_removes_windows_characters() -> None:
    assert _safe_filename('A/B: C*D? "Live"') == "A B C D Live"


def test_ffmpeg_filter_escape_handles_windows_drive() -> None:
    escaped = _filter_escape(Path("C:/Music/lyrics.ass"))
    assert "\\:" in escaped


def test_ffmpeg_has_ass_subtitle_filter() -> None:
    assert _ffmpeg_filter_available("ass") is True


def test_missing_ass_filter_stops_before_youtube_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    download_started = False

    def unexpected_download(*_: object, **__: object) -> None:
        nonlocal download_started
        download_started = True

    monkeypatch.setattr(pipeline, "_ffmpeg_filter_available", lambda *_: False)
    monkeypatch.setattr(pipeline, "_download_youtube", unexpected_download)

    with pytest.raises(PipelineError, match="ASS 動態字幕濾鏡"):
        run_pipeline(
            JobSettings(
                source_type="youtube",
                youtube_url="https://youtu.be/abcdefghijk",
                lyrics_source="lrc",
                lyrics_text="[00:01.00]測試",
            )
        )

    assert download_started is False


def test_youtube_options_enable_reliable_download_features(tmp_path: Path) -> None:
    logger = _YoutubeLogger()
    options = _youtube_options(
        job_dir=tmp_path,
        max_height=720,
        cookie_browser="edge",
        progress_hook=lambda event: None,
        logger=logger,
    )

    assert options["js_runtimes"] == {"deno": {}, "node": {}}
    assert options["cookiesfrombrowser"] == ("edge", None, None, None)
    assert options["concurrent_fragment_downloads"] == 4
    assert options["continuedl"] is True
    assert options["retries"] == 5
    assert options["socket_timeout"] == 20
    if os.name == "nt":
        assert options["compat_opts"] == {"no-certifi"}


def test_youtube_options_do_not_read_cookies_by_default(tmp_path: Path) -> None:
    options = _youtube_options(
        job_dir=tmp_path,
        max_height=1080,
        cookie_browser="none",
        progress_hook=lambda event: None,
        logger=_YoutubeLogger(),
    )

    assert "cookiesfrombrowser" not in options


def test_youtube_error_explains_login_requirement() -> None:
    error = _youtube_pipeline_error(
        RuntimeError("Sign in to confirm you’re not a bot"),
        [],
    )

    assert "瀏覽器" in str(error)
    assert "cookies" in str(error)
    assert "not a bot" in error.technical_details


def test_kugeci_candidate_matches_title_and_artist() -> None:
    candidates = [
        _KugeciCandidate("wrong", "海闊天空", "許冠傑"),
        _KugeciCandidate("right", "海阔天空", "BEYOND"),
    ]

    result = _select_kugeci_candidate(candidates, "海闊天空", "Beyond")

    assert result is not None
    assert result.song_id == "right"


def test_lyrics_lookup_uses_kugeci_before_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = LyricsLookup(
        lyrics="[00:01.00]測試",
        track="測試",
        artist="歌手",
        source="Kugeci",
        source_url="https://www.kugeci.com/song/test",
    )
    monkeypatch.setattr(pipeline, "_fetch_kugeci_synced_lyrics", lambda *_: expected)

    def unexpected_fallback(*_: object) -> None:
        pytest.fail("LRCLIB should not be called after a Kugeci match")

    monkeypatch.setattr(pipeline, "_fetch_lrclib_synced_lyrics", unexpected_fallback)

    assert lookup_synced_lyrics("測試", "歌手") == expected


def test_lyrics_lookup_falls_back_after_kugeci_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = LyricsLookup(
        lyrics="[00:01.00]後備",
        track="測試",
        artist="歌手",
        source="LRCLIB",
        source_url="https://lrclib.net/",
    )
    monkeypatch.setattr(pipeline, "_fetch_kugeci_synced_lyrics", lambda *_: None)
    monkeypatch.setattr(pipeline, "_fetch_lrclib_synced_lyrics", lambda *_: expected)

    assert lookup_synced_lyrics("測試", "歌手") == expected


def test_missing_lyrics_stops_before_youtube_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    download_started = False

    def fail_lookup(*_: object) -> None:
        raise PipelineError("搵唔到歌詞")

    def unexpected_download(*_: object, **__: object) -> None:
        nonlocal download_started
        download_started = True

    monkeypatch.setattr(pipeline, "lookup_synced_lyrics", fail_lookup)
    monkeypatch.setattr(pipeline, "_download_youtube", unexpected_download)

    with pytest.raises(PipelineError, match="搵唔到歌詞"):
        run_pipeline(
            JobSettings(
                source_type="youtube",
                youtube_url="https://youtu.be/abcdefghijk",
                lyrics_source="auto",
                track_name="不存在歌曲",
            )
        )

    assert download_started is False


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
