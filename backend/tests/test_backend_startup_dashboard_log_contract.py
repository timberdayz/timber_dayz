from pathlib import Path


def test_backend_startup_dashboard_bootstrap_logs_are_human_readable():
    text = Path("backend/main.py").read_text(encoding="utf-8")

    assert "资产已自动初始化" in text
    assert "资产已就绪" in text
    assert "资产初始化失败" in text
    assert "连接池预热失败" in text
    assert "璧勪骇" not in text
    assert "???????" not in text
