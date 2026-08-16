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

formula_ffmpeg_path() {
    local formula="$1"
    local prefix=""
    prefix="$(brew --prefix "$formula" 2>/dev/null || true)"
    if [[ -n "$prefix" ]]; then
        printf '%s/bin/ffmpeg\n' "$prefix"
    fi
}

install_or_reinstall_formula() {
    local formula="$1"
    if brew list --versions "$formula" >/dev/null 2>&1; then
        echo "正在重新安裝 $formula……"
        brew reinstall "$formula"
    else
        echo "正在安裝 $formula……"
        brew install "$formula"
    fi
}

pip_install_with_retry() {
    local description="$1"
    shift
    local attempt=1
    local max_attempts=3
    local retry_delay=5

    while true; do
        echo "$description（第 $attempt/$max_attempts 次）……"
        if "$VENV_PYTHON" -m pip install \
            --retries 10 \
            --timeout 60 \
            --disable-pip-version-check \
            "$@"; then
            return 0
        fi
        if [[ $attempt -ge $max_attempts ]]; then
            echo "$description 連續 $max_attempts 次失敗。"
            echo "如果訊息包含 502／503，通常係 PyPI 下載服務暫時繁忙，請稍後再執行 setup.command。"
            return 1
        fi
        echo "下載服務暫時未能連線，等待 $retry_delay 秒後自動再試……"
        sleep "$retry_delay"
        attempt=$((attempt + 1))
        retry_delay=$((retry_delay + 5))
    done
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
    FFMPEG_BIN="$(formula_ffmpeg_path ffmpeg@7)"
    if ! ffmpeg_supports_ass "$FFMPEG_BIN"; then
        install_or_reinstall_formula ffmpeg@7
        FFMPEG_BIN="$(formula_ffmpeg_path ffmpeg@7)"
    fi
fi

if ! ffmpeg_supports_ass "$FFMPEG_BIN"; then
    echo "ffmpeg@7 仍然缺少 ASS 濾鏡，正在改用完整版本……"
    install_or_reinstall_formula ffmpeg-full
    FFMPEG_BIN="$(formula_ffmpeg_path ffmpeg-full)"
fi

if ! ffmpeg_supports_ass "$FFMPEG_BIN"; then
    echo "已嘗試安裝 ffmpeg@7 同 ffmpeg-full，但仍然搵唔到 ASS 字幕濾鏡。"
    echo "請將以上完整安裝訊息回報，方便進一步診斷。"
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

pip_install_with_retry "正在更新 Python 安裝工具" --upgrade pip setuptools wheel
pip_install_with_retry "正在安裝 K 歌工房基本套件" -r requirements.txt

if [[ $WITH_AI -eq 1 ]]; then
    MACHINE="$(uname -m)"
    if [[ "$MACHINE" == "arm64" ]]; then
        pip_install_with_retry \
            "正在安裝 Demucs AI 套件；下載時間可能較長" \
            -r requirements-ai-macos.txt
    elif [[ "$MACHINE" == "x86_64" ]]; then
        pip_install_with_retry \
            "正在安裝 Demucs AI 套件；下載時間可能較長" \
            -r requirements-ai-macos-intel.txt
    else
        echo "未支援的 Mac 架構：$MACHINE"
        exit 1
    fi
fi

echo
echo "安裝完成。請雙擊 start.command 開啟 K 歌工房。"
