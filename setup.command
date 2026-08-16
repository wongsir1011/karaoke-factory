#!/bin/bash

set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

ffmpeg_supports_ass() {
    local candidate="${1:-}"
    [[ -n "$candidate" && -x "$candidate" ]] || return 1
    "$candidate" -hide_banner -filters 2>/dev/null \
        | grep -Eq '[[:space:]]ass[[:space:]]+V->V'
}

WITH_AI=0
if [[ "${1:-}" == "--with-ai" ]]; then
    WITH_AI=1
fi

on_exit() {
    local status=$?
    if [[ $status -ne 0 ]]; then
        echo
        echo "安裝未完成。請查看上方訊息修正問題後再試。"
        read -r -p "按 Return 關閉視窗……" _ || true
    fi
}
trap on_exit EXIT

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "這個安裝程式只適用於 macOS。"
    exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
    echo "K 歌工房需要 Homebrew 安裝 Python、FFmpeg 及 Deno。"
    echo "請先按照 https://brew.sh/ 的指示安裝 Homebrew，再重新開啟此檔案。"
    if command -v open >/dev/null 2>&1; then
        open "https://brew.sh/"
    fi
    exit 1
fi

if ! brew list --versions python@3.12 >/dev/null 2>&1; then
    echo "正在安裝 Python 3.12……"
    brew install python@3.12
fi

PYTHON_BIN="$(brew --prefix python@3.12)/bin/python3.12"
if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "找不到 Homebrew Python 3.12：$PYTHON_BIN"
    exit 1
fi

FFMPEG_BIN="$(command -v ffmpeg || true)"
if ! ffmpeg_supports_ass "$FFMPEG_BIN"; then
    if [[ -n "$FFMPEG_BIN" ]]; then
        echo "現有 FFmpeg 缺少 ASS 動態字幕支援，正在安裝相容版本……"
    else
        echo "正在安裝包含 ASS 動態字幕支援嘅 FFmpeg……"
    fi
    if ! brew list --versions ffmpeg@7 >/dev/null 2>&1; then
        brew install ffmpeg@7
    fi
    FFMPEG_BIN="$(brew --prefix ffmpeg@7)/bin/ffmpeg"
fi

if ! ffmpeg_supports_ass "$FFMPEG_BIN"; then
    echo "FFmpeg 安裝完成，但仍然搵唔到 ASS 字幕濾鏡。"
    echo "請執行：brew reinstall ffmpeg@7"
    exit 1
fi
export PATH="$(dirname "$FFMPEG_BIN"):$PATH"
echo "FFmpeg 動態字幕支援已確認：$FFMPEG_BIN"

if ! command -v deno >/dev/null 2>&1 && ! command -v node >/dev/null 2>&1; then
    echo "正在安裝 Deno，供 YouTube 下載解算使用……"
    brew install deno
fi

VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "正在建立獨立 Python 環境……"
    "$PYTHON_BIN" -m venv "$PROJECT_DIR/.venv"
fi

echo "正在安裝 K 歌工房基本套件……"
"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel
"$VENV_PYTHON" -m pip install -r requirements.txt

if [[ $WITH_AI -eq 1 ]]; then
    MACHINE="$(uname -m)"
    echo "正在安裝 Demucs AI 套件；下載時間可能較長……"
    if [[ "$MACHINE" == "arm64" ]]; then
        "$VENV_PYTHON" -m pip install -r requirements-ai-macos.txt
    elif [[ "$MACHINE" == "x86_64" ]]; then
        "$VENV_PYTHON" -m pip install -r requirements-ai-macos-intel.txt
    else
        echo "未支援的 Mac 架構：$MACHINE"
        exit 1
    fi
fi

echo
echo "安裝完成。請雙擊 start.command 開啟 K 歌工房。"
