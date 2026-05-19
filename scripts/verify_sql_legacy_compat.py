#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Static gate: legacy column compatibility for dashboard SQL assets.

CI cannot access production snapshots, so we enforce a simple contract:
Any SQL asset referencing legacy Chinese columns that are known to vary across
historical databases MUST include a guard that detects available columns and
builds a compatible expression.

Currently enforced:
- a_class.operating_costs: "营销费用" vs "工资"
"""

from __future__ import annotations

from pathlib import Path


SQL_ROOTS = [
    Path("sql") / "api_modules",
    Path("sql") / "mart",
    Path("sql") / "semantic",
    Path("sql") / "ops",
]


LEGACY_COLUMN_RULES: list[dict[str, str]] = [
    {
        "needle": '"营销费用"',
        # Heuristic: file must contain a column-existence probe OR a shared expr variable.
        "required_any": [
            "column_name = '营销费用'",
            "marketing_fee_expr",
        ],
        "message": 'SQL asset references column "营销费用" but has no compatibility guard (expected column probe / marketing_fee_expr).',
    },
]


def verify_sql_legacy_compat() -> bool:
    offenders: list[str] = []
    roots = [p for p in SQL_ROOTS if p.exists()]
    for root in roots:
        for path in root.rglob("*.sql"):
            text = path.read_text(encoding="utf-8", errors="replace")
            for rule in LEGACY_COLUMN_RULES:
                if rule["needle"] not in text:
                    continue
                if any(req in text for req in rule["required_any"]):
                    continue
                offenders.append(f"{path.as_posix()}: {rule['message']}")

    if offenders:
        raise RuntimeError("Legacy SQL compat gate failed:\n" + "\n".join(offenders))
    return True


def main() -> int:
    ok = verify_sql_legacy_compat()
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
