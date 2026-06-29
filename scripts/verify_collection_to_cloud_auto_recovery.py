#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _engine_from_env(name: str):
    url = os.getenv(name)
    if not url:
        raise RuntimeError(f"{name} is not configured")
    return create_engine(url)


def _fetch_all(engine, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(text(sql), params or {}).mappings().all()]


def _fetch_one(engine, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    rows = _fetch_all(engine, sql, params)
    return rows[0] if rows else None


def _alembic_revisions(engine) -> list[str]:
    rows = _fetch_all(
        engine,
        """
        SELECT table_schema
        FROM information_schema.tables
        WHERE table_name = 'alembic_version'
        ORDER BY table_schema
        """,
    )
    revisions: list[str] = []
    for row in rows:
        schema = row["table_schema"]
        revisions.extend(
            item["version_num"]
            for item in _fetch_all(engine, f'SELECT version_num FROM "{schema}".alembic_version')
        )
    return sorted(revisions)


def _parse_file_ids(raw: str) -> list[int]:
    ids = [int(token.strip()) for token in raw.split(",") if token.strip()]
    if not ids:
        raise ValueError("--file-ids must include at least one id")
    return ids


def verify(file_ids: list[int], timeout: int) -> dict[str, Any]:
    local_engine = _engine_from_env("DATABASE_URL")
    cloud_engine = _engine_from_env("CLOUD_DATABASE_URL")
    deadline = time.time() + timeout

    try:
        while True:
            local_files = _fetch_all(
                local_engine,
                """
                SELECT id, file_name, status, data_domain, granularity, date_from, date_to, last_processed_at
                FROM public.catalog_files
                WHERE id = ANY(:file_ids)
                ORDER BY id
                """,
                {"file_ids": file_ids},
            )
            sync_tasks = _fetch_all(
                local_engine,
                """
                SELECT source_file_id, source_table_name, status, attempt_count, finished_at
                FROM public.cloud_b_class_sync_tasks
                WHERE source_file_id = ANY(:file_ids)
                ORDER BY id DESC
                """,
                {"file_ids": file_ids},
            )
            latest_by_file: dict[int, dict[str, Any]] = {}
            for task in sync_tasks:
                latest_by_file.setdefault(int(task["source_file_id"]), task)

            receive_logs = _fetch_all(
                cloud_engine,
                """
                SELECT source_file_id, source_table_name, written_rows, status,
                       business_date_min, business_date_max, created_at
                FROM ops.cloud_sync_receive_log
                WHERE source_file_id = ANY(:file_ids)
                ORDER BY created_at DESC
                """,
                {"file_ids": file_ids},
            )
            received_files = {
                int(row["source_file_id"])
                for row in receive_logs
                if row.get("status") == "completed" and row.get("source_file_id") is not None
            }

            local_done = all(row.get("status") == "ingested" for row in local_files)
            sync_done = all(
                latest_by_file.get(file_id, {}).get("status") == "completed"
                for file_id in file_ids
            )
            receive_done = set(file_ids).issubset(received_files)
            if local_done and sync_done and receive_done:
                break
            if time.time() >= deadline:
                break
            time.sleep(5)

        freshness = []
        for table_name in sorted({task["source_table_name"] for task in sync_tasks if task.get("source_table_name")}):
            freshness.append(
                {
                    "source_table_name": table_name,
                    **(
                        _fetch_one(
                            cloud_engine,
                            f"""
                            SELECT count(*) AS rows,
                                   max(period_end_date) AS max_period_end_date,
                                   max(ingest_timestamp) AS latest_ingest_timestamp
                            FROM b_class."{table_name}"
                            """
                        )
                        or {}
                    ),
                }
            )

        recovery_actions = _fetch_all(
            local_engine,
            """
            SELECT id, job_id, source_file_id, source_table_name, metadata_json
            FROM public.cloud_b_class_sync_tasks
            WHERE source_file_id = ANY(:file_ids)
              AND metadata_json ? 'auto_recovery'
            ORDER BY id DESC
            """,
            {"file_ids": file_ids},
        )

        return {
            "local_alembic_revisions": _alembic_revisions(local_engine),
            "cloud_alembic_revisions": _alembic_revisions(cloud_engine),
            "local_ingest_status": local_files,
            "cloud_sync_status": list(latest_by_file.values()),
            "receive_log_status": receive_logs,
            "cloud_fact_freshness": freshness,
            "auto_recovery_actions": recovery_actions,
            "success": all(row.get("status") == "ingested" for row in local_files)
            and all(latest_by_file.get(file_id, {}).get("status") == "completed" for file_id in file_ids)
            and set(file_ids).issubset(
                {
                    int(row["source_file_id"])
                    for row in receive_logs
                    if row.get("status") == "completed" and row.get("source_file_id") is not None
                }
            ),
        }
    finally:
        local_engine.dispose()
        cloud_engine.dispose()


def main(argv: list[str] | None = None) -> int:
    _load_env_file(PROJECT_ROOT / ".env")
    _load_env_file(PROJECT_ROOT / ".env.local")
    _load_env_file(PROJECT_ROOT / ".env.collection.local")

    parser = argparse.ArgumentParser(description="Verify collection-to-cloud auto recovery chain")
    parser.add_argument("--file-ids", required=True, help="Comma-separated catalog file ids")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args(argv)

    result = verify(_parse_file_ids(args.file_ids), args.timeout)
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))
    return 0 if result.get("success") else 2


if __name__ == "__main__":
    raise SystemExit(main())
