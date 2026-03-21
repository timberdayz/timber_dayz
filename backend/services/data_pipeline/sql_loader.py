from __future__ import annotations

from pathlib import Path


def load_sql_text(path: str | Path) -> str:
    sql_path = Path(path)
    if not sql_path.is_absolute():
        sql_path = Path.cwd() / sql_path
    return sql_path.read_text(encoding="utf-8").lstrip("\ufeff")


def split_sql_statements(sql_text: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_double_quote = False
    in_dollar_quote = False
    dollar_tag = "$$"

    i = 0
    length = len(sql_text)
    while i < length:
        char = sql_text[i]
        next_two = sql_text[i : i + 2]

        if not in_single_quote and not in_double_quote and next_two == "$$":
            in_dollar_quote = not in_dollar_quote
            current.append(next_two)
            i += 2
            continue

        if not in_double_quote and not in_dollar_quote and char == "'" and (i == 0 or sql_text[i - 1] != "\\"):
            in_single_quote = not in_single_quote
            current.append(char)
            i += 1
            continue

        if not in_single_quote and not in_dollar_quote and char == '"' and (i == 0 or sql_text[i - 1] != "\\"):
            in_double_quote = not in_double_quote
            current.append(char)
            i += 1
            continue

        if char == ";" and not in_single_quote and not in_double_quote and not in_dollar_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            i += 1
            continue

        current.append(char)
        i += 1

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements
