#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Analyze duplicate / misplaced database tables for phased schema cleanup.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, inspect

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import (
    resolve_runtime_table_schema,
    resolve_runtime_time_column,
)
from backend.utils.config import get_settings
from modules.core.db import Base


KEEP_DUPLICATE_TABLES = {
    "task_center_tasks",
    "task_center_logs",
    "task_center_links",
}

LIKELY_CLEANUP_DUPLICATES = {
    "performance_config",
    "sales_campaigns",
    "sales_campaign_shops",
    "target_breakdown",
    "entity_aliases",
    "staging_raw_data",
    "dim_shops",
}
WAVE_ONE_PRIORITY_TABLES = {
    "catalog_files": "P0",
    "collection_tasks": "P0",
    "collection_task_logs": "P0",
    "task_center_tasks": "P1",
    "task_center_logs": "P1",
    "task_center_links": "P1",
}


def build_migration_evidence_map() -> dict[str, list[str]]:
    evidence: dict[str, list[str]] = {}
    candidates = [
        Path("migrations/versions/20260112_v5_0_0_schema_snapshot.py"),
        Path("migrations/versions/20260328_add_task_center_tables.py"),
    ]
    for path in candidates:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for table_name in WAVE_ONE_PRIORITY_TABLES:
            if table_name in text:
                evidence.setdefault(table_name, []).append(str(path).replace("\\", "/"))
    return evidence


def build_expected_schema_map() -> dict[str, str]:
    expected: dict[str, str] = {}
    for table in Base.metadata.tables.values():
        expected[table.name] = table.schema or "public"
    return expected


def inspect_actual_schema_map(database_url: str | None = None) -> dict[str, list[str]]:
    settings = get_settings()
    url = database_url or settings.DATABASE_URL
    engine = create_engine(url)
    inspector = inspect(engine)
    skip = {"pg_catalog", "information_schema", "pg_toast"}
    actual: dict[str, list[str]] = defaultdict(list)
    try:
        for schema in inspector.get_schema_names():
            if schema in skip:
                continue
            for table_name in inspector.get_table_names(schema=schema):
                actual[table_name].append(schema)
    finally:
        engine.dispose()
    return {k: sorted(v) for k, v in actual.items()}


def classify_duplicate_group(table_name: str, canonical_schema: str, actual_schemas: list[str]) -> tuple[str, str]:
    if table_name in KEEP_DUPLICATE_TABLES:
        return "canonical_keep", "keep current runtime table; do not cleanup in first wave"
    if table_name in LIKELY_CLEANUP_DUPLICATES:
        return "likely_cleanup_candidate", "prove canonical target usage first, then remove duplicate public copy"
    return "needs_manual_review", "requires runtime and data lineage audit before cleanup"


def classify_extra_only_table(table_name: str, actual_schemas: list[str]) -> tuple[str, str, str]:
    schemas = set(actual_schemas)
    if any(schema == "b_class" for schema in schemas) and table_name.startswith("fact_"):
        return (
            "generated_runtime_fact",
            "wave_2_runtime_generated",
            "treat as generated runtime fact asset; exclude from duplicate cleanup and classify with runtime SQL ownership",
        )
    if any(schema == "api" for schema in schemas) and table_name.endswith("_module"):
        return (
            "generated_runtime_api",
            "wave_2_runtime_generated",
            "treat as generated API module asset; exclude from duplicate cleanup and classify with SQL/view generation ownership",
        )
    if any(schema == "ops" for schema in schemas):
        return (
            "operations_runtime_table",
            "wave_3_ops_and_historical",
            "treat as operations/support table and review with infra ownership",
        )
    if table_name.startswith("alembic_version"):
        return (
            "historical_migration_artifact",
            "wave_3_ops_and_historical",
            "treat as migration-history artifact; do not mix with business-table cleanup",
        )
    return (
        "runtime_or_legacy_extra",
        "wave_4_manual_review",
        "inventory and classify before any cleanup",
    )


def analyze_duplicate_groups(
    expected_schema_map: dict[str, str],
    actual_schema_map: dict[str, list[str]],
) -> dict[str, Any]:
    duplicate_groups = []
    misplaced_tables = []
    missing_tables = []

    for table_name, canonical_schema in sorted(expected_schema_map.items()):
        actual_schemas = sorted(actual_schema_map.get(table_name, []))
        if not actual_schemas:
            missing_tables.append(
                {
                    "table_name": table_name,
                    "canonical_schema": canonical_schema,
                    "status": "missing",
                }
            )
            continue

        if len(actual_schemas) > 1:
            risk_class, recommended_action = classify_duplicate_group(
                table_name, canonical_schema, actual_schemas
            )
            duplicate_groups.append(
                {
                    "table_name": table_name,
                    "canonical_schema": canonical_schema,
                    "actual_schemas": actual_schemas,
                    "risk_class": risk_class,
                    "recommended_action": recommended_action,
                }
            )
        elif canonical_schema not in actual_schemas:
            misplaced_tables.append(
                {
                    "table_name": table_name,
                    "canonical_schema": canonical_schema,
                    "actual_schemas": actual_schemas,
                    "risk_class": "schema_alignment_needed",
                    "recommended_action": "align ORM/migration/runtime expectations before cleanup",
                }
            )

    extra_only = []
    follow_up_waves: dict[str, list[str]] = defaultdict(list)
    for table_name, actual_schemas in sorted(actual_schema_map.items()):
        if table_name not in expected_schema_map:
            risk_class, follow_up_wave, recommended_action = classify_extra_only_table(
                table_name,
                sorted(actual_schemas),
            )
            extra_only.append(
                {
                    "table_name": table_name,
                    "actual_schemas": sorted(actual_schemas),
                    "risk_class": risk_class,
                    "follow_up_wave": follow_up_wave,
                    "recommended_action": recommended_action,
                }
            )
            follow_up_waves[follow_up_wave].append(table_name)

    migration_evidence = build_migration_evidence_map()
    wave_one_priority_tables = []
    for table_name, priority in WAVE_ONE_PRIORITY_TABLES.items():
        orm_schema = expected_schema_map.get(table_name)
        runtime_schemas = sorted(actual_schema_map.get(table_name, []))
        runtime_schema = resolve_runtime_table_schema(table_name) or (
            runtime_schemas[0] if runtime_schemas else orm_schema
        )
        wave_one_priority_tables.append(
            {
                "table_name": table_name,
                "wave": "wave_1",
                "priority": priority,
                "orm_schema": orm_schema,
                "runtime_schema": runtime_schema,
                "runtime_schemas": runtime_schemas,
                "runtime_time_column": resolve_runtime_time_column(table_name),
                "migration_evidence": migration_evidence.get(table_name, []),
            }
        )

    return {
        "summary": {
            "expected_table_count": len(expected_schema_map),
            "actual_table_count": len(actual_schema_map),
            "duplicate_group_count": len(duplicate_groups),
            "misplaced_table_count": len(misplaced_tables),
            "missing_table_count": len(missing_tables),
            "extra_only_count": len(extra_only),
        },
        "duplicate_groups": duplicate_groups,
        "misplaced_tables": misplaced_tables,
        "missing_tables": missing_tables,
        "extra_only_tables": extra_only,
        "wave_one_priority_tables": wave_one_priority_tables,
        "follow_up_waves": {key: sorted(value) for key, value in sorted(follow_up_waves.items())},
    }


def main() -> None:
    expected = build_expected_schema_map()
    actual = inspect_actual_schema_map()
    report = analyze_duplicate_groups(expected, actual)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
