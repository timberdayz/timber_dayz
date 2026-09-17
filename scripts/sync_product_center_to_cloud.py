#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-time bulk overwrite of product-center tables from local DB to cloud DB.

Subcommands:
    plan       Inspect local/cloud row counts and existence. Read-only.
    backup     COPY cloud tables to CSV under backups/cloud-product-center-<ts>/.
    overwrite  TRUNCATE + INSERT from local. Requires --i-understand-this-overwrites-cloud
               and a fresh backup directory on disk.
    verify     Compare local vs cloud row counts.

Usage:
    python scripts/sync_product_center_to_cloud.py plan
    python scripts/sync_product_center_to_cloud.py backup
    python scripts/sync_product_center_to_cloud.py overwrite --i-understand-this-overwrites-cloud
    python scripts/sync_product_center_to_cloud.py verify
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, inspect as sa_inspect, text
from sqlalchemy.engine import make_url

from backend.models.database import DATABASE_URL


# Tier-1 product-center tables, in FK-safe insert order (parents first).
PRODUCT_CENTER_TABLES = [
    ("core", "dim_platforms"),
    ("core", "dim_warehouses"),
    ("core", "dim_product_categories"),
    ("finance", "product_cost_assumption_profiles"),
    ("finance", "warehouse_storage_rules"),
    ("finance", "logistics_provider_rules"),
    ("core", "dim_spu"),
    ("core", "dim_erp_sku"),
    ("core", "bridge_erp_sku_keys"),
    ("core", "bridge_spu_sku"),
    ("finance", "sku_operating_profiles"),
    ("finance", "logistics_bills"),
    ("finance", "logistics_bill_lines"),
    ("finance", "logistics_bill_line_allocations"),
    ("finance", "logistics_bill_purchase_orders"),
    ("finance", "sku_profit_estimates"),
]

# Truncate order = reversed (leaves first, CASCADE handles the rest).
TRUNCATE_ORDER = list(reversed(PRODUCT_CENTER_TABLES))

BATCH_SIZE = 1000
BACKUP_ROOT = Path("backups")


def _tcp_probe(host: str, port: int, timeout: float = 3.0) -> tuple[bool, str | None]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, None
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _load_cloud_url_from_dotenv() -> str | None:
    """Read only the CLOUD_DATABASE_URL line from the repo's .env, if present.

    We deliberately do not load the rest of the .env into the process environment —
    .env carries the full local dev runtime, and this script only needs the cloud URL.
    Returns the value if found, else None.
    """
    env_path = project_root / ".env"
    if not env_path.exists():
        return None
    try:
        text_content = env_path.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text_content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].lstrip()
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key == "CLOUD_DATABASE_URL" and value:
            return value
    return None


def _resolve_engines():
    cloud_url = os.environ.get("CLOUD_DATABASE_URL")
    if not cloud_url:
        cloud_url = _load_cloud_url_from_dotenv()
        if cloud_url:
            os.environ["CLOUD_DATABASE_URL"] = cloud_url
    if not cloud_url:
        raise RuntimeError(
            "CLOUD_DATABASE_URL is required. Export it (usually via SSH tunnel) or set it in .env before running."
        )

    local_engine = create_engine(DATABASE_URL)
    cloud_engine = create_engine(cloud_url)

    parsed = make_url(cloud_url)
    host = parsed.host or "127.0.0.1"
    port = int(parsed.port or 5432)
    ok, err = _tcp_probe(host, port)
    if not ok:
        raise RuntimeError(
            f"Cloud DB not reachable at {host}:{port}: {err}. "
            "Is the SSH tunnel up? See docs/deployment/WINDOWS_COLLECTION_CLOUD_SYNC.md."
        )

    with cloud_engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    return local_engine, cloud_engine


def _existing_tables(engine, schema: str) -> set[str]:
    return set(sa_inspect(engine).get_table_names(schema=schema))


def _count_rows(engine, schema: str, table: str) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text(f'SELECT COUNT(*) FROM "{schema}"."{table}"')).scalar() or 0)


def _current_backup_dir() -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return BACKUP_ROOT / f"cloud-product-center-{ts}"


def cmd_plan(_args) -> int:
    local_engine, cloud_engine = _resolve_engines()

    print(f"{'table':<58} {'local_rows':>12} {'cloud_exists':>14} {'cloud_rows':>12}")
    print("-" * 98)
    missing: list[str] = []
    for schema, table in PRODUCT_CENTER_TABLES:
        local_n = _count_rows(local_engine, schema, table)
        exists = table in _existing_tables(cloud_engine, schema)
        cloud_n = _count_rows(cloud_engine, schema, table) if exists else 0
        if not exists:
            missing.append(f"{schema}.{table}")
        print(
            f"{schema + '.' + table:<58} {local_n:>12} {str(exists):>14} {cloud_n:>12}"
        )

    if missing:
        print(f"\n[ABORT] {len(missing)} table(s) missing on cloud: {', '.join(missing)}")
        return 1

    print("\n[OK] All 16 tier-1 product-center tables present on both sides.")
    print("Next: run `backup` then `overwrite --i-understand-this-overwrites-cloud`.")
    return 0


