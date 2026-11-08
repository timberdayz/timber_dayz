"""语义层就绪状态位（语义层 SSOT 改造 · 阶段 6 · 任务 6.2）。

为什么需要这个状态位
--------------------
采集落盘 -> 语义层就绪之间有**时间差**：2026-11-08 实测，采集文件 12:24:57 落盘，
``semantic.fact_orders_atomic_mv`` 12:29:00 就绪、``semantic.fact_orders_monthly_atomic_mv``
12:31:03 才就绪 => 中间约 **70 秒**（月粒度链路约 6 分钟）看板对着**旧数据/空数据**，
让人只能靠猜「今天是没单还是没采到」。

本模块给出看板可用的状态位（**只新增字段，不改既有字段语义**）：

===============  =============================================================
状态             含义
===============  =============================================================
``fresh``        语义层已经包含最新一次采集入库的数据
``updating``     采集已完成、语义层尚未就绪（仍在刷新窗口内）
``stale``        超出新鲜度阈值：源数据太旧，或语义层长时间没跟上
``unknown``      既没有采集入库记录，也没有语义层刷新记录（判不了）
===============  =============================================================

复用既有机制（**不另起一套并行状态**）
--------------------------------------
- 「语义层什么时候就绪」-> ``ops.data_freshness_log.last_succeeded_at``
  （``backend/services/data_pipeline/refresh_runner.py`` 每次刷新成功都会写；
  ``refresh_validation._target_is_fresh_enough`` 用的就是同一份口径）。
- 「源数据有多旧」-> ``backend/services/data_pipeline/source_freshness_service``
  的 ``classify_source_freshness`` + ``max_age_days_for``（阈值口径完全一致，
  链级例外、环境变量覆盖都直接继承）。
- 「哪些源表在用」-> 与 ``postgresql_dashboard_service`` 的 freshness 侧同一份
  订单源表清单（``fact_{platform}_orders_{granularity}``，共 9 张）。

[注意] 边界：本模块**只读**（不改表、不改迁移、不刷新视图），
   状态位是给看板/巡检消费的一个**新增**事实，不替换既有的
   ``meta.data_status``（那是空周期/降级口径，两者互不干扰）。
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.data_pipeline.source_freshness_service import (
    classify_source_freshness,
    max_age_days_for,
)

__all__ = [
    "DEFAULT_UPDATING_WINDOW_SECONDS",
    "ORDER_SOURCE_TABLES_BY_GRANULARITY",
    "SEMANTIC_READINESS_FRESH",
    "SEMANTIC_READINESS_STALE",
    "SEMANTIC_READINESS_UNKNOWN",
    "SEMANTIC_READINESS_UPDATING",
    "SEMANTIC_READY_TARGETS_BY_GRANULARITY",
    "classify_semantic_readiness",
    "collect_semantic_readiness",
    "collect_semantic_readiness_standalone",
    "updating_window_seconds",
]


SEMANTIC_READINESS_FRESH = "fresh"
SEMANTIC_READINESS_UPDATING = "updating"
SEMANTIC_READINESS_STALE = "stale"
SEMANTIC_READINESS_UNKNOWN = "unknown"

#: 「采集已完成但语义层还没跟上」的最长宽容时间（秒）。
#:
#: 默认 30 分钟：实测月粒度链路从落盘到月物化视图就绪约 6 分钟，
#: 30 分钟既能覆盖慢刷新，也不会把「刷新链路坏了」拖成半天的假新鲜。
#: 可用环境变量 ``SEMANTIC_READINESS_UPDATING_WINDOW_SECONDS`` 覆盖。
DEFAULT_UPDATING_WINDOW_SECONDS = 1800

#: 订单域的源表（``b_class`` schema）—— 与看板 freshness 侧同一份清单。
#:
#: [注意] 表名里的平台前缀**不等于采集器**：shopee / tiktok 的订单数据实际由
#: miaoshou 采集器写入（见 ``order_source_governance``）。
ORDER_SOURCE_TABLES_BY_GRANULARITY: dict[str, tuple[str, ...]] = {
    "daily": (
        "fact_shopee_orders_daily",
        "fact_tiktok_orders_daily",
        "fact_miaoshou_orders_daily",
    ),
    "weekly": (
        "fact_shopee_orders_weekly",
        "fact_tiktok_orders_weekly",
        "fact_miaoshou_orders_weekly",
    ),
    "monthly": (
        "fact_shopee_orders_monthly",
        "fact_tiktok_orders_monthly",
        "fact_miaoshou_orders_monthly",
    ),
}

#: 各粒度对应的**语义层物化目标**（刷新成功时间写在
#: ``ops.data_freshness_log``）。
SEMANTIC_READY_TARGETS_BY_GRANULARITY: dict[str, tuple[str, ...]] = {
    "daily": ("semantic.fact_orders_atomic_mv",),
    "weekly": ("semantic.fact_orders_atomic_mv",),
    "monthly": ("semantic.fact_orders_monthly_atomic_mv",),
}


def updating_window_seconds() -> int:
    """「采集中/刷新中」的宽容窗口（秒），可用环境变量覆盖。"""
    raw = os.getenv("SEMANTIC_READINESS_UPDATING_WINDOW_SECONDS")
    if raw:
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            pass
    return DEFAULT_UPDATING_WINDOW_SECONDS


def _as_utc(value: datetime | None) -> datetime | None:
    """统一成 UTC aware。

    [注意] 源表的 ``ingest_timestamp`` 历史上有两种类型：基线迁移建的是
    ``timestamptz``，而 ``platform_table_manager`` 动态建的表是**无时区**
    ``timestamp`` => 读出来可能是 naive => 这里统一按 UTC 补齐，
    否则新旧表混在一起比较会差 8 小时。
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_datetimeish(value: Any) -> datetime | None:
    """把数据库返回的时间统一解析成 UTC aware datetime。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return _as_utc(value)
    raw = str(value).strip()
    if not raw:
        return None
    normalized = raw.replace(" ", "T", 1)
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    # PostgreSQL 的 timestamptz 文本形如 "+00"/"-05"，补成 ISO 的 "+00:00"。
    if len(normalized) >= 3 and normalized[-3] in "+-" and normalized[-2:].isdigit():
        normalized = f"{normalized[:-2]}{normalized[-2:]}:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return _as_utc(parsed)


def _parse_dateish(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def classify_semantic_readiness(
    *,
    last_ingest_at: datetime | None,
    last_semantic_ready_at: datetime | None,
    now: datetime,
    updating_window_seconds: int = DEFAULT_UPDATING_WINDOW_SECONDS,
    source_status: str | None = None,
) -> tuple[str, str]:
    """返回 ``(状态, 原因)``。

    判定规则（**先判源数据新旧，再判语义层是否跟上**）：

    1. 源数据本身超出新鲜度阈值（``source_status == "stale"``）=> ``stale``
       —— 语义层跟得再紧也只是旧数据的忠实呈现；
    2. 既没有采集入库记录、也没有语义层刷新记录 => ``unknown``（判不了）；
    3. 没有采集入库记录但语义层刷新过 => ``fresh``（没有待处理的采集）；
    4. 语义层就绪时间 **≥** 最新采集入库时间 => ``fresh``（已包含最新数据）；
    5. 语义层还没跟上，且等待时长在宽容窗口内 => ``updating``（正在刷新）；
    6. 语义层还没跟上且已超窗口 => ``stale``（刷新链路卡住了）。
    """
    if source_status == "stale":
        return SEMANTIC_READINESS_STALE, "source_data_exceeds_freshness_threshold"

    if last_ingest_at is None and last_semantic_ready_at is None:
        return SEMANTIC_READINESS_UNKNOWN, "no_ingest_and_no_semantic_ready"

    if last_ingest_at is None:
        return SEMANTIC_READINESS_FRESH, "semantic_ready_without_pending_ingest"

    if last_semantic_ready_at is not None and last_semantic_ready_at >= last_ingest_at:
        return SEMANTIC_READINESS_FRESH, "semantic_layer_includes_latest_ingest"

    pending_seconds = max(0.0, (now - last_ingest_at).total_seconds())
    if pending_seconds <= updating_window_seconds:
        return SEMANTIC_READINESS_UPDATING, "semantic_layer_pending_after_ingest"

    return SEMANTIC_READINESS_STALE, "semantic_layer_pending_too_long"


def _build_source_aggregate_sql(
    table_names: list[str],
    *,
    platform: str | None,
    shop_id: str | None,
) -> tuple[str, dict[str, Any]]:
    """构造源表聚合 SQL（只统计存在的表，避免整条查询失败）。"""
    params: dict[str, Any] = {}
    conditions: list[str] = []
    if platform:
        conditions.append("platform_code = :platform_code")
        params["platform_code"] = platform
    if shop_id:
        conditions.append("shop_id = :shop_id")
        params["shop_id"] = shop_id
    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    union_parts = [
        f"SELECT metric_date, ingest_timestamp FROM b_class.{table_name}{where_clause}"
        for table_name in table_names
    ]
    sql = f"""
        SELECT
            COUNT(*) AS row_count,
            MAX(metric_date) AS max_metric_date,
            MAX(ingest_timestamp) AS max_ingest_timestamp
        FROM (
            {' UNION ALL '.join(union_parts)}
        ) semantic_readiness_source_rows
    """
    return sql, params


async def _load_existing_source_tables(
    db: AsyncSession, table_names: list[str]
) -> list[str]:
    if not table_names:
        return []
    result = await db.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'b_class'
              AND table_name = ANY(:table_names)
            """
        ),
        {"table_names": table_names},
    )
    existing = {str(row[0]) for row in result.fetchall() if row and row[0]}
    return [name for name in table_names if name in existing]


