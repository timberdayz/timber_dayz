"""
Annual cost aggregate service.

Combines:
- A-class operating costs
- B-class monthly order-side costs and GMV

The current runtime still uses this service directly for annual-cost style
payloads. Keep behavior stable, but do not silently collapse B-side query
failures into false zero values.
"""

from datetime import date as date_cls
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.logger import get_logger

logger = get_logger(__name__)


def _safe_float(v: Any) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _resolve_period_bounds(granularity: str, period: str) -> tuple[date_cls, date_cls]:
    if granularity == "monthly":
        year = int(period[:4])
        month = int(period[5:7])
        period_start = date_cls(year, month, 1)
        if month == 12:
            period_end = date_cls(year + 1, 1, 1)
        else:
            period_end = date_cls(year, month + 1, 1)
        return period_start, period_end

    period_start = date_cls(int(period), 1, 1)
    period_end = date_cls(int(period) + 1, 1, 1)
    return period_start, period_end


async def get_annual_cost_aggregate(
    db: AsyncSession,
    granularity: str,
    period: str,
) -> dict[str, Any]:
    if granularity not in ("monthly", "yearly"):
        raise ValueError("granularity must be monthly or yearly")

    period_start, period_end = _resolve_period_bounds(granularity, period)
    year_month_like = f"{period}-%"

    if granularity == "monthly":
        a_sql = text(
            """
            SELECT COALESCE(SUM("租金" + "工资" + "水电费" + "其他成本"), 0) AS total_a
            FROM a_class.operating_costs
            WHERE "年月" = :ym
            """
        )
        a_params = {"ym": period[:7]}
    else:
        a_sql = text(
            """
            SELECT COALESCE(SUM("租金" + "工资" + "水电费" + "其他成本"), 0) AS total_a
            FROM a_class.operating_costs
            WHERE "年月" LIKE :ym_prefix
            """
        )
        a_params = {"ym_prefix": year_month_like}

    try:
        a_row = (await db.execute(a_sql, a_params)).fetchone()
        total_a = _safe_float(a_row[0] if a_row else 0)
    except Exception as exc:
        logger.warning(f"Annual cost aggregate A-side query failed: {exc}")
        total_a = 0.0

    b_sql = text(
        """
        WITH u AS (
            SELECT raw_data, period_start_date FROM b_class.fact_shopee_orders_monthly
            UNION ALL
            SELECT raw_data, period_start_date FROM b_class.fact_tiktok_orders_monthly
            UNION ALL
            SELECT raw_data, period_start_date FROM b_class.fact_miaoshou_orders_monthly
        )
        SELECT
            SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'采购金额', raw_data->>'采购价', ''), ',', ''), ' ', ''), CHR(8212), '-'), CHR(8211), '-'), '[^0-9.-]', '', 'g'), '')::numeric, 0)) AS purchase_amount,
            SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'仓库操作费', ''), ',', ''), ' ', ''), CHR(8212), '-'), CHR(8211), '-'), '[^0-9.-]', '', 'g'), '')::numeric, 0)) AS warehouse_operation_fee,
            (
                SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'运费', ''), ',', ''), ' ', ''), CHR(8212), '-'), CHR(8211), '-'), '[^0-9.-]', '', 'g'), '')::numeric, 0))
                + SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'推广费', ''), ',', ''), ' ', ''), CHR(8212), '-'), CHR(8211), '-'), '[^0-9.-]', '', 'g'), '')::numeric, 0))
                + SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'平台佣金', ''), ',', ''), ' ', ''), CHR(8212), '-'), CHR(8211), '-'), '[^0-9.-]', '', 'g'), '')::numeric, 0))
                + SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'平台扣费', ''), ',', ''), ' ', ''), CHR(8212), '-'), CHR(8211), '-'), '[^0-9.-]', '', 'g'), '')::numeric, 0))
                + SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'代金券', ''), ',', ''), ' ', ''), CHR(8212), '-'), CHR(8211), '-'), '[^0-9.-]', '', 'g'), '')::numeric, 0))
                + SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'服务费', ''), ',', ''), ' ', ''), CHR(8212), '-'), CHR(8211), '-'), '[^0-9.-]', '', 'g'), '')::numeric, 0))
            ) AS platform_fees,
            SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'实付金额', raw_data->>'买家实付金额', ''), ',', ''), ' ', ''), CHR(8212), '-'), CHR(8211), '-'), '[^0-9.-]', '', 'g'), '')::numeric, 0)) AS paid_amount
        FROM u
        WHERE period_start_date >= :period_start AND period_start_date < :period_end
        """
    )
    b_params = {"period_start": period_start, "period_end": period_end}

    try:
        b_row = (await db.execute(b_sql, b_params)).fetchone()
    except Exception as exc:
        logger.warning(f"Annual cost aggregate B-side query failed: {exc}")
        raise

    if b_row:
        purchase_amount = _safe_float(b_row[0])
        warehouse_operation_fee = _safe_float(b_row[1])
        platform_fees = _safe_float(b_row[2]) if b_row[2] is not None else 0.0
        paid_amount = _safe_float(b_row[3])
    else:
        purchase_amount = warehouse_operation_fee = platform_fees = paid_amount = 0.0

    total_b = purchase_amount + warehouse_operation_fee + platform_fees
    total_cost = total_a + total_b
    gmv = paid_amount

    return {
        "total_cost_a": total_a,
        "total_cost_b": total_b,
        "total_cost": total_cost,
        "gmv": gmv,
        "cost_to_revenue_ratio": (total_cost / gmv) if gmv and gmv != 0 else None,
        "roi": ((gmv - total_cost) / total_cost) if total_cost and total_cost != 0 else None,
        "gross_margin": ((gmv - purchase_amount) / gmv) if gmv and gmv != 0 else None,
        "net_margin": ((gmv - total_cost) / gmv) if gmv and gmv != 0 else None,
    }


