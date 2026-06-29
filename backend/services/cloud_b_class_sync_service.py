from __future__ import annotations

import inspect
import json
import uuid
from collections.abc import Iterable
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import create_engine, insert, inspect as sa_inspect, select, text, update

from backend.services.cloud_b_class_mirror_manager import build_canonical_columns
from backend.services.cloud_b_class_sync_utils import quote_ident, validate_b_class_table_name
from backend.services.data_pipeline.refresh_queue_service import RefreshQueueService
from modules.core.db import CloudSyncReceiveLog, RefreshQueueTask


def build_sync_payload(row: dict[str, Any]) -> dict[str, Any]:
    """Build canonical sync payload from one local B-class row."""
    payload = {column: row.get(column) for column in build_canonical_columns()}
    if payload.get("data_domain") != "services" and payload.get("shop_id") is None:
        payload["shop_id"] = ""
    raw_data = payload.get("raw_data")
    if isinstance(raw_data, dict):
        raw_payload = dict(raw_data)
    else:
        raw_payload = {}
        if raw_data not in (None, ""):
            raw_payload["_cloud_sync_original_raw_data"] = raw_data
    if row.get("file_id") is not None:
        raw_payload["_cloud_sync_source_file_id"] = row.get("file_id")
    if raw_payload:
        payload["raw_data"] = raw_payload
    # Cloud-side raw facts do not own the local file/template dimension rows.
    payload["file_id"] = None
    payload["template_id"] = None
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

    TARGET_SCHEMA = "b_class"

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
            f'INSERT INTO {SQLAlchemyCloudWriter.TARGET_SCHEMA}."{table_name}" ({column_list}) '
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

    def write_rows_with_receive_log(
        self,
        *,
        table_name: str,
        rows: list[dict[str, Any]],
        data_domain: str,
        receive_log_recorder: "CloudSyncReceiveLogRecorder",
        receive_log_context: dict[str, Any],
    ) -> dict[str, Any]:
        if self.dry_run:
            return {"success": True, "written_rows": len(rows), "dry_run": True}

        sql = self._build_upsert_sql(table_name, data_domain)
        prepared_rows = self._prepare_rows_for_insert(rows)
        with self.engine.begin() as conn:
            conn.execute(text(sql), prepared_rows)
            receive_result = receive_log_recorder.record_success_on_connection(
                conn,
                **receive_log_context,
            )
        return {
            "success": True,
            "written_rows": len(rows),
            "receive_log": receive_result,
            "receive_id": receive_result.get("receive_id"),
        }

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


