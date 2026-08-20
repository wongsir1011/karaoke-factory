#!/bin/bash

set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

ffmpeg_supports_ass() {
    local candidate="${1:-}"
    [[ -n "$candidate" && -x "$candidate" ]] || return 1
    "$candidate" -hide_banner -filters 2>&1 \
        | awk '$2 == "ass" { found = 1 } END { exit(found ? 0 : 1) }'
}

configure_subtitle_ffmpeg() {
    local formula=""
    local prefix=""
    local candidate=""
    if ! command -v brew >/dev/null 2>&1; then
        return
    fi
    for formula in ffmpeg@7 ffmpeg-full; do
        prefix="$(brew --prefix "$formula" 2>/dev/null || true)"
        candidate="$prefix/bin/ffmpeg"
        if ffmpeg_supports_ass "$candidate"; then
            export PATH="$prefix/bin:$PATH"
            return
        fi
    done
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

FFMPEG_BIN="$(command -v ffmpeg || true)"
if ! ffmpeg_supports_ass "$FFMPEG_BIN"; then
    echo "FFmpeg 修復後仍然缺少 ASS 動態字幕支援，未能啟動 K 歌工房。"
    exit 1
fi

exec "$VENV_PYTHON" -m streamlit run streamlit_app.py
