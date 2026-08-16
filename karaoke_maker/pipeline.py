from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Literal
from urllib.parse import urlparse

import requests

from .lyrics import LyricLine, lyrics_from_text, write_ass


BASE_DIR = Path(__file__).resolve().parent.parent
WORK_DIR = BASE_DIR / "work" / "jobs"
OUTPUT_DIR = BASE_DIR / "outputs"
YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtube-nocookie.com",
}
ProgressCallback = Callable[[str, float, str], None]


class PipelineError(RuntimeError):
    def __init__(self, message: str, technical_details: str = "") -> None:
        super().__init__(message)
        self.technical_details = technical_details


@dataclass(frozen=True)
class JobSettings:
    source_type: Literal["youtube", "upload"]
    youtube_url: str = ""
    youtube_cookie_browser: Literal["none", "chrome", "edge", "firefox"] = "none"
    upload_name: str = ""
    upload_bytes: bytes | None = None
    lyrics_source: Literal["auto", "lrc", "paste"] = "auto"
    lyrics_text: str = ""
    track_name: str = ""
    artist_name: str = ""
    separation_mode: Literal["ai", "center"] = "ai"
    lyric_offset_ms: int = 0
    max_height: int = 1080
    font_name: str = "Microsoft JhengHei"
    font_size: int = 64
    highlight_color: str = "#FFC928"


@dataclass(frozen=True)
class SourceInfo:
    path: Path
    title: str
    artist: str
    duration: float


@dataclass(frozen=True)
class PipelineResult:
    output_path: Path
    title: str
    artist: str
    duration: float
    lyric_lines: int
    timing_estimated: bool
    separation_mode: str


def ai_separation_available() -> bool:
    return importlib.util.find_spec("demucs") is not None


def _report(callback: ProgressCallback | None, stage: str, value: float, message: str) -> None:
    if callback:
        callback(stage, max(0.0, min(1.0, value)), message)


def _safe_filename(value: str, fallback: str = "karaoke") -> str:
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    if not value:
        value = fallback
    if value.upper() in {"CON", "PRN", "AUX", "NUL", "COM1", "LPT1"}:
        value = f"_{value}"
    return value[:100].rstrip(" .")


def _validate_youtube_url(url: str) -> None:
    try:
        parsed = urlparse(url.strip())
    except ValueError as exc:
        raise PipelineError("YouTube 連結格式唔正確。") from exc
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or host not in YOUTUBE_HOSTS:
        raise PipelineError("請輸入有效嘅 YouTube 或 youtu.be 連結。")


class _YoutubeLogger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def _remember(self, message: object) -> None:
        text = str(message).strip()
        if text:
            self.messages.append(text)

    def debug(self, message: object) -> None:
        # yt-dlp sends normal console output through debug(); progress is already
        # handled separately, so only retain warnings and errors for diagnosis.
        if str(message).lstrip().startswith(("WARNING:", "ERROR:")):
            self._remember(message)

    def info(self, message: object) -> None:
        return None

    def warning(self, message: object) -> None:
        self._remember(f"WARNING: {message}")

    def error(self, message: object) -> None:
        self._remember(f"ERROR: {message}")


def _sanitize_download_diagnostics(messages: list[str]) -> str:
    text = "\n".join(messages)
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    replacements = {
        str(Path.home()): "%USERPROFILE%",
        str(BASE_DIR): "%PROJECT_DIR%",
    }
    for original, replacement in replacements.items():
        text = text.replace(original, replacement)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[-30:])[-4_000:]


