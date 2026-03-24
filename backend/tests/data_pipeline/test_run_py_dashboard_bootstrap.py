from pathlib import Path


def test_run_py_mentions_dashboard_bootstrap_script():
    text = Path("run.py").read_text(encoding="utf-8", errors="replace")

    assert "bootstrap_postgresql_dashboard.py" in text
    assert "PostgreSQL Dashboard" in text
