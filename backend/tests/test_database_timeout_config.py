from pathlib import Path


def test_database_layer_uses_120s_statement_timeout():
    text = Path("backend/models/database.py").read_text(encoding="utf-8", errors="replace")

    assert "statement_timeout=120000" in text
    assert 'cursor.execute("SET statement_timeout TO 120000")' in text
    assert "statement_timeout=30000" not in text
    assert 'cursor.execute("SET statement_timeout TO 30000")' not in text
