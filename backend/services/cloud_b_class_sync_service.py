from __future__ import annotations

import inspect
import json
from collections.abc import Iterable
from typing import Any

from sqlalchemy import create_engine, inspect as sa_inspect, text

from backend.services.cloud_b_class_mirror_manager import build_canonical_columns
from backend.services.cloud_b_class_sync_utils import quote_ident, validate_b_class_table_name


def build_sync_payload(row: dict[str, Any]) -> dict[str, Any]:
    """Build canonical sync payload from one local B-class row."""
    payload = {column: row.get(column) for column in build_canonical_columns()}
    if payload.get("data_domain") != "services" and payload.get("shop_id") is None:
        payload["shop_id"] = ""
    return payload


class SQLAlchemyBClassSourceReader:
    """Read canonical rows from local B-class tables."""

    def __init__(self, engine):
        self.engine = engine

    def _build_select_sql(
        self,
        table_name: str,
        where_sql: str,
        available_columns: set[str] | None = None,
    ) -> str:
        validate_b_class_table_name(table_name)
        select_columns = []
        for column in build_canonical_columns():
            if available_columns is None or column in available_columns:
                select_columns.append(column)
            else:
                select_columns.append(f"NULL AS {column}")
        where_clause = f"WHERE {where_sql}" if where_sql else ""
        return (
            f'SELECT id, {", ".join(select_columns)} '
            f"FROM b_class.{quote_ident(table_name)} "
            f"{where_clause} "
            "ORDER BY ingest_timestamp ASC, id ASC "
            "LIMIT :batch_size"
        )

    def __call__(self, table_name: str, checkpoint, batch_size: int = 1000):
        where_sql, params = CloudBClassSyncService._build_checkpoint_where_clause(checkpoint)
        inspector = sa_inspect(self.engine)
        available_columns = {
            column["name"] for column in inspector.get_columns(table_name, schema="b_class")
        }
        sql = self._build_select_sql(table_name, where_sql, available_columns=available_columns)
        bind_params = dict(params)
        bind_params["batch_size"] = batch_size
        with self.engine.begin() as conn:
            result = conn.execute(text(sql), bind_params)
            return [dict(row) for row in result.mappings().all()]


