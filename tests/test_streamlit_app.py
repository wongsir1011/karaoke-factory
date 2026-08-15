from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_app_initial_view_renders_without_exception() -> None:
    app_path = Path(__file__).resolve().parent.parent / "streamlit_app.py"
    app = AppTest.from_file(str(app_path), default_timeout=30).run()

    assert not app.exception
    assert app.title[0].value == "K 歌工房"
    assert app.button[0].label == "製作卡拉 OK 影片"
    assert app.toggle[0].label == "影片要求登入時使用瀏覽器 cookies"

    app.toggle[0].set_value(True).run()
    assert not app.exception
    assert any(item.label == "已登入 YouTube 嘅瀏覽器" for item in app.selectbox)
