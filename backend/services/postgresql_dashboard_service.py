from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text

from backend.models.database import AsyncSessionLocal


def _to_float(value: Any) -> float:
    return float(value)


def _to_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _round_or_none(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _sum_present_values(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [_to_optional_float(row.get(key)) for row in rows if row.get(key) is not None]
    if not values:
        return None
    return sum(values)


def _sort_numeric(value: Any) -> float:
    maybe_value = _to_optional_float(value)
    return maybe_value if maybe_value is not None else float("-inf")


def reduce_business_overview_kpi_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_gmv = _sum_present_values(rows, "gmv")
    total_orders_raw = _sum_present_values(rows, "order_count")
    total_visitors_raw = _sum_present_values(rows, "visitor_count")
    total_items = _sum_present_values(rows, "total_items")
    total_profit = _sum_present_values(rows, "profit")

    total_orders = int(total_orders_raw) if total_orders_raw is not None else None
    total_visitors = int(total_visitors_raw) if total_visitors_raw is not None else None

    if total_orders is None or total_visitors is None:
        conversion_rate = None
    elif total_visitors > 0:
        conversion_rate = round((total_orders * 100.0 / total_visitors), 2)
    elif total_visitors == 0 and total_orders == 0:
        conversion_rate = 0
    else:
        conversion_rate = None

    if total_orders is None or total_gmv is None:
        avg_order_value = None
    elif total_orders > 0:
        avg_order_value = round((total_gmv / total_orders), 2)
    elif total_orders == 0 and total_gmv == 0:
        avg_order_value = 0
    else:
        avg_order_value = None

    if total_orders is None or total_items is None:
        attach_rate = None
    elif total_orders > 0:
        attach_rate = round((total_items / total_orders), 2)
    elif total_orders == 0 and total_items == 0:
        attach_rate = 0
    else:
        attach_rate = None

    return {
        "gmv": _round_or_none(total_gmv, 2),
        "order_count": total_orders,
        "visitor_count": total_visitors,
        "conversion_rate": conversion_rate,
        "avg_order_value": avg_order_value,
        "attach_rate": attach_rate,
        "labor_efficiency": 0,
        "profit": _round_or_none(total_profit, 2),
    }


def reduce_b_cost_analysis_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "period_month": None,
            "platform_code": None,
            "currency_code": None,
            "gmv": None,
            "purchase_amount": None,
            "warehouse_operation_fee": None,
            "shipping_fee": None,
            "promotion_fee": None,
            "platform_commission": None,
            "platform_deduction_fee": None,
            "platform_voucher": None,
            "platform_service_fee": None,
            "platform_total_cost_itemized": None,
            "total_cost_b": None,
            "gross_margin_ref": None,
            "net_margin_ref": None,
        }

    def _sum(name: str) -> float | None:
        return _round_or_none(_sum_present_values(rows, name), 2)

    gmv = _sum("gmv")
    purchase_amount = _sum("purchase_amount")
    total_cost_b = _sum("total_cost_b")
    if gmv is None or purchase_amount is None:
        gross_margin_ref = None
    elif gmv > 0:
        gross_margin_ref = round((gmv - purchase_amount) / gmv, 4)
    elif gmv == 0 and purchase_amount == 0:
        gross_margin_ref = 0
    else:
        gross_margin_ref = None

    if gmv is None or total_cost_b is None:
        net_margin_ref = None
    elif gmv > 0:
        net_margin_ref = round((gmv - total_cost_b) / gmv, 4)
    elif gmv == 0 and total_cost_b == 0:
        net_margin_ref = 0
    else:
        net_margin_ref = None

    platform_codes = {str(row.get("platform_code")) for row in rows if row.get("platform_code") is not None}
    currency_codes = {str(row.get("currency_code")) for row in rows if row.get("currency_code") is not None}

    period_month = rows[0].get("period_month")
    platform_code = next(iter(platform_codes)) if len(platform_codes) == 1 else None
    currency_code = next(iter(currency_codes)) if len(currency_codes) == 1 else None

    return {
        "period_month": period_month,
        "platform_code": platform_code,
        "currency_code": currency_code,
        "gmv": gmv,
        "purchase_amount": purchase_amount,
        "warehouse_operation_fee": _sum("warehouse_operation_fee"),
        "shipping_fee": _sum("shipping_fee"),
        "promotion_fee": _sum("promotion_fee"),
        "platform_commission": _sum("platform_commission"),
        "platform_deduction_fee": _sum("platform_deduction_fee"),
        "platform_voucher": _sum("platform_voucher"),
        "platform_service_fee": _sum("platform_service_fee"),
        "platform_total_cost_itemized": _sum("platform_total_cost_itemized"),
        "total_cost_b": total_cost_b,
        "gross_margin_ref": gross_margin_ref,
        "net_margin_ref": net_margin_ref,
    }


def _change_pct(current: float, previous: float) -> float | None:
    if current is None or previous is None:
        return None
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
        today = _to_optional_float(current_row.get(name))
        previous = _to_optional_float(previous_row.get(name))
        average = _to_optional_float(average_row.get(name))
        metrics[name] = {
            "today": _round_or_none(today, 2),
            "yesterday": _round_or_none(previous, 2),
            "average": _round_or_none(average, 2),
            "change": _change_pct(today, previous),
        }

    target_sales_amount = _to_optional_float(current_row.get("target_sales_amount"))
    target_sales_quantity = _to_optional_float(current_row.get("target_sales_quantity"))
    if target_sales_amount is None or metrics["sales_amount"]["today"] is None:
        achievement_rate = None
    elif target_sales_amount > 0:
        achievement_rate = round(metrics["sales_amount"]["today"] * 100.0 / target_sales_amount, 2)
    elif target_sales_amount == 0 and metrics["sales_amount"]["today"] == 0:
        achievement_rate = 0
    else:
        achievement_rate = None

    return {
        "metrics": metrics,
        "target": {
            "sales_amount": _round_or_none(target_sales_amount, 2),
            "sales_quantity": _round_or_none(target_sales_quantity, 2),
            "achievement_rate": achievement_rate,
        },
    }


def aggregate_comparison_source_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def _sum(name: str) -> float | None:
        value = _sum_present_values(rows, name)
        return _round_or_none(value, 2)

    sales_amount = _sum("sales_amount")
    sales_quantity = _sum("sales_quantity")
    traffic = _sum("traffic")
    profit = _sum("profit")
    target_sales_amount = _sum("target_sales_amount")
    target_sales_quantity = _sum("target_sales_quantity")

    if traffic is None or sales_quantity is None:
        conversion_rate = None
    elif traffic > 0:
        conversion_rate = round((sales_quantity * 100.0 / traffic), 2)
    elif traffic == 0 and sales_quantity == 0:
        conversion_rate = 0
    else:
        conversion_rate = None

    if sales_amount is None or sales_quantity is None:
        avg_order_value = None
    elif sales_quantity > 0:
        avg_order_value = round((sales_amount / sales_quantity), 2)
    elif sales_quantity == 0 and sales_amount == 0:
        avg_order_value = 0
    else:
        avg_order_value = None

    attach_rate = None

    return {
        "sales_amount": sales_amount,
        "sales_quantity": sales_quantity,
        "traffic": traffic,
        "conversion_rate": conversion_rate,
        "avg_order_value": avg_order_value,
        "attach_rate": attach_rate,
        "profit": profit,
        "target_sales_amount": target_sales_amount,
        "target_sales_quantity": target_sales_quantity,
    }


def rank_inventory_backlog_rows(
    rows: list[dict[str, Any]],
    min_days: int = 30,
) -> list[dict[str, Any]]:
    def _classify_risk(row: dict[str, Any]) -> str:
        turnover_days = _to_float(row.get("estimated_turnover_days"))
        stagnant_count = int(_to_float(row.get("stagnant_snapshot_count")))
        if turnover_days >= 60 or stagnant_count >= 3:
            return "high"
        if turnover_days >= 30 or stagnant_count >= 2:
            return "medium"
        return "low"

    def _priority_score(row: dict[str, Any]) -> float:
        if row.get("clearance_priority_score") is not None:
            return _to_float(row.get("clearance_priority_score"))
        return round(
            _to_float(row.get("inventory_value")) * 0.5
            + _to_float(row.get("estimated_stagnant_days")) * 10
            + _to_float(row.get("estimated_turnover_days")) * 2,
            2,
        )

    filtered = [
        dict(row)
        for row in rows
        if (_to_optional_float(row.get("estimated_turnover_days")) or float("-inf")) >= min_days
    ]
    for row in filtered:
        row["risk_level"] = row.get("risk_level") or _classify_risk(row)
        row["clearance_priority_score"] = _priority_score(row)
    filtered.sort(
        key=lambda row: (
            _sort_numeric(row.get("clearance_priority_score")),
            _sort_numeric(row.get("inventory_value")),
            _sort_numeric(row.get("estimated_turnover_days")),
        ),
        reverse=True,
    )
    for index, row in enumerate(filtered, start=1):
        row["rank"] = index
    return filtered


def rank_shop_racing_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = [dict(row) for row in rows]
    ordered.sort(key=lambda row: (_sort_numeric(row.get("gmv")), _sort_numeric(row.get("order_count"))), reverse=True)
    for index, row in enumerate(ordered, start=1):
        row["rank"] = index
    return ordered


def rank_traffic_rows(rows: list[dict[str, Any]], dimension: str = "visitor") -> list[dict[str, Any]]:
    ordered = [dict(row) for row in rows]
    if dimension == "pv":
        ordered.sort(key=lambda row: _sort_numeric(row.get("page_views")), reverse=True)
    else:
        ordered.sort(key=lambda row: _sort_numeric(row.get("visitor_count")), reverse=True)
    for index, row in enumerate(ordered, start=1):
        row["rank"] = index
    return ordered


def reduce_annual_summary_kpi_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_gmv = _sum_present_values(rows, "gmv")
    total_cost = _sum_present_values(rows, "total_cost")
    total_profit = _sum_present_values(rows, "profit")

    if total_gmv is None or total_profit is None:
        gross_margin = None
    elif total_gmv > 0:
        gross_margin = round(total_profit * 100.0 / total_gmv, 2)
    elif total_gmv == 0 and total_profit == 0:
        gross_margin = 0
    else:
        gross_margin = None

    if total_gmv is None or total_profit is None or total_cost is None:
        net_margin = None
    elif total_gmv > 0:
        net_margin = round((total_profit - total_cost) * 100.0 / total_gmv, 2)
    elif total_gmv == 0 and total_profit == 0 and total_cost == 0:
        net_margin = 0
    else:
        net_margin = None

    if total_cost is None or total_profit is None:
        roi = None
    elif total_cost > 0:
        roi = round((total_profit - total_cost) / total_cost, 2)
    elif total_cost == 0 and total_profit == 0:
        roi = 0
    else:
        roi = None
    return {
        "gmv": _round_or_none(total_gmv, 2),
        "total_cost": _round_or_none(total_cost, 2),
        "profit": _round_or_none(total_profit, 2),
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

    async def _load_target_summary(
        self,
        granularity: str,
        period_start: date_cls,
        period_end: date_cls,
        platform: str | None = None,
    ) -> dict[str, float]:
        async with AsyncSessionLocal() as session:
            if granularity == "monthly":
                if platform:
                    try:
                        result = await session.execute(
                            text(
                                """
                                SELECT
                                    SUM(tb.target_amount) AS target_amount,
                                    SUM(tb.target_quantity) AS target_quantity
                                FROM a_class.target_breakdown tb
                                INNER JOIN a_class.sales_targets st ON st.id = tb.target_id
                                WHERE st.status = 'active'
                                  AND st.period_start <= :period_start
                                  AND st.period_end >= :period_end
                                  AND tb.breakdown_type = 'shop'
                                  AND LOWER(tb.platform_code) = LOWER(:platform)
                                """
                            ),
                            {
                                "period_start": period_start,
                                "period_end": period_end,
                                "platform": platform,
                            },
                        )
                    except Exception:
                        await session.rollback()
                        result = await session.execute(
                            text(
                                """
                                SELECT
                                    SUM(target_sales_amount) AS target_amount,
                                    SUM(target_quantity) AS target_quantity
                                FROM a_class.sales_targets_a
                                WHERE year_month = :year_month
                                """
                            ),
                            {"year_month": period_start.strftime("%Y-%m")},
                        )
                else:
                    try:
                        result = await session.execute(
                            text(
                                """
                                SELECT
                                    SUM(target_amount) AS target_amount,
                                    SUM(target_quantity) AS target_quantity
                                FROM a_class.sales_targets
                                WHERE status = 'active'
                                  AND period_start <= :period_start
                                  AND period_end >= :period_end
                                """
                            ),
                            {"period_start": period_start, "period_end": period_end},
                        )
                    except Exception:
                        await session.rollback()
                        try:
                            result = await session.execute(
                                text(
                                    """
                                    SELECT
                                        SUM(target_sales_amount) AS target_amount,
                                        SUM(target_quantity) AS target_quantity
                                    FROM a_class.sales_targets_a
                                    WHERE year_month = :year_month
                                    """
                                ),
                                {"year_month": period_start.strftime("%Y-%m")},
                            )
                        except Exception:
                            await session.rollback()
                            try:
                                result = await session.execute(
                                    text(
                                        """
                                        SELECT
                                            COALESCE(SUM("目标销售额"), 0) AS target_amount,
                                            COALESCE(SUM("目标订单数"), 0) AS target_quantity
                                        FROM a_class.sales_targets_a
                                        WHERE "年月" = :year_month
                                        """
                                    ),
                                    {"year_month": period_start.strftime("%Y-%m")},
                                )
                            except Exception:
                                await session.rollback()
                                result = await session.execute(
                                    text(
                                        """
                                        SELECT
                                            COALESCE(SUM("目标销售额"), 0) AS target_amount,
                                            COALESCE(SUM("目标单量"), 0) AS target_quantity
                                        FROM a_class.sales_targets_a
                                        WHERE "年月" = :year_month
                                        """
                                    ),
                                    {"year_month": period_start.strftime("%Y-%m")},
                                )
            else:
                query = """
                    SELECT
                        SUM(tb.target_amount) AS target_amount,
                        SUM(tb.target_quantity) AS target_quantity
                    FROM a_class.target_breakdown tb
                    INNER JOIN a_class.sales_targets st ON st.id = tb.target_id
                    WHERE st.status = 'active'
                      AND tb.breakdown_type IN ('time', 'shop_time')
                      AND tb.period_start >= :period_start
                      AND tb.period_end <= :period_end
                """
                params = {
                    "period_start": period_start,
                    "period_end": period_end,
                }
                if platform:
                    query += " AND LOWER(COALESCE(tb.platform_code, '')) = LOWER(:platform)"
                    params["platform"] = platform

                result = await session.execute(text(query), params)

            row = result.fetchone()
            return {
                "target_amount": _to_optional_float(row[0]) if row else None,
                "target_quantity": _to_optional_float(row[1]) if row else None,
            }

    async def _load_operating_expenses_summary(
        self,
        period_month: date_cls,
    ) -> float | None:
        year_month = period_month.strftime("%Y-%m")
        async with AsyncSessionLocal() as session:
            try:
                result = await session.execute(
                    text(
                        """
                        SELECT SUM(rent + salary + utilities + other_costs)
                        FROM a_class.operating_costs
                        WHERE year_month = :year_month
                        """
                    ),
                    {"year_month": year_month},
                )
            except Exception:
                await session.rollback()
                try:
                    result = await session.execute(
                        text(
                            """
                            SELECT COALESCE(SUM("租金" + "工资" + "水电费" + "其他成本"), 0)
                            FROM a_class.operating_costs
                            WHERE "年月" = :year_month
                            """
                        ),
                        {"year_month": year_month},
                    )
                except Exception:
                    await session.rollback()
                    return None
            value = result.scalar_one_or_none()
            return _to_optional_float(value)

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

        current_comparison = aggregate_comparison_source_rows(current_rows)
        previous_comparison = aggregate_comparison_source_rows(previous_rows)
        average_comparison = aggregate_comparison_source_rows(average_rows)

        reduced = reduce_business_overview_comparison_rows(
            current_row=current_comparison,
            previous_row=previous_comparison,
            average_row=average_comparison,
        )
        current_end = (
            current_start
            if granularity == "daily"
            else current_start + timedelta(days=6)
            if granularity == "weekly"
            else (current_start + timedelta(days=31)).replace(day=1) - timedelta(days=1)
        )
        target_summary = await self._load_target_summary(
            granularity=granularity,
            period_start=current_start,
            period_end=current_end,
            platform=platform,
        )
        reduced["target"]["sales_amount"] = round(target_summary["target_amount"], 2)
        reduced["target"]["sales_quantity"] = round(target_summary["target_quantity"], 2)
        reduced["target"]["achievement_rate"] = (
            round(reduced["metrics"]["sales_amount"]["today"] * 100.0 / target_summary["target_amount"], 2)
            if target_summary["target_amount"]
            else 0
        )
        return reduced

    async def get_business_overview_inventory_backlog(
        self,
        min_days: int = 30,
    ) -> dict[str, Any]:
        rows = await self._fetch_rows(
            "SELECT * FROM api.business_overview_inventory_backlog_module",
            {},
        )
        summary_rows = await self._fetch_rows(
            "SELECT * FROM api.inventory_backlog_summary_module",
            {},
        )
        summary = summary_rows[0] if summary_rows else {}
        total_value = _to_float(summary.get("total_value"))
        backlog_30d_value = _to_float(summary.get("backlog_30d_value"))
        backlog_60d_value = _to_float(summary.get("backlog_60d_value"))
        backlog_90d_value = _to_float(summary.get("backlog_90d_value"))
        return {
            "summary": {
                "total_value": round(total_value, 2),
                "backlog_30d_value": round(backlog_30d_value, 2),
                "backlog_60d_value": round(backlog_60d_value, 2),
                "backlog_90d_value": round(backlog_90d_value, 2),
                "backlog_30d_ratio": round(backlog_30d_value * 100.0 / total_value, 2) if total_value else 0,
                "backlog_60d_ratio": round(backlog_60d_value * 100.0 / total_value, 2) if total_value else 0,
                "backlog_90d_ratio": round(backlog_90d_value * 100.0 / total_value, 2) if total_value else 0,
                "total_quantity": int(_to_float(summary.get("total_quantity"))),
                "high_risk_sku_count": int(_to_float(summary.get("high_risk_sku_count"))),
                "medium_risk_sku_count": int(_to_float(summary.get("medium_risk_sku_count"))),
                "low_risk_sku_count": int(_to_float(summary.get("low_risk_sku_count"))),
            },
            "top_products": rank_inventory_backlog_rows(rows, min_days=min_days),
        }

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

    async def get_business_overview_shop_racing(
        self,
        granularity: str,
        target_date: str,
        group_by: str = "shop",
        platform: str | None = None,
    ) -> list[dict[str, Any]]:
        period_key = _normalize_period_start(target_date)
        query = """
            SELECT granularity, period_key, platform_code, shop_id, gmv, order_count, avg_order_value, attach_rate, profit, target_amount, achievement_rate
            FROM api.business_overview_shop_racing_module
            WHERE granularity = :granularity
              AND period_key = :period_key
            """
        params = {"granularity": granularity, "period_key": period_key}
        if platform:
            query += " AND platform_code = :platform_code"
            params["platform_code"] = platform
        rows = await self._fetch_rows(query, params)

        if group_by in ("platform", "account"):
            grouped: dict[str, dict[str, Any]] = {}
            for row in rows:
                key = row["platform_code"]
                grouped.setdefault(
                    key,
                    {
                        "name": key,
                        "platform_code": key,
                        "shop_id": "ALL",
                        "gmv": 0.0,
                        "order_count": 0.0,
                        "avg_order_value": 0.0,
                        "attach_rate": 0.0,
                        "target_amount": 0.0,
                        "achievement_rate": 0.0,
                    },
                )
                grouped[key]["gmv"] += _to_optional_float(row.get("gmv")) or 0.0
                grouped[key]["order_count"] += _to_optional_float(row.get("order_count")) or 0.0
                grouped[key]["target_amount"] += _to_optional_float(row.get("target_amount")) or 0.0
            for value in grouped.values():
                if value["order_count"]:
                    value["avg_order_value"] = round(value["gmv"] / value["order_count"], 2)
                if value["target_amount"]:
                    value["achievement_rate"] = round(value["gmv"] * 100.0 / value["target_amount"], 2)
            return rank_shop_racing_rows(list(grouped.values()))

        normalized_rows = [
            {
                "name": row.get("shop_id") or "unknown",
                "platform_code": row.get("platform_code"),
                "shop_id": row.get("shop_id") or "unknown",
                "gmv": _to_optional_float(row.get("gmv")),
                "order_count": _to_optional_float(row.get("order_count")),
                "avg_order_value": _to_optional_float(row.get("avg_order_value")),
                "attach_rate": _to_optional_float(row.get("attach_rate")),
                "profit": _to_optional_float(row.get("profit")),
                "target_amount": _to_optional_float(row.get("target_amount")),
                "achievement_rate": _to_optional_float(row.get("achievement_rate")),
            }
            for row in rows
        ]
        return rank_shop_racing_rows(normalized_rows)

    async def get_business_overview_traffic_ranking(
        self,
        granularity: str,
        target_date: str,
        dimension: str = "visitor",
        platform: str | None = None,
    ) -> list[dict[str, Any]]:
        period_key = _normalize_period_start(target_date)
        query = """
            SELECT granularity, period_key, platform_code, shop_id, visitor_count, page_views, conversion_rate
            FROM api.business_overview_traffic_ranking_module
            WHERE granularity = :granularity
              AND period_key = :period_key
            """
        params = {"granularity": granularity, "period_key": period_key}
        if platform:
            query += " AND platform_code = :platform_code"
            params["platform_code"] = platform
        rows = await self._fetch_rows(query, params)
        normalized_rows = [
            {
                "name": row.get("shop_id") or row.get("platform_code") or "unknown",
                "platform_code": row.get("platform_code"),
                "shop_id": row.get("shop_id") or "unknown",
                "visitor_count": _to_optional_float(row.get("visitor_count")),
                "page_views": _to_optional_float(row.get("page_views")),
                "conversion_rate": _to_optional_float(row.get("conversion_rate")),
            }
            for row in rows
        ]
        return rank_traffic_rows(normalized_rows, dimension=dimension)

    async def get_business_overview_operational_metrics(
        self,
        month: str,
        platform: str | None = None,
    ) -> dict[str, Any]:
        period_month = _normalize_period_start(month)
        query = """
            SELECT *
            FROM api.business_overview_operational_metrics_module
            WHERE period_month = :period_month
        """
        params: dict[str, Any] = {"period_month": period_month}
        if platform:
            query += " AND platform_code = :platform_code"
            params["platform_code"] = platform

        rows = await self._fetch_rows(query, params)
        total = {
            "monthly_target": None,
            "monthly_total_achieved": None,
            "today_sales": None,
            "monthly_achievement_rate": None,
            "time_gap": None,
            "estimated_gross_profit": None,
            "estimated_expenses": None,
            "operating_result": None,
            "monthly_order_count": None,
            "today_order_count": None,
        }
        for row in rows:
            for key in total.keys():
                value = _to_optional_float(row.get(key))
                if value is None:
                    continue
                total[key] = value if total[key] is None else total[key] + value

        month_end = (period_month + timedelta(days=31)).replace(day=1) - timedelta(days=1)
        target_summary = await self._load_target_summary(
            granularity="monthly",
            period_start=period_month,
            period_end=month_end,
            platform=platform,
        )
        if target_summary["target_amount"] is not None:
            total["monthly_target"] = round(target_summary["target_amount"], 2)
        loaded_expenses = await self._load_operating_expenses_summary(period_month)
        if loaded_expenses is not None and total["estimated_expenses"] in (None, 0, 0.0):
            total["estimated_expenses"] = round(loaded_expenses, 2)
        if total["estimated_gross_profit"] is not None and total["estimated_expenses"] is not None:
            total["operating_result"] = round(total["estimated_gross_profit"] - total["estimated_expenses"], 2)

        if total["monthly_total_achieved"] is not None and total["monthly_target"] is not None:
            if total["monthly_target"] > 0:
                total["monthly_achievement_rate"] = round(
                    total["monthly_total_achieved"] * 100.0 / total["monthly_target"], 2
                )
            elif total["monthly_target"] == 0 and total["monthly_total_achieved"] == 0:
                total["monthly_achievement_rate"] = 0
            else:
                total["monthly_achievement_rate"] = None
        else:
            total["monthly_achievement_rate"] = _round_or_none(total["monthly_achievement_rate"], 2)
        total["time_gap"] = _round_or_none(total["time_gap"], 2)
        operating_result_missing = total["operating_result"] is None
        if operating_result_missing:
            total["operating_result"] = float("-inf")
        total["operating_result_text"] = "盈利" if total["operating_result"] > 0 else "亏损"
        total["monthly_order_count"] = int(total["monthly_order_count"]) if total["monthly_order_count"] is not None else None
        total["today_order_count"] = int(total["today_order_count"]) if total["today_order_count"] is not None else None
        if operating_result_missing:
            total["operating_result"] = None
            total["operating_result_text"] = None
        return total

    async def get_b_cost_analysis_overview(
        self,
        period_month: str,
        platform: str | None = None,
        shop_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_period = _normalize_period_start(period_month)
        period_start = date_cls(normalized_period.year, normalized_period.month, 1)
        if shop_id:
            # shop_id 过滤场景优先回退到 shop_month 明细层聚合
            rows = await self.get_b_cost_analysis_shop_month(
                period_month=period_month,
                platform=platform,
                shop_id=shop_id,
            )
            return reduce_b_cost_analysis_rows(rows)

        query = """
            SELECT *
            FROM api.b_cost_analysis_overview_module
            WHERE period_month = :period_month
        """
        params: dict[str, Any] = {"period_month": period_start}
        if platform:
            query += " AND platform_code = :platform_code"
            params["platform_code"] = platform
        rows = await self._fetch_rows(query, params)
        return reduce_b_cost_analysis_rows(rows)

    async def get_b_cost_analysis_shop_month(
        self,
        period_month: str,
        platform: str | None = None,
        shop_id: str | None = None,
    ) -> list[dict[str, Any]]:
        normalized_period = _normalize_period_start(period_month)
        period_start = date_cls(normalized_period.year, normalized_period.month, 1)
        query = """
            SELECT *
            FROM api.b_cost_analysis_shop_month_module
            WHERE period_month = :period_month
        """
        params: dict[str, Any] = {"period_month": period_start}
        if platform:
            query += " AND platform_code = :platform_code"
            params["platform_code"] = platform
        if shop_id:
            query += " AND shop_id = :shop_id"
            params["shop_id"] = shop_id
        query += " ORDER BY platform_code, shop_id"
        return await self._fetch_rows(query, params)

    async def get_b_cost_analysis_order_detail(
        self,
        period_month: str,
        platform: str | None = None,
        shop_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        if page < 1:
            raise ValueError("page must be greater than 0")
        if page_size < 1:
            raise ValueError("page_size must be greater than 0")

        normalized_period = _normalize_period_start(period_month)
        period_start = date_cls(normalized_period.year, normalized_period.month, 1)
        where_sql = " WHERE period_month = :period_month"
        params: dict[str, Any] = {"period_month": period_start}
        if platform:
            where_sql += " AND platform_code = :platform_code"
            params["platform_code"] = platform
        if shop_id:
            where_sql += " AND shop_id = :shop_id"
            params["shop_id"] = shop_id

        count_rows = await self._fetch_rows(
            f"SELECT COUNT(1) AS total FROM api.b_cost_analysis_order_detail_module{where_sql}",
            params,
        )
        total = int(count_rows[0]["total"]) if count_rows else 0

        offset = (page - 1) * page_size
        detail_params = {**params, "limit": page_size, "offset": offset}
        items = await self._fetch_rows(
            f"""
            SELECT *
            FROM api.b_cost_analysis_order_detail_module
            {where_sql}
            ORDER BY order_time DESC NULLS LAST, order_id DESC
            LIMIT :limit OFFSET :offset
            """,
            detail_params,
        )
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
        }

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

    async def get_annual_summary_target_completion(
        self,
        db,
        granularity: str,
        period: str,
    ) -> dict[str, Any]:
        if granularity not in ("monthly", "yearly"):
            raise ValueError("granularity must be monthly or yearly")

        if len(period) == 4:
            year_month_filter = "year_month LIKE :period_prefix"
            db_params: dict[str, Any] = {"period_prefix": f"{period}-%"}
            year_month_filter_cn = '"年月" LIKE :period_prefix'
        else:
            year_month_filter = "year_month = :period"
            db_params = {"period": period}
            year_month_filter_cn = '"年月" = :period'

        try:
            result = await db.execute(
                text(
                    f"""
                    SELECT SUM(target_sales_amount) AS target_gmv,
                           SUM(target_quantity) AS target_orders
                    FROM a_class.sales_targets_a
                    WHERE {year_month_filter}
                    """
                ),
                db_params,
            )
        except Exception:
            await db.rollback()
            try:
                result = await db.execute(
                    text(
                        f"""
                        SELECT COALESCE(SUM("目标销售额"), 0) AS target_gmv,
                               COALESCE(SUM("目标订单数"), 0) AS target_orders
                        FROM a_class.sales_targets_a
                        WHERE {year_month_filter_cn}
                        """
                    ),
                    db_params,
                )
            except Exception:
                await db.rollback()
                result = await db.execute(
                    text(
                        f"""
                        SELECT COALESCE(SUM("目标销售额"), 0) AS target_gmv,
                               COALESCE(SUM("目标单量"), 0) AS target_orders
                        FROM a_class.sales_targets_a
                        WHERE {year_month_filter_cn}
                        """
                    ),
                    db_params,
                )
        row = result.fetchone()
        target_gmv = float(row[0]) if row and row[0] is not None else None
        target_orders = int(row[1]) if row and row[1] is not None else None

        achieved = await self.get_annual_summary_kpi(granularity=granularity, period=period)
        achieved_gmv = achieved.get("gmv")
        if target_gmv is None or achieved_gmv is None:
            achievement_rate_gmv = None
        elif target_gmv > 0:
            achievement_rate_gmv = round(achieved_gmv / target_gmv * 100, 2)
        elif target_gmv == 0 and achieved_gmv == 0:
            achievement_rate_gmv = 0
        else:
            achievement_rate_gmv = None

        return {
            "target_gmv": target_gmv,
            "achieved_gmv": achieved_gmv,
            "achievement_rate_gmv": achievement_rate_gmv,
            "target_orders": target_orders,
            "target_profit": None,
            "achieved_profit": achieved.get("profit"),
            "achievement_rate_profit": None,
        }


_service: PostgresqlDashboardService | None = None


def get_postgresql_dashboard_service() -> PostgresqlDashboardService:
    global _service
    if _service is None:
        _service = PostgresqlDashboardService()
    return _service