def cmd_backup(_args) -> int:
    _, cloud_engine = _resolve_engines()
    backup_dir = _current_backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    print(f"Backup directory: {backup_dir}")

    for schema, table in PRODUCT_CENTER_TABLES:
        target = backup_dir / f"{schema}.{table}.csv"
        if table not in _existing_tables(cloud_engine, schema):
            print(f"[SKIP] {schema}.{table}: does not exist on cloud (creating empty marker)")
            target.touch()
            continue
        raw_conn = cloud_engine.raw_connection()
        try:
            cur = raw_conn.cursor()
            try:
                with open(target, "wb") as f:
                    cur.copy_expert(
                        f'COPY (SELECT * FROM "{schema}"."{table}") TO STDOUT WITH CSV HEADER',
                        f,
                    )
            finally:
                cur.close()
        finally:
            raw_conn.close()
        rows = _count_rows(cloud_engine, schema, table)
        print(f"[OK]   {schema}.{table}: {rows} rows -> {target.name}")

    print(f"\n[DONE] Backup complete. Marker file: {backup_dir.name}")
    return 0


def cmd_overwrite(args) -> int:
    if not args.i_understand_this_overwrites_cloud:
        print(
            "[REFUSED] overwrite mode requires --i-understand-this-overwrites-cloud flag.",
            file=sys.stderr,
        )
        return 2

    local_engine, cloud_engine = _resolve_engines()

    # Refuse unless a fresh backup directory from this session exists with CSVs in it.
    backup_dirs = sorted(
        (p for p in BACKUP_ROOT.glob("cloud-product-center-*") if p.is_dir()),
        key=lambda p: p.name,
    )
    if not backup_dirs:
        print("[REFUSED] no backup directory found under backups/. Run `backup` first.", file=sys.stderr)
        return 2
    latest = backup_dirs[-1]
    non_empty = [p for p in latest.glob("*.csv") if p.stat().st_size > 0]
    if not non_empty:
        print(
            f"[REFUSED] latest backup directory {latest} has no non-empty CSVs.",
            file=sys.stderr,
        )
        return 2
    print(f"[GATE] Fresh backup confirmed: {latest} ({len(non_empty)} non-empty CSV files)")

    # Verify schema first.
    for schema, table in PRODUCT_CENTER_TABLES:
        if table not in _existing_tables(cloud_engine, schema):
            print(f"[ABORT] {schema}.{table} missing on cloud. Refusing to truncate.", file=sys.stderr)
            return 1

    # Truncate in reverse order (leaves first). CASCADE handles the rest.
    print("\n[STEP 1] Truncate cloud tables (reverse order)")
    with cloud_engine.begin() as conn:
        for schema, table in TRUNCATE_ORDER:
            conn.execute(text(f'TRUNCATE "{schema}"."{table}" RESTART IDENTITY CASCADE'))
            print(f"  truncated {schema}.{table}")

    # Copy in insert order.
    print("\n[STEP 2] Copy local rows -> cloud")
    summary: list[tuple[str, str, int]] = []
    for schema, table in PRODUCT_CENTER_TABLES:
        inspector = sa_inspect(local_engine)
        cols = [c["name"] for c in inspector.get_columns(table, schema=schema)]
        col_list = ", ".join(f'"{c}"' for c in cols)
        placeholders = ", ".join(f":p{i}" for i in range(len(cols)))
        insert_sql = text(
            f'INSERT INTO "{schema}"."{table}" ({col_list}) VALUES ({placeholders})'
        )
        with local_engine.connect() as local_conn:
            result = local_conn.execute(text(f'SELECT * FROM "{schema}"."{table}"'))
            rows = [tuple(r) for r in result.fetchall()]
        if not rows:
            print(f"  {schema}.{table}: 0 rows (skipped)")
            summary.append((schema, table, 0))
            continue
        written = 0
        with cloud_engine.begin() as cloud_conn:
            for i in range(0, len(rows), BATCH_SIZE):
                batch = rows[i : i + BATCH_SIZE]
                params = [dict(zip([f"p{j}" for j in range(len(cols))], row)) for row in batch]
                cloud_conn.execute(insert_sql, params)
                written += len(batch)
        print(f"  {schema}.{table}: wrote {written} rows")
        summary.append((schema, table, written))

    print("\n[STEP 3] Summary")
    for schema, table, n in summary:
        print(f"  {schema}.{table}: {n} rows")
    print("\n[DONE] Overwrite complete. Run `verify` to confirm row counts match.")
    return 0


def cmd_verify(_args) -> int:
    local_engine, cloud_engine = _resolve_engines()
    print(f"{'table':<58} {'local_rows':>12} {'cloud_rows':>12} {'match':>8}")
    print("-" * 92)
    mismatches = 0
    for schema, table in PRODUCT_CENTER_TABLES:
        local_n = _count_rows(local_engine, schema, table)
        cloud_n = _count_rows(cloud_engine, schema, table)
        match = local_n == cloud_n
        if not match:
            mismatches += 1
        print(f"{schema + '.' + table:<58} {local_n:>12} {cloud_n:>12} {str(match):>8}")
    if mismatches:
        print(f"\n[FAIL] {mismatches} table(s) have row-count mismatches.")
        return 1
    print("\n[OK] All 16 tier-1 product-center tables match.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan", help="Inspect row counts and existence (read-only).")
    sub.add_parser("backup", help="Dump cloud tables to local CSV.")
    over = sub.add_parser(
        "overwrite",
        help="Truncate cloud tables and bulk-copy from local.",
    )
    over.add_argument(
        "--i-understand-this-overwrites-cloud",
        action="store_true",
        dest="i_understand_this_overwrites_cloud",
        help="Required confirmation flag for overwrite mode.",
    )
    sub.add_parser("verify", help="Compare local vs cloud row counts.")
    args = parser.parse_args(argv)

    try:
        if args.cmd == "plan":
            return cmd_plan(args)
        if args.cmd == "backup":
            return cmd_backup(args)
        if args.cmd == "overwrite":
            return cmd_overwrite(args)
        if args.cmd == "verify":
            return cmd_verify(args)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
