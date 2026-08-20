from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from karaoke_maker import (
    JobSettings,
    LyricsLookup,
    LyricsTimingResult,
    PipelineError,
    PipelineResult,
    ai_lyric_timing_available,
    ai_separation_available,
    discard_lyrics_timing,
    lookup_synced_lyrics,
    prepare_lyrics_timing,
    run_pipeline,
)
from karaoke_maker.lyric_timing import suggested_lines_to_lrc, validate_manual_lines
from karaoke_maker.lyrics import LyricLine, has_lrc_timestamps


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


def safe_lrc_filename(track: str) -> str:
    name = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", " ", track).strip(" .")
    return f"{name or 'karaoke'} AI對時.lrc"


@st.cache_data(ttl="1h", max_entries=100, show_spinner=False)
def cached_lyrics_lookup(track: str, artist: str) -> LyricsLookup:
    return lookup_synced_lyrics(track, artist)


st.session_state.setdefault("karaoke_result", None)
st.session_state.setdefault("lyrics_lookup", None)
st.session_state.setdefault("lyrics_lookup_signature", None)
st.session_state.setdefault("lyrics_lookup_error", "")
st.session_state.setdefault("lyrics_timing_result", None)
st.session_state.setdefault("lyrics_timing_signature", None)
st.session_state.setdefault("lyrics_timing_confirmed_lrc", "")
st.session_state.setdefault("lyrics_timing_confirmed_signature", None)

st.title("K 歌工房")
st.caption("將你有權使用嘅 MV 變成無主唱、配有動態歌詞嘅卡拉 OK 影片。")

with st.container(horizontal=True):
    st.badge("先確認歌詞", icon=":material/lyrics:", color="green")
    st.badge("下載／上載 MV", icon=":material/video_file:", color="blue")
    st.badge("分離人聲", icon=":material/graphic_eq:", color="violet")
    st.badge("動態字幕", icon=":material/subtitles:", color="orange")

ai_ready = ai_separation_available()
timing_ai_ready = ai_lyric_timing_available()
ai_installer_name = "install-ai.command" if sys.platform == "darwin" else "install-ai.bat"

with st.sidebar:
    st.subheader("系統狀態")
    if ai_ready:
        st.badge("Demucs AI 已安裝", icon=":material/check:", color="green")
    else:
        st.badge("Demucs AI 未安裝", icon=":material/info:", color="orange")
        st.caption(f"高質模式需要先執行 `{ai_installer_name}`。快速模式可以即時使用。")
    if timing_ai_ready:
        st.badge("AI 歌詞對時已安裝", icon=":material/timer:", color="green")
    elif ai_ready:
        st.badge("AI 歌詞對時未安裝", icon=":material/info:", color="orange")
        st.caption(f"重新執行 `{ai_installer_name}` 即可加入歌聲辨認功能。")
    st.caption("成品會保存在專案嘅 `outputs` 資料夾。")

