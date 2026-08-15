from __future__ import annotations

from pathlib import Path

import streamlit as st

from karaoke_maker import (
    JobSettings,
    PipelineError,
    PipelineResult,
    ai_separation_available,
    run_pipeline,
)


st.set_page_config(
    page_title="K 歌工房",
    page_icon=":material/lyrics:",
    layout="centered",
)


def decode_lyric_file(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "big5", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def duration_label(seconds: float) -> str:
    minutes, secs = divmod(int(round(seconds)), 60)
    return f"{minutes}:{secs:02d}"


st.session_state.setdefault("karaoke_result", None)

st.title("K 歌工房")
st.caption("將你有權使用嘅 MV 變成無主唱、配有動態歌詞嘅卡拉 OK 影片。")

with st.container(horizontal=True):
    st.badge("下載／上載 MV", icon=":material/video_file:", color="blue")
    st.badge("分離人聲", icon=":material/graphic_eq:", color="violet")
    st.badge("動態字幕", icon=":material/subtitles:", color="orange")

ai_ready = ai_separation_available()

with st.sidebar:
    st.subheader("系統狀態")
    if ai_ready:
        st.badge("Demucs AI 已安裝", icon=":material/check:", color="green")
    else:
        st.badge("Demucs AI 未安裝", icon=":material/info:", color="orange")
        st.caption("高質模式需要先執行 `.\\setup.ps1 -WithAI`。快速模式可以即時使用。")
    st.caption("成品會保存在專案嘅 `outputs` 資料夾。")

with st.container(border=True):
    st.subheader("1. 選擇 MV")
    source_choice = st.segmented_control(
        "影片來源",
        ["YouTube 連結", "本機影片"],
        default="YouTube 連結",
        required=True,
        width="stretch",
        key="source_choice",
    )
    youtube_url = ""
    uploaded_video = None
    if source_choice == "YouTube 連結":
        youtube_url = st.text_input(
            "YouTube MV 連結",
            placeholder="https://www.youtube.com/watch?v=…",
            help="只會下載單一影片，唔會下載成條播放清單。",
        )
    else:
        uploaded_video = st.file_uploader(
            "上載影片",
            type=["mp4", "mov", "mkv", "webm", "m4v"],
            help="支援 MP4、MOV、MKV、WEBM 同 M4V。",
        )

with st.container(border=True):
    st.subheader("2. 準備歌詞")
    lyrics_choice = st.segmented_control(
        "歌詞來源",
        ["自動搜尋", "上載 LRC", "貼上歌詞"],
        default="自動搜尋",
        required=True,
        width="stretch",
        key="lyrics_choice",
    )

    title_col, artist_col = st.columns(2)
    with title_col:
        track_name = st.text_input(
            "歌名",
            placeholder="留空會嘗試從影片讀取",
        )
    with artist_col:
        artist_name = st.text_input(
            "歌手",
            placeholder="留空會嘗試從影片讀取",
        )

    lyric_text = ""
    if lyrics_choice == "自動搜尋":
        st.caption("會搜尋公開同步歌詞；填寫準確歌名同歌手可以大幅提高配對成功率。所有中文歌詞會統一轉成香港繁體。")
    elif lyrics_choice == "上載 LRC":
        lrc_file = st.file_uploader(
            "LRC 歌詞檔",
            type=["lrc", "txt"],
            help="標準格式例如 `[00:12.50]第一句歌詞`。",
        )
        if lrc_file is not None:
            lyric_text = decode_lyric_file(lrc_file.getvalue())
    else:
        lyric_text = st.text_area(
            "歌詞內容",
            height=180,
            placeholder="最好貼上有 [分鐘:秒數] 時間碼嘅 LRC；普通逐行歌詞亦可，但時間只會平均估算。",
        )

with st.container(border=True):
    st.subheader("3. 聲音同字幕設定")
    separation_label = st.segmented_control(
        "去人聲方法",
        ["AI 高質分離", "快速中心聲道"],
        default="AI 高質分離" if ai_ready else "快速中心聲道",
        required=True,
        width="stretch",
        help="AI 效果通常較好但需時較長；快速模式對主唱置中嘅立體聲歌曲最有效。",
    )

    with st.expander("進階設定", icon=":material/tune:"):
        max_height = st.selectbox("影片最高解像度", [720, 1080], index=1)
        lyric_offset_ms = st.number_input(
            "歌詞整體時間微調（毫秒）",
            min_value=-10_000,
            max_value=10_000,
            value=0,
            step=100,
            help="正數令歌詞遲啲出現；負數令歌詞早啲出現。",
        )
        font_name = st.text_input("字幕字體", value="Microsoft JhengHei")
        font_size = st.slider("字幕大小", min_value=42, max_value=88, value=64)
        highlight_color = st.color_picker("唱到位置嘅顏色", value="#FFC928")

rights_confirmed = st.checkbox(
    "我確認自己有權下載及改作呢段影片，並只會按授權或合理用途使用成品。"
)

start = st.button(
    "製作卡拉 OK 影片",
    type="primary",
    icon=":material/movie_edit:",
    width="stretch",
    disabled=not rights_confirmed,
)

if start:
    st.session_state.karaoke_result = None
    source_type = "youtube" if source_choice == "YouTube 連結" else "upload"
    lyrics_source = {
        "自動搜尋": "auto",
        "上載 LRC": "lrc",
        "貼上歌詞": "paste",
    }[lyrics_choice]

    settings = JobSettings(
        source_type=source_type,
        youtube_url=youtube_url,
        upload_name=uploaded_video.name if uploaded_video else "",
        upload_bytes=uploaded_video.getvalue() if uploaded_video else None,
        lyrics_source=lyrics_source,
        lyrics_text=lyric_text,
        track_name=track_name,
        artist_name=artist_name,
        separation_mode="ai" if separation_label == "AI 高質分離" else "center",
        lyric_offset_ms=int(lyric_offset_ms),
        max_height=int(max_height),
        font_name=font_name,
        font_size=int(font_size),
        highlight_color=highlight_color,
    )

    progress = st.progress(0, text="準備開始…")
    status = st.status("準備製作…", expanded=True)
    last_stage = {"value": ""}

    def update_progress(stage: str, fraction: float, message: str) -> None:
        progress.progress(int(fraction * 100), text=message)
        status.update(label=message, state="running")
        if stage != last_stage["value"]:
            status.write(message)
            last_stage["value"] = stage

    try:
        result = run_pipeline(settings, update_progress)
    except PipelineError as exc:
        progress.empty()
        status.update(label="製作未完成", state="error", expanded=True)
        st.error(str(exc), icon=":material/error:")
    except Exception as exc:
        progress.empty()
        status.update(label="發生未預期錯誤", state="error", expanded=True)
        st.error("程式遇到未預期錯誤。請展開下面嘅技術資料。", icon=":material/error:")
        with st.expander("技術資料", icon=":material/code:"):
            st.exception(exc)
    else:
        progress.progress(100, text="完成")
        status.update(label="卡拉 OK 影片完成", state="complete", expanded=False)
        st.session_state.karaoke_result = result
        st.toast("影片製作完成", icon=":material/check_circle:")

result: PipelineResult | None = st.session_state.karaoke_result
if result and Path(result.output_path).exists():
    st.subheader("完成作品")
    st.video(str(result.output_path))

    with st.container(horizontal=True):
        st.badge(duration_label(result.duration), icon=":material/schedule:", color="gray")
        st.badge(f"{result.lyric_lines} 句歌詞", icon=":material/subtitles:", color="blue")
        method = "AI 分離" if result.separation_mode == "ai" else "快速消聲"
        st.badge(method, icon=":material/graphic_eq:", color="violet")

    if result.timing_estimated:
        st.warning(
            "你提供嘅歌詞冇時間碼，所以字幕時間係平均估算。用同步 LRC 再整一次會準好多。",
            icon=":material/timer:",
        )

    output_path = Path(result.output_path)
    st.download_button(
        "下載卡拉 OK MP4",
        data=lambda path=output_path: path.read_bytes(),
        file_name=output_path.name,
        mime="video/mp4",
        type="primary",
        icon=":material/download:",
        width="stretch",
        on_click="ignore",
    )

st.caption("提示：分離效果取決於原曲混音；和聲、混響同現場錄音通常會保留少量人聲。")
