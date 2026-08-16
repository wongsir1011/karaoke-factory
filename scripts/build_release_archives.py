from __future__ import annotations

import stat
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXECUTABLE_FILES = {"setup.command", "start.command", "install-ai.command"}

COMMON_FILES = [
    ".streamlit/config.toml",
    "karaoke_maker/__init__.py",
    "karaoke_maker/demucs_runner.py",
    "karaoke_maker/lyrics.py",
    "karaoke_maker/pipeline.py",
    "requirements.txt",
    "streamlit_app.py",
]

WINDOWS_FILES = [
    *COMMON_FILES,
    "README.md",
    "requirements-ai.txt",
    "setup.ps1",
    "start.ps1",
    "start.bat",
    "install-ai.bat",
]

MACOS_FILES = [
    *COMMON_FILES,
    "README-macOS.txt",
    "requirements-ai-macos.txt",
    "requirements-ai-macos-intel.txt",
    "setup.command",
    "start.command",
    "install-ai.command",
]


def _write_archive(archive_path: Path, relative_files: list[str]) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        archive_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for relative_name in relative_files:
            source = ROOT / relative_name
            if not source.is_file():
                raise FileNotFoundError(f"Release file is missing: {relative_name}")

            info = zipfile.ZipInfo(relative_name)
            info.create_system = 3
            mode = 0o755 if relative_name in EXECUTABLE_FILES else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            info.date_time = (2026, 8, 16, 0, 0, 0)
            archive.writestr(info, source.read_bytes())


def build_archives(output_dir: Path | None = None) -> tuple[Path, Path]:
    destination = output_dir or ROOT / "outputs"
    windows_archive = destination / "Karaoke_Factory_Windows.zip"
    macos_archive = destination / "Karaoke_Factory_macOS.zip"
    _write_archive(windows_archive, WINDOWS_FILES)
    _write_archive(macos_archive, MACOS_FILES)
    return windows_archive, macos_archive


if __name__ == "__main__":
    for built_archive in build_archives():
        print(built_archive)

