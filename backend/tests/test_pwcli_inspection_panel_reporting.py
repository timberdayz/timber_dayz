from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PANEL_HTML = REPO_ROOT / "scripts" / "pwcli_inspection_panel_static" / "index.html"
PANEL_PY = REPO_ROOT / "scripts" / "pwcli_inspection_panel.py"


def test_panel_html_renders_message_not_only_status():
    """前端日志必须渲染 result.message（真实 stdout/stderr），不能只有 result.status。

    注意：断言必须写 ``result.message``（精确），不能写 ``.message`` —— 后者会被
    文件里已有的 ``error.message`` 命中，测试就成了永远通过的空守卫。
    """
    text = PANEL_HTML.read_text(encoding="utf-8")
    assert "result.status" in text, "前端未渲染 result.status"
    assert "result.message" in text, "前端未渲染 result.message"

    matched = [line for line in text.splitlines() if "result.message" in line]
    assert matched, "未找到渲染 result.message 的语句"
    assert any("result.status" in line for line in matched), (
        "result.message 与 result.status 不在同一条日志里，失败信息仍会被丢掉"
    )


def test_panel_success_response_includes_message():
    """成功时也必须把 stdout 带回来，否则前端没有可显示的内容。"""
    text = PANEL_PY.read_text(encoding="utf-8")
    assert "combined_output" in text, "成功分支没有把 stdout/stderr 合并进 message"
