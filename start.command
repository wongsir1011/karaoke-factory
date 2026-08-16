#!/bin/bash

set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

configure_subtitle_ffmpeg() {
    local prefix=""
    if command -v brew >/dev/null 2>&1; then
        prefix="$(brew --prefix ffmpeg@7 2>/dev/null || true)"
    fi
    if [[ -n "$prefix" && -x "$prefix/bin/ffmpeg" ]]; then
        export PATH="$prefix/bin:$PATH"
    fi
}

ffmpeg_supports_ass() {
    local candidate="${1:-}"
    [[ -n "$candidate" && -x "$candidate" ]] || return 1
    "$candidate" -hide_banner -filters 2>/dev/null \
        | grep -Eq '[[:space:]]ass[[:space:]]+V->V'
}

configure_subtitle_ffmpeg

VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
FFMPEG_BIN="$(command -v ffmpeg || true)"
if [[ ! -x "$VENV_PYTHON" ]] || ! ffmpeg_supports_ass "$FFMPEG_BIN"; then
    if [[ -x "$VENV_PYTHON" ]] && ! ffmpeg_supports_ass "$FFMPEG_BIN"; then
        echo "偵測到舊版 FFmpeg 缺少動態字幕支援，現在自動修復……"
    fi
    "$PROJECT_DIR/setup.command"
    configure_subtitle_ffmpeg
fi

exec "$VENV_PYTHON" -m streamlit run streamlit_app.py
