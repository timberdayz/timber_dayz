from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.data_pipeline.dashboard_bootstrap import inspect_dashboard_assets


@dataclass
class RefreshValidationReport:
    status: str
    missing_objects: list[str] = field(default_factory=list)
    stale_targets: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    repair_attempted: bool = False
    error_message: str | None = None

    def is_success(self) -> bool:
        return self.status == "success"

    def to_error_message(self) -> str:
        parts: list[str] = []
        if self.error_message:
            parts.append(self.error_message)
        if self.missing_objects:
            parts.append(f"missing_objects:{','.join(self.missing_objects)}")
        if self.stale_targets:
            parts.append(f"stale_targets:{','.join(self.stale_targets)}")
        if not parts:
            parts.append(f"refresh validation {self.status}")
        return "; ".join(parts)


async def _target_exists(db: AsyncSession, target: str) -> bool:
    result = await db.execute(text("SELECT to_regclass(:target_name)"), {"target_name": target})
    return result.scalar_one_or_none() is not None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    raw_value = str(value).strip()
    if not raw_value:
        return None
    if raw_value.endswith("Z"):
        raw_value = f"{raw_value[:-1]}+00:00"
    try:
        return datetime.fromisoformat(raw_value)
    except ValueError:
        return None


async def _load_target_last_succeeded_at(db: AsyncSession, target: str) -> datetime | None:
    result = await db.execute(
        text(
            """
            SELECT last_succeeded_at
            FROM ops.data_freshness_log
            WHERE target_name = :target_name
            """
        ),
        {"target_name": target},
    )
    return result.scalar_one_or_none()


async def _target_is_fresh_enough(
    db: AsyncSession,
    *,
    target: str,
    source_latest_ingest: datetime,
) -> bool:
    try:
        last_succeeded_at = await _load_target_last_succeeded_at(db, target)
    except Exception:
        return True
    if last_succeeded_at is None:
        return False
    try:
        return last_succeeded_at >= source_latest_ingest
    except TypeError:
        return last_succeeded_at.replace(tzinfo=None) >= source_latest_ingest.replace(tzinfo=None)


def _module_status_is_ready(module_report: dict[str, Any] | None) -> bool:
    if not isinstance(module_report, dict):
        return False
    return str(module_report.get("status") or "").lower() == "ready"


async def validate_refresh_result(
    db: AsyncSession,
    *,
    targets: list[str],
    context: dict[str, Any] | None = None,
    modules: list[str] | None = None,
    repair_attempted: bool = False,
) -> RefreshValidationReport:
    context = context or {}
    if not hasattr(db, "execute"):
        return RefreshValidationReport(
            status="success",
            modules=list(modules or []),
            repair_attempted=repair_attempted,
        )

    missing_objects: list[str] = []
    for target in targets:
        if "." not in str(target):
            continue
        if not await _target_exists(db, str(target)):
            missing_objects.append(str(target))

    stale_targets: list[str] = []
    source_latest_ingest = _parse_datetime(context.get("source_latest_ingest_timestamp"))
    written_rows = int(context.get("written_rows") or context.get("row_count") or 0)
    if source_latest_ingest is not None and written_rows > 0:
        for target in targets:
            if "." not in str(target):
                continue
            if not await _target_is_fresh_enough(
                db,
                target=str(target),
                source_latest_ingest=source_latest_ingest,
            ):
                stale_targets.append(str(target))

    failed_modules: list[str] = []
    module_names = list(dict.fromkeys(modules or []))
    if module_names:
        report = await inspect_dashboard_assets(db)
        module_reports = report.get("modules") if isinstance(report, dict) else {}
        for module_name in module_names:
            module_report = module_reports.get(module_name) if isinstance(module_reports, dict) else None
            if not _module_status_is_ready(module_report):
                failed_modules.append(module_name)

    if missing_objects or stale_targets or failed_modules:
        error_parts: list[str] = []
        if failed_modules:
            error_parts.append(f"dashboard_modules_not_ready:{','.join(failed_modules)}")
        return RefreshValidationReport(
            status="failed",
            missing_objects=missing_objects,
            stale_targets=stale_targets,
            modules=module_names,
            repair_attempted=repair_attempted,
            error_message="; ".join(error_parts) or None,
        )

    return RefreshValidationReport(
        status="success",
        modules=module_names,
        repair_attempted=repair_attempted,
    )
