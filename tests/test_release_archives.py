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

    with zipfile.ZipFile(macos_archive) as archive:
        macos_names = set(archive.namelist())
        assert "start.command" in macos_names
        assert "start.bat" not in macos_names
        assert "requirements-ai-macos-intel.txt" in macos_names

        for command_name in ("setup.command", "start.command", "install-ai.command"):
            mode = archive.getinfo(command_name).external_attr >> 16
            assert mode & stat.S_IXUSR

        setup_script = archive.read("setup.command").decode("utf-8")
        start_script = archive.read("start.command").decode("utf-8")
        assert "install_or_reinstall_formula ffmpeg@7" in setup_script
        assert "install_or_reinstall_formula ffmpeg-full" in setup_script
        assert "ffmpeg_supports_ass" in setup_script
        assert "ffmpeg_supports_ass" in start_script


def test_download_page_links_both_v042_installers() -> None:
    html = (ROOT / "index.html").read_text(encoding="utf-8")

    assert "v0.4.2-rc.1/Karaoke_Factory_Windows.zip" in html
    assert "v0.4.2-rc.1/Karaoke_Factory_macOS.zip" in html
