from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_app_initial_view_renders_without_exception() -> None:
    app_path = Path(__file__).resolve().parent.parent / "streamlit_app.py"
    app = AppTest.from_file(str(app_path), default_timeout=30).run()

    assert not app.exception
    assert app.title[0].value == "K 歌工房"
    assert any(item.label == "搜尋並確認同步歌詞" for item in app.button)
    assert any(item.label == "製作卡拉 OK 影片" for item in app.button)
    assert [item.value for item in app.subheader[:3]] == [
        "1. 先確認歌詞",
        "2. 選擇 MV",
        "3. 聲音同字幕設定",
    ]
    assert app.toggle[0].label == "影片要求登入時使用瀏覽器 cookies"
    lyric_offset = next(
        item
        for item in app.number_input
        if item.label == "歌詞整體時間微調（秒）"
    )
    assert lyric_offset.min == -120.0
    assert lyric_offset.max == 120.0
    assert lyric_offset.proto.step == 0.1
    assert lyric_offset.proto.format == "%.1f"

    app.toggle[0].set_value(True).run()
    assert not app.exception
    assert any(item.label == "已登入 YouTube 嘅瀏覽器" for item in app.selectbox)


def test_plain_lyrics_require_ai_timing_before_video_creation() -> None:
    app_path = Path(__file__).resolve().parent.parent / "streamlit_app.py"
    app = AppTest.from_file(str(app_path), default_timeout=30).run()

    app.segmented_control[0].set_value("貼上歌詞").run()
    app.text_area[0].set_value("第一句\n第二句").run()

    assert not app.exception
    assert [item.value for item in app.subheader[:4]] == [
        "1. 先確認歌詞",
        "2. 選擇 MV",
        "3. AI 句級歌詞對時",
        "4. 聲音同字幕設定",
    ]
    assert any(item.label == "演唱語言" for item in app.segmented_control)
    assert any(item.label == "分析模式" for item in app.segmented_control)
    analyse = next(item for item in app.button if item.label == "下載音訊並自動對時")
    create = next(item for item in app.button if item.label == "製作卡拉 OK 影片")
    assert analyse.disabled is True
    assert create.disabled is True