with st.container(border=True):
    st.subheader("1. 先確認歌詞")
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
            placeholder="自動搜尋時必填",
            key="track_name",
        )
    with artist_col:
        artist_name = st.text_input(
            "歌手",
            placeholder="建議填寫，避免揀錯版本",
            key="artist_name",
        )

    lyric_text = ""
    lyrics_ready = False
    lyrics_needs_timing = False
    if lyrics_choice == "自動搜尋":
        st.caption(
            "會先搜尋 Kugeci；搵唔到先用後備同步歌詞服務。確認成功前唔會下載影片或分離人聲。"
            "所有中文歌詞會統一轉成香港繁體。"
        )
        signature = (track_name.strip().casefold(), artist_name.strip().casefold())
        if st.session_state.lyrics_lookup_signature != signature:
            st.session_state.lyrics_lookup = None
            st.session_state.lyrics_lookup_error = ""
            st.session_state.lyrics_lookup_signature = None

        search_lyrics = st.button(
            "搜尋並確認同步歌詞",
            icon=":material/search:",
            width="stretch",
            disabled=not track_name.strip(),
        )
        if search_lyrics:
            st.session_state.lyrics_lookup = None
            st.session_state.lyrics_lookup_error = ""
            with st.spinner("先到 Kugeci 搜尋同步歌詞…"):
                try:
                    found_lyrics = cached_lyrics_lookup(track_name, artist_name)
                except PipelineError as exc:
                    st.session_state.lyrics_lookup_error = str(exc)
                else:
                    st.session_state.lyrics_lookup = found_lyrics
                    st.session_state.lyrics_lookup_signature = signature

        lyrics_lookup: LyricsLookup | None = st.session_state.lyrics_lookup
        if lyrics_lookup is not None and st.session_state.lyrics_lookup_signature == signature:
            lyrics_ready = True
            lyric_text = lyrics_lookup.lyrics
            matched_artist = f"／{lyrics_lookup.artist}" if lyrics_lookup.artist else ""
            st.success(
                f"已從 {lyrics_lookup.source} 找到：{lyrics_lookup.track}{matched_artist}",
                icon=":material/check_circle:",
            )
            st.link_button(
                "查看歌詞來源",
                lyrics_lookup.source_url,
                icon=":material/open_in_new:",
            )
        elif st.session_state.lyrics_lookup_error:
            st.error(st.session_state.lyrics_lookup_error, icon=":material/lyrics:")
        elif not track_name.strip():
            st.info("請先填寫歌名，再搜尋同步歌詞。", icon=":material/info:")
    elif lyrics_choice == "上載 LRC":
        lrc_file = st.file_uploader(
            "LRC 歌詞檔",
            type=["lrc", "txt"],
            help="標準格式例如 `[00:12.50]第一句歌詞`。",
        )
        if lrc_file is not None:
            lyric_text = decode_lyric_file(lrc_file.getvalue())
            lyrics_ready = bool(lyric_text.strip()) and has_lrc_timestamps(lyric_text)
            lyrics_needs_timing = bool(lyric_text.strip()) and not lyrics_ready
    else:
        lyric_text = st.text_area(
            "歌詞內容",
            height=180,
            placeholder="貼上普通逐行歌詞；程式可以先聽歌，再自動加入句級時間。",
            key="pasted_lyrics",
        )
        lyrics_ready = bool(lyric_text.strip()) and has_lrc_timestamps(lyric_text)
        lyrics_needs_timing = bool(lyric_text.strip()) and not lyrics_ready

    if lyrics_needs_timing:
        st.info(
            "呢份歌詞未有時間碼。選擇影片後，可以使用 AI 先聽歌並產生句級 LRC。",
            icon=":material/timer:",
        )

with st.container(border=True):
    st.subheader("2. 選擇 MV")
    source_choice = st.segmented_control(
        "影片來源",
        ["YouTube 連結", "本機影片"],
        default="YouTube 連結",
        required=True,
        width="stretch",
        key="source_choice",
    )
    youtube_url = ""
    youtube_cookie_browser = "none"
    uploaded_video = None
    if source_choice == "YouTube 連結":
        youtube_url = st.text_input(
            "YouTube MV 連結",
            placeholder="https://www.youtube.com/watch?v=…",
            help="只會下載單一影片，唔會下載成條播放清單。",
        )
        with st.expander("下載有困難？", icon=":material/download_for_offline:"):
            use_browser_cookies = st.toggle(
                "影片要求登入時使用瀏覽器 cookies",
                help="一般公開影片唔需要啟用。只有啟用後，程式先會讀取所選瀏覽器嘅 YouTube 登入資料。",
            )
            if use_browser_cookies:
                browser_label = st.selectbox(
                    "已登入 YouTube 嘅瀏覽器",
                    ["Microsoft Edge", "Google Chrome", "Mozilla Firefox"],
                )
                youtube_cookie_browser = {
                    "Microsoft Edge": "edge",
                    "Google Chrome": "chrome",
                    "Mozilla Firefox": "firefox",
                }[browser_label]
                st.warning(
                    "只應喺年齡限制或 YouTube 要求登入時使用。下載過密可能令帳戶暫時受限；"
                    "如果讀取失敗，請完全關閉所選瀏覽器後再試。",
                    icon=":material/warning:",
                )
    else:
        uploaded_video = st.file_uploader(
            "上載影片",
            type=["mp4", "mov", "mkv", "webm", "m4v"],
            help="支援 MP4、MOV、MKV、WEBM 同 M4V。",
        )

