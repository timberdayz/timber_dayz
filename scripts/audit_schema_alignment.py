#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate a schema-alignment audit artifact that combines:
- full ORM/runtime drift inventory
- wave-1 runtime-critical table priorities
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.analyze_schema_cleanup_candidates import (  # noqa: E402
    analyze_duplicate_groups,
    build_expected_schema_map,
    build_migration_evidence_map,
    inspect_actual_schema_map,
)


def build_markdown_report(report: dict) -> str:
    lines: list[str] = []
    summary = report["summary"]

    lines.append("# Schema Alignment Audit")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Expected ORM tables: `{summary['expected_table_count']}`")
    lines.append(f"- Actual runtime table names: `{summary['actual_table_count']}`")
    lines.append(f"- Duplicate groups: `{summary['duplicate_group_count']}`")
    lines.append(f"- Misplaced tables: `{summary['misplaced_table_count']}`")
    lines.append(f"- Missing ORM tables: `{summary['missing_table_count']}`")
    lines.append(f"- Extra-only runtime tables: `{summary['extra_only_count']}`")
    lines.append("")

    lines.append("## Wave 1 Priority Tables")
    lines.append("")
    for item in report["wave_one_priority_tables"]:
        lines.append(f"### {item['table_name']}")
        lines.append("")
        lines.append(f"- Priority: `{item['priority']}`")
        lines.append(f"- Wave: `{item['wave']}`")
        lines.append(f"- ORM schema: `{item['orm_schema']}`")
        lines.append(f"- Runtime schema: `{item['runtime_schema']}`")
        lines.append(f"- Runtime schemas discovered: `{item['runtime_schemas']}`")
        lines.append(f"- Runtime time column: `{item['runtime_time_column']}`")
        lines.append(
            f"- Migration evidence: `{', '.join(item['migration_evidence']) if item['migration_evidence'] else 'none recorded'}`"
        )
        lines.append("")

    lines.append("## Duplicate Groups")
    lines.append("")
    if report["duplicate_groups"]:
        for item in report["duplicate_groups"]:
            lines.append(f"- `{item['table_name']}`: canonical `{item['canonical_schema']}`, actual `{item['actual_schemas']}`, class `{item['risk_class']}`")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("## Misplaced Tables")
    lines.append("")
    for item in report["misplaced_tables"][:50]:
        lines.append(
            f"- `{item['table_name']}`: ORM `{item['canonical_schema']}` vs runtime `{item['actual_schemas']}`"
        )
    if len(report["misplaced_tables"]) > 50:
        lines.append(f"- ... {len(report['misplaced_tables']) - 50} more")
    lines.append("")

    lines.append("## Missing Tables")
    lines.append("")
    if report["missing_tables"]:
        for item in report["missing_tables"]:
            lines.append(f"- `{item['table_name']}` expected in `{item['canonical_schema']}`")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("## Extra-Only Runtime Tables")
    lines.append("")
    for item in report["extra_only_tables"][:50]:
        lines.append(
            f"- `{item['table_name']}` in `{item['actual_schemas']}`"
            f" class=`{item['risk_class']}` wave=`{item['follow_up_wave']}`"
        )
    if len(report["extra_only_tables"]) > 50:
        lines.append(f"- ... {len(report['extra_only_tables']) - 50} more")
    lines.append("")

    lines.append("## Follow-Up Waves")
    lines.append("")
    for wave_name, table_names in report.get("follow_up_waves", {}).items():
        lines.append(f"### {wave_name}")
        lines.append("")
        for table_name in table_names[:30]:
            lines.append(f"- `{table_name}`")
        if len(table_names) > 30:
            lines.append(f"- ... {len(table_names) - 30} more")
        lines.append("")

    lines.append("## Wave 2 Governance")
    lines.append("")
    lines.append("`wave_2_runtime_generated` contains generated runtime assets, not canonical business tables.")
    lines.append("")
    lines.append("- generated runtime fact asset: `b_class.fact_*` tables produced by collection/data pipelines")
    lines.append("- generated runtime API asset: `api.*_module` tables/materialized outputs used by dashboard/query paths")
    lines.append("- these assets must not be treated as ORM-missing business-table drift")
    lines.append("- these assets must not be targeted by duplicate/public cleanup waves")
    lines.append("- later work should govern ownership, generation, refresh, and verification, not force ORM parity")
    lines.append("")

    lines.append("## First Repair Wave Recommendation")
    lines.append("")
    lines.append("- Start with the wave-1 runtime-critical table family.")
    lines.append("- Treat schema-placement mismatches and time-column mismatches as immediate alignment targets.")
    lines.append("- Keep duplicate cleanup for non-wave-1 tables behind proof-based follow-up waves.")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    expected = build_expected_schema_map()
    actual = inspect_actual_schema_map()
    report = analyze_duplicate_groups(expected, actual)
    report["migration_evidence"] = build_migration_evidence_map()

    if "--json" in sys.argv:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print(build_markdown_report(report))


if __name__ == "__main__":
    main()
