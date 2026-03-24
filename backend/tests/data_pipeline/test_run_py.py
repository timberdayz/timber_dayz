from pathlib import Path


def test_run_py_no_longer_accepts_with_metabase_flag():
    text = Path("run.py").read_text(encoding="utf-8", errors="replace")

    assert "--with-metabase" not in text
    assert "check_metabase" not in text
    assert "Metabase" not in text