rights_confirmed = st.checkbox(
    "我確認自己有權下載及改作呢段影片，並只會按授權或合理用途使用成品。"
)

source_ready = bool(youtube_url.strip()) if source_choice == "YouTube 連結" else uploaded_video is not None
if source_choice == "YouTube 連結":
    source_signature: tuple[object, ...] = (
        "youtube",
        youtube_url.strip(),
        youtube_cookie_browser,
    )
else:
    source_signature = (
        "upload",
        getattr(uploaded_video, "file_id", "") if uploaded_video else "",
        uploaded_video.name if uploaded_video else "",
        uploaded_video.size if uploaded_video else 0,
    )

if lyrics_needs_timing:
    with st.container(border=True):
        st.subheader("3. AI 句級歌詞對時")
        st.caption(
            "程式只會下載分析所需音訊，抽出主唱後在本機辨認演唱位置；歌曲及歌詞唔會上載去第三方 AI 服務。"
        )
        timing_language_label = st.segmented_control(
            "演唱語言",
            ["廣東話", "普通話", "自動判斷"],
            default="廣東話",
            required=True,
            width="stretch",
            key="timing_language_label",
        )
        timing_quality_label = st.segmented_control(
            "分析模式",
            ["標準（較快）", "較準確（較慢）"],
            default="標準（較快）",
            required=True,
            width="stretch",
            key="timing_quality_label",
            help="較準確模式首次需要下載較大模型，舊款電腦或 Intel Mac 可能需要較長時間。",
        )
        timing_language = {
            "廣東話": "cantonese",
            "普通話": "mandarin",
            "自動判斷": "auto",
        }[timing_language_label]
        timing_model = "turbo" if timing_quality_label == "較準確（較慢）" else "small"
        lyric_digest = hashlib.sha256(lyric_text.encode("utf-8")).hexdigest()
        timing_signature = (
            *source_signature,
            lyric_digest,
            timing_language,
            timing_model,
        )

        if not timing_ai_ready:
            st.warning(
                f"需要先關閉程式並執行 `{ai_installer_name}`，加入 Demucs 同 AI 歌詞對時模型。",
                icon=":material/download:",
            )

        analyse_timing = st.button(
            "下載音訊並自動對時",
            icon=":material/hearing:",
            width="stretch",
            disabled=not timing_ai_ready or not source_ready or not rights_confirmed,
        )

        if analyse_timing:
            discard_lyrics_timing(st.session_state.lyrics_timing_result)
            st.session_state.lyrics_timing_result = None
            st.session_state.lyrics_timing_confirmed_lrc = ""
            st.session_state.lyrics_timing_confirmed_signature = None
            timing_settings = JobSettings(
                source_type="youtube" if source_choice == "YouTube 連結" else "upload",
                youtube_url=youtube_url,
                youtube_cookie_browser=youtube_cookie_browser,
                upload_name=uploaded_video.name if uploaded_video else "",
                upload_bytes=uploaded_video.getvalue() if uploaded_video else None,
                track_name=track_name,
                artist_name=artist_name,
            )
            timing_progress = st.progress(0, text="準備分析音訊…")
            timing_status = st.status("準備 AI 歌詞對時…", expanded=True)
            last_timing_stage = {"value": ""}

            def update_timing_progress(stage: str, fraction: float, message: str) -> None:
                timing_progress.progress(int(fraction * 100), text=message)
                timing_status.update(label=message, state="running")
                if stage != last_timing_stage["value"]:
                    timing_status.write(message)
                    last_timing_stage["value"] = stage

            try:
                timing_result = prepare_lyrics_timing(
                    timing_settings,
                    lyric_text,
                    language=timing_language,
                    model_name=timing_model,
                    callback=update_timing_progress,
                )
            except PipelineError as exc:
                timing_progress.empty()
                timing_status.update(label="AI 歌詞對時未完成", state="error", expanded=True)
                st.error(str(exc), icon=":material/error:")
                if exc.technical_details:
                    with st.expander("技術資料", icon=":material/code:"):
                        st.code(exc.technical_details, language="text")
            except Exception as exc:
                timing_progress.empty()
                timing_status.update(label="AI 歌詞對時發生未預期錯誤", state="error")
                st.exception(exc)
            else:
                timing_progress.progress(100, text="AI 對時完成，請逐句覆核")
                timing_status.update(label="AI 對時完成", state="complete", expanded=False)
                st.session_state.lyrics_timing_result = timing_result
                st.session_state.lyrics_timing_signature = timing_signature

        timing_result: LyricsTimingResult | None = st.session_state.lyrics_timing_result
        timing_matches = (
            timing_result is not None
            and st.session_state.lyrics_timing_signature == timing_signature
            and timing_result.preview_path.exists()
        )
        if timing_matches and timing_result is not None:
            st.audio(timing_result.preview_path, format="audio/mpeg")
            review_count = sum(line.confidence < 0.55 for line in timing_result.lines)
            if review_count:
                st.warning(
                    f"有 {review_count} 句 AI 配對信心較低。請播放歌曲並優先校正已標示「需要覆核」嘅句子。",
                    icon=":material/warning:",
                )
            else:
                st.success(
                    "AI 已產生初步句級時間。請播放歌曲並覆核每句開始秒數。",
                    icon=":material/check_circle:",
                )

            editor_rows = pd.DataFrame(
                [
                    {
                        "句數": index,
                        "開始時間（秒）": round(line.start, 2),
                        "歌詞": line.text,
                        "AI 配對信心": line.confidence,
                        "需要覆核": line.confidence < 0.55,
                    }
                    for index, line in enumerate(timing_result.lines, start=1)
                ]
            )
            with st.form(f"lyrics_timing_form_{timing_result.analysis_id}"):
                edited_rows = st.data_editor(
                    editor_rows,
                    key=f"lyrics_timing_editor_{timing_result.analysis_id}",
                    hide_index=True,
                    num_rows="fixed",
                    disabled=["句數", "AI 配對信心", "需要覆核"],
                    column_config={
                        "句數": st.column_config.NumberColumn("句數", width="small"),
                        "開始時間（秒）": st.column_config.NumberColumn(
                            "開始時間（秒）",
                            min_value=0.0,
                            max_value=float(timing_result.duration),
                            step=0.05,
                            format="%.2f",
                            required=True,
                        ),
                        "歌詞": st.column_config.TextColumn(
                            "歌詞（可修改）",
                            width="large",
                            required=True,
                        ),
                        "AI 配對信心": st.column_config.ProgressColumn(
                            "AI 配對信心",
                            min_value=0.0,
                            max_value=1.0,
                            format="percent",
                            width="small",
                        ),
                        "需要覆核": st.column_config.CheckboxColumn(
                            "需要覆核",
                            help="AI 配對信心較低嘅句子會自動標示，請播放歌曲後校正時間。",
                            width="small",
                        ),
                    },
                )
                confirm_timing = st.form_submit_button(
                    "確認時間並使用呢份 LRC",
                    type="primary",
                    icon=":material/check:",
                    width="stretch",
                )

            if confirm_timing:
                corrected_lines = [
                    LyricLine(float(row["開始時間（秒）"]), str(row["歌詞"]))
                    for row in edited_rows.to_dict(orient="records")
                ]
                timing_error = validate_manual_lines(corrected_lines, timing_result.duration)
                if timing_error:
                    st.error(timing_error, icon=":material/error:")
                else:
                    confirmed_lrc = suggested_lines_to_lrc(corrected_lines)
                    st.session_state.lyrics_timing_confirmed_lrc = confirmed_lrc
                    st.session_state.lyrics_timing_confirmed_signature = timing_signature
                    st.toast("句級 LRC 已確認", icon=":material/check_circle:")

        if st.session_state.lyrics_timing_confirmed_signature == timing_signature:
            lyric_text = st.session_state.lyrics_timing_confirmed_lrc
            lyrics_ready = bool(lyric_text.strip())
            st.success(
                "句級 LRC 已確認，可以繼續製作卡拉 OK 影片。",
                icon=":material/check_circle:",
            )
            st.download_button(
                "下載已校正 LRC",
                data=lyric_text,
                file_name=safe_lrc_filename(track_name),
                mime="text/plain; charset=utf-8",
                icon=":material/download:",
                width="stretch",
                on_click="ignore",
            )

