from __future__ import annotations

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


class PostgresqlDashboardService:
    async def get_business_overview_kpi(
        self,
        month: str,
        platform: str | None = None,
    ) -> dict[str, Any]:
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
        params: dict[str, Any] = {"period_month": month}
        if platform:
            query += " AND platform_code = :platform_code"
            params["platform_code"] = platform

        async with AsyncSessionLocal() as session:
            result = await session.execute(text(query), params)
            rows = [dict(row) for row in result.mappings().all()]

        return reduce_business_overview_kpi_rows(rows)


_service: PostgresqlDashboardService | None = None


def get_postgresql_dashboard_service() -> PostgresqlDashboardService:
    global _service
    if _service is None:
        _service = PostgresqlDashboardService()
    return _service
