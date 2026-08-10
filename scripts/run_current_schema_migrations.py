#!/usr/bin/env python3
"""Fail-closed entrypoint for the isolated current-schema Alembic chain."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, inspect, text
from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[1]
CURRENT_VERSION_TABLE = "current_schema_alembic_version"
LEGACY_VERSION_TABLE = "alembic_version"
SYSTEM_SCHEMAS = {"information_schema", "pg_catalog", "pg_toast"}
SUPPORT_POLICY_PATH = ROOT / "current_migrations" / "support_policy.json"


class MigrationSafetyError(RuntimeError):
    """Raised when migration preflight cannot prove that writing is safe."""


@dataclass(frozen=True)
class MigrationState:
    database_empty: bool
    current_revision: str | None
    legacy_revision: str | None
    schema_fingerprint: str | None


def _normalize(value: Any) -> str | None:
    if value is None:
        return None
    return " ".join(str(value).strip().lower().split())


def _stable_values(values: list[Any] | None) -> list[str]:
    return sorted(_normalize(value) or "<null>" for value in values or [])


def _single_revision(connection, schema: str, table: str) -> str | None:
    inspector = inspect(connection)
    if not inspector.has_table(table, schema=schema):
        return None
    rows = (
        connection.execute(
            text(f'SELECT version_num FROM "{schema}"."{table}" ORDER BY version_num')
        )
        .scalars()
        .all()
    )
    if len(rows) != 1:
        raise MigrationSafetyError(
            f"{schema}.{table} must contain exactly one revision, found {len(rows)}"
        )
    return str(rows[0])


def schema_fingerprint(connection, inspector=None) -> str:
    """Build a stable, read-only fingerprint from PostgreSQL schema metadata."""
    inspector = inspector or inspect(connection)
    tables: list[dict[str, Any]] = []
    ignored_tables = {CURRENT_VERSION_TABLE, LEGACY_VERSION_TABLE}

    for schema in sorted(inspector.get_schema_names()):
        if schema in SYSTEM_SCHEMAS:
            continue
        for table in sorted(inspector.get_table_names(schema=schema)):
            if table in ignored_tables:
                continue
            columns = [
                {
                    "default": _normalize(column.get("default")),
                    "name": column["name"],
                    "nullable": bool(column.get("nullable")),
                    "type": _normalize(column.get("type")),
                }
                for column in inspector.get_columns(table, schema=schema)
            ]
            foreign_keys = [
                {
                    "constrained_columns": _stable_values(
                        fk.get("constrained_columns")
                    ),
                    "referred_columns": _stable_values(fk.get("referred_columns")),
                    "referred_schema": fk.get("referred_schema") or "public",
                    "referred_table": fk.get("referred_table"),
                }
                for fk in inspector.get_foreign_keys(table, schema=schema)
            ]
            indexes = [
                {
                    "column_names": _stable_values(index.get("column_names")),
                    "expressions": _stable_values(index.get("expressions")),
                    "name": index.get("name"),
                    "unique": bool(index.get("unique")),
                }
                for index in inspector.get_indexes(table, schema=schema)
            ]
            tables.append(
                {
                    "columns": columns,
                    "foreign_keys": sorted(
                        foreign_keys,
                        key=lambda item: json.dumps(item, sort_keys=True),
                    ),
                    "indexes": sorted(
                        indexes, key=lambda item: json.dumps(item, sort_keys=True)
                    ),
                    "primary_key": _stable_values(
                        inspector.get_pk_constraint(table, schema=schema).get(
                            "constrained_columns"
                        )
                    ),
                    "schema": schema,
                    "table": table,
                    "unique_constraints": sorted(
                        _stable_values(constraint.get("column_names"))
                        for constraint in inspector.get_unique_constraints(
                            table, schema=schema
                        )
                    ),
                }
            )

    payload = json.dumps(tables, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _database_empty(inspector) -> bool:
    for schema in inspector.get_schema_names():
        if schema in SYSTEM_SCHEMAS or schema == "public":
            continue
        return False
    return not inspector.get_table_names(schema="public")


def probe_migration_state(database_url: str) -> MigrationState:
    """Read current and legacy state without issuing any DDL or DML."""
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            current_revision = _single_revision(
                connection, "public", CURRENT_VERSION_TABLE
            )
            legacy_revision = _single_revision(connection, "core", LEGACY_VERSION_TABLE)
            if legacy_revision is None:
                legacy_revision = _single_revision(
                    connection, "public", LEGACY_VERSION_TABLE
                )
            return MigrationState(
                database_empty=_database_empty(inspector),
                current_revision=current_revision,
                legacy_revision=legacy_revision,
                schema_fingerprint=schema_fingerprint(connection, inspector),
            )
    finally:
        engine.dispose()


def get_supported_current_revisions() -> set[str]:
    config = Config(str(ROOT / "alembic-current.ini"))
    script = ScriptDirectory.from_config(config)
    return {
        revision.revision
        for revision in script.walk_revisions(base="base", head="heads")
        if revision.revision
    }


def get_current_schema_baseline_revision() -> str:
    config = Config(str(ROOT / "alembic-current.ini"))
    baseline_revision = ScriptDirectory.from_config(config).get_base()
    if not baseline_revision:
        raise MigrationSafetyError("current-schema chain has no baseline revision")
    return baseline_revision


def _approved_legacy_source(legacy_revision: str | None) -> dict[str, str] | None:
    if not legacy_revision:
        return None
    policy = json.loads(SUPPORT_POLICY_PATH.read_text(encoding="utf-8"))
    for source in policy.get("approved_legacy_sources", []):
        if source.get("legacy_revision") == legacy_revision:
            return source
    return None


def choose_migration_action(
    state: MigrationState,
    *,
    expected_source_revision: str | None,
    expected_source_fingerprint: str | None = None,
    supported_current_revisions: set[str] | None = None,
) -> str:
    """Return the only permitted write action after fail-closed preflight."""
    if state.current_revision is not None:
        reachable_revisions = (
            supported_current_revisions or get_supported_current_revisions()
        )
        if state.current_revision not in reachable_revisions:
            raise MigrationSafetyError(
                f"{state.current_revision!r} is not a supported current revision"
            )
        return "upgrade"

    if state.database_empty:
        return "upgrade"

    approved_source = _approved_legacy_source(state.legacy_revision)
    if approved_source is None:
        raise MigrationSafetyError("database revision is not an approved legacy source")
    if state.schema_fingerprint != approved_source["schema_fingerprint"]:
        raise MigrationSafetyError(
            "database schema fingerprint is not approved for its legacy revision"
        )
    if (
        expected_source_revision
        and expected_source_revision != approved_source["legacy_revision"]
    ):
        raise MigrationSafetyError(
            "configured source revision does not match the approved legacy source"
        )
    if (
        expected_source_fingerprint
        and expected_source_fingerprint != approved_source["schema_fingerprint"]
    ):
        raise MigrationSafetyError(
            "configured source schema fingerprint does not match the approved legacy source"
        )
    if approved_source["baseline_revision"] != get_current_schema_baseline_revision():
        raise MigrationSafetyError(
            "approved legacy source does not match the current baseline"
        )
    return "stamp"


def _has_column(connection, table: str, column: str, schema: str = "a_class") -> bool:
    if not inspect(connection).has_table(table, schema=schema):
        return False
    return column in {
        item["name"] for item in inspect(connection).get_columns(table, schema=schema)
    }


def _operation_audit_category(connection, query: str) -> dict[str, Any]:
    count = connection.execute(
        text(f"SELECT count(*) FROM ({query}) AS operation_audit_rows")
    ).scalar_one()
    rows = connection.execute(text(f"{query} LIMIT 10")).scalars().all()
    return {"count": int(count), "ids": [int(row) for row in rows]}


def audit_legacy_operation_data(database_url: str) -> dict[str, Any]:
    """Return a read-only summary of historical operation records outside the current contract."""
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            current_contract_available = _has_column(
                connection, "sales_targets", "metric_catalog_version"
            )
            legacy_where = (
                "st.target_type = 'operation' AND st.metric_catalog_version IS NULL"
                if current_contract_available
                else "st.target_type = 'operation'"
            )
            legacy_count = connection.execute(
                text(
                    f"SELECT count(*) FROM a_class.sales_targets AS st WHERE {legacy_where}"
                )
            ).scalar_one()
            categories = {
                "missing_metric_code": _operation_audit_category(
                    connection,
                    f"""
                    SELECT st.id FROM a_class.sales_targets AS st
                    WHERE {legacy_where} AND NULLIF(btrim(st.metric_code), '') IS NULL
                    ORDER BY st.id
                    """,
                ),
                "missing_metric_direction": _operation_audit_category(
                    connection,
                    f"""
                    SELECT st.id FROM a_class.sales_targets AS st
                    WHERE {legacy_where}
                      AND (st.metric_direction IS NULL
                           OR st.metric_direction NOT IN ('higher_better', 'lower_better', 'manual_score'))
                    ORDER BY st.id
                    """,
                ),
                "non_calendar_month": _operation_audit_category(
                    connection,
                    f"""
                    SELECT st.id FROM a_class.sales_targets AS st
                    WHERE {legacy_where}
                      AND (st.period_start IS NULL OR st.period_end IS NULL
                           OR st.period_start <> date_trunc('month', st.period_start)::date
                           OR st.period_end <> (date_trunc('month', st.period_start) + interval '1 month - 1 day')::date)
                    ORDER BY st.id
                    """,
                ),
                "missing_shop_scope": _operation_audit_category(
                    connection,
                    f"""
                    SELECT st.id FROM a_class.sales_targets AS st
                    WHERE {legacy_where} AND st.scope_type IS DISTINCT FROM 'shop'
                    ORDER BY st.id
                    """,
                ),
                "incomplete_override": _operation_audit_category(
                    connection,
                    f"""
                    SELECT tb.id
                    FROM a_class.target_breakdown AS tb
                    JOIN a_class.sales_targets AS st ON st.id = tb.target_id
                    WHERE {legacy_where}
                      AND (tb.breakdown_type NOT IN ('shop', 'shop_time')
                           OR NULLIF(btrim(tb.platform_code), '') IS NULL
                           OR NULLIF(btrim(tb.shop_id), '') IS NULL
                           OR tb.period_start IS DISTINCT FROM st.period_start
                           OR tb.period_end IS DISTINCT FROM st.period_end)
                    ORDER BY tb.id
                    """,
                ),
                "duplicate_override": _operation_audit_category(
                    connection,
                    f"""
                    SELECT duplicate_rows.id
                    FROM (
                        SELECT tb.id,
                               count(*) OVER (
                                   PARTITION BY st.id, tb.platform_code, tb.shop_id
                               ) AS duplicate_count
                        FROM a_class.target_breakdown AS tb
                        JOIN a_class.sales_targets AS st ON st.id = tb.target_id
                        WHERE {legacy_where}
                          AND tb.breakdown_type IN ('shop', 'shop_time')
                    ) AS duplicate_rows
                    WHERE duplicate_rows.duplicate_count > 1
                    ORDER BY duplicate_rows.id
                    """,
                ),
            }
    finally:
        engine.dispose()
    return {"legacy_count": int(legacy_count), **categories}


def assert_legacy_adoption_data_is_safe(database_url: str) -> dict[str, Any]:
    """Fail closed only for invalid records explicitly marked as current contract data."""
    current_target = None
    version_mismatch = None
    current_override = None
    duplicate_override = None
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            if not inspector.has_table("sales_targets", schema="a_class"):
                return {}
            if _has_column(connection, "sales_targets", "metric_catalog_version"):
                current_target = connection.execute(
                    text(
                        """
                        SELECT id FROM a_class.sales_targets
                        WHERE target_type = 'operation' AND metric_catalog_version IS NOT NULL
                          AND (scope_type IS DISTINCT FROM 'shop'
                               OR period_start IS NULL OR period_end IS NULL
                               OR period_start <> date_trunc('month', period_start)::date
                               OR period_end <> (date_trunc('month', period_start) + interval '1 month - 1 day')::date
                               OR NULLIF(btrim(metric_code), '') IS NULL
                               OR metric_direction NOT IN ('higher_better', 'lower_better', 'manual_score'))
                        LIMIT 1
                        """
                    )
                ).first()
                if _has_column(
                    connection, "target_breakdown", "operation_contract_version"
                ):
                    version_mismatch = connection.execute(
                        text(
                            """
                            SELECT tb.id FROM a_class.target_breakdown AS tb
                            JOIN a_class.sales_targets AS st ON st.id = tb.target_id
                            WHERE st.target_type = 'operation'
                              AND st.metric_catalog_version IS NOT NULL
                              AND tb.operation_contract_version IS DISTINCT FROM st.metric_catalog_version
                            LIMIT 1
                            """
                        )
                    ).first()
                    current_override = connection.execute(
                        text(
                            """
                            SELECT tb.id FROM a_class.target_breakdown AS tb
                            JOIN a_class.sales_targets AS st ON st.id = tb.target_id
                            WHERE st.target_type = 'operation'
                              AND st.metric_catalog_version IS NOT NULL
                              AND tb.operation_contract_version = st.metric_catalog_version
                              AND (tb.breakdown_type IS DISTINCT FROM 'shop'
                                   OR NULLIF(btrim(tb.platform_code), '') IS NULL
                                   OR NULLIF(btrim(tb.shop_id), '') IS NULL
                                   OR tb.period_start IS DISTINCT FROM st.period_start
                                   OR tb.period_end IS DISTINCT FROM st.period_end)
                            LIMIT 1
                            """
                        )
                    ).first()
                    duplicate_override = connection.execute(
                        text(
                            """
                            SELECT tb.target_id FROM a_class.target_breakdown AS tb
                            JOIN a_class.sales_targets AS st ON st.id = tb.target_id
                            WHERE st.target_type = 'operation'
                              AND st.metric_catalog_version IS NOT NULL
                              AND tb.operation_contract_version = st.metric_catalog_version
                              AND tb.breakdown_type = 'shop'
                            GROUP BY tb.target_id, tb.operation_contract_version, tb.platform_code, tb.shop_id
                            HAVING count(*) > 1
                            LIMIT 1
                            """
                        )
                    ).first()
                elif inspect(connection).has_table(
                    "target_breakdown", schema="a_class"
                ):
                    current_override = connection.execute(
                        text(
                            """
                            SELECT tb.id FROM a_class.target_breakdown AS tb
                            JOIN a_class.sales_targets AS st ON st.id = tb.target_id
                            WHERE st.target_type = 'operation'
                              AND st.metric_catalog_version IS NOT NULL
                              AND (tb.breakdown_type IS DISTINCT FROM 'shop'
                                   OR NULLIF(btrim(tb.platform_code), '') IS NULL
                                   OR NULLIF(btrim(tb.shop_id), '') IS NULL
                                   OR tb.period_start IS DISTINCT FROM st.period_start
                                   OR tb.period_end IS DISTINCT FROM st.period_end)
                            LIMIT 1
                            """
                        )
                    ).first()
                    duplicate_override = connection.execute(
                        text(
                            """
                            SELECT tb.target_id FROM a_class.target_breakdown AS tb
                            JOIN a_class.sales_targets AS st ON st.id = tb.target_id
                            WHERE st.target_type = 'operation'
                              AND st.metric_catalog_version IS NOT NULL
                              AND tb.breakdown_type = 'shop'
                            GROUP BY tb.target_id, tb.platform_code, tb.shop_id
                            HAVING count(*) > 1
                            LIMIT 1
                            """
                        )
                    ).first()
    finally:
        engine.dispose()
    if (
        current_target is not None
        or version_mismatch is not None
        or current_override is not None
        or duplicate_override is not None
    ):
        raise MigrationSafetyError(
            "invalid current operation contract data requires manual resolution before adoption"
        )
    return audit_legacy_operation_data(database_url)


def preflight_current_schema_migrations(
    database_url: str,
    *,
    expected_source_revision: str | None,
    expected_source_fingerprint: str | None,
) -> str:
    """Resolve the allowed migration action without invoking any writer."""
    state = probe_migration_state(database_url)
    action = choose_migration_action(
        state,
        expected_source_revision=expected_source_revision,
        expected_source_fingerprint=expected_source_fingerprint,
        supported_current_revisions=get_supported_current_revisions(),
    )
    if action == "stamp" or not state.database_empty:
        legacy_audit = assert_legacy_adoption_data_is_safe(database_url)
        legacy_summary = (
            {
                key: value.get("count") if isinstance(value, dict) else value
                for key, value in legacy_audit.items()
            }
            if isinstance(legacy_audit, dict)
            else {}
        )
        print(
            f"[INFO] legacy operation data summary: {json.dumps(legacy_summary, sort_keys=True)}"
        )
    return action


def run_current_schema_migrations(
    database_url: str,
    *,
    expected_source_revision: str | None,
    expected_source_fingerprint: str | None,
) -> str:
    action = preflight_current_schema_migrations(
        database_url,
        expected_source_revision=expected_source_revision,
        expected_source_fingerprint=expected_source_fingerprint,
    )
    commands = (
        [("stamp", get_current_schema_baseline_revision()), ("upgrade", "head")]
        if action == "stamp"
        else [("upgrade", "head")]
    )
    for command, revision in commands:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "alembic-current.ini",
                command,
                revision,
            ],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": database_url},
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"current-schema alembic {command} {revision} failed ({result.returncode})"
            )
    return action


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument(
        "--source-revision", default=os.getenv("CURRENT_SCHEMA_SOURCE_REVISION")
    )
    parser.add_argument(
        "--source-fingerprint",
        default=os.getenv("CURRENT_SCHEMA_SOURCE_FINGERPRINT"),
    )
    parser.add_argument("--print-schema-fingerprint", action="store_true")
    parser.add_argument("--audit-legacy-operation-data", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()

    database_url = (args.database_url or "").strip()
    if not database_url:
        print("[FAIL] DATABASE_URL is required", file=sys.stderr)
        return 2
    if args.print_schema_fingerprint:
        state = probe_migration_state(database_url)
        print(state.schema_fingerprint)
        return 0
    if args.audit_legacy_operation_data:
        print(json.dumps(audit_legacy_operation_data(database_url), sort_keys=True))
        return 0

    try:
        migration_options = {
            "expected_source_revision": (args.source_revision or "").strip() or None,
            "expected_source_fingerprint": (args.source_fingerprint or "").strip()
            or None,
        }
        action = (
            preflight_current_schema_migrations(database_url, **migration_options)
            if args.preflight_only
            else run_current_schema_migrations(database_url, **migration_options)
        )
    except MigrationSafetyError as exc:
        print(
            f"[FAIL] Current-schema migration preflight rejected write: {exc}",
            file=sys.stderr,
        )
        return 2
    except RuntimeError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    status = "preflight passed" if args.preflight_only else "migration action completed"
    print(f"[OK] Current-schema {status}: {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