with st.container(border=True):
    st.subheader("4. 聲音同字幕設定" if lyrics_needs_timing else "3. 聲音同字幕設定")
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
        lyric_offset_seconds = st.number_input(
            "歌詞整體時間微調（秒）",
            min_value=-120.0,
            max_value=120.0,
            value=0.0,
            step=0.1,
            format="%.1f",
            help="正數令歌詞遲啲出現；負數令歌詞早啲出現。最多可以前後微調 120 秒。",
        )
        font_name = st.text_input("字幕字體", value="Microsoft JhengHei")
        font_size = st.slider("字幕大小", min_value=42, max_value=88, value=64)
        highlight_color = st.color_picker("唱到位置嘅顏色", value="#FFC928")

start = st.button(
    "製作卡拉 OK 影片",
    type="primary",
    icon=":material/movie_edit:",
    width="stretch",
    disabled=not rights_confirmed or not lyrics_ready or not source_ready,
)

if not lyrics_ready:
    if lyrics_needs_timing:
        st.caption("請先完成 AI 句級對時並確認時間，之後先可以開始製作影片。")
    else:
        st.caption("請先確認自動歌詞、上載 LRC 或貼上歌詞，之後先可以開始處理影片。")

if start:
    st.session_state.karaoke_result = None
    source_type = "youtube" if source_choice == "YouTube 連結" else "upload"
    lyrics_source = {
        "自動搜尋": "lrc",
        "上載 LRC": "lrc",
        "貼上歌詞": "paste",
    }[lyrics_choice]

    settings = JobSettings(
        source_type=source_type,
        youtube_url=youtube_url,
        youtube_cookie_browser=youtube_cookie_browser,
        upload_name=uploaded_video.name if uploaded_video else "",
        upload_bytes=uploaded_video.getvalue() if uploaded_video else None,
        lyrics_source=lyrics_source,
        lyrics_text=lyric_text,
        track_name=track_name,
        artist_name=artist_name,
        separation_mode="ai" if separation_label == "AI 高質分離" else "center",
        lyric_offset_ms=int(round(float(lyric_offset_seconds) * 1_000)),
        max_height=int(max_height),
        font_name=font_name,
        font_size=int(font_size),
        highlight_color=highlight_color,
        prepared_instrumental_path=(
            str(timing_result.instrumental_path)
            if lyrics_needs_timing
            and timing_matches
            and timing_result is not None
            and separation_label == "AI 高質分離"
            else ""
        ),
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
        if exc.technical_details:
            with st.expander("下載技術資料", icon=":material/code:"):
                st.code(exc.technical_details, language="text")
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
        discard_lyrics_timing(st.session_state.lyrics_timing_result)
        st.session_state.lyrics_timing_result = None
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
