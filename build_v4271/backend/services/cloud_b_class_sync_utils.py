from __future__ import annotations

import re

TABLE_NAME_PATTERN = re.compile(r"^fact_[a-z0-9_]+$")


def validate_b_class_table_name(table_name: str) -> str:
    if not TABLE_NAME_PATTERN.fullmatch(table_name or ""):
        raise ValueError(f"Invalid B-class table name: {table_name}")
    return table_name


def quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
