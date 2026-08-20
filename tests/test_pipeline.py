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
    LyricsTimingResult,
    PipelineError,
    SourceInfo,
    _KugeciCandidate,
    _YoutubeLogger,
    _center_channel_remove,
    _extract_audio,
    _ffmpeg_filter_available,
    _ffmpeg_path,
    _filter_escape,
    _prepared_instrumental,
    _render_video,
    _safe_filename,
    _select_kugeci_candidate,
    _validate_youtube_url,
    _youtube_options,
    _youtube_pipeline_error,
    discard_lyrics_timing,
    lookup_synced_lyrics,
    prepare_lyrics_timing,
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


def test_prepare_lyrics_timing_returns_editable_line_suggestions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline, "WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(pipeline, "ai_lyric_timing_available", lambda: True)

    def fake_save_upload(settings: JobSettings, job_dir: Path) -> SourceInfo:
        source = job_dir / "source.mp4"
        source.write_bytes(b"video")
        return SourceInfo(source, "測試歌", "歌手", 30.0)

    def fake_extract(source: Path, output: Path) -> None:
        output.write_bytes(b"wav")

    def fake_preview(source: Path, output: Path) -> None:
        output.write_bytes(b"mp3")

    def fake_separate(mixture: Path, instrumental: Path, vocals: Path | None = None) -> Path:
        instrumental.write_bytes(b"instrumental")
        assert vocals is not None
        vocals.write_bytes(b"vocals")
        return instrumental

    monkeypatch.setattr(pipeline, "_save_upload", fake_save_upload)
    monkeypatch.setattr(pipeline, "_extract_audio", fake_extract)
    monkeypatch.setattr(pipeline, "_encode_audio_preview", fake_preview)
    monkeypatch.setattr(pipeline, "_demucs_separate", fake_separate)
    monkeypatch.setattr(
        pipeline,
        "_transcribe_vocals",
        lambda *_: [
            {
                "start": 5.0,
                "end": 6.0,
                "text": "第一句",
                "words": [{"start": 5.0, "end": 6.0, "word": "第一句"}],
            },
            {
                "start": 12.0,
                "end": 13.0,
                "text": "第二句",
                "words": [{"start": 12.0, "end": 13.0, "word": "第二句"}],
            },
        ],
    )

    result = prepare_lyrics_timing(
        JobSettings(
            source_type="upload",
            upload_name="song.mp4",
            upload_bytes=b"video",
        ),
        "第一句\n第二句",
        language="cantonese",
        model_name="small",
    )

    assert [line.start for line in result.lines] == [5.0, 12.0]
    assert result.preview_path.read_bytes() == b"mp3"
    assert result.average_confidence == 1.0
    assert result.instrumental_path.read_bytes() == b"instrumental"
    assert sorted(path.name for path in result.preview_path.parent.glob("*.wav")) == [
        "instrumental.wav"
    ]


def test_prepared_instrumental_must_be_inside_matching_work_folder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work_dir = tmp_path / "work"
    valid = work_dir / "lyrics-valid" / "instrumental.wav"
    valid.parent.mkdir(parents=True)
    valid.write_bytes(b"audio")
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"audio")
    monkeypatch.setattr(pipeline, "WORK_DIR", work_dir)

    assert _prepared_instrumental(
        JobSettings(source_type="upload", prepared_instrumental_path=str(valid))
    ) == valid.resolve()
    assert _prepared_instrumental(
        JobSettings(source_type="upload", prepared_instrumental_path=str(outside))
    ) is None


def test_discard_lyrics_timing_removes_only_its_analysis_folder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work_dir = tmp_path / "work"
    analysis_dir = work_dir / "lyrics-abc123"
    analysis_dir.mkdir(parents=True)
    preview = analysis_dir / "preview.mp3"
    instrumental = analysis_dir / "instrumental.wav"
    preview.write_bytes(b"preview")
    instrumental.write_bytes(b"audio")
    monkeypatch.setattr(pipeline, "WORK_DIR", work_dir)

    discard_lyrics_timing(
        LyricsTimingResult(
            analysis_id="abc123",
            preview_path=preview,
            instrumental_path=instrumental,
            lines=(),
            duration=30.0,
            title="測試",
            artist="歌手",
            language="cantonese",
            model_name="small",
        )
    )

    assert not analysis_dir.exists()


def test_run_pipeline_reuses_prepared_instrumental_without_extracting_again(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work_dir = tmp_path / "work"
    output_dir = tmp_path / "outputs"
    prepared = work_dir / "lyrics-existing" / "instrumental.wav"
    prepared.parent.mkdir(parents=True)
    prepared.write_bytes(b"prepared accompaniment")
    monkeypatch.setattr(pipeline, "WORK_DIR", work_dir)
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(pipeline, "_ensure_subtitle_rendering_support", lambda: None)

    def fake_save_upload(settings: JobSettings, job_dir: Path) -> SourceInfo:
        source = job_dir / "source.mp4"
        source.write_bytes(b"video")
        return SourceInfo(source, "測試歌", "歌手", 30.0)

    def unexpected_extract(*_: object) -> None:
        pytest.fail("prepared accompaniment should skip audio extraction")

    def fake_render(source: Path, instrumental: Path, subtitles: Path, output: Path) -> None:
        assert source.read_bytes() == b"video"
        assert instrumental.read_bytes() == b"prepared accompaniment"
        assert "第一句" in subtitles.read_text(encoding="utf-8-sig")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"karaoke")

    monkeypatch.setattr(pipeline, "_save_upload", fake_save_upload)
    monkeypatch.setattr(pipeline, "_extract_audio", unexpected_extract)
    monkeypatch.setattr(pipeline, "_render_video", fake_render)

    result = run_pipeline(
        JobSettings(
            source_type="upload",
            upload_name="song.mp4",
            upload_bytes=b"video",
            lyrics_source="lrc",
            lyrics_text="[00:01.00]第一句",
            separation_mode="ai",
            prepared_instrumental_path=str(prepared),
        )
    )

    assert result.output_path.read_bytes() == b"karaoke"
    assert prepared.exists()


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
