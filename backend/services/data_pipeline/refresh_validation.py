from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.data_pipeline.dashboard_bootstrap import (
    DASHBOARD_ASSET_AVAILABLE_STATUSES,
    inspect_dashboard_assets,
)
from backend.services.data_pipeline.refresh_registry import LOGICAL_TARGET_OBJECTS


__all__ = [
    "DASHBOARD_ASSET_AVAILABLE_STATUSES",
    "LOGICAL_TARGET_OBJECTS",
    "RefreshValidationReport",
    "find_missing_targets",
]


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


# 目标名与真实数据库对象名不一致的「逻辑目标」——
# 登记表在 ``refresh_registry``（本模块与 ``dashboard_bootstrap`` 都要用它，
# 而本模块已经 import 了 ``dashboard_bootstrap`` ⇒ 反向 import 会成环）。
LOGICAL_TARGET_OBJECTS = LOGICAL_TARGET_OBJECTS


async def _target_exists(db: AsyncSession, target: str) -> bool:
    """目标对象是否存在（**关系或函数**都算）。

    ``to_regclass`` 只认表/视图/物化视图/序列，**认不出函数**
    ⇒ 函数型目标（如共享的店铺身份解析函数）会被永远算成 missing。
    """
    object_name = LOGICAL_TARGET_OBJECTS.get(target, target)
    result = await db.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname || '.' || c.relname = :object_name
            )
            OR EXISTS (
                SELECT 1
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname || '.' || p.proname = :object_name
            )
            """
        ),
        {"object_name": object_name},
    )
    return bool(result.scalar_one_or_none())


async def find_missing_targets(
    db: AsyncSession,
    target_names: Iterable[str],
) -> set[str]:
    """批量核对目标对象当前是否仍然存在于数据库中。

    freshness 只记录「上一次刷新当时的结果」：对象后来被删除/改名时，
    状态仍显示 success，监控因此「假绿」。这里做一次实时存在性核对，
    把「已注册但对象已不存在」的目标挑出来。

    仅检查带 schema 前缀的目标（如 `api.xxx_module`）；不带前缀的名字不是数据库对象。
    逻辑目标按 LOGICAL_TARGET_OBJECTS 登记的真实对象名核对。
    """
    resolved: dict[str, str] = {}
    for name in {str(n) for n in target_names if n and "." in str(n)}:
        resolved[name] = LOGICAL_TARGET_OBJECTS.get(name, name)
    if not resolved:
        return set()

    object_names = sorted(set(resolved.values()))
    result = await db.execute(
        text(
            """
            SELECT n.nspname || '.' || c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname || '.' || c.relname = ANY(:targets)
            UNION
            -- 有些逻辑目标建的是**函数**（如共享的店铺身份解析函数），
            -- 函数不在 pg_class 里 ⇒ 必须单独查 pg_proc，否则会被误报成 missing。
            SELECT n.nspname || '.' || p.proname
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname || '.' || p.proname = ANY(:targets)
            """
        ),
        {"targets": object_names},
    )
    existing = {row[0] for row in result.fetchall()}
    return {
        name for name, object_name in resolved.items() if object_name not in existing
    }


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


async def _load_target_last_succeeded_at(
    db: AsyncSession, target: str
) -> datetime | None:
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
        return last_succeeded_at.replace(tzinfo=None) >= source_latest_ingest.replace(
            tzinfo=None
        )


def _module_status_is_ready(module_report: dict[str, Any] | None) -> bool:
    """模块是否**可用**（口径与运行期门禁完全一致）。

    ⚠️ 旧口径要求 ``status == 'ready'`` —— 等于让**修复方把自己制造的
    ``refreshing`` 状态当成失败条件**：

        安全网/刷新排了修复任务 → 修复任务跑起来 → 模块进入 ``refreshing``
        → 验收方要求 ``ready`` → 验收失败 → 任务标记 failed → 退避重排
        → 下一轮安全网又看到「不是 ready」→ 再排一次 → 无限自锁。

    2026-11-07 事故链实测：``dashboard_safety_net_repair`` 攒出 **859 次 failed**。

    现在只把 ``drift``（对象缺失 / 定义漂移 = 数据不可信）当失败，
    ``refreshing`` 是**可用**状态 —— 与
    ``dashboard_api_postgresql._require_dashboard_assets_ready`` 用同一份
    ``DASHBOARD_ASSET_AVAILABLE_STATUSES``，两边口径不可能再分叉。
    """
    if not isinstance(module_report, dict):
        return False
    status = str(module_report.get("status") or "").lower()
    return status in DASHBOARD_ASSET_AVAILABLE_STATUSES


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
    source_latest_ingest = _parse_datetime(
        context.get("source_latest_ingest_timestamp")
    )
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
            module_report = (
                module_reports.get(module_name)
                if isinstance(module_reports, dict)
                else None
            )
            if not _module_status_is_ready(module_report):
                failed_modules.append(module_name)

    if missing_objects or stale_targets or failed_modules:
        error_parts: list[str] = []
        if failed_modules:
            error_parts.append(
                f"dashboard_modules_not_ready:{','.join(failed_modules)}"
            )
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