class CloudSyncReceiveLogRecorder:
    """Append cloud-side receive ledger rows after successful mirror writes."""

    def __init__(self, engine, source_environment: str | None = None):
        self.engine = engine
        self.source_environment = source_environment

    @staticmethod
    def _coerce_business_date(value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    @classmethod
    def _business_date_range(cls, rows: list[dict[str, Any]]) -> tuple[date | None, date | None]:
        dates: list[date] = []
        for row in rows:
            for key in ("business_date", "period_end_date", "analytics_date", "order_date", "stat_date", "date"):
                parsed = cls._coerce_business_date(row.get(key))
                if parsed is not None:
                    dates.append(parsed)
                    break
        if not dates:
            return None, None
        return min(dates), max(dates)

    @staticmethod
    def _first_non_empty(rows: list[dict[str, Any]], key: str) -> Any | None:
        for row in rows:
            value = row.get(key)
            if value not in (None, ""):
                return value
        return None

    def record_success(
        self,
        *,
        source_table_name: str,
        receive_id: str | None = None,
        source_file_id: int | None = None,
        platform_code: str | None = None,
        data_domain: str | None = None,
        granularity: str | None = None,
        checkpoint_scope: str = "b_class",
        source_latest_ingest_timestamp: Any | None = None,
        written_rows: int = 0,
        rows: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload = self._build_success_payload(
            source_table_name=source_table_name,
            receive_id=receive_id,
            source_file_id=source_file_id,
            platform_code=platform_code,
            data_domain=data_domain,
            granularity=granularity,
            checkpoint_scope=checkpoint_scope,
            source_latest_ingest_timestamp=source_latest_ingest_timestamp,
            written_rows=written_rows,
            rows=rows,
        )
        with self.engine.begin() as conn:
            conn.execute(insert(CloudSyncReceiveLog.__table__).values(**payload))
        return {"status": "completed", "receive_id": payload["receive_id"], "written_rows": written_rows}

    def record_success_on_connection(
        self,
        conn,
        *,
        source_table_name: str,
        receive_id: str | None = None,
        source_file_id: int | None = None,
        platform_code: str | None = None,
        data_domain: str | None = None,
        granularity: str | None = None,
        checkpoint_scope: str = "b_class",
        source_latest_ingest_timestamp: Any | None = None,
        written_rows: int = 0,
        rows: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload = self._build_success_payload(
            source_table_name=source_table_name,
            receive_id=receive_id,
            source_file_id=source_file_id,
            platform_code=platform_code,
            data_domain=data_domain,
            granularity=granularity,
            checkpoint_scope=checkpoint_scope,
            source_latest_ingest_timestamp=source_latest_ingest_timestamp,
            written_rows=written_rows,
            rows=rows,
        )
        conn.execute(insert(CloudSyncReceiveLog.__table__).values(**payload))
        return {"status": "completed", "receive_id": payload["receive_id"], "written_rows": written_rows}

    def _build_success_payload(
        self,
        *,
        source_table_name: str,
        receive_id: str | None = None,
        source_file_id: int | None = None,
        platform_code: str | None = None,
        data_domain: str | None = None,
        granularity: str | None = None,
        checkpoint_scope: str = "b_class",
        source_latest_ingest_timestamp: Any | None = None,
        written_rows: int = 0,
        rows: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        rows = list(rows or [])
        business_date_min, business_date_max = self._business_date_range(rows)
        receive_id = receive_id or f"receive-{uuid.uuid4().hex}"
        return {
            "receive_id": receive_id,
            "source_environment": self.source_environment,
            "checkpoint_scope": checkpoint_scope,
            "source_table_name": source_table_name,
            "source_file_id": source_file_id if source_file_id is not None else self._first_non_empty(rows, "file_id"),
            "platform_code": platform_code or self._first_non_empty(rows, "platform_code"),
            "data_domain": data_domain or self._first_non_empty(rows, "data_domain"),
            "granularity": granularity or self._first_non_empty(rows, "granularity"),
            "business_date_min": business_date_min,
            "business_date_max": business_date_max,
            "source_latest_ingest_timestamp": source_latest_ingest_timestamp,
            "written_rows": written_rows,
            "status": "completed",
        }


class CloudRefreshQueueEnqueuer:
    """Write post-sync refresh intents into the target database refresh queue."""

    PIPELINE_NAME = "data_ingested_refresh"
    TRIGGER_TYPE = "cloud_sync"

    def __init__(self, engine):
        self.engine = engine

    def enqueue_after_sync(
        self,
        *,
        source_table_name: str,
        data_domain: str,
        written_rows: int,
        checkpoint_scope: str,
        source_latest_ingest_timestamp: Any | None = None,
    ) -> dict[str, Any]:
        from backend.services.event_listeners import determine_pipeline_targets_for_data_ingested
        from backend.utils.events import DataIngestedEvent

        event = DataIngestedEvent(
            file_id=None,
            platform_code=None,
            data_domain=data_domain,
            sub_domain=None,
            granularity=None,
            source_table_name=source_table_name,
            row_count=written_rows,
        )
        targets = determine_pipeline_targets_for_data_ingested(event)
        if not targets:
            return {"status": "not_required", "targets": []}

        context = {
            "source_table_name": source_table_name,
            "data_domain": data_domain,
            "written_rows": written_rows,
            "checkpoint_scope": checkpoint_scope,
            "trigger_source": self.TRIGGER_TYPE,
            "related_table_names": [source_table_name],
        }
        if source_latest_ingest_timestamp is not None:
            context["source_latest_ingest_timestamp"] = str(source_latest_ingest_timestamp)
        dedupe_key = RefreshQueueService.build_dedupe_key(self.PIPELINE_NAME, targets)
        table = RefreshQueueTask.__table__

        with self.engine.begin() as conn:
            existing = conn.execute(
                select(table.c.id, table.c.job_id, table.c.context_json)
                .where(table.c.dedupe_key == dedupe_key, table.c.status == "pending")
                .order_by(table.c.id.asc())
                .limit(1)
            ).mappings().first()

            if existing is not None:
                merged_context = RefreshQueueService._merge_context(
                    dict(existing.get("context_json") or {}),
                    context,
                )
                conn.execute(
                    update(table)
                    .where(table.c.id == existing["id"])
                    .values(context_json=merged_context)
                )
                return {
                    "status": "queued",
                    "job_id": existing["job_id"],
                    "targets": sorted(set(targets)),
                    "coalesced": True,
                }

            job_id = f"refresh-{uuid.uuid4().hex}"
            conn.execute(
                insert(table).values(
                    job_id=job_id,
                    trigger_type=self.TRIGGER_TYPE,
                    pipeline_name=self.PIPELINE_NAME,
                    dedupe_key=dedupe_key,
                    targets_json=sorted(str(target).strip() for target in targets if str(target).strip()),
                    context_json=context,
                    status="pending",
                    attempt_count=0,
                )
            )
            return {
                "status": "queued",
                "job_id": job_id,
                "targets": sorted(set(targets)),
                "coalesced": False,
            }


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
        checkpoint_scope: str = "b_class",
        projection_enqueuer=None,
        receive_log_recorder=None,
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
        self.checkpoint_scope = checkpoint_scope
        self.projection_enqueuer = projection_enqueuer
        self.receive_log_recorder = receive_log_recorder
        if self.projection_enqueuer is None and cloud_engine is not None:
            self.projection_enqueuer = CloudRefreshQueueEnqueuer(cloud_engine)
        if self.receive_log_recorder is None and cloud_engine is not None:
            self.receive_log_recorder = CloudSyncReceiveLogRecorder(cloud_engine)

    @staticmethod
    def _should_advance_checkpoint(write_succeeded: bool, dry_run: bool = False) -> bool:
        return bool(write_succeeded) and not dry_run

    @staticmethod
    def _filter_b_class_tables(table_names: Iterable[str]) -> list[str]:
        filtered: list[str] = []
        for table_name in table_names:
            if "." in table_name:
                continue
            if table_name.startswith("fact_test_"):
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
            checkpoint = self.checkpoint_service.create_or_get_checkpoint(
                table_name,
                table_schema=self.checkpoint_scope,
            )
            data_domain = self._infer_data_domain(table_name)
            self.mirror_manager.ensure_cloud_mirror_table(table_name, data_domain)
            total_written_rows = 0
            dry_run_seen = False
            latest_ingest_timestamp = None

            def _projection_result() -> dict[str, Any]:
                if total_written_rows <= 0 or dry_run_seen:
                    return {"projection_status": "not_required"}
                if self.projection_enqueuer is None:
                    return {"projection_status": "not_required"}
                try:
                    enqueue_result = self.projection_enqueuer.enqueue_after_sync(
                        source_table_name=table_name,
                        data_domain=data_domain,
                        written_rows=total_written_rows,
                        checkpoint_scope=self.checkpoint_scope,
                        source_latest_ingest_timestamp=latest_ingest_timestamp,
                    )
                except Exception as exc:  # noqa: BLE001
                    return {
                        "projection_status": "failed",
                        "projection_error": str(exc),
                        "error_code": "projection_runtime_failure",
                    }

                status = enqueue_result.get("status", "not_required")
                payload = {
                    "projection_status": status,
                    "refresh_queue_job_id": enqueue_result.get("job_id"),
                    "refresh_targets": enqueue_result.get("targets", []),
                }
                if status == "not_required":
                    payload["projection_status"] = "not_required"
                return payload

            while True:
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
                        "written_rows": total_written_rows,
                        **_projection_result(),
                    }

                receive_id = f"receive-{uuid.uuid4().hex}"
                source_file_id = CloudSyncReceiveLogRecorder._first_non_empty(rows, "file_id")
                for payload_row in payload_rows:
                    raw_payload = payload_row.get("raw_data")
                    if not isinstance(raw_payload, dict):
                        raw_payload = {}
                    raw_payload["_cloud_sync_receive_id"] = receive_id
                    if source_file_id is not None:
                        raw_payload.setdefault("_cloud_sync_source_file_id", source_file_id)
                    payload_row["raw_data"] = raw_payload

                receive_log_context = {
                    "source_table_name": table_name,
                    "receive_id": receive_id,
                    "source_file_id": source_file_id,
                    "data_domain": data_domain,
                    "granularity": (payload_rows[0] or {}).get("granularity") if payload_rows else None,
                    "platform_code": (payload_rows[0] or {}).get("platform_code") if payload_rows else None,
                    "checkpoint_scope": self.checkpoint_scope,
                    "source_latest_ingest_timestamp": rows[-1].get("ingest_timestamp") if rows else None,
                    "written_rows": len(rows),
                    "rows": rows,
                }
                if (
                    self.receive_log_recorder is not None
                    and hasattr(self.remote_writer, "write_rows_with_receive_log")
                ):
                    write_result = await self._maybe_await(
                        self.remote_writer.write_rows_with_receive_log(
                            table_name=table_name,
                            rows=payload_rows,
                            data_domain=data_domain,
                            receive_log_recorder=self.receive_log_recorder,
                            receive_log_context=receive_log_context,
                        )
                    )
                else:
                    write_result = await self._maybe_await(
                        self.remote_writer(
                            table_name=table_name,
                            rows=payload_rows,
                            data_domain=data_domain,
                        )
                    )

                write_succeeded = bool(write_result.get("success"))
                if not write_succeeded:
                    return {
                        "status": "failed",
                        "table_name": table_name,
                        "written_rows": total_written_rows,
                        "error": write_result.get("error") or write_result.get("detail") or "sync_failed",
                        "error_code": write_result.get("error_code") or "sync_failed",
                    }

                total_written_rows += int(write_result.get("written_rows", len(rows)))
                if (
                    self.receive_log_recorder is not None
                    and not bool(write_result.get("dry_run"))
                    and not write_result.get("receive_log")
                ):
                    await self._maybe_await(
                        self.receive_log_recorder.record_success(**receive_log_context)
                    )
                dry_run_seen = dry_run_seen or bool(write_result.get("dry_run"))
                if self._should_advance_checkpoint(write_succeeded, dry_run=bool(write_result.get("dry_run"))):
                    last_row = rows[-1]
                    latest_ingest_timestamp = last_row["ingest_timestamp"]
                    self.checkpoint_service.advance_checkpoint(
                        table_name=table_name,
                        ingest_timestamp=last_row["ingest_timestamp"],
                        source_id=last_row["id"],
                        status="completed",
                        table_schema=self.checkpoint_scope,
                    )
                else:
                    return {
                        "status": "completed",
                        "table_name": table_name,
                        "written_rows": total_written_rows,
                        **_projection_result(),
                    }

                if len(rows) < batch_size:
                    return {
                        "status": "completed",
                        "table_name": table_name,
                        "written_rows": total_written_rows,
                        **_projection_result(),
                    }
        except Exception as exc:
            self.checkpoint_service.mark_failure(
                table_name,
                str(exc),
                table_schema=self.checkpoint_scope,
            )
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
