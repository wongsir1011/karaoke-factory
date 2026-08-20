from __future__ import annotations

import stat
import zipfile
from pathlib import Path

from scripts.build_release_archives import ROOT, build_archives


def test_release_archives_have_platform_specific_launchers(tmp_path: Path) -> None:
    windows_archive, macos_archive = build_archives(tmp_path)

    with zipfile.ZipFile(windows_archive) as archive:
        windows_names = set(archive.namelist())
        assert "start.bat" in windows_names
        assert "start.command" not in windows_names
        assert "karaoke_maker/lyric_timing.py" in windows_names
        assert "openai-whisper==20250625" in archive.read(
            "requirements-ai.txt"
        ).decode("utf-8")
        assert "--no-build-isolation" in archive.read("setup.ps1").decode("utf-8")

    with zipfile.ZipFile(macos_archive) as archive:
        macos_names = set(archive.namelist())
        assert "start.command" in macos_names
        assert "start.bat" not in macos_names
        assert "requirements-ai-macos-intel.txt" in macos_names
        assert "karaoke_maker/lyric_timing.py" in macos_names
        assert "openai-whisper==20250625" in archive.read(
            "requirements-ai-macos.txt"
        ).decode("utf-8")

        for command_name in ("setup.command", "start.command", "install-ai.command"):
            mode = archive.getinfo(command_name).external_attr >> 16
            assert mode & stat.S_IXUSR

        setup_script = archive.read("setup.command").decode("utf-8")
        start_script = archive.read("start.command").decode("utf-8")
        assert "install_or_reinstall_formula ffmpeg@7" in setup_script
        assert "install_or_reinstall_formula ffmpeg-full" in setup_script
        assert "ffmpeg_supports_ass" in setup_script
        assert "ffmpeg_supports_ass" in start_script
        assert "pip_install_with_retry" in setup_script
        assert "--retries 10" in setup_script
        assert "--timeout 60" in setup_script
        assert "max_attempts=3" in setup_script
        assert "--no-build-isolation" in setup_script


def test_download_page_links_both_v050_installers() -> None:
    html = (ROOT / "index.html").read_text(encoding="utf-8")

    assert "v0.5.0-rc.1/Karaoke_Factory_Windows.zip" in html
    assert "v0.5.0-rc.1/Karaoke_Factory_macOS.zip" in html
    assert "AI 句級歌詞對時" in html