def _youtube_pipeline_error(exc: Exception, messages: list[str]) -> PipelineError:
    diagnostics = _sanitize_download_diagnostics([*messages, str(exc)])
    lowered = diagnostics.lower()

    if "certificate_verify_failed" in lowered or "certificate verify failed" in lowered:
        if os.name == "nt":
            message = (
                "YouTube 安全連線憑證驗證失敗。程式已使用 Windows 系統憑證庫；"
                "請檢查防毒軟件、公司網絡或代理伺服器嘅 HTTPS 掃描設定。"
            )
        else:
            message = (
                "YouTube 安全連線憑證驗證失敗。請確認 macOS 日期時間正確，"
                "並檢查防毒軟件、公司網絡或代理伺服器嘅 HTTPS 掃描設定。"
            )
    elif "could not copy" in lowered and "cookie" in lowered:
        message = "讀取瀏覽器 cookies 失敗。請完全關閉所選瀏覽器後再試，或者關閉 cookies 選項。"
    elif "failed to decrypt" in lowered and "cookie" in lowered:
        if os.name == "nt":
            message = "Windows 無法解密所選瀏覽器嘅 cookies。請改用同一個 Windows 帳戶執行程式。"
        else:
            message = "macOS 無法讀取所選瀏覽器嘅 cookies。請允許終端機存取相關資料，或關閉 cookies 選項。"
    elif any(
        marker in lowered
        for marker in (
            "sign in to confirm",
            "sign in to confirm you're not a bot",
            "login required",
            "authentication required",
        )
    ):
        message = (
            "YouTube 要求登入或驗證你唔係機械人。請展開「下載有困難？」、啟用瀏覽器 cookies，"
            "再選擇你已登入 YouTube 嘅瀏覽器。"
        )
    elif "private video" in lowered:
        message = "呢段係私人影片；只有獲授權並已登入嘅帳戶先可以存取。"
    elif "members-only" in lowered:
        message = "呢段係會員專屬影片；請確認帳戶有觀看權限並啟用瀏覽器 cookies。"
    elif "age-restricted" in lowered or "confirm your age" in lowered:
        message = "呢段影片有年齡限制；請啟用已登入 YouTube 嘅瀏覽器 cookies。"
    elif any(marker in lowered for marker in ("not available in your country", "geo restricted")):
        message = "呢段影片受地區限制，目前網絡位置無法存取。"
    elif any(
        marker in lowered
        for marker in (
            "http error 403",
            "po token",
            "signature solving failed",
            "n challenge solving failed",
            "requested format is not available",
        )
    ):
        message = (
            "YouTube 拒絕咗影片格式請求。請重新執行 .\\setup.ps1 更新 EJS 支援後再試；"
            "如影片要求登入，再啟用瀏覽器 cookies。"
        )
    elif any(marker in lowered for marker in ("timed out", "temporary failure", "connection reset")):
        message = "連接 YouTube 逾時或中斷。程式已自動重試；請檢查網絡後再試。"
    elif "video unavailable" in lowered:
        message = "YouTube 顯示影片無法播放；影片可能已下架、設為私人或限制咗所在地區。"
    else:
        message = "YouTube 下載失敗。請展開技術資料查看實際原因，或者改用本機影片。"

    return PipelineError(message, diagnostics)


def _youtube_options(
    *,
    job_dir: Path,
    max_height: int,
    cookie_browser: str,
    progress_hook: Callable[[dict[str, object]], None],
    logger: _YoutubeLogger,
) -> dict[str, object]:
    options: dict[str, object] = {
        "format": f"bv*[height<={max_height}]+ba/b[height<={max_height}]/best",
        "outtmpl": str(job_dir / "source.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": False,
        "logger": logger,
        "ffmpeg_location": str(_ffmpeg_path()),
        "progress_hooks": [progress_hook],
        "retries": 5,
        "fragment_retries": 5,
        "extractor_retries": 3,
        "file_access_retries": 3,
        "retry_sleep_functions": {
            "http": lambda attempt: min(2 ** max(0, attempt - 1), 10),
            "fragment": lambda attempt: min(2 ** max(0, attempt - 1), 10),
            "extractor": lambda attempt: min(attempt * 2, 10),
        },
        "socket_timeout": 20,
        "concurrent_fragment_downloads": 4,
        "continuedl": True,
        "windowsfilenames": True,
        "js_runtimes": {"deno": {}, "node": {}},
    }
    if os.name == "nt":
        # Prefer the Windows trust store so HTTPS inspection certificates trusted
        # by the operating system also work without disabling TLS verification.
        options["compat_opts"] = {"no-certifi"}
    if cookie_browser in {"chrome", "edge", "firefox"}:
        options["cookiesfrombrowser"] = (cookie_browser, None, None, None)
    return options


def _ffmpeg_path() -> Path:
    system = shutil.which("ffmpeg")
    if system:
        return Path(system)
    try:
        import imageio_ffmpeg

        return Path(imageio_ffmpeg.get_ffmpeg_exe())
    except (ImportError, RuntimeError) as exc:
        raise PipelineError(
            "搵唔到 FFmpeg。請先執行 .\\setup.ps1 安裝所需套件。"
        ) from exc


def _run_command(command: list[str], *, description: str) -> str:
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
        check=False,
    )
    combined = "\n".join(part for part in (process.stdout, process.stderr) if part)
    if process.returncode != 0:
        tail = "\n".join(combined.splitlines()[-25:])
        raise PipelineError(f"{description}失敗。\n\n{tail}")
    return combined


def _probe_duration(media_path: Path) -> float:
    command = [str(_ffmpeg_path()), "-hide_banner", "-i", str(media_path)]
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
        check=False,
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", process.stderr)
    if not match:
        raise PipelineError("讀取唔到影片長度；請確認檔案係有效影片。")
    return int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))