class SQLAlchemyCloudWriter:
    """Write canonical rows to cloud mirror tables via PostgreSQL upsert."""

    def __init__(self, engine, dry_run: bool = False):
        self.engine = engine
        self.dry_run = dry_run

    @staticmethod
    def _build_upsert_sql(table_name: str, data_domain: str) -> str:
        columns = build_canonical_columns()
        column_list = ", ".join(columns)
        bind_list = ", ".join(f":{column}" for column in columns)
        update_fields = ", ".join(
            f"{column} = EXCLUDED.{column}"
            for column in columns
            if column not in {"platform_code", "shop_id", "data_domain", "granularity", "sub_domain", "data_hash"}
        )
        if data_domain == "services":
            conflict_clause = "(data_domain, sub_domain, granularity, data_hash)"
        else:
            conflict_clause = "(platform_code, shop_id, data_domain, granularity, data_hash)"
        return (
            f'INSERT INTO cloud_b_class."{table_name}" ({column_list}) '
            f"VALUES ({bind_list}) "
            f"ON CONFLICT {conflict_clause} DO UPDATE SET {update_fields}"
        )

    def __call__(self, table_name: str, rows: list[dict[str, Any]], data_domain: str):
        if self.dry_run:
            return {"success": True, "written_rows": len(rows), "dry_run": True}

        sql = self._build_upsert_sql(table_name, data_domain)
        prepared_rows = self._prepare_rows_for_insert(rows)
        with self.engine.begin() as conn:
            conn.execute(text(sql), prepared_rows)
        return {"success": True, "written_rows": len(rows)}

    @staticmethod
    def _prepare_rows_for_insert(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        prepared_rows: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            if isinstance(record.get("raw_data"), dict):
                record["raw_data"] = json.dumps(record["raw_data"], ensure_ascii=False)
            if isinstance(record.get("header_columns"), list):
                record["header_columns"] = json.dumps(record["header_columns"], ensure_ascii=False)
            prepared_rows.append(record)
        return prepared_rows


class CloudBClassSyncService:
    """Checkpointed local-to-cloud B-class sync orchestration."""

    def __init__(
        self,
        checkpoint_service,
        mirror_manager,
        source_batch_reader,
        remote_writer,
        table_inspector=None,
        run_recorder=None,
        sync_table_handler=None,
        local_engine=None,
        cloud_engine=None,
        owns_engines: bool = False,
    ) -> None:
        self.checkpoint_service = checkpoint_service
        self.mirror_manager = mirror_manager
        self.source_batch_reader = source_batch_reader
        self.remote_writer = remote_writer
        self.table_inspector = table_inspector
        self.run_recorder = run_recorder
        self.sync_table_handler = sync_table_handler
        self.local_engine = local_engine
        self.cloud_engine = cloud_engine
        self.owns_engines = owns_engines

    @staticmethod
    def _should_advance_checkpoint(write_succeeded: bool, dry_run: bool = False) -> bool:
        return bool(write_succeeded) and not dry_run

    @staticmethod
    def _filter_b_class_tables(table_names: Iterable[str]) -> list[str]:
        filtered: list[str] = []
        for table_name in table_names:
            if "." in table_name:
                continue
            if table_name.startswith("fact_"):
                filtered.append(table_name)
        return filtered

    @staticmethod
    def _build_checkpoint_where_clause(checkpoint) -> tuple[str, dict[str, Any]]:
        if not checkpoint or not checkpoint.last_ingest_timestamp:
            return "", {}

        where_sql = (
            "(ingest_timestamp > :last_ingest_timestamp "
            "OR (ingest_timestamp = :last_ingest_timestamp AND id > :last_source_id))"
        )
        return where_sql, {
            "last_ingest_timestamp": checkpoint.last_ingest_timestamp,
            "last_source_id": checkpoint.last_source_id or 0,
        }

    @staticmethod
    def _infer_data_domain(table_name: str) -> str:
        validate_b_class_table_name(table_name)
        parts = table_name.split("_")
        if len(parts) < 4 or parts[0] != "fact":
            raise ValueError(f"Unsupported B-class table name: {table_name}")
        return parts[2]

    async def _maybe_await(self, value):
        if inspect.isawaitable(value):
            return await value
        return value

    async def sync_all_tables(self, batch_size: int = 1000) -> dict[str, Any]:
        if self.table_inspector is None:
            return {
                "status": "completed",
                "total_tables": 0,
                "succeeded_tables": 0,
                "failed_tables": 0,
                "results": [],
            }

        inspected = await self._maybe_await(self.table_inspector())
        tables = self._filter_b_class_tables(inspected)
        run_id = None
        if self.run_recorder is not None:
            run_id = self.run_recorder.create_run(total_tables=len(tables))

        results = []
        succeeded = 0
        failed = 0
        for table_name in tables:
            if self.sync_table_handler is not None:
                result = await self._maybe_await(
                    self.sync_table_handler(table_name, batch_size=batch_size)
                )
            else:
                result = await self.sync_table(table_name, batch_size=batch_size)
            results.append(result)
            if result["status"] == "completed":
                succeeded += 1
            else:
                failed += 1

        summary = {
            "status": "completed" if failed == 0 else "partial_success",
            "total_tables": len(tables),
            "succeeded_tables": succeeded,
            "failed_tables": failed,
            "results": results,
        }
        if run_id is not None:
            self.run_recorder.finish_run(
                run_id=run_id,
                status=summary["status"],
                succeeded_tables=succeeded,
                failed_tables=failed,
                error_summary=None if failed == 0 else f"{failed} tables failed",
            )
            summary["run_id"] = run_id
        return summary

    def list_b_class_tables(self) -> list[str]:
        if self.table_inspector is None:
            return []
        inspected = self.table_inspector()
        if inspect.isawaitable(inspected):
            raise RuntimeError("Async table inspector is not supported in synchronous list_b_class_tables")
        return self._filter_b_class_tables(inspected)

    async def sync_table(self, table_name: str, batch_size: int = 1000) -> dict[str, Any]:
        try:
            validate_b_class_table_name(table_name)
            checkpoint = self.checkpoint_service.create_or_get_checkpoint(table_name)
            data_domain = self._infer_data_domain(table_name)
            self.mirror_manager.ensure_cloud_mirror_table(table_name, data_domain)

            rows = await self._maybe_await(
                self.source_batch_reader(
                    table_name=table_name,
                    checkpoint=checkpoint,
                    batch_size=batch_size,
                )
            )
            rows = list(rows)
            payload_rows = [build_sync_payload(row) for row in rows]

            if not rows:
                return {
                    "status": "completed",
                    "table_name": table_name,
                    "written_rows": 0,
                }

            write_result = await self._maybe_await(
                self.remote_writer(
                    table_name=table_name,
                    rows=payload_rows,
                    data_domain=data_domain,
                )
            )

            write_succeeded = bool(write_result.get("success"))
            if self._should_advance_checkpoint(write_succeeded, dry_run=bool(write_result.get("dry_run"))):
                last_row = rows[-1]
                self.checkpoint_service.advance_checkpoint(
                    table_name=table_name,
                    ingest_timestamp=last_row["ingest_timestamp"],
                    source_id=last_row["id"],
                    status="completed",
                )

            return {
                "status": "completed" if write_succeeded else "failed",
                "table_name": table_name,
                "written_rows": write_result.get("written_rows", len(rows) if write_succeeded else 0),
            }
        except Exception as exc:
            self.checkpoint_service.mark_failure(table_name, str(exc))
            return {
                "status": "failed",
                "table_name": table_name,
                "error": str(exc),
            }

    def close(self) -> None:
        db = getattr(self.checkpoint_service, "db", None)
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
        if self.owns_engines:
            if self.local_engine is not None:
                try:
                    self.local_engine.dispose()
                except Exception:
                    pass
            if self.cloud_engine is not None and self.cloud_engine is not self.local_engine:
                try:
                    self.cloud_engine.dispose()
                except Exception:
                    pass