async def _load_semantic_ready_at(
    db: AsyncSession, targets: list[str]
) -> datetime | None:
    """语义层目标**最近一次刷新成功**的时间。

    数据源是 ``ops.data_freshness_log``（``refresh_runner`` 刷新成功时写入），
    口径与 ``refresh_validation._target_is_fresh_enough`` 完全一致。
    """
    if not targets:
        return None
    try:
        result = await db.execute(
            text(
                """
                SELECT MAX(last_succeeded_at) AS last_semantic_ready_at
                FROM ops.data_freshness_log
                WHERE target_name = ANY(:targets)
                """
            ),
            {"targets": targets},
        )
        row = result.fetchone()
    except Exception:
        # 监控表缺失/无权限时不能让看板整个失败 => 判成「还没就绪过」。
        return None
    if not row:
        return None
    return _parse_datetimeish(row[0])


async def collect_semantic_readiness(
    db: AsyncSession,
    *,
    granularity: str = "monthly",
    platform: str | None = None,
    shop_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """采集「语义层就绪状态位」。

    返回字典里的 ``status`` ∈ {``fresh``, ``updating``, ``stale``, ``unknown``}，
    并附带 ``last_ingest_at`` / ``last_semantic_ready_at`` 两个时间戳。
    """
    effective_granularity = str(granularity or "monthly").strip().lower()
    current_time = _as_utc(now or datetime.now(timezone.utc)) or datetime.now(
        timezone.utc
    )

    candidate_tables = list(
        ORDER_SOURCE_TABLES_BY_GRANULARITY.get(effective_granularity, ())
    )
    if platform:
        platform_prefix = f"fact_{str(platform).strip().lower()}_"
        candidate_tables = [
            name for name in candidate_tables if name.startswith(platform_prefix)
        ]
    targets = list(SEMANTIC_READY_TARGETS_BY_GRANULARITY.get(effective_granularity, ()))

    source_tables = await _load_existing_source_tables(db, candidate_tables)

    row_count = 0
    max_metric_date: date | None = None
    last_ingest_at: datetime | None = None
    if source_tables:
        aggregate_sql, params = _build_source_aggregate_sql(
            source_tables, platform=platform, shop_id=shop_id
        )
        result = await db.execute(text(aggregate_sql), params)
        row = result.fetchone()
        if row:
            row_count = int(row[0] or 0)
            max_metric_date = _parse_dateish(row[1])
            last_ingest_at = _parse_datetimeish(row[2])

    last_semantic_ready_at = await _load_semantic_ready_at(db, targets)

    limit_days = max_age_days_for(effective_granularity)
    source_status, business_age_days = classify_source_freshness(
        row_count=row_count,
        max_metric_date=max_metric_date,
        now_date=current_time.date(),
        max_age_days=limit_days,
    )

    window_seconds = updating_window_seconds()
    status, reason = classify_semantic_readiness(
        last_ingest_at=last_ingest_at,
        last_semantic_ready_at=last_semantic_ready_at,
        now=current_time,
        updating_window_seconds=window_seconds,
        source_status=source_status,
    )

    pending_seconds: int | None = None
    if last_ingest_at is not None and status in {
        SEMANTIC_READINESS_UPDATING,
        SEMANTIC_READINESS_STALE,
    }:
        pending_seconds = int(max(0.0, (current_time - last_ingest_at).total_seconds()))

    return {
        "status": status,
        "reason": reason,
        "granularity": effective_granularity,
        "platform_code": platform,
        "shop_id": shop_id,
        "source_tables": source_tables,
        "semantic_targets": targets,
        "row_count": row_count,
        "last_ingest_at": last_ingest_at.isoformat() if last_ingest_at else None,
        "last_semantic_ready_at": (
            last_semantic_ready_at.isoformat() if last_semantic_ready_at else None
        ),
        "pending_seconds": pending_seconds,
        "updating_window_seconds": window_seconds,
        "max_age_days": limit_days,
        "business_age_days": business_age_days,
        "source_status": source_status,
        "checked_at": current_time.isoformat(),
    }


async def collect_semantic_readiness_standalone(
    *,
    granularity: str = "monthly",
    platform: str | None = None,
    shop_id: str | None = None,
) -> dict[str, Any]:
    """自己开连接的版本（看板 service 用；不依赖调用方持有 session）。"""
    from backend.models.database import AsyncSessionLocal, apply_statement_timeout

    async with AsyncSessionLocal() as session:
        try:
            await apply_statement_timeout(session, 15000)
        except Exception:
            pass
        return await collect_semantic_readiness(
            session,
            granularity=granularity,
            platform=platform,
            shop_id=shop_id,
        )