def _shop_key(platform_code: str, shop_id: str | None) -> str:
    if not shop_id:
        return platform_code or ""
    return f"{platform_code or ''}|{shop_id}"


async def get_annual_cost_aggregate_by_shop(
    db: AsyncSession,
    granularity: str,
    period: str,
) -> list[dict[str, Any]]:
    if granularity not in ("monthly", "yearly"):
        raise ValueError("granularity must be monthly or yearly")

    period_start, period_end = _resolve_period_bounds(granularity, period)
    year_month_like = f"{period}-%"

    if granularity == "monthly":
        a_sql = text(
            """
            SELECT "店铺ID" AS shop_key,
                   COALESCE(SUM("租金" + "工资" + "水电费" + "其他成本"), 0) AS total_a
            FROM a_class.operating_costs
            WHERE "年月" = :ym
            GROUP BY "店铺ID"
            """
        )
        a_params = {"ym": period[:7]}
    else:
        a_sql = text(
            """
            SELECT "店铺ID" AS shop_key,
                   COALESCE(SUM("租金" + "工资" + "水电费" + "其他成本"), 0) AS total_a
            FROM a_class.operating_costs
            WHERE "年月" LIKE :ym_prefix
            GROUP BY "店铺ID"
            """
        )
        a_params = {"ym_prefix": year_month_like}

    a_by_shop: dict[str, float] = {}
    try:
        a_rows = (await db.execute(a_sql, a_params)).fetchall()
        for row in a_rows or []:
            a_by_shop[str(row[0]) or ""] = _safe_float(row[1])
    except Exception as exc:
        logger.warning(f"Annual cost aggregate by shop A-side query failed: {exc}")

    b_sql = text(
        """
        WITH u AS (
            SELECT 'shopee' AS platform_code, shop_id, raw_data, period_start_date
            FROM b_class.fact_shopee_orders_monthly
            UNION ALL
            SELECT 'tiktok', shop_id, raw_data, period_start_date FROM b_class.fact_tiktok_orders_monthly
            UNION ALL
            SELECT 'miaoshou', shop_id, raw_data, period_start_date FROM b_class.fact_miaoshou_orders_monthly
        )
        SELECT
            platform_code,
            COALESCE(shop_id, '') AS shop_id,
            SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'采购金额', raw_data->>'采购价', ''), ',', ''), ' ', ''), CHR(8212), '-'), CHR(8211), '-'), '[^0-9.-]', '', 'g'), '')::numeric, 0)) AS purchase_amount,
            SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'仓库操作费', ''), ',', ''), ' ', ''), CHR(8212), '-'), CHR(8211), '-'), '[^0-9.-]', '', 'g'), '')::numeric, 0)) AS warehouse_operation_fee,
            (
                SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'运费', ''), ',', ''), ' ', ''), CHR(8212), '-'), CHR(8211), '-'), '[^0-9.-]', '', 'g'), '')::numeric, 0))
                + SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'推广费', ''), ',', ''), ' ', ''), CHR(8212), '-'), CHR(8211), '-'), '[^0-9.-]', '', 'g'), '')::numeric, 0))
                + SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'平台佣金', ''), ',', ''), ' ', ''), CHR(8212), '-'), CHR(8211), '-'), '[^0-9.-]', '', 'g'), '')::numeric, 0))
                + SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'平台扣费', ''), ',', ''), ' ', ''), CHR(8212), '-'), CHR(8211), '-'), '[^0-9.-]', '', 'g'), '')::numeric, 0))
                + SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'代金券', ''), ',', ''), ' ', ''), CHR(8212), '-'), CHR(8211), '-'), '[^0-9.-]', '', 'g'), '')::numeric, 0))
                + SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'服务费', ''), ',', ''), ' ', ''), CHR(8212), '-'), CHR(8211), '-'), '[^0-9.-]', '', 'g'), '')::numeric, 0))
            ) AS platform_fees,
            SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'实付金额', raw_data->>'买家实付金额', ''), ',', ''), ' ', ''), CHR(8212), '-'), CHR(8211), '-'), '[^0-9.-]', '', 'g'), '')::numeric, 0)) AS paid_amount
        FROM u
        WHERE period_start_date >= :period_start AND period_start_date < :period_end
        GROUP BY platform_code, shop_id
        """
    )
    b_params = {"period_start": period_start, "period_end": period_end}

    try:
        b_rows = (await db.execute(b_sql, b_params)).fetchall()
    except Exception as exc:
        logger.warning(f"Annual cost aggregate by shop B-side query failed: {exc}")
        raise

    b_by_shop: dict[str, dict[str, Any]] = {}
    for row in b_rows or []:
        platform_code, shop_id = (row[0] or ""), (row[1] or "")
        key = _shop_key(platform_code, shop_id)
        purchase = _safe_float(row[2])
        warehouse = _safe_float(row[3])
        platform_fees = _safe_float(row[4]) if row[4] is not None else 0.0
        paid = _safe_float(row[5])
        total_b = purchase + warehouse + platform_fees
        b_by_shop[key] = {
            "total_cost_b": total_b,
            "purchase_amount": purchase,
            "gmv": paid,
            "cost_to_revenue_ratio": (total_b / paid) if paid and paid != 0 else None,
            "roi": ((paid - total_b) / total_b) if total_b and total_b != 0 else None,
            "gross_margin": ((paid - purchase) / paid) if paid and paid != 0 else None,
            "net_margin": ((paid - total_b) / paid) if paid and paid != 0 else None,
        }

    all_keys = set(a_by_shop) | set(b_by_shop)
    result: list[dict[str, Any]] = []
    for shop_key in sorted(all_keys):
        total_a = a_by_shop.get(shop_key, 0.0)
        b_row = b_by_shop.get(shop_key) or {}
        total_b = b_row.get("total_cost_b", 0.0)
        gmv = b_row.get("gmv", 0.0)
        total_cost = total_a + total_b
        result.append(
            {
                "shop_key": shop_key,
                "total_cost_a": total_a,
                "total_cost_b": total_b,
                "total_cost": total_cost,
                "gmv": gmv,
                "cost_to_revenue_ratio": (total_cost / gmv) if gmv and gmv != 0 else None,
                "roi": ((gmv - total_cost) / total_cost) if total_cost and total_cost != 0 else None,
                "gross_margin": ((gmv - b_row.get("purchase_amount", 0.0)) / gmv) if gmv and gmv != 0 else None,
                "net_margin": ((gmv - total_cost) / gmv) if gmv and gmv != 0 else None,
            }
        )
    return result
