"""Convert all TIMESTAMP columns to TIMESTAMPTZ (timezone-aware).

Phase 3 of refactor-rules-and-code-patterns:
- Scans all project schemas for TIMESTAMP WITHOUT TIME ZONE columns
- Converts them to TIMESTAMP WITH TIME ZONE using AT TIME ZONE 'UTC'
- Existing naive timestamps are interpreted as UTC values
- Idempotent: only converts columns that are not already TIMESTAMPTZ
- Handles materialized views: drops and recreates them around ALTER TYPE

Revision ID: 20260316_tz
Revises: 20260220_pasi
Create Date: 2026-03-16

"""

from alembic import op
from sqlalchemy import text


revision = "20260316_tz"
down_revision = "20260220_pasi"
branch_labels = None
depends_on = None

PROJECT_SCHEMAS = ("public", "core", "a_class", "b_class", "c_class", "finance")


def safe_print(msg: str) -> None:
    """Windows-safe print (avoid GBK encoding errors)."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"))


def _get_timestamp_columns(conn, schemas):
    """Query information_schema for all TIMESTAMP WITHOUT TIME ZONE columns."""
    rows = conn.execute(
        text("""
            SELECT table_schema, table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = ANY(:schemas)
              AND data_type = 'timestamp without time zone'
            ORDER BY table_schema, table_name, ordinal_position
        """),
        {"schemas": list(schemas)},
    ).fetchall()
    return rows


def _get_matviews(conn, schemas):
    """Get all materialized views and their definitions in project schemas."""
    rows = conn.execute(
        text("""
            SELECT schemaname, matviewname, definition
            FROM pg_matviews
            WHERE schemaname = ANY(:schemas)
            ORDER BY schemaname, matviewname
        """),
        {"schemas": list(schemas)},
    ).fetchall()
    return rows


def _get_matview_indexes(conn, schema, matview):
    """Get index definitions for a materialized view."""
    rows = conn.execute(
        text("""
            SELECT indexdef
            FROM pg_indexes
            WHERE schemaname = :schema
              AND tablename = :matview
        """),
        {"schema": schema, "matview": matview},
    ).fetchall()
    return [r[0] for r in rows]


def upgrade() -> None:
    conn = op.get_bind()

    columns = _get_timestamp_columns(conn, PROJECT_SCHEMAS)
    safe_print(
        f"[INFO] Found {len(columns)} TIMESTAMP columns to convert to TIMESTAMPTZ"
    )

    if not columns:
        safe_print("[INFO] No columns to convert, skipping")
        return

    # Phase A: Drop materialized views (they block ALTER TYPE on source tables)
    matviews = _get_matviews(conn, PROJECT_SCHEMAS)
    dropped_views = []

    for schema, name, definition in matviews:
        fqn = f'"{schema}"."{name}"'
        indexes = _get_matview_indexes(conn, schema, name)
        safe_print(f"[INFO] Dropping materialized view {fqn} ({len(indexes)} indexes)")
        conn.execute(text(f"DROP MATERIALIZED VIEW IF EXISTS {fqn} CASCADE"))
        dropped_views.append((schema, name, definition, indexes))

    safe_print(f"[INFO] Dropped {len(dropped_views)} materialized views")

    # Phase B: Convert all TIMESTAMP columns using savepoints
    converted = 0
    skipped = 0
    for schema, table, column in columns:
        fqn = f'"{schema}"."{table}"'
        stmt = (
            f'ALTER TABLE {fqn} '
            f'ALTER COLUMN "{column}" '
            f"TYPE TIMESTAMPTZ USING \"{column}\" AT TIME ZONE 'UTC'"
        )
        conn.execute(text("SAVEPOINT alter_col"))
        try:
            conn.execute(text(stmt))
            conn.execute(text("RELEASE SAVEPOINT alter_col"))
            converted += 1
        except Exception as exc:
            conn.execute(text("ROLLBACK TO SAVEPOINT alter_col"))
            safe_print(f"[WARN] Skipped {fqn}.{column}: {exc}")
            skipped += 1

    safe_print(
        f"[INFO] Converted {converted}/{len(columns)} columns "
        f"({skipped} skipped)"
    )

    # Phase C: Recreate materialized views
    recreated = 0
    for schema, name, definition, indexes in dropped_views:
        fqn = f'"{schema}"."{name}"'
        try:
            conn.execute(
                text(f"CREATE MATERIALIZED VIEW {fqn} AS {definition}")
            )
            for idx_def in indexes:
                conn.execute(text(idx_def))
            recreated += 1
            safe_print(f"[INFO] Recreated materialized view {fqn}")
        except Exception as exc:
            safe_print(f"[WARN] Failed to recreate {fqn}: {exc}")

    safe_print(
        f"[INFO] Recreated {recreated}/{len(dropped_views)} materialized views"
    )


def downgrade() -> None:
    """Revert TIMESTAMPTZ back to TIMESTAMP (loses timezone info)."""
    conn = op.get_bind()

    # Phase A: Drop materialized views
    matviews = _get_matviews(conn, PROJECT_SCHEMAS)
    dropped_views = []

    for schema, name, definition in matviews:
        fqn = f'"{schema}"."{name}"'
        indexes = _get_matview_indexes(conn, schema, name)
        conn.execute(text(f"DROP MATERIALIZED VIEW IF EXISTS {fqn} CASCADE"))
        dropped_views.append((schema, name, definition, indexes))

    # Phase B: Revert columns
    rows = conn.execute(
        text("""
            SELECT table_schema, table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = ANY(:schemas)
              AND data_type = 'timestamp with time zone'
            ORDER BY table_schema, table_name, ordinal_position
        """),
        {"schemas": list(PROJECT_SCHEMAS)},
    ).fetchall()

    safe_print(
        f"[INFO] Reverting {len(rows)} TIMESTAMPTZ columns back to TIMESTAMP"
    )

    reverted = 0
    for schema, table, column in rows:
        fqn = f'"{schema}"."{table}"'
        stmt = (
            f'ALTER TABLE {fqn} '
            f'ALTER COLUMN "{column}" '
            f"TYPE TIMESTAMP USING \"{column}\" AT TIME ZONE 'UTC'"
        )
        conn.execute(text("SAVEPOINT alter_col"))
        try:
            conn.execute(text(stmt))
            conn.execute(text("RELEASE SAVEPOINT alter_col"))
            reverted += 1
        except Exception as exc:
            conn.execute(text("ROLLBACK TO SAVEPOINT alter_col"))
            safe_print(f"[WARN] Failed to revert {fqn}.{column}: {exc}")

    safe_print(f"[INFO] Successfully reverted {reverted}/{len(rows)} columns")

    # Phase C: Recreate materialized views
    for schema, name, definition, indexes in dropped_views:
        fqn = f'"{schema}"."{name}"'
        try:
            conn.execute(
                text(f"CREATE MATERIALIZED VIEW {fqn} AS {definition}")
            )
            for idx_def in indexes:
                conn.execute(text(idx_def))
        except Exception as exc:
            safe_print(f"[WARN] Failed to recreate {fqn}: {exc}")
