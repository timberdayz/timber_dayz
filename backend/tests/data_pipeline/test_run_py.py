from pathlib import Path
import re


def test_run_py_no_longer_accepts_with_metabase_flag():
    text = Path("run.py").read_text(encoding="utf-8", errors="replace")

    assert "--with-metabase" not in text
    assert "check_metabase" not in text
    assert "Metabase" not in text


def test_run_py_does_not_keep_duplicate_entrypoint_definitions():
    text = Path("run.py").read_text(encoding="utf-8", errors="replace")

    for func_name in [
        "main",
        "start_backend",
        "start_frontend",
        "ensure_postgres_redis_docker",
        "_resolve_npm_path",
        "wait_for_frontend_port",
    ]:
        matches = re.findall(rf"^def {re.escape(func_name)}\(", text, flags=re.MULTILINE)
        assert len(matches) == 1, f"{func_name} should be defined exactly once"
