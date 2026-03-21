from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text

from backend.models.database import AsyncSessionLocal


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def reduce_business_overview_kpi_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_gmv = sum(_to_float(row.get("gmv")) for row in rows)
    total_orders = int(sum(_to_float(row.get("order_count")) for row in rows))
    total_visitors = int(sum(_to_float(row.get("visitor_count")) for row in rows))
    total_items = sum(_to_float(row.get("total_items")) for row in rows)
    total_profit = sum(_to_float(row.get("profit")) for row in rows)

    conversion_rate = round((total_orders * 100.0 / total_visitors), 2) if total_visitors else 0
    avg_order_value = round((total_gmv / total_orders), 2) if total_orders else 0
    attach_rate = round((total_items / total_orders), 2) if total_orders else 0

    return {
        "gmv": round(total_gmv, 2),
        "order_count": total_orders,
        "visitor_count": total_visitors,
        "conversion_rate": conversion_rate,
        "avg_order_value": avg_order_value,
        "attach_rate": attach_rate,
        "labor_efficiency": 0,
        "profit": round(total_profit, 2),
    }


def _change_pct(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return round((current - previous) * 100.0 / previous, 2)


def reduce_business_overview_comparison_rows(
    current_row: dict[str, Any],
    previous_row: dict[str, Any],
    average_row: dict[str, Any],
) -> dict[str, Any]:
    metric_names = (
        "sales_amount",
        "sales_quantity",
        "traffic",
        "conversion_rate",
        "avg_order_value",
        "attach_rate",
        "profit",
    )
    metrics: dict[str, dict[str, Any]] = {}
    for name in metric_names:
        today = _to_float(current_row.get(name))
        previous = _to_float(previous_row.get(name))
        average = _to_float(average_row.get(name))
        metrics[name] = {
            "today": round(today, 2),
            "yesterday": round(previous, 2),
            "average": round(average, 2),
            "change": _change_pct(today, previous),
        }

    target_sales_amount = _to_float(current_row.get("target_sales_amount"))
    target_sales_quantity = _to_float(current_row.get("target_sales_quantity"))
    achievement_rate = (
        round(metrics["sales_amount"]["today"] * 100.0 / target_sales_amount, 2)
        if target_sales_amount
        else 0
    )

    return {
        "metrics": metrics,
        "target": {
            "sales_amount": round(target_sales_amount, 2),
            "sales_quantity": round(target_sales_quantity, 2),
            "achievement_rate": achievement_rate,
        },
    }


def rank_inventory_backlog_rows(
    rows: list[dict[str, Any]],
    min_days: int = 30,
) -> list[dict[str, Any]]:
    filtered = [
        dict(row)
        for row in rows
        if _to_float(row.get("estimated_turnover_days")) >= min_days
    ]
    filtered.sort(
        key=lambda row: (
            _to_float(row.get("inventory_value")),
            _to_float(row.get("estimated_turnover_days")),
        ),
        reverse=True,
    )
    for index, row in enumerate(filtered, start=1):
        row["rank"] = index
    return filtered


def reduce_annual_summary_kpi_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_gmv = sum(_to_float(row.get("gmv")) for row in rows)
    total_cost = sum(_to_float(row.get("total_cost")) for row in rows)
    total_profit = sum(_to_float(row.get("profit")) for row in rows)
    gross_margin = round(total_profit * 100.0 / total_gmv, 2) if total_gmv else 0
    net_margin = round((total_profit - total_cost) * 100.0 / total_gmv, 2) if total_gmv else 0
    roi = round((total_profit - total_cost) / total_cost, 2) if total_cost else 0
    return {
        "gmv": round(total_gmv, 2),
        "total_cost": round(total_cost, 2),
        "profit": round(total_profit, 2),
        "gross_margin": gross_margin,
        "net_margin": net_margin,
        "roi": roi,
    }


def _normalize_period_start(value: str) -> date_cls:
    value = value.strip()
    if len(value) == 7:
        return datetime.strptime(f"{value}-01", "%Y-%m-%d").date()
    if len(value) == 10:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    if len(value) == 4:
        return datetime.strptime(f"{value}-01-01", "%Y-%m-%d").date()
    raise ValueError("Unsupported period/date format")


class PostgresqlDashboardService:
    async def _fetch_rows(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text(query), params)
            return [dict(row) for row in result.mappings().all()]

    async def get_business_overview_kpi(
        self,
        month: str,
        platform: str | None = None,
    ) -> dict[str, Any]:
        period_month = _normalize_period_start(month)
        query = """
            SELECT
                period_month,
                platform_code,
                gmv,
                order_count,
                visitor_count,
                conversion_rate,
                avg_order_value,
                attach_rate,
                total_items,
                profit
            FROM api.business_overview_kpi_module
            WHERE period_month = :period_month
        """
        params: dict[str, Any] = {"period_month": period_month}
        if platform:
            query += " AND platform_code = :platform_code"
            params["platform_code"] = platform

        rows = await self._fetch_rows(query, params)
        return reduce_business_overview_kpi_rows(rows)

    async def get_business_overview_comparison(
        self,
        granularity: str,
        target_date: str,
        platform: str | None = None,
    ) -> dict[str, Any]:
        normalized = _normalize_period_start(target_date)
        if granularity == "daily":
            current_start = normalized
            previous_start = normalized - timedelta(days=1)
            average_start = normalized.replace(day=1)
        elif granularity == "weekly":
            current_start = normalized - timedelta(days=normalized.weekday())
            previous_start = current_start - timedelta(days=7)
            average_start = current_start
        elif granularity == "monthly":
            current_start = normalized.replace(day=1)
            previous_start = (current_start - timedelta(days=1)).replace(day=1)
            average_start = current_start
        else:
            raise ValueError("granularity must be daily, weekly or monthly")

        query = """
            SELECT *
            FROM api.business_overview_comparison_module
            WHERE granularity = :granularity
              AND period_key = :period_key
        """
        if platform:
            query += " AND platform_code = :platform_code"

        current_rows = await self._fetch_rows(
            query,
            {
                "granularity": granularity,
                "period_key": current_start,
                "platform_code": platform,
            },
        )
        previous_rows = await self._fetch_rows(
            query,
            {
                "granularity": granularity,
                "period_key": previous_start,
                "platform_code": platform,
            },
        )
        average_query = """
            SELECT *
            FROM api.business_overview_comparison_module
            WHERE granularity = :granularity
              AND period_key >= :period_start
              AND period_key <= :period_end
        """
        if platform:
            average_query += " AND platform_code = :platform_code"

        average_rows = await self._fetch_rows(
            average_query,
            {
                "granularity": granularity,
                "period_start": average_start,
                "period_end": current_start,
                "platform_code": platform,
            },
        )

        current = reduce_business_overview_kpi_rows(current_rows)
        previous = reduce_business_overview_kpi_rows(previous_rows)
        average = reduce_business_overview_kpi_rows(average_rows)

        current_comparison = {
            "sales_amount": current["gmv"],
            "sales_quantity": current["order_count"],
            "traffic": current["visitor_count"],
            "conversion_rate": current["conversion_rate"],
            "avg_order_value": current["avg_order_value"],
            "attach_rate": current["attach_rate"],
            "profit": current["profit"],
            "target_sales_amount": 0,
            "target_sales_quantity": 0,
        }
        previous_comparison = {
            "sales_amount": previous["gmv"],
            "sales_quantity": previous["order_count"],
            "traffic": previous["visitor_count"],
            "conversion_rate": previous["conversion_rate"],
            "avg_order_value": previous["avg_order_value"],
            "attach_rate": previous["attach_rate"],
            "profit": previous["profit"],
        }
        average_comparison = {
            "sales_amount": average["gmv"],
            "sales_quantity": average["order_count"],
            "traffic": average["visitor_count"],
            "conversion_rate": average["conversion_rate"],
            "avg_order_value": average["avg_order_value"],
            "attach_rate": average["attach_rate"],
            "profit": average["profit"],
        }

        return reduce_business_overview_comparison_rows(
            current_row=current_comparison,
            previous_row=previous_comparison,
            average_row=average_comparison,
        )

    async def get_business_overview_inventory_backlog(
        self,
        min_days: int = 30,
    ) -> list[dict[str, Any]]:
        rows = await self._fetch_rows(
            "SELECT * FROM api.business_overview_inventory_backlog_module",
            {},
        )
        return rank_inventory_backlog_rows(rows, min_days=min_days)

    async def get_clearance_ranking(
        self,
        min_days: int = 30,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        rows = await self._fetch_rows(
            "SELECT * FROM api.clearance_ranking_module",
            {},
        )
        ranked = rank_inventory_backlog_rows(rows, min_days=min_days)
        return ranked[:limit]

    async def get_annual_summary_kpi(
        self,
        granularity: str,
        period: str,
    ) -> dict[str, Any]:
        if granularity not in ("monthly", "yearly"):
            raise ValueError("granularity must be monthly or yearly")
        query = "SELECT * FROM api.annual_summary_kpi_module WHERE period_month >= :period_start AND period_month <= :period_end"
        period_start = _normalize_period_start(period)
        if granularity == "monthly":
            period_end = period_start
        else:
            period_end = date_cls(period_start.year, 12, 1)
        rows = await self._fetch_rows(query, {"period_start": period_start, "period_end": period_end})
        return reduce_annual_summary_kpi_rows(rows)

    async def get_annual_summary_trend(
        self,
        granularity: str,
        period: str,
    ) -> list[dict[str, Any]]:
        if granularity not in ("monthly", "yearly"):
            raise ValueError("granularity must be monthly or yearly")
        period_start = _normalize_period_start(period)
        period_end = period_start if granularity == "monthly" else date_cls(period_start.year, 12, 1)
        return await self._fetch_rows(
            """
            SELECT *
            FROM api.annual_summary_trend_module
            WHERE period_month >= :period_start
              AND period_month <= :period_end
            ORDER BY period_month
            """,
            {"period_start": period_start, "period_end": period_end},
        )

    async def get_annual_summary_platform_share(
        self,
        granularity: str,
        period: str,
    ) -> list[dict[str, Any]]:
        if granularity not in ("monthly", "yearly"):
            raise ValueError("granularity must be monthly or yearly")
        period_start = _normalize_period_start(period)
        period_end = period_start if granularity == "monthly" else date_cls(period_start.year, 12, 1)
        return await self._fetch_rows(
            """
            SELECT *
            FROM api.annual_summary_platform_share_module
            WHERE period_month >= :period_start
              AND period_month <= :period_end
            ORDER BY period_month, platform_code
            """,
            {"period_start": period_start, "period_end": period_end},
        )

    async def get_annual_summary_by_shop(
        self,
        granularity: str,
        period: str,
    ) -> list[dict[str, Any]]:
        if granularity not in ("monthly", "yearly"):
            raise ValueError("granularity must be monthly or yearly")
        period_start = _normalize_period_start(period)
        period_end = period_start if granularity == "monthly" else date_cls(period_start.year, 12, 1)
        return await self._fetch_rows(
            """
            SELECT *
            FROM api.annual_summary_by_shop_module
            WHERE period_month >= :period_start
              AND period_month <= :period_end
            ORDER BY period_month, platform_code, shop_id
            """,
            {"period_start": period_start, "period_end": period_end},
        )


_service: PostgresqlDashboardService | None = None


def get_postgresql_dashboard_service() -> PostgresqlDashboardService:
    global _service
    if _service is None:
        _service = PostgresqlDashboardService()
    return _service