def _download_youtube(
    url: str,
    job_dir: Path,
    max_height: int,
    cookie_browser: str,
    callback: ProgressCallback | None,
) -> SourceInfo:
    _validate_youtube_url(url)
    try:
        import yt_dlp
    except ImportError as exc:
        raise PipelineError("未安裝 yt-dlp；請先執行 .\\setup.ps1。") from exc

    _report(callback, "download", 0.03, "正在連接 YouTube…")

    def progress_hook(event: dict[str, object]) -> None:
        if event.get("status") == "downloading":
            downloaded = float(event.get("downloaded_bytes") or 0)
            total = float(event.get("total_bytes") or event.get("total_bytes_estimate") or 0)
            fraction = downloaded / total if total else 0.1
            _report(callback, "download", 0.03 + fraction * 0.22, "正在下載 MV…")
        elif event.get("status") == "finished":
            _report(callback, "download", 0.25, "MV 下載完成，正在合併音畫…")

    logger = _YoutubeLogger()
    options = _youtube_options(
        job_dir=job_dir,
        max_height=max_height,
        cookie_browser=cookie_browser,
        progress_hook=progress_hook,
        logger=logger,
    )

    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url.strip(), download=True)
    except Exception as exc:
        raise _youtube_pipeline_error(exc, logger.messages) from exc

    candidates = [
        path
        for path in job_dir.glob("source.*")
        if path.is_file() and path.suffix.lower() not in {".part", ".ytdl", ".json"}
    ]
    if not candidates:
        raise PipelineError("下載完成但搵唔到影片檔案。")
    source_path = next((path for path in candidates if path.suffix.lower() == ".mp4"), candidates[0])
    title = str(info.get("track") or info.get("title") or "YouTube MV")
    artist = str(info.get("artist") or info.get("creator") or info.get("uploader") or "")
    duration = float(info.get("duration") or 0) or _probe_duration(source_path)
    return SourceInfo(source_path, title, artist, duration)


def _save_upload(settings: JobSettings, job_dir: Path) -> SourceInfo:
    if not settings.upload_bytes:
        raise PipelineError("請先上載一個影片檔案。")
    suffix = Path(settings.upload_name).suffix.lower()
    if suffix not in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}:
        raise PipelineError("只支援 MP4、MOV、MKV、WEBM 或 M4V 影片。")
    source_path = job_dir / f"source{suffix}"
    source_path.write_bytes(settings.upload_bytes)
    duration = _probe_duration(source_path)
    return SourceInfo(
        source_path,
        settings.track_name.strip() or Path(settings.upload_name).stem,
        settings.artist_name.strip(),
        duration,
    )


def _extract_audio(source: Path, output: Path) -> None:
    _run_command(
        [
            str(_ffmpeg_path()),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "2",
            "-ar",
            "44100",
            "-c:a",
            "pcm_s16le",
            str(output),
        ],
        description="抽取音軌",
    )


def _center_channel_remove(mixture: Path, instrumental: Path) -> None:
    _run_command(
        [
            str(_ffmpeg_path()),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(mixture),
            "-af",
            "pan=stereo|c0=c0-c1|c1=c1-c0,volume=1.65",
            "-c:a",
            "pcm_s16le",
            str(instrumental),
        ],
        description="快速人聲消除",
    )


def _demucs_separate(mixture: Path, instrumental: Path) -> Path:
    if not ai_separation_available():
        raise PipelineError(
            "未安裝 Demucs AI 套件。請關閉程式後執行 `.\\setup.ps1 -WithAI`，"
            "或者改用「快速中心聲道」模式。"
        )
    _run_command(
        [
            sys.executable,
            "-m",
            "karaoke_maker.demucs_runner",
            str(mixture),
            str(instrumental),
        ],
        description="AI 人聲分離",
    )
    if not instrumental.exists():
        raise PipelineError("Demucs 已完成，但搵唔到無人聲音軌。")
    return instrumental


def _normalise_title(title: str) -> str:
    title = re.sub(r"[\[(【].*?(?:official|mv|music video|lyrics?).*?[]\)】]", "", title, flags=re.I)
    title = re.sub(r"\s+", " ", title)
    return title.strip(" -|–—")


def _lyric_score(item: dict[str, object], track: str, artist: str, duration: float) -> float:
    item_track = str(item.get("trackName") or "")
    item_artist = str(item.get("artistName") or "")
    score = SequenceMatcher(None, item_track.casefold(), track.casefold()).ratio() * 4
    if artist:
        score += SequenceMatcher(None, item_artist.casefold(), artist.casefold()).ratio() * 2
    item_duration = float(item.get("duration") or 0)
    if duration and item_duration:
        score += max(0.0, 1.5 - abs(item_duration - duration) / 20)
    return score


