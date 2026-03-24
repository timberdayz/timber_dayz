from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def _normalize_period_start(year_month: str):
    return datetime.strptime(f"{year_month}-01", "%Y-%m-%d").date()


def _shop_key(platform_code: Any, shop_id: Any) -> str:
    return f"{(platform_code or '').lower()}|{str(shop_id or '').lower()}"


async def load_shop_monthly_metrics(
    db: AsyncSession,
    year_month: str,
) -> dict[str, dict[str, float]]:
    period_key = _normalize_period_start(year_month)
    result = await db.execute(
        text(
            """
            SELECT platform_code, shop_id, gmv, profit, achievement_rate
            FROM api.business_overview_shop_racing_module
            WHERE granularity = 'monthly'
              AND period_key = :period_key
            """
        ),
        {"period_key": period_key},
    )

    metrics_by_shop: dict[str, dict[str, float]] = {}
    for row in result.mappings().all():
        key = _shop_key(row.get("platform_code"), row.get("shop_id"))
        metrics_by_shop[key] = {
            "monthly_sales": _to_float(row.get("gmv")),
            "monthly_profit": _to_float(row.get("profit")),
            "achievement_rate": _to_float(row.get("achievement_rate")),
        }
    return metrics_by_shop


async def load_shop_monthly_target_achievement(
    db: AsyncSession,
    year_month: str,
) -> dict[str, dict[str, float | str]]:
    period_key = _normalize_period_start(year_month)
    result = await db.execute(
        text(
            """
            SELECT platform_code, shop_id, gmv, target_amount, achievement_rate
            FROM api.business_overview_shop_racing_module
            WHERE granularity = 'monthly'
              AND period_key = :period_key
            """
        ),
        {"period_key": period_key},
    )

    source_rows: dict[str, dict[str, float | str]] = {}
    for row in result.mappings().all():
        key = _shop_key(row.get("platform_code"), row.get("shop_id"))
        source_rows[key] = {
            "platform_code": (row.get("platform_code") or "").lower(),
            "shop_id": row.get("shop_id") or "",
            "target": _to_float(row.get("target_amount")),
            "achieved": _to_float(row.get("gmv")),
            "achievement_rate": _to_float(row.get("achievement_rate")),
        }
    return source_rows
