from __future__ import annotations

from pathlib import Path


def load_sql_text(path: str | Path) -> str:
    sql_path = Path(path)
    if not sql_path.is_absolute():
        sql_path = Path.cwd() / sql_path
    return sql_path.read_text(encoding="utf-8")