def _fetch_synced_lyrics(track: str, artist: str, duration: float) -> str:
    params = {"track_name": track}
    if artist:
        params["artist_name"] = artist
    try:
        response = requests.get(
            "https://lrclib.net/api/search",
            params=params,
            headers={"User-Agent": "KaraokeWorkshop/1.0 (local personal-use app)"},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, json.JSONDecodeError) as exc:
        raise PipelineError("連接同步歌詞服務失敗；請改為上載 LRC 歌詞。") from exc

    choices = [item for item in payload if item.get("syncedLyrics")]
    if not choices:
        raise PipelineError(
            f"搵唔到「{track}」嘅同步歌詞。請上載有時間碼嘅 LRC 檔案。"
        )
    best = max(choices, key=lambda item: _lyric_score(item, track, artist, duration))
    return str(best["syncedLyrics"])


def _prepare_lyrics(
    settings: JobSettings,
    source: SourceInfo,
) -> tuple[list[LyricLine], bool, str, str]:
    track = settings.track_name.strip() or _normalise_title(source.title)
    artist = settings.artist_name.strip() or source.artist.strip()

    if settings.lyrics_source == "auto":
        if not track:
            raise PipelineError("自動搵歌詞需要歌名。")
        lyric_text = _fetch_synced_lyrics(track, artist, source.duration)
    else:
        lyric_text = settings.lyrics_text.strip()
        if not lyric_text:
            raise PipelineError("請上載 LRC 或貼上歌詞。")

    lines, estimated = lyrics_from_text(
        lyric_text,
        source.duration,
        settings.lyric_offset_ms,
    )
    if not lines:
        raise PipelineError("歌詞入面搵唔到可用內容或 LRC 時間碼。")
    return lines, estimated, track, artist


def _filter_escape(path: Path) -> str:
    value = path.resolve().as_posix().replace("'", r"\'")
    value = value.replace(":", r"\:")
    return value


def _render_video(source: Path, instrumental: Path, subtitles: Path, output: Path) -> None:
    ass_filter = f"ass=filename='{_filter_escape(subtitles)}'"
    _run_command(
        [
            str(_ffmpeg_path()),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-i",
            str(instrumental),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-vf",
            ass_filter,
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "256k",
            "-movflags",
            "+faststart",
            "-shortest",
            str(output),
        ],
        description="合成卡拉 OK 影片",
    )


def run_pipeline(
    settings: JobSettings,
    callback: ProgressCallback | None = None,
) -> PipelineResult:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    job_dir = WORK_DIR / uuid.uuid4().hex
    job_dir.mkdir(parents=True)
    succeeded = False

    try:
        if settings.source_type == "youtube":
            source = _download_youtube(
                settings.youtube_url,
                job_dir,
                settings.max_height,
                settings.youtube_cookie_browser,
                callback,
            )
        else:
            _report(callback, "source", 0.05, "正在讀取上載影片…")
            source = _save_upload(settings, job_dir)

        _report(callback, "audio", 0.30, "正在抽取高質音軌…")
        mixture = job_dir / "mixture.wav"
        _extract_audio(source.path, mixture)

        if settings.separation_mode == "ai":
            _report(callback, "separate", 0.38, "AI 正在分離人聲；首次會下載模型…")
            instrumental = _demucs_separate(mixture, job_dir / "instrumental.wav")
        else:
            _report(callback, "separate", 0.42, "正在消除中心聲道人聲…")
            instrumental = job_dir / "instrumental.wav"
            _center_channel_remove(mixture, instrumental)

        _report(callback, "lyrics", 0.68, "正在準備同步歌詞…")
        lyric_lines, timing_estimated, track, artist = _prepare_lyrics(settings, source)
        subtitle_path = job_dir / "karaoke.ass"
        write_ass(
            subtitle_path,
            lyric_lines,
            source.duration,
            font_name=settings.font_name,
            font_size=settings.font_size,
            highlight_color=settings.highlight_color,
        )

        _report(callback, "render", 0.75, "正在加入動態字幕及重新編碼…")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_name = _safe_filename(f"{artist} - {track}".strip(" -"))
        output_path = OUTPUT_DIR / f"{output_name} 卡拉OK {timestamp}.mp4"
        _render_video(source.path, instrumental, subtitle_path, output_path)
        _report(callback, "done", 1.0, "卡拉 OK 影片完成！")
        succeeded = True
        return PipelineResult(
            output_path=output_path,
            title=track,
            artist=artist,
            duration=source.duration,
            lyric_lines=len(lyric_lines),
            timing_estimated=timing_estimated,
            separation_mode=settings.separation_mode,
        )
    finally:
        if succeeded:
            shutil.rmtree(job_dir, ignore_errors=True)
