from pathlib import Path


def test_backend_startup_logs_postgres_path_status_conditionally():
    text = Path("backend/main.py").read_text(encoding="utf-8")

    assert "postgres_path_configured = auto_configure_postgres_path(emit_output=False)" in text
    assert "[OK] PostgreSQL客户端PATH配置完成" in text
    assert "[SKIP] PostgreSQL客户端工具未找到，跳过PATH配置" in text
    assert "PostgreSQL客户端PATH:" in text
