from __future__ import annotations

from pathlib import Path


def load_sql_text(path: str | Path) -> str:
    sql_path = Path(path)
    if not sql_path.is_absolute():
        sql_path = Path.cwd() / sql_path
    return sql_path.read_text(encoding="utf-8").lstrip("\ufeff")


def _match_dollar_quote(sql_text: str, start: int) -> str | None:
    if sql_text[start] != "$":
        return None
    end = sql_text.find("$", start + 1)
    if end == -1:
        return None
    token = sql_text[start : end + 1]
    if len(token) < 2 or token[-1] != "$":
        return None
    inner = token[1:-1]
    if inner and not inner.replace("_", "a").isalnum():
        return None
    return token


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
        if not in_single_quote and not in_double_quote:
            matched_dollar_tag = _match_dollar_quote(sql_text, i)
            if matched_dollar_tag:
                if not in_dollar_quote:
                    in_dollar_quote = True
                    dollar_tag = matched_dollar_tag
                    current.append(matched_dollar_tag)
                    i += len(matched_dollar_tag)
                    continue
                if sql_text.startswith(dollar_tag, i):
                    in_dollar_quote = False
                    current.append(dollar_tag)
                    i += len(dollar_tag)
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
