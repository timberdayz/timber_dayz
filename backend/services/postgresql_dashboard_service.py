from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

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


def reduce_business_overview_kpi_rows(
    rows: list[dict[str, Any]],
    labor_efficiency: float | None = 0,
) -> dict[str, Any]:
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
        "labor_efficiency": _round_or_none(labor_efficiency, 2),
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
    order_count = _sum("order_count")
    total_items = _sum("total_items")
    traffic = _sum("traffic")
    profit = _sum("profit")
    target_sales_amount = _sum("target_sales_amount")
    target_sales_quantity = _sum("target_sales_quantity")

    effective_order_count = order_count if order_count is not None else sales_quantity
    effective_total_items = total_items if total_items is not None else sales_quantity

    if traffic is None or effective_order_count is None:
        conversion_rate = None
    elif traffic > 0:
        conversion_rate = round((effective_order_count * 100.0 / traffic), 2)
    elif traffic == 0 and effective_order_count == 0:
        conversion_rate = 0
    else:
        conversion_rate = None

    if sales_amount is None or effective_order_count is None:
        avg_order_value = None
    elif effective_order_count > 0:
        avg_order_value = round((sales_amount / effective_order_count), 2)
    elif effective_order_count == 0 and sales_amount == 0:
        avg_order_value = 0
    else:
        avg_order_value = None

    if effective_total_items is None or effective_order_count is None:
        attach_rate = None
    elif effective_order_count > 0:
        attach_rate = round((effective_total_items / effective_order_count), 2)
    elif effective_order_count == 0 and effective_total_items == 0:
        attach_rate = 0
    else:
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


def _comparison_source_for_granularity(granularity: str) -> tuple[str, str]:
    if granularity == "daily":
        return "mart.shop_day_kpi", "period_date"
    if granularity == "weekly":
        return "mart.shop_week_kpi", "period_week"
    if granularity == "monthly":
        return "mart.shop_month_kpi", "period_month"
    raise ValueError("granularity must be daily, weekly or monthly")


def _platform_kpi_source_for_granularity(granularity: str) -> tuple[str, str]:
    normalized = str(granularity or "").strip().lower()
    if normalized == "daily":
        return "mart.platform_day_kpi", "period_date"
    if normalized == "weekly":
        return "mart.platform_week_kpi", "period_week"
    if normalized == "monthly":
        return "mart.platform_month_kpi", "period_month"
    raise ValueError("granularity must be daily, weekly or monthly")


def _monthly_orders_raw_source_sql() -> str:
    return """
        SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
        FROM b_class.fact_shopee_orders_monthly
        UNION ALL
        SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
        FROM b_class.fact_tiktok_orders_monthly
        UNION ALL
        SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
        FROM b_class.fact_miaoshou_orders_monthly
    """


def _monthly_analytics_raw_source_sql() -> str:
    return """
        SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
        FROM b_class.fact_shopee_analytics_monthly
        UNION ALL
        SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
        FROM b_class.fact_tiktok_analytics_monthly
        UNION ALL
        SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
        FROM b_class.fact_miaoshou_analytics_monthly
    """


def _daily_orders_raw_source_sql() -> str:
    return """
        SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
        FROM b_class.fact_shopee_orders_daily
        UNION ALL
        SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
        FROM b_class.fact_tiktok_orders_daily
        UNION ALL
        SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
        FROM b_class.fact_miaoshou_orders_daily
    """


def _normalized_identity_sql(expr: str) -> str:
    return (
        "REGEXP_REPLACE("
        "REGEXP_REPLACE(LOWER(TRIM(COALESCE({expr}, ''))), "
        "'^(shopee|tiktok\\s*shop|tiktok|tk|miaoshou|amazon|lazada)\\s*', '', 'i'), "
        "'[[:space:]_()/-]+', '', 'g')"
    ).format(expr=expr)


def _filter_rows_by_period_key(rows: list[dict[str, Any]], target_period: date_cls) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for row in rows:
        period_value = row.get("period_key")
        if period_value is None:
            continue
        if isinstance(period_value, datetime):
            normalized = period_value.date()
        elif isinstance(period_value, date_cls):
            normalized = period_value
        else:
            normalized = _normalize_period_start(str(period_value))
        if normalized == target_period:
            matched.append(row)
    return matched


def _filter_rows_by_period_range(
    rows: list[dict[str, Any]],
    period_start: date_cls,
    period_end: date_cls,
) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for row in rows:
        period_value = row.get("period_key")
        if period_value is None:
            continue
        if isinstance(period_value, datetime):
            normalized = period_value.date()
        elif isinstance(period_value, date_cls):
            normalized = period_value
        else:
            normalized = _normalize_period_start(str(period_value))
        if period_start <= normalized <= period_end:
            matched.append(row)
    return matched


def rank_inventory_backlog_rows(
    rows: list[dict[str, Any]],
    min_days: int = 30,
) -> list[dict[str, Any]]:
    filtered = [
        dict(row)
        for row in rows
        if (_to_optional_float(row.get("estimated_turnover_days")) or float("-inf")) >= min_days
    ]
    for row in filtered:
        row["risk_level"] = row.get("risk_level") or _classify_inventory_backlog_risk(row)
        row["clearance_priority_score"] = _inventory_backlog_priority_score(row)
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


def _normalize_join_key(value: Any) -> str:
    return "" if value is None else str(value)


def _inventory_snapshot_join_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        _normalize_join_key(row.get("platform_code")),
        _normalize_join_key(row.get("shop_id")),
        _normalize_join_key(row.get("platform_sku")),
        _normalize_join_key(row.get("product_sku")),
        _normalize_join_key(row.get("warehouse_name")),
    )


def _inventory_sales_join_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        _normalize_join_key(row.get("platform_code")),
        _normalize_join_key(row.get("shop_id")),
        _normalize_join_key(row.get("platform_sku")),
        _normalize_join_key(row.get("product_sku")),
    )


def _classify_inventory_backlog_risk(row: dict[str, Any]) -> str:
    turnover_days = _to_float(row.get("estimated_turnover_days"))
    stagnant_count = int(_to_float(row.get("stagnant_snapshot_count")))
    if turnover_days >= 60 or stagnant_count >= 3:
        return "high"
    if turnover_days >= 30 or stagnant_count >= 2:
        return "medium"
    return "low"


def _inventory_backlog_priority_score(row: dict[str, Any]) -> float:
    if row.get("clearance_priority_score") is not None:
        return _to_float(row.get("clearance_priority_score"))
    return round(
        _to_float(row.get("inventory_value")) * 0.5
        + _to_float(row.get("estimated_stagnant_days")) * 10
        + _to_float(row.get("estimated_turnover_days")) * 2,
        2,
    )


def build_inventory_backlog_rows(
    latest_rows: list[dict[str, Any]],
    change_rows: list[dict[str, Any]],
    sales_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    change_by_key = {_inventory_snapshot_join_key(row): row for row in change_rows}
    sales_by_key = {_inventory_sales_join_key(row): row for row in sales_rows}
    backlog_rows: list[dict[str, Any]] = []

    for latest_row in latest_rows:
        change_row = change_by_key.get(_inventory_snapshot_join_key(latest_row), {})
        sales_row = sales_by_key.get(_inventory_sales_join_key(latest_row), {})

        available_stock = _to_optional_float(latest_row.get("available_stock")) or 0.0
        sold_units_30d = _to_optional_float(sales_row.get("sold_units_30d")) or 0.0
        active_days_30d = _to_optional_float(sales_row.get("active_days_30d")) or 0.0

        if sold_units_30d > 0 and active_days_30d > 0:
            daily_avg_sales = round(sold_units_30d / active_days_30d, 2)
            estimated_turnover_days = round(available_stock / (sold_units_30d / active_days_30d), 0)
        elif available_stock > 0:
            daily_avg_sales = 0.0
            estimated_turnover_days = 9999.0
        else:
            daily_avg_sales = 0.0
            estimated_turnover_days = 0.0

        backlog_row = {
            "snapshot_date": latest_row.get("snapshot_date"),
            "platform_code": latest_row.get("platform_code"),
            "shop_id": latest_row.get("shop_id"),
            "product_id": latest_row.get("product_id"),
            "product_name": latest_row.get("product_name"),
            "platform_sku": latest_row.get("platform_sku"),
            "product_sku": latest_row.get("product_sku"),
            "warehouse_name": latest_row.get("warehouse_name"),
            "available_stock": available_stock,
            "on_hand_stock": _to_optional_float(latest_row.get("on_hand_stock")) or 0.0,
            "inventory_value": _to_optional_float(latest_row.get("inventory_value")) or 0.0,
            "daily_avg_sales": daily_avg_sales,
            "estimated_turnover_days": estimated_turnover_days,
            "stock_delta": _to_optional_float(change_row.get("stock_delta")) or 0.0,
            "inventory_value_delta": _to_optional_float(change_row.get("inventory_value_delta")) or 0.0,
            "is_stagnant": bool(change_row.get("is_stagnant", False)),
            "snapshot_gap_days": _to_optional_float(change_row.get("snapshot_gap_days")) or 0.0,
            "estimated_stagnant_days": _to_optional_float(change_row.get("estimated_stagnant_days")) or 0.0,
            "stagnant_snapshot_count": int(_to_optional_float(change_row.get("stagnant_snapshot_count")) or 0.0),
        }
        backlog_row["risk_level"] = _classify_inventory_backlog_risk(backlog_row)
        backlog_row["clearance_priority_score"] = _inventory_backlog_priority_score(backlog_row)
        backlog_rows.append(backlog_row)

    return backlog_rows


def summarize_inventory_backlog_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_value = sum(_to_optional_float(row.get("inventory_value")) or 0.0 for row in rows)
    backlog_30d_value = sum(
        (_to_optional_float(row.get("inventory_value")) or 0.0)
        for row in rows
        if (_to_optional_float(row.get("estimated_turnover_days")) or 0.0) >= 30
    )
    backlog_60d_value = sum(
        (_to_optional_float(row.get("inventory_value")) or 0.0)
        for row in rows
        if (_to_optional_float(row.get("estimated_turnover_days")) or 0.0) >= 60
    )
    backlog_90d_value = sum(
        (_to_optional_float(row.get("inventory_value")) or 0.0)
        for row in rows
        if (_to_optional_float(row.get("estimated_turnover_days")) or 0.0) >= 90
    )

    return {
        "total_value": round(total_value, 2),
        "backlog_30d_value": round(backlog_30d_value, 2),
        "backlog_60d_value": round(backlog_60d_value, 2),
        "backlog_90d_value": round(backlog_90d_value, 2),
        "backlog_30d_ratio": round(backlog_30d_value * 100.0 / total_value, 2) if total_value else 0,
        "backlog_60d_ratio": round(backlog_60d_value * 100.0 / total_value, 2) if total_value else 0,
        "backlog_90d_ratio": round(backlog_90d_value * 100.0 / total_value, 2) if total_value else 0,
        "total_quantity": int(sum(_to_optional_float(row.get("available_stock")) or 0.0 for row in rows)),
        "high_risk_sku_count": sum(1 for row in rows if row.get("risk_level") == "high"),
        "medium_risk_sku_count": sum(1 for row in rows if row.get("risk_level") == "medium"),
        "low_risk_sku_count": sum(1 for row in rows if row.get("risk_level") == "low"),
    }


def rank_shop_racing_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = [dict(row) for row in rows]
    ordered.sort(key=lambda row: (_sort_numeric(row.get("gmv")), _sort_numeric(row.get("order_count"))), reverse=True)
    for index, row in enumerate(ordered, start=1):
        row["rank"] = index
    return ordered


def rank_traffic_rows(rows: list[dict[str, Any]], dimension: str = "visitor") -> list[dict[str, Any]]:
    ordered = [dict(row) for row in rows]
    if dimension in {"pv", "page_views", "traffic", "shop", "account"}:
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


def _resolve_business_overview_window(granularity: str, target_date: str) -> tuple[date_cls, date_cls]:
    period_start = _normalize_period_start(target_date)
    normalized_granularity = str(granularity or "").strip().lower()
    if normalized_granularity == "daily":
        return period_start, period_start
    if normalized_granularity == "weekly":
        week_start = period_start - timedelta(days=period_start.weekday())
        return week_start, week_start + timedelta(days=6)
    if normalized_granularity == "monthly":
        month_start = date_cls(period_start.year, period_start.month, 1)
        return month_start, _start_of_next_month(month_start) - timedelta(days=1)
    raise ValueError("granularity must be daily, weekly or monthly")


def _start_of_quarter(day: date_cls) -> date_cls:
    quarter_month = ((day.month - 1) // 3) * 3 + 1
    return date_cls(day.year, quarter_month, 1)


def _start_of_next_month(day: date_cls) -> date_cls:
    if day.month == 12:
        return date_cls(day.year + 1, 1, 1)
    return date_cls(day.year, day.month + 1, 1)


def _resolve_store_analysis_effective_granularity(platform: str, granularity: str) -> str:
    normalized_platform = str(platform or "").strip().lower()
    normalized_granularity = str(granularity or "").strip().lower()
    if normalized_granularity not in {"daily", "weekly", "monthly", "quarterly", "yearly"}:
        raise ValueError("granularity must be one of daily/weekly/monthly/quarterly/yearly")
    if normalized_granularity == "daily":
        return "hourly" if normalized_platform == "shopee" else "daily"
    if normalized_granularity == "yearly":
        return "monthly"
    return "daily"


def _resolve_store_analysis_window(granularity: str, target_date: str) -> tuple[date_cls, date_cls]:
    period_start = _normalize_period_start(target_date)
    normalized_granularity = str(granularity or "").strip().lower()
    if normalized_granularity == "daily":
        return period_start, period_start
    if normalized_granularity == "weekly":
        return period_start, period_start + timedelta(days=6)
    if normalized_granularity == "monthly":
        month_start = date_cls(period_start.year, period_start.month, 1)
        return month_start, _start_of_next_month(month_start) - timedelta(days=1)
    if normalized_granularity == "quarterly":
        quarter_start = _start_of_quarter(period_start)
        quarter_end = _start_of_next_month(_start_of_next_month(_start_of_next_month(quarter_start))) - timedelta(days=1)
        return quarter_start, quarter_end
    if normalized_granularity == "yearly":
        year_start = date_cls(period_start.year, 1, 1)
        return year_start, date_cls(period_start.year, 12, 31)
    raise ValueError("granularity must be one of daily/weekly/monthly/quarterly/yearly")


def _previous_store_analysis_anchor(granularity: str, target_date: str) -> str:
    period_start = _normalize_period_start(target_date)
    normalized_granularity = str(granularity or "").strip().lower()
    if normalized_granularity == "daily":
        return (period_start - timedelta(days=1)).isoformat()
    if normalized_granularity == "weekly":
        return (period_start - timedelta(days=7)).isoformat()
    if normalized_granularity == "monthly":
        if period_start.month == 1:
            return f"{period_start.year - 1}-12"
        return f"{period_start.year}-{period_start.month - 1:02d}"
    if normalized_granularity == "quarterly":
        quarter_start = _start_of_quarter(period_start)
        month = quarter_start.month - 3
        year = quarter_start.year
        if month <= 0:
            month += 12
            year -= 1
        return f"{year}-{month:02d}"
    if normalized_granularity == "yearly":
        return str(period_start.year - 1)
    raise ValueError("granularity must be one of daily/weekly/monthly/quarterly/yearly")


class PostgresqlDashboardService:
    async def _fetch_rows(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text(query), params)
            return [dict(row) for row in result.mappings().all()]

    async def _fetch_rows_with_statement_timeout(
        self,
        query: str,
        params: dict[str, Any],
        *,
        timeout_ms: int,
    ) -> list[dict[str, Any]]:
        async with AsyncSessionLocal() as session:
            await session.execute(text(f"SET LOCAL statement_timeout = {int(timeout_ms)}"))
            result = await session.execute(text(query), params)
            return [dict(row) for row in result.mappings().all()]

    async def _load_active_employee_count(self, _period_key: date_cls) -> int:
        async with AsyncSessionLocal() as session:
            try:
                result = await session.execute(
                    text(
                        """
                        SELECT COUNT(*) AS active_employee_count
                        FROM a_class.employees
                        WHERE status = 'active'
                          AND employee_identity_type = 'employee'
                        """
                    )
                )
            except ProgrammingError as exc:
                await session.rollback()
                orig_message = str(getattr(exc, "orig", exc)).lower()
                if 'employee_identity_type' in orig_message:
                    fallback = await session.execute(
                        text(
                            """
                            SELECT COUNT(*) AS active_employee_count
                            FROM a_class.employees
                            WHERE status = 'active'
                            """
                        )
                    )
                    value = fallback.scalar_one_or_none()
                    return int(value or 0)
                if 'a_class.employees' in orig_message or 'relation "a_class.employees"' in orig_message:
                    return 0
                raise
            value = result.scalar_one_or_none()
            return int(value or 0)

    async def _load_inventory_backlog_summary(
        self,
        period_start: date_cls | None = None,
        period_end: date_cls | None = None,
    ) -> dict[str, Any]:
        if period_start is not None and period_end is not None:
            rows = await self._fetch_rows(
                """
                SELECT
                    SUM(inventory_value) AS total_value,
                    SUM(CASE WHEN estimated_turnover_days >= 30 THEN inventory_value ELSE 0 END) AS backlog_30d_value,
                    SUM(CASE WHEN estimated_turnover_days >= 60 THEN inventory_value ELSE 0 END) AS backlog_60d_value,
                    SUM(CASE WHEN estimated_turnover_days >= 90 THEN inventory_value ELSE 0 END) AS backlog_90d_value,
                    SUM(available_stock) AS total_quantity,
                    COUNT(*) FILTER (WHERE risk_level = 'high') AS high_risk_sku_count,
                    COUNT(*) FILTER (WHERE risk_level = 'medium') AS medium_risk_sku_count,
                    COUNT(*) FILTER (WHERE risk_level = 'low') AS low_risk_sku_count
                FROM api.business_overview_inventory_backlog_module
                WHERE snapshot_date >= :period_start
                  AND snapshot_date <= :period_end
                """,
                {"period_start": period_start, "period_end": period_end},
            )
        else:
            rows = await self._fetch_rows(
                """
                SELECT
                    total_value,
                    backlog_30d_value,
                    backlog_60d_value,
                    backlog_90d_value,
                    total_quantity,
                    high_risk_sku_count,
                    medium_risk_sku_count,
                    low_risk_sku_count
                FROM api.inventory_backlog_summary_module
                """,
                {},
            )
        row = rows[0] if rows else {}
        total_value = _to_optional_float(row.get("total_value")) or 0.0
        backlog_30d_value = _to_optional_float(row.get("backlog_30d_value")) or 0.0
        backlog_60d_value = _to_optional_float(row.get("backlog_60d_value")) or 0.0
        backlog_90d_value = _to_optional_float(row.get("backlog_90d_value")) or 0.0
        return {
            "total_value": round(total_value, 2),
            "backlog_30d_value": round(backlog_30d_value, 2),
            "backlog_60d_value": round(backlog_60d_value, 2),
            "backlog_90d_value": round(backlog_90d_value, 2),
            "backlog_30d_ratio": round(backlog_30d_value * 100.0 / total_value, 2) if total_value else 0,
            "backlog_60d_ratio": round(backlog_60d_value * 100.0 / total_value, 2) if total_value else 0,
            "backlog_90d_ratio": round(backlog_90d_value * 100.0 / total_value, 2) if total_value else 0,
            "total_quantity": int(_to_optional_float(row.get("total_quantity")) or 0.0),
            "high_risk_sku_count": int(_to_optional_float(row.get("high_risk_sku_count")) or 0.0),
            "medium_risk_sku_count": int(_to_optional_float(row.get("medium_risk_sku_count")) or 0.0),
            "low_risk_sku_count": int(_to_optional_float(row.get("low_risk_sku_count")) or 0.0),
        }

    async def _load_ranked_inventory_backlog_module_rows(
        self,
        *,
        source_table: str,
        min_days: int,
        limit: int,
        period_start: date_cls | None = None,
        period_end: date_cls | None = None,
    ) -> list[dict[str, Any]]:
        where_clauses = ["estimated_turnover_days >= :min_days"]
        params: dict[str, Any] = {"min_days": min_days, "limit": limit}
        if period_start is not None and period_end is not None:
            where_clauses.append("snapshot_date >= :period_start")
            where_clauses.append("snapshot_date <= :period_end")
            params["period_start"] = period_start
            params["period_end"] = period_end
        rows = await self._fetch_rows(
            """
            SELECT *
            FROM {source_table}
            WHERE {where_clause}
            ORDER BY clearance_priority_score DESC, inventory_value DESC, estimated_turnover_days DESC
            LIMIT :limit
            """.format(source_table=source_table, where_clause=" AND ".join(where_clauses)),
            params,
        )
        ranked: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            normalized = dict(row)
            normalized["risk_level"] = normalized.get("risk_level") or _classify_inventory_backlog_risk(normalized)
            normalized["clearance_priority_score"] = normalized.get("clearance_priority_score") or _inventory_backlog_priority_score(normalized)
            normalized["rank"] = index
            ranked.append(normalized)
        return ranked

    async def _load_inventory_backlog_rows(self) -> list[dict[str, Any]]:
        latest_rows = await self._fetch_rows(
            """
            SELECT
                snapshot_date,
                platform_code,
                shop_id,
                product_id,
                product_name,
                platform_sku,
                product_sku,
                warehouse_name,
                available_stock,
                on_hand_stock,
                inventory_value
            FROM mart.inventory_snapshot_latest
            """,
            {},
        )
        change_rows = await self._fetch_rows(
            """
            SELECT
                platform_code,
                shop_id,
                platform_sku,
                product_sku,
                warehouse_name,
                stock_delta,
                inventory_value_delta,
                is_stagnant,
                snapshot_gap_days,
                estimated_stagnant_days,
                stagnant_snapshot_count
            FROM mart.inventory_snapshot_change
            """,
            {},
        )
        sales_rows = await self._fetch_rows(
            """
            SELECT
                platform_code,
                shop_id,
                platform_sku,
                product_sku,
                COALESCE(SUM(product_quantity), 0) AS sold_units_30d,
                COUNT(DISTINCT metric_date::date) AS active_days_30d
            FROM semantic.fact_orders_atomic
            WHERE metric_date::date >= CURRENT_DATE - INTERVAL '30 days'
              AND metric_date::date <= CURRENT_DATE
            GROUP BY platform_code, shop_id, platform_sku, product_sku
            """,
            {},
        )
        return build_inventory_backlog_rows(
            latest_rows=latest_rows,
            change_rows=change_rows,
            sales_rows=sales_rows,
        )

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
                        SELECT SUM(rent + marketing_fee + utilities + other_costs)
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
                            SELECT COALESCE(SUM("租金" + "营销费用" + "水电费" + "其他成本"), 0)
                            FROM a_class.operating_costs
                            WHERE "年月" = :year_month
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
                                SELECT COALESCE(SUM("???" + "???" + "????? + "??????"), 0)
                                FROM a_class.operating_costs
                                WHERE "???" = :year_month
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
        month: str | None = None,
        platform: str | None = None,
        granularity: str = "monthly",
        target_date: str | None = None,
    ) -> dict[str, Any]:
        effective_granularity = str(granularity or "monthly").strip().lower()
        effective_target_date = target_date or month
        if effective_target_date is None:
            raise ValueError("target_date or month is required")
        period_key = _normalize_period_start(effective_target_date)

        if effective_granularity == "monthly":
            platform_filter_sql = " AND platform_code = :platform_code" if platform else ""
            rows = await self._fetch_rows(
                """
                WITH raw_orders AS (
                    {orders_source}
                ),
                mapped_orders AS (
                    SELECT
                        platform_code,
                        NULLIF(TRIM(COALESCE(shop_id, '')), '') AS source_shop_id,
                        COALESCE(
                            raw_data->>'订单号',
                            raw_data->>'订单ID',
                            raw_data->>'订单编号',
                            raw_data->>'ID',
                            raw_data->>'order_id',
                            raw_data->>'Order ID',
                            raw_data->>'order_no'
                        ) AS order_id,
                        CASE
                            WHEN COALESCE(
                                raw_data->>'实付金额',
                                raw_data->>'买家实付金额',
                                raw_data->>'总收入',
                                raw_data->>'buyer_payment_rmb',
                                raw_data->>'buyer_payment',
                                raw_data->>'买家支付(RMB)',
                                raw_data->>'买家支付',
                                raw_data->>'买家实付金额(RMB)',
                                raw_data->>'paid_amount',
                                raw_data->>'Paid Amount'
                            ) IS NULL THEN NULL
                            ELSE NULLIF(
                                REGEXP_REPLACE(
                                    REPLACE(REPLACE(REPLACE(REPLACE(
                                        COALESCE(
                                            raw_data->>'实付金额',
                                            raw_data->>'买家实付金额',
                                            raw_data->>'总收入',
                                            raw_data->>'buyer_payment_rmb',
                                            raw_data->>'buyer_payment',
                                            raw_data->>'买家支付(RMB)',
                                            raw_data->>'买家支付',
                                            raw_data->>'买家实付金额(RMB)',
                                            raw_data->>'paid_amount',
                                            raw_data->>'Paid Amount'
                                        ),
                                        ',', ''
                                    ), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                                    '[^0-9.-]',
                                    '',
                                    'g'
                                ),
                                ''
                            )::numeric
                        END AS paid_amount,
                        CASE
                            WHEN COALESCE(
                                raw_data->>'利润(RMB)',
                                raw_data->>'profit_rmb',
                                raw_data->>'利润',
                                raw_data->>'profit',
                                raw_data->>'毛利',
                                raw_data->>'Profit'
                            ) IS NULL THEN NULL
                            ELSE NULLIF(
                                REGEXP_REPLACE(
                                    REPLACE(REPLACE(REPLACE(REPLACE(
                                        COALESCE(
                                            raw_data->>'利润(RMB)',
                                            raw_data->>'profit_rmb',
                                            raw_data->>'利润',
                                            raw_data->>'profit',
                                            raw_data->>'毛利',
                                            raw_data->>'Profit'
                                        ),
                                        ',', ''
                                    ), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                                    '[^0-9.-]',
                                    '',
                                    'g'
                                ),
                                ''
                            )::numeric
                        END AS profit,
                        CASE
                            WHEN COALESCE(
                                raw_data->>'产品数量',
                                raw_data->>'商品数量',
                                raw_data->>'数量',
                                raw_data->>'件数',
                                raw_data->>'销售数量',
                                raw_data->>'出库数量',
                                raw_data->>'product_quantity',
                                raw_data->>'quantity',
                                raw_data->>'qty',
                                raw_data->>'item_quantity'
                            ) IS NULL THEN NULL
                            ELSE NULLIF(
                                REGEXP_REPLACE(
                                    REPLACE(REPLACE(REPLACE(REPLACE(
                                        COALESCE(
                                            raw_data->>'产品数量',
                                            raw_data->>'商品数量',
                                            raw_data->>'数量',
                                            raw_data->>'件数',
                                            raw_data->>'销售数量',
                                            raw_data->>'出库数量',
                                            raw_data->>'product_quantity',
                                            raw_data->>'quantity',
                                            raw_data->>'qty',
                                            raw_data->>'item_quantity'
                                        ),
                                        ',', ''
                                    ), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                                    '[^0-9.-]',
                                    '',
                                    'g'
                                ),
                                ''
                            )::numeric
                        END AS product_quantity,
                        data_hash,
                        ingest_timestamp
                    FROM raw_orders
                    WHERE date_trunc('month', metric_date)::date = :period_key
                    {platform_filter_sql}
                ),
                deduplicated_orders AS (
                    SELECT
                        *,
                        ROW_NUMBER() OVER (
                            PARTITION BY platform_code, COALESCE(source_shop_id, ''), data_hash
                            ORDER BY ingest_timestamp DESC
                        ) AS rn
                    FROM mapped_orders
                ),
                monthly_orders AS (
                    SELECT
                        :period_key AS period_key,
                        platform_code,
                        SUM(paid_amount) AS gmv,
                        CASE WHEN COUNT(*) > 0 THEN COUNT(DISTINCT order_id)::numeric ELSE NULL END AS order_count,
                        SUM(product_quantity) AS total_items,
                        SUM(profit) AS profit
                    FROM deduplicated_orders
                    WHERE rn = 1
                    GROUP BY platform_code
                ),
                raw_analytics AS (
                    {analytics_source}
                ),
                mapped_analytics AS (
                    SELECT
                        platform_code,
                        NULLIF(TRIM(COALESCE(shop_id, '')), '') AS source_shop_id,
                        CASE
                            WHEN COALESCE(
                                raw_data->>'访客数',
                                raw_data->>'独立访客',
                                raw_data->>'去重页面浏览次数',
                                raw_data->>'unique_visitors',
                                raw_data->>'Unique Visitors',
                                raw_data->>'uv',
                                raw_data->>'visitor_count'
                            ) IS NULL THEN NULL
                            ELSE NULLIF(
                                REGEXP_REPLACE(
                                    REPLACE(REPLACE(REPLACE(REPLACE(
                                        COALESCE(
                                            raw_data->>'访客数',
                                            raw_data->>'独立访客',
                                            raw_data->>'去重页面浏览次数',
                                            raw_data->>'unique_visitors',
                                            raw_data->>'Unique Visitors',
                                            raw_data->>'uv',
                                            raw_data->>'visitor_count'
                                        ),
                                        ',', ''
                                    ), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                                    '[^0-9.-]',
                                    '',
                                    'g'
                                ),
                                ''
                            )::numeric
                        END AS visitor_count,
                        CASE
                            WHEN COALESCE(
                                raw_data->>'浏览量',
                                raw_data->>'页面浏览数',
                                raw_data->>'页面浏览次数',
                                raw_data->>'page_views',
                                raw_data->>'Page Views',
                                raw_data->>'views',
                                raw_data->>'page_view'
                            ) IS NULL THEN NULL
                            ELSE NULLIF(
                                REGEXP_REPLACE(
                                    REPLACE(REPLACE(REPLACE(REPLACE(
                                        COALESCE(
                                            raw_data->>'浏览量',
                                            raw_data->>'页面浏览数',
                                            raw_data->>'页面浏览次数',
                                            raw_data->>'page_views',
                                            raw_data->>'Page Views',
                                            raw_data->>'views',
                                            raw_data->>'page_view'
                                        ),
                                        ',', ''
                                    ), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                                    '[^0-9.-]',
                                    '',
                                    'g'
                                ),
                                ''
                            )::numeric
                        END AS page_views,
                        data_hash,
                        ingest_timestamp
                    FROM raw_analytics
                    WHERE date_trunc('month', metric_date)::date = :period_key
                    {platform_filter_sql}
                ),
                deduplicated_analytics AS (
                    SELECT
                        *,
                        ROW_NUMBER() OVER (
                            PARTITION BY platform_code, COALESCE(source_shop_id, ''), data_hash
                            ORDER BY ingest_timestamp DESC
                        ) AS rn
                    FROM mapped_analytics
                ),
                monthly_traffic AS (
                    SELECT
                        :period_key AS period_key,
                        platform_code,
                        SUM(visitor_count) AS visitor_count,
                        SUM(page_views) AS page_views
                    FROM deduplicated_analytics
                    WHERE rn = 1
                    GROUP BY platform_code
                )
                SELECT
                    COALESCE(o.period_key, t.period_key) AS period_key,
                    COALESCE(o.platform_code, t.platform_code) AS platform_code,
                    o.gmv,
                    o.order_count,
                    COALESCE(t.page_views, t.visitor_count) AS visitor_count,
                    CASE
                        WHEN o.order_count IS NOT NULL
                         AND COALESCE(t.page_views, t.visitor_count) IS NOT NULL
                         AND COALESCE(t.page_views, t.visitor_count) > 0
                        THEN ROUND(o.order_count::numeric * 100.0 / COALESCE(t.page_views, t.visitor_count), 2)
                        WHEN o.order_count IS NOT NULL
                         AND COALESCE(t.page_views, t.visitor_count) = 0
                         AND o.order_count = 0
                        THEN 0
                        ELSE NULL
                    END AS conversion_rate,
                    CASE
                        WHEN o.gmv IS NOT NULL AND o.order_count > 0
                        THEN ROUND(o.gmv::numeric / o.order_count, 2)
                        WHEN o.gmv IS NOT NULL AND o.order_count = 0 AND o.gmv = 0
                        THEN 0
                        ELSE NULL
                    END AS avg_order_value,
                    CASE
                        WHEN o.total_items IS NOT NULL AND o.order_count > 0
                        THEN ROUND(o.total_items::numeric / o.order_count, 2)
                        WHEN o.total_items IS NOT NULL AND o.order_count = 0 AND o.total_items = 0
                        THEN 0
                        ELSE NULL
                    END AS attach_rate,
                    o.total_items,
                    o.profit
                FROM monthly_orders o
                FULL OUTER JOIN monthly_traffic t
                  ON o.period_key = t.period_key
                 AND o.platform_code = t.platform_code
                """.format(
                    orders_source=_monthly_orders_raw_source_sql(),
                    analytics_source=_monthly_analytics_raw_source_sql(),
                    platform_filter_sql=platform_filter_sql,
                ),
                {
                    "period_key": period_key,
                    "platform_code": platform,
                },
            )
            reduced = reduce_business_overview_kpi_rows(rows)
            employee_count = await self._load_active_employee_count(period_key)
            gmv = reduced.get("gmv")
            if employee_count > 0 and gmv is not None:
                reduced["labor_efficiency"] = round(float(gmv) / employee_count, 2)
            else:
                reduced["labor_efficiency"] = 0
            return reduced

        source_table, period_column = _platform_kpi_source_for_granularity(effective_granularity)
        query = """
            SELECT
                {period_column} AS period_key,
                platform_code,
                gmv,
                order_count,
                COALESCE(page_views, visitor_count) AS visitor_count,
                conversion_rate,
                avg_order_value,
                attach_rate,
                total_items,
                profit
            FROM {source_table}
            WHERE {period_column} = :period_key
        """.format(period_column=period_column, source_table=source_table)
        params: dict[str, Any] = {"period_key": period_key}
        if platform:
            query += " AND platform_code = :platform_code"
            params["platform_code"] = platform

        rows = await self._fetch_rows(query, params)
        reduced = reduce_business_overview_kpi_rows(rows)
        employee_count = await self._load_active_employee_count(period_key)
        gmv = reduced.get("gmv")
        if employee_count > 0 and gmv is not None:
            reduced["labor_efficiency"] = round(float(gmv) / employee_count, 2)
        else:
            reduced["labor_efficiency"] = 0
        return reduced

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

        combined_query = """
            SELECT
                period_key,
                sales_amount,
                sales_quantity,
                order_count,
                total_items,
                traffic,
                conversion_rate,
                avg_order_value,
                attach_rate,
                profit
            FROM api.business_overview_comparison_platform_module
            WHERE granularity = :granularity
              AND period_key >= :range_start
              AND period_key <= :range_end
        """
        if platform:
            combined_query += " AND platform_code = :platform_code"

        combined_rows = await self._fetch_rows(
            combined_query,
            {
                "granularity": granularity,
                "range_start": min(previous_start, average_start),
                "range_end": current_start,
                "platform_code": platform,
            },
        )

        current_rows = _filter_rows_by_period_key(combined_rows, current_start)
        previous_rows = _filter_rows_by_period_key(combined_rows, previous_start)
        average_rows = _filter_rows_by_period_range(
            combined_rows,
            average_start,
            current_start,
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
        reduced["target"]["sales_amount"] = _round_or_none(target_summary["target_amount"], 2)
        reduced["target"]["sales_quantity"] = _round_or_none(target_summary["target_quantity"], 2)
        reduced["target"]["achievement_rate"] = (
            round(reduced["metrics"]["sales_amount"]["today"] * 100.0 / target_summary["target_amount"], 2)
            if target_summary["target_amount"] and reduced["metrics"]["sales_amount"]["today"] is not None
            else 0
        )
        return reduced

    async def get_business_overview_inventory_backlog(
        self,
        min_days: int = 30,
        limit: int = 20,
        granularity: str | None = None,
        target_date: str | None = None,
    ) -> dict[str, Any]:
        period_start = None
        period_end = None
        if granularity and target_date:
            period_start, period_end = _resolve_business_overview_window(granularity, target_date)
        return {
            "summary": await (
                self._load_inventory_backlog_summary(period_start=period_start, period_end=period_end)
                if period_start is not None and period_end is not None
                else self._load_inventory_backlog_summary()
            ),
            "top_products": await self._load_ranked_inventory_backlog_module_rows(
                source_table="api.business_overview_inventory_backlog_module",
                min_days=min_days,
                limit=limit,
                period_start=period_start,
                period_end=period_end,
            ),
        }

    async def get_clearance_ranking(
        self,
        min_days: int = 30,
        limit: int = 100,
        granularity: str | None = None,
        target_date: str | None = None,
    ) -> list[dict[str, Any]]:
        period_start = None
        period_end = None
        if granularity and target_date:
            period_start, period_end = _resolve_business_overview_window(granularity, target_date)

        where_snapshot = []
        if period_start is not None and period_end is not None:
            where_snapshot.append("i.snapshot_date >= :period_start")
            where_snapshot.append("i.snapshot_date <= :period_end")
        snapshot_filter_sql = ""
        if where_snapshot:
            snapshot_filter_sql = "WHERE " + " AND ".join(where_snapshot)

        rows = await self._fetch_rows(
            """
            WITH sales_30d AS (
                SELECT
                    platform_code,
                    COALESCE(raw_data->>'platform_sku', raw_data->>'平台SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku,
                    COALESCE(raw_data->>'product_sku', raw_data->>'商品SKU', raw_data->>'商品货号') AS product_sku,
                    COALESCE(
                        SUM(
                            CASE
                                WHEN COALESCE(
                                    raw_data->>'产品数量',
                                    raw_data->>'商品数量',
                                    raw_data->>'数量',
                                    raw_data->>'件数',
                                    raw_data->>'销售数量',
                                    raw_data->>'出库数量',
                                    raw_data->>'product_quantity',
                                    raw_data->>'quantity',
                                    raw_data->>'qty',
                                    raw_data->>'item_quantity'
                                ) IS NULL THEN 0::numeric
                                ELSE NULLIF(
                                    REGEXP_REPLACE(
                                        REPLACE(REPLACE(REPLACE(REPLACE(
                                            COALESCE(
                                                raw_data->>'产品数量',
                                                raw_data->>'商品数量',
                                                raw_data->>'数量',
                                                raw_data->>'件数',
                                                raw_data->>'销售数量',
                                                raw_data->>'出库数量',
                                                raw_data->>'product_quantity',
                                                raw_data->>'quantity',
                                                raw_data->>'qty',
                                                raw_data->>'item_quantity'
                                            ),
                                            ',', ''
                                        ), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                                        '[^0-9.-]',
                                        '',
                                        'g'
                                    ),
                                    ''
                                )::numeric
                            END
                        ),
                        0
                    ) AS sold_units_30d,
                    COUNT(DISTINCT metric_date::date) AS active_days_30d
                FROM (
                    {daily_orders_source}
                ) o
                WHERE metric_date::date >= CURRENT_DATE - INTERVAL '30 days'
                  AND metric_date::date <= CURRENT_DATE
                GROUP BY platform_code, platform_sku, product_sku
            )
            SELECT
                i.snapshot_date,
                i.platform_code,
                i.shop_id,
                i.product_id,
                i.product_name,
                i.platform_sku,
                i.product_sku,
                i.available_stock,
                i.inventory_value,
                COALESCE(
                    ROUND(s.sold_units_30d::numeric / NULLIF(s.active_days_30d, 0), 2),
                    0
                ) AS daily_avg_sales,
                CASE
                    WHEN COALESCE(s.sold_units_30d, 0) > 0 AND COALESCE(s.active_days_30d, 0) > 0
                    THEN ROUND(COALESCE(i.available_stock, 0)::numeric / NULLIF(s.sold_units_30d::numeric / s.active_days_30d, 0), 0)
                    WHEN COALESCE(i.available_stock, 0) > 0
                    THEN 9999
                    ELSE 0
                END AS estimated_turnover_days,
                COALESCE(c.stagnant_snapshot_count, 0) AS stagnant_snapshot_count,
                COALESCE(c.estimated_stagnant_days, 0) AS estimated_stagnant_days,
                CASE
                    WHEN (
                        CASE
                            WHEN COALESCE(s.sold_units_30d, 0) > 0 AND COALESCE(s.active_days_30d, 0) > 0
                            THEN ROUND(COALESCE(i.available_stock, 0)::numeric / NULLIF(s.sold_units_30d::numeric / s.active_days_30d, 0), 0)
                            WHEN COALESCE(i.available_stock, 0) > 0
                            THEN 9999
                            ELSE 0
                        END
                    ) >= 60
                    OR COALESCE(c.stagnant_snapshot_count, 0) >= 3
                    THEN 'high'
                    WHEN (
                        CASE
                            WHEN COALESCE(s.sold_units_30d, 0) > 0 AND COALESCE(s.active_days_30d, 0) > 0
                            THEN ROUND(COALESCE(i.available_stock, 0)::numeric / NULLIF(s.sold_units_30d::numeric / s.active_days_30d, 0), 0)
                            WHEN COALESCE(i.available_stock, 0) > 0
                            THEN 9999
                            ELSE 0
                        END
                    ) >= 30
                    OR COALESCE(c.stagnant_snapshot_count, 0) >= 2
                    THEN 'medium'
                    ELSE 'low'
                END AS risk_level,
                (
                    COALESCE(i.inventory_value, 0) * 0.5
                    + COALESCE(c.estimated_stagnant_days, 0) * 10
                    + (
                        CASE
                            WHEN COALESCE(s.sold_units_30d, 0) > 0 AND COALESCE(s.active_days_30d, 0) > 0
                            THEN ROUND(COALESCE(i.available_stock, 0)::numeric / NULLIF(s.sold_units_30d::numeric / s.active_days_30d, 0), 0)
                            WHEN COALESCE(i.available_stock, 0) > 0
                            THEN 9999
                            ELSE 0
                        END
                    ) * 2
                ) AS clearance_priority_score
            FROM mart.inventory_snapshot_latest i
            LEFT JOIN sales_30d s
              ON i.platform_code = s.platform_code
             AND COALESCE(i.platform_sku, '') = COALESCE(s.platform_sku, '')
             AND COALESCE(i.product_sku, '') = COALESCE(s.product_sku, '')
            LEFT JOIN mart.inventory_snapshot_change c
              ON i.platform_code = c.platform_code
             AND COALESCE(i.platform_sku, '') = COALESCE(c.platform_sku, '')
             AND COALESCE(i.product_sku, '') = COALESCE(c.product_sku, '')
             AND COALESCE(i.warehouse_name, '') = COALESCE(c.warehouse_name, '')
            {snapshot_filter_sql}
            AND (
                CASE
                    WHEN COALESCE(s.sold_units_30d, 0) > 0 AND COALESCE(s.active_days_30d, 0) > 0
                    THEN ROUND(COALESCE(i.available_stock, 0)::numeric / NULLIF(s.sold_units_30d::numeric / s.active_days_30d, 0), 0)
                    WHEN COALESCE(i.available_stock, 0) > 0
                    THEN 9999
                    ELSE 0
                END
            ) >= :min_days
            ORDER BY clearance_priority_score DESC, inventory_value DESC, estimated_turnover_days DESC
            LIMIT :limit
            """.format(
                daily_orders_source=_daily_orders_raw_source_sql(),
                snapshot_filter_sql=(snapshot_filter_sql or "WHERE TRUE"),
            ),
            {
                "min_days": min_days,
                "limit": limit,
                "period_start": period_start,
                "period_end": period_end,
            },
        )
        ranked: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            normalized = dict(row)
            normalized["risk_level"] = normalized.get("risk_level") or _classify_inventory_backlog_risk(normalized)
            normalized["clearance_priority_score"] = normalized.get("clearance_priority_score") or _inventory_backlog_priority_score(normalized)
            normalized["rank"] = index
            ranked.append(normalized)
        return ranked

    async def get_business_overview_shop_racing(
        self,
        granularity: str,
        target_date: str,
        group_by: str = "shop",
        platform: str | None = None,
    ) -> list[dict[str, Any]]:
        period_key = _normalize_period_start(target_date)
        if granularity == "monthly":
            period_start, period_end = _resolve_business_overview_window(granularity, target_date)
            platform_filter_sql = " AND platform_code = :platform_code" if platform else ""
            monthly_fast_query = """
                WITH target_summary AS (
                    SELECT
                        tb.platform_code,
                        tb.shop_id,
                        CASE
                            WHEN SUM(CASE WHEN tb.breakdown_type = 'shop' THEN tb.target_amount ELSE 0 END) > 0
                            THEN SUM(CASE WHEN tb.breakdown_type = 'shop' THEN tb.target_amount ELSE 0 END)::numeric
                            ELSE SUM(CASE WHEN tb.breakdown_type = 'shop_time' THEN tb.target_amount ELSE 0 END)::numeric
                        END AS target_amount
                    FROM a_class.target_breakdown tb
                    INNER JOIN a_class.sales_targets st
                        ON st.id = tb.target_id
                       AND st.status = 'active'
                    WHERE tb.breakdown_type IN ('shop', 'shop_time')
                      AND tb.period_start <= :period_end
                      AND tb.period_end >= :period_start
                    GROUP BY tb.platform_code, tb.shop_id
                ),
                raw_orders AS (
                    {orders_source}
                ),
                mapped_orders AS (
                    SELECT
                        date_trunc('month', metric_date)::date AS period_key,
                        platform_code,
                        NULLIF(TRIM(COALESCE(shop_id, '')), '') AS source_shop_id,
                        NULLIF(TRIM(COALESCE(raw_data->>'店铺', raw_data->>'店铺名', raw_data->>'店铺名称', raw_data->>'store_name', raw_data->>'store_label_raw')), '') AS store_label_raw,
                        NULLIF(TRIM(COALESCE(raw_data->>'platform_shop_id', raw_data->>'shop_id', raw_data->>'平台店铺ID', raw_data->>'店铺ID')), '') AS source_platform_shop_id,
                        NULLIF(TRIM(COALESCE(raw_data->>'shop_account_id', raw_data->>'account_id', raw_data->>'店铺账号ID', raw_data->>'账号ID', raw_data->>'account')), '') AS source_shop_account_id,
                        COALESCE(raw_data->>'订单号', raw_data->>'订单ID', raw_data->>'订单编号', raw_data->>'ID', raw_data->>'order_id', raw_data->>'Order ID', raw_data->>'order_no') AS order_id,
                        CASE
                            WHEN COALESCE(raw_data->>'实付金额', raw_data->>'买家实付金额', raw_data->>'总收入', raw_data->>'buyer_payment_rmb', raw_data->>'buyer_payment', raw_data->>'买家支付(RMB)', raw_data->>'买家支付', raw_data->>'买家实付金额(RMB)', raw_data->>'paid_amount', raw_data->>'Paid Amount') IS NULL THEN NULL
                            ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'实付金额', raw_data->>'买家实付金额', raw_data->>'总收入', raw_data->>'buyer_payment_rmb', raw_data->>'buyer_payment', raw_data->>'买家支付(RMB)', raw_data->>'买家支付', raw_data->>'买家实付金额(RMB)', raw_data->>'paid_amount', raw_data->>'Paid Amount'), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
                        END AS paid_amount,
                        CASE
                            WHEN COALESCE(raw_data->>'利润(RMB)', raw_data->>'profit_rmb', raw_data->>'利润', raw_data->>'profit', raw_data->>'毛利', raw_data->>'Profit') IS NULL THEN NULL
                            ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'利润(RMB)', raw_data->>'profit_rmb', raw_data->>'利润', raw_data->>'profit', raw_data->>'毛利', raw_data->>'Profit'), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
                        END AS profit,
                        CASE
                            WHEN COALESCE(raw_data->>'产品数量', raw_data->>'商品数量', raw_data->>'数量', raw_data->>'件数', raw_data->>'销售数量', raw_data->>'出库数量', raw_data->>'product_quantity', raw_data->>'quantity', raw_data->>'qty', raw_data->>'item_quantity') IS NULL THEN NULL
                            ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'产品数量', raw_data->>'商品数量', raw_data->>'数量', raw_data->>'件数', raw_data->>'销售数量', raw_data->>'出库数量', raw_data->>'product_quantity', raw_data->>'quantity', raw_data->>'qty', raw_data->>'item_quantity'), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
                        END AS product_quantity,
                        data_hash,
                        ingest_timestamp
                    FROM raw_orders
                    WHERE date_trunc('month', metric_date)::date = :period_key
                    {platform_filter_sql}
                ),
                resolved_orders AS (
                    SELECT
                        m.period_key,
                        m.platform_code,
                        CASE
                            WHEN resolved.resolved_shop_id IS NOT NULL THEN resolved.resolved_shop_id
                            WHEN LOWER(COALESCE(m.source_shop_id, '')) IN ('', 'none', 'unknown', 'xihong') THEN 'unknown'
                            ELSE COALESCE(m.source_platform_shop_id, m.source_shop_account_id, m.store_label_raw, m.source_shop_id, 'unknown')
                        END AS shop_id,
                        m.order_id,
                        m.paid_amount,
                        m.product_quantity,
                        m.profit,
                        m.data_hash,
                        m.ingest_timestamp
                    FROM mapped_orders m
                    LEFT JOIN LATERAL (
                        SELECT c.resolved_shop_id, c.resolution_priority
                        FROM semantic.shop_identity_resolution_candidates c
                        WHERE c.platform_code = LOWER(COALESCE(m.platform_code, ''))
                          AND c.identity_value_normalized IN (
                              LOWER(COALESCE(m.source_platform_shop_id, '')),
                              LOWER(COALESCE(m.source_shop_account_id, '')),
                              LOWER(COALESCE(m.source_shop_id, '')),
                              {_source_shop_norm},
                              {_store_label_norm}
                          )
                        ORDER BY c.resolution_priority, c.resolved_shop_id
                        LIMIT 1
                    ) resolved ON TRUE
                ),
                deduplicated_orders AS (
                    SELECT *,
                           ROW_NUMBER() OVER (
                               PARTITION BY platform_code, COALESCE(shop_id, ''), data_hash
                               ORDER BY ingest_timestamp DESC
                           ) AS rn
                    FROM resolved_orders
                ),
                orders_agg AS (
                    SELECT
                        period_key,
                        platform_code,
                        shop_id,
                        SUM(paid_amount) AS gmv,
                        CASE WHEN COUNT(*) > 0 THEN COUNT(DISTINCT order_id)::numeric ELSE NULL END AS order_count,
                        SUM(product_quantity) AS total_items,
                        SUM(profit) AS profit
                    FROM deduplicated_orders
                    WHERE rn = 1
                    GROUP BY period_key, platform_code, shop_id
                ),
                combined AS (
                    SELECT
                        o.period_key,
                        o.platform_code,
                        o.shop_id,
                        o.gmv,
                        o.order_count,
                        CASE
                            WHEN o.gmv IS NOT NULL AND o.order_count > 0 THEN ROUND(o.gmv::numeric / o.order_count, 2)
                            WHEN o.gmv IS NOT NULL AND o.order_count = 0 AND o.gmv = 0 THEN 0
                            ELSE NULL
                        END AS avg_order_value,
                        CASE
                            WHEN o.total_items IS NOT NULL AND o.order_count > 0 THEN ROUND(o.total_items::numeric / o.order_count, 2)
                            WHEN o.total_items IS NOT NULL AND o.order_count = 0 AND o.total_items = 0 THEN 0
                            ELSE NULL
                        END AS attach_rate,
                        o.profit
                    FROM orders_agg o
                )
                SELECT
                    :granularity AS granularity,
                    src.period_key,
                    src.platform_code,
                    src.shop_id,
                    sa.shop_account_id,
                    sa.main_account_id,
                    ma.main_account_name,
                    sa.store_name AS account_store_name,
                    COALESCE(
                        NULLIF(TRIM(ds.shop_name), ''),
                        NULLIF(TRIM(sa.store_name), ''),
                        CASE
                            WHEN LOWER(COALESCE(src.shop_id, '')) IN ('', 'none', 'unknown') THEN NULL
                            ELSE src.shop_id
                        END
                    ) AS display_name,
                    src.gmv,
                    src.order_count,
                    src.avg_order_value,
                    src.attach_rate,
                    src.profit,
                    COALESCE(t.target_amount, 0) AS target_amount,
                    CASE
                        WHEN COALESCE(t.target_amount, 0) > 0 THEN ROUND(src.gmv::numeric * 100.0 / t.target_amount, 2)
                        ELSE 0::numeric
                    END AS achievement_rate
                FROM combined src
                LEFT JOIN target_summary t
                  ON t.platform_code = src.platform_code
                 AND COALESCE(t.shop_id, '') = COALESCE(src.shop_id, '')
                LEFT JOIN core.dim_shops ds
                  ON ds.platform_code = src.platform_code
                 AND ds.shop_id = src.shop_id
                LEFT JOIN core.shop_accounts sa
                  ON LOWER(COALESCE(sa.platform, '')) = LOWER(COALESCE(src.platform_code, ''))
                 AND (
                      COALESCE(sa.platform_shop_id, '') = COALESCE(src.shop_id, '')
                      OR COALESCE(sa.shop_account_id, '') = COALESCE(src.shop_id, '')
                      OR sa.id::text = COALESCE(src.shop_id, '')
                 )
                LEFT JOIN core.main_accounts ma
                  ON ma.main_account_id = sa.main_account_id
                WHERE src.period_key = :period_key
                """.format(
                    orders_source=_monthly_orders_raw_source_sql(),
                    platform_filter_sql=platform_filter_sql,
                    _source_shop_norm=_normalized_identity_sql("m.source_shop_id"),
                    _store_label_norm=_normalized_identity_sql("m.store_label_raw"),
            )
            try:
                rows = await self._fetch_rows_with_statement_timeout(
                    monthly_fast_query,
                    {
                        "granularity": granularity,
                        "period_key": period_key,
                        "period_start": period_start,
                        "period_end": period_end,
                        "platform_code": platform,
                    },
                    timeout_ms=120000,
                )
            except Exception:
                source_table, period_column = _comparison_source_for_granularity(granularity)
                query = """
                    SELECT
                        :granularity AS granularity,
                        src.{period_column} AS period_key,
                        src.platform_code,
                        src.shop_id,
                        sa.shop_account_id,
                        sa.main_account_id,
                        ma.main_account_name,
                        sa.store_name AS account_store_name,
                        COALESCE(
                            NULLIF(TRIM(ds.shop_name), ''),
                            NULLIF(TRIM(sa.store_name), ''),
                            CASE
                                WHEN LOWER(COALESCE(src.shop_id, '')) IN ('', 'none', 'unknown')
                                THEN NULL
                                ELSE src.shop_id
                            END
                        ) AS display_name,
                        src.gmv,
                        src.order_count,
                        src.avg_order_value,
                        src.attach_rate,
                        src.profit,
                        COALESCE(t.target_amount, 0) AS target_amount,
                        CASE
                            WHEN COALESCE(t.target_amount, 0) > 0
                            THEN ROUND(src.gmv::numeric * 100.0 / t.target_amount, 2)
                            ELSE 0::numeric
                        END AS achievement_rate
                    FROM {source_table} src
                    LEFT JOIN LATERAL (
                        WITH shop_target AS (
                            SELECT COALESCE(SUM(tb.target_amount)::numeric, 0::numeric) AS target_amount
                            FROM a_class.target_breakdown tb
                            INNER JOIN a_class.sales_targets st
                                ON st.id = tb.target_id
                               AND st.status = 'active'
                            WHERE tb.breakdown_type = 'shop'
                              AND tb.platform_code = src.platform_code
                              AND COALESCE(tb.shop_id, '') = COALESCE(src.shop_id, '')
                              AND tb.period_start <= :period_end
                              AND tb.period_end >= :period_start
                        ),
                        shop_time_target AS (
                            SELECT COALESCE(SUM(tb.target_amount)::numeric, 0::numeric) AS target_amount
                            FROM a_class.target_breakdown tb
                            INNER JOIN a_class.sales_targets st
                                ON st.id = tb.target_id
                               AND st.status = 'active'
                            WHERE tb.breakdown_type = 'shop_time'
                              AND tb.platform_code = src.platform_code
                              AND COALESCE(tb.shop_id, '') = COALESCE(src.shop_id, '')
                              AND tb.period_start <= :period_end
                              AND tb.period_end >= :period_start
                        )
                        SELECT
                            CASE
                                WHEN :granularity = 'monthly' AND (SELECT target_amount FROM shop_target) > 0
                                THEN (SELECT target_amount FROM shop_target)
                                WHEN (SELECT target_amount FROM shop_time_target) > 0
                                THEN (SELECT target_amount FROM shop_time_target)
                                ELSE (SELECT target_amount FROM shop_target)
                            END AS target_amount
                    ) t ON TRUE
                    LEFT JOIN core.dim_shops ds
                      ON ds.platform_code = src.platform_code
                     AND ds.shop_id = src.shop_id
                    LEFT JOIN core.shop_accounts sa
                      ON LOWER(COALESCE(sa.platform, '')) = LOWER(COALESCE(src.platform_code, ''))
                     AND (
                          COALESCE(sa.platform_shop_id, '') = COALESCE(src.shop_id, '')
                          OR COALESCE(sa.shop_account_id, '') = COALESCE(src.shop_id, '')
                          OR sa.id::text = COALESCE(src.shop_id, '')
                     )
                    LEFT JOIN core.main_accounts ma
                      ON ma.main_account_id = sa.main_account_id
                    WHERE src.{period_column} = :period_key
                    """.format(source_table=source_table, period_column=period_column)
                params = {
                    "granularity": granularity,
                    "period_key": period_key,
                    "period_start": period_start,
                    "period_end": period_end,
                }
                if platform:
                    query += " AND src.platform_code = :platform_code"
                    params["platform_code"] = platform
                rows = await self._fetch_rows_with_statement_timeout(query, params, timeout_ms=120000)
        else:
            source_table, period_column = _comparison_source_for_granularity(granularity)
            query = """
                SELECT
                    :granularity AS granularity,
                    src.{period_column} AS period_key,
                    src.platform_code,
                    src.shop_id,
                    sa.shop_account_id,
                    sa.main_account_id,
                    ma.main_account_name,
                    sa.store_name AS account_store_name,
                    COALESCE(
                        NULLIF(TRIM(ds.shop_name), ''),
                        NULLIF(TRIM(sa.store_name), ''),
                        CASE
                            WHEN LOWER(COALESCE(src.shop_id, '')) IN ('', 'none', 'unknown')
                            THEN NULL
                            ELSE src.shop_id
                        END
                    ) AS display_name,
                    src.gmv,
                    src.order_count,
                    src.avg_order_value,
                    src.attach_rate,
                    src.profit,
                    COALESCE(t.target_amount, 0) AS target_amount,
                    CASE
                        WHEN COALESCE(t.target_amount, 0) > 0
                        THEN ROUND(src.gmv::numeric * 100.0 / t.target_amount, 2)
                        ELSE 0::numeric
                    END AS achievement_rate
                FROM {source_table} src
                LEFT JOIN LATERAL (
                    WITH shop_target AS (
                        SELECT COALESCE(SUM(tb.target_amount)::numeric, 0::numeric) AS target_amount
                        FROM a_class.target_breakdown tb
                        INNER JOIN a_class.sales_targets st
                            ON st.id = tb.target_id
                           AND st.status = 'active'
                        WHERE tb.breakdown_type = 'shop'
                          AND tb.platform_code = src.platform_code
                          AND COALESCE(tb.shop_id, '') = COALESCE(src.shop_id, '')
                          AND tb.period_start <= :period_end
                          AND tb.period_end >= :period_start
                    ),
                    shop_time_target AS (
                        SELECT COALESCE(SUM(tb.target_amount)::numeric, 0::numeric) AS target_amount
                        FROM a_class.target_breakdown tb
                        INNER JOIN a_class.sales_targets st
                            ON st.id = tb.target_id
                           AND st.status = 'active'
                        WHERE tb.breakdown_type = 'shop_time'
                          AND tb.platform_code = src.platform_code
                          AND COALESCE(tb.shop_id, '') = COALESCE(src.shop_id, '')
                          AND tb.period_start <= :period_end
                          AND tb.period_end >= :period_start
                    )
                    SELECT
                        CASE
                            WHEN :granularity = 'monthly' AND (SELECT target_amount FROM shop_target) > 0
                            THEN (SELECT target_amount FROM shop_target)
                            WHEN (SELECT target_amount FROM shop_time_target) > 0
                            THEN (SELECT target_amount FROM shop_time_target)
                            ELSE (SELECT target_amount FROM shop_target)
                        END AS target_amount
                ) t ON TRUE
                LEFT JOIN core.dim_shops ds
                  ON ds.platform_code = src.platform_code
                 AND ds.shop_id = src.shop_id
                LEFT JOIN core.shop_accounts sa
                  ON LOWER(COALESCE(sa.platform, '')) = LOWER(COALESCE(src.platform_code, ''))
                 AND (
                      COALESCE(sa.platform_shop_id, '') = COALESCE(src.shop_id, '')
                      OR COALESCE(sa.shop_account_id, '') = COALESCE(src.shop_id, '')
                      OR sa.id::text = COALESCE(src.shop_id, '')
                 )
                LEFT JOIN core.main_accounts ma
                  ON ma.main_account_id = sa.main_account_id
                WHERE src.{period_column} = :period_key
                """.format(source_table=source_table, period_column=period_column)
            period_start, period_end = _resolve_business_overview_window(granularity, target_date)
            params = {
                "granularity": granularity,
                "period_key": period_key,
                "period_start": period_start,
                "period_end": period_end,
            }
            if platform:
                query += " AND src.platform_code = :platform_code"
                params["platform_code"] = platform
            rows = await self._fetch_rows_with_statement_timeout(query, params, timeout_ms=120000)

        if group_by == "platform":
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

        if group_by == "account":
            grouped: dict[str, dict[str, Any]] = {}
            for row in rows:
                account_id = row.get("shop_account_id")
                main_account_id = row.get("main_account_id")
                account_store_name = row.get("account_store_name")
                main_account_name = row.get("main_account_name")
                display_name = row.get("account_display_name") or " / ".join(
                    [
                        part
                        for part in (
                            (str(main_account_name).strip() if main_account_name else None),
                            (str(account_store_name).strip() if account_store_name else None),
                        )
                        if part
                    ]
                )
                fallback_name = display_name or account_store_name or account_id or "未匹配账号"
                key = account_id or f"unmatched::{row.get('platform_code') or 'unknown'}"
                grouped.setdefault(
                    key,
                    {
                        "name": fallback_name,
                        "platform_code": row.get("platform_code"),
                        "shop_id": "ALL",
                        "shop_account_id": account_id,
                        "main_account_id": main_account_id,
                        "main_account_name": main_account_name,
                        "is_unmatched": not bool(account_id),
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
                "name": row.get("display_name") or "未匹配店铺",
                "platform_code": row.get("platform_code"),
                "shop_id": row.get("shop_id") or "unknown",
                "shop_account_id": row.get("shop_account_id"),
                "main_account_id": row.get("main_account_id"),
                "main_account_name": row.get("main_account_name"),
                "is_unmatched": not bool(row.get("shop_account_id")),
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
        source_table, period_column = _comparison_source_for_granularity(granularity)
        query = """
            SELECT
                :granularity AS granularity,
                src.{period_column} AS period_key,
                src.platform_code,
                src.shop_id,
                sa.shop_account_id,
                sa.main_account_id,
                ma.main_account_name,
                sa.store_name AS account_store_name,
                COALESCE(
                    NULLIF(TRIM(ds.shop_name), ''),
                    NULLIF(TRIM(sa.store_name), ''),
                    CASE
                        WHEN LOWER(COALESCE(src.shop_id, '')) IN ('', 'none', 'unknown')
                        THEN NULL
                        ELSE src.shop_id
                    END
                ) AS display_name,
                src.visitor_count,
                src.page_views,
                src.conversion_rate
            FROM {source_table} src
            LEFT JOIN core.dim_shops ds
              ON ds.platform_code = src.platform_code
             AND ds.shop_id = src.shop_id
            LEFT JOIN core.shop_accounts sa
              ON LOWER(COALESCE(sa.platform, '')) = LOWER(COALESCE(src.platform_code, ''))
             AND (
                  COALESCE(sa.platform_shop_id, '') = COALESCE(src.shop_id, '')
                  OR COALESCE(sa.shop_account_id, '') = COALESCE(src.shop_id, '')
                  OR sa.id::text = COALESCE(src.shop_id, '')
             )
            LEFT JOIN core.main_accounts ma
              ON ma.main_account_id = sa.main_account_id
            WHERE src.{period_column} = :period_key
            """.format(period_column=period_column, source_table=source_table)
        params = {"granularity": granularity, "period_key": period_key}
        if platform:
            query += " AND src.platform_code = :platform_code"
            params["platform_code"] = platform
        rows = await self._fetch_rows(query, params)

        if dimension == "account":
            grouped: dict[str, dict[str, Any]] = {}
            for row in rows:
                account_id = row.get("shop_account_id")
                main_account_id = row.get("main_account_id")
                account_store_name = row.get("account_store_name")
                main_account_name = row.get("main_account_name")
                display_name = row.get("account_display_name") or " / ".join(
                    [
                        part
                        for part in (
                            (str(main_account_name).strip() if main_account_name else None),
                            (str(account_store_name).strip() if account_store_name else None),
                        )
                        if part
                    ]
                )
                fallback_name = display_name or account_store_name or account_id or "未匹配账号"
                key = account_id or f"unmatched::{row.get('platform_code') or 'unknown'}"
                grouped.setdefault(
                    key,
                    {
                        "name": fallback_name,
                        "platform_code": row.get("platform_code"),
                        "shop_id": "ALL",
                        "shop_account_id": account_id,
                        "main_account_id": main_account_id,
                        "main_account_name": main_account_name,
                        "is_unmatched": not bool(account_id),
                        "visitor_count": 0.0,
                        "page_views": 0.0,
                        "conversion_rate": None,
                    },
                )
                grouped[key]["visitor_count"] += _to_optional_float(row.get("visitor_count")) or 0.0
                grouped[key]["page_views"] += _to_optional_float(row.get("page_views")) or 0.0
            normalized_rows = list(grouped.values())
        else:
            normalized_rows = [
                {
                    "name": row.get("display_name")
                    or (
                        row.get("shop_id")
                        if str(row.get("shop_id") or "").strip().lower() not in {"", "none", "unknown"}
                        else "未匹配店铺"
                    ),
                    "platform_code": row.get("platform_code"),
                    "shop_id": row.get("shop_id") or "unknown",
                    "shop_account_id": row.get("shop_account_id"),
                    "main_account_id": row.get("main_account_id"),
                    "main_account_name": row.get("main_account_name"),
                    "is_unmatched": not bool(row.get("shop_account_id")),
                    "visitor_count": _to_optional_float(row.get("visitor_count")),
                    "page_views": _to_optional_float(row.get("page_views")),
                    "conversion_rate": _to_optional_float(row.get("conversion_rate")),
                }
                for row in rows
            ]
        return rank_traffic_rows(normalized_rows, dimension="pv")

    async def get_store_analysis_capabilities(
        self,
        platform: str,
        shop_id: str,
    ) -> dict[str, Any]:
        normalized_platform = str(platform or "").strip().lower()
        normalized_shop_id = str(shop_id or "").strip()
        query = """
            SELECT platform_code, shop_id, supports_hourly_daily, supported_daily_mode, supported_long_range_mode
            FROM api.store_analysis_capability_module
            WHERE platform_code = :platform_code
              AND shop_id = :shop_id
        """
        rows = await self._fetch_rows(
            query,
            {
                "platform_code": normalized_platform,
                "shop_id": normalized_shop_id,
            },
        )
        if rows:
            row = rows[0]
            return {
                "platform_code": row.get("platform_code"),
                "shop_id": row.get("shop_id"),
                "supports_hourly_daily": bool(row.get("supports_hourly_daily")),
                "supported_daily_mode": row.get("supported_daily_mode"),
                "supported_long_range_mode": row.get("supported_long_range_mode"),
            }
        return {
            "platform_code": normalized_platform,
            "shop_id": normalized_shop_id,
            "supports_hourly_daily": normalized_platform == "shopee",
            "supported_daily_mode": "hourly" if normalized_platform == "shopee" else "daily",
            "supported_long_range_mode": "monthly",
        }

    async def get_store_analysis_shops(
        self,
        platform: str,
    ) -> list[dict[str, Any]]:
        normalized_platform = str(platform or "").strip().lower()
        rows = await self._fetch_rows(
            """
            SELECT platform_code, shop_id, supported_daily_mode, supported_long_range_mode
            FROM api.store_analysis_capability_module
            WHERE platform_code = :platform_code
              AND COALESCE(shop_id, '') NOT IN ('', 'none', 'unknown')
            ORDER BY shop_id
            """,
            {"platform_code": normalized_platform},
        )
        return [
            {
                "platform_code": row.get("platform_code"),
                "shop_id": row.get("shop_id"),
                "supported_daily_mode": row.get("supported_daily_mode"),
                "supported_long_range_mode": row.get("supported_long_range_mode"),
            }
            for row in rows
        ]

    async def get_store_analysis_overview(
        self,
        platform: str,
        shop_id: str,
        granularity: str,
        target_date: str,
    ) -> dict[str, Any]:
        normalized_platform = str(platform or "").strip().lower()
        normalized_shop_id = str(shop_id or "").strip()
        requested_granularity = str(granularity or "").strip().lower()
        period_start, period_end = _resolve_store_analysis_window(requested_granularity, target_date)

        if requested_granularity in {"daily", "weekly", "monthly"}:
            trend_query = """
                SELECT gmv, order_count, avg_order_value, profit, target_amount, achievement_rate
                FROM api.business_overview_shop_racing_module
                WHERE granularity = :granularity
                  AND period_key = :period_key
                  AND platform_code = :platform_code
                  AND shop_id = :shop_id
            """
            trend_rows = await self._fetch_rows(
                trend_query,
                {
                    "granularity": requested_granularity,
                    "period_key": period_start,
                    "platform_code": normalized_platform,
                    "shop_id": normalized_shop_id,
                },
            )
        else:
            trend_query = """
                SELECT gmv, order_count, avg_order_value, profit, target_amount, achievement_rate
                FROM api.business_overview_shop_racing_module
                WHERE granularity = 'monthly'
                  AND period_key >= :period_start
                  AND period_key <= :period_end
                  AND platform_code = :platform_code
                  AND shop_id = :shop_id
            """
            trend_rows = await self._fetch_rows(
                trend_query,
                {
                    "period_start": period_start,
                    "period_end": period_end,
                    "platform_code": normalized_platform,
                    "shop_id": normalized_shop_id,
                },
            )

        gmv = _sum_present_values(trend_rows, "gmv")
        order_count_raw = _sum_present_values(trend_rows, "order_count")
        profit = _sum_present_values(trend_rows, "profit")
        target_amount = _sum_present_values(trend_rows, "target_amount")
        order_count = int(order_count_raw) if order_count_raw is not None else None
        avg_order_value = None
        if gmv is not None and order_count is not None:
            if order_count > 0:
                avg_order_value = round(gmv / order_count, 2)
            elif order_count == 0 and gmv == 0:
                avg_order_value = 0
        achievement_rate = None
        if gmv is not None and target_amount is not None:
            if target_amount > 0:
                achievement_rate = round(gmv * 100.0 / target_amount, 2)
            elif target_amount == 0 and gmv == 0:
                achievement_rate = 0

        period_month = date_cls(period_start.year, period_start.month, 1)
        operational_rows = await self._fetch_rows(
            """
            SELECT monthly_target, monthly_achievement_rate, time_gap, operating_result, operating_result_text
            FROM api.business_overview_operational_metrics_module
            WHERE period_month = :period_month
              AND platform_code = :platform_code
              AND shop_id = :shop_id
            """,
            {
                "period_month": period_month,
                "platform_code": normalized_platform,
                "shop_id": normalized_shop_id,
            },
        )
        operational = operational_rows[0] if operational_rows else {}

        return {
            "platform_code": normalized_platform,
            "shop_id": normalized_shop_id,
            "requested_granularity": requested_granularity,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "gmv": _round_or_none(gmv, 2),
            "order_count": order_count,
            "avg_order_value": avg_order_value,
            "achievement_rate": achievement_rate,
            "profit": _round_or_none(profit, 2),
            "monthly_target": _to_optional_float(operational.get("monthly_target")),
            "monthly_achievement_rate": _to_optional_float(operational.get("monthly_achievement_rate")),
            "time_gap": _to_optional_float(operational.get("time_gap")),
            "operating_result": _to_optional_float(operational.get("operating_result")),
            "operating_result_text": operational.get("operating_result_text"),
        }

    async def get_store_analysis_comparison(
        self,
        platform: str,
        shop_id: str,
        granularity: str,
        target_date: str,
    ) -> dict[str, Any]:
        previous_anchor = _previous_store_analysis_anchor(granularity, target_date)
        current_overview = await self.get_store_analysis_overview(platform, shop_id, granularity, target_date)
        current_summary = await self.get_store_analysis_traffic_summary(platform, shop_id, granularity, target_date)
        previous_overview = await self.get_store_analysis_overview(platform, shop_id, granularity, previous_anchor)
        previous_summary = await self.get_store_analysis_traffic_summary(platform, shop_id, granularity, previous_anchor)

        def _metric(current: Any, previous: Any) -> dict[str, Any]:
            cur = _to_optional_float(current)
            prev = _to_optional_float(previous)
            return {
                "current": _round_or_none(cur, 2),
                "previous": _round_or_none(prev, 2),
                "change_pct": _change_pct(cur, prev),
            }

        return {
            "requested_granularity": granularity,
            "current_period_label": current_overview.get("period_start"),
            "previous_period_label": previous_overview.get("period_start"),
            "metrics": {
                "gmv": _metric(current_overview.get("gmv"), previous_overview.get("gmv")),
                "order_count": _metric(current_overview.get("order_count"), previous_overview.get("order_count")),
                "visitor_count": _metric(current_summary.get("visitor_count"), previous_summary.get("visitor_count")),
                "page_views": _metric(current_summary.get("page_views"), previous_summary.get("page_views")),
                "page_views_per_visitor": _metric(
                    current_summary.get("page_views_per_visitor"),
                    previous_summary.get("page_views_per_visitor"),
                ),
                "profit": _metric(current_overview.get("profit"), previous_overview.get("profit")),
            },
        }

    async def get_store_analysis_top_products(
        self,
        platform: str,
        shop_id: str,
        granularity: str,
        target_date: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        period_start, period_end = _resolve_store_analysis_window(granularity, target_date)
        rows = await self._fetch_rows(
            """
            SELECT product_name, platform_sku, sales_amount, order_count, sales_volume, page_views, unique_visitors, conversion_rate
            FROM mart.product_day_kpi
            WHERE platform_code = :platform_code
              AND shop_id = :shop_id
              AND period_date >= :period_start
              AND period_date <= :period_end
            ORDER BY sales_amount DESC, order_count DESC, product_name
            LIMIT :limit
            """,
            {
                "platform_code": str(platform or "").strip().lower(),
                "shop_id": str(shop_id or "").strip(),
                "period_start": period_start,
                "period_end": period_end,
                "limit": limit,
            },
        )
        return [
            {
                "product_name": row.get("product_name"),
                "platform_sku": row.get("platform_sku"),
                "sales_amount": _to_optional_float(row.get("sales_amount")),
                "order_count": _to_optional_float(row.get("order_count")),
                "sales_volume": _to_optional_float(row.get("sales_volume")),
                "page_views": _to_optional_float(row.get("page_views")),
                "unique_visitors": _to_optional_float(row.get("unique_visitors")),
                "conversion_rate": _to_optional_float(row.get("conversion_rate")),
            }
            for row in rows
        ]

    async def get_store_analysis_traffic_summary(
        self,
        platform: str,
        shop_id: str,
        granularity: str,
        target_date: str,
    ) -> dict[str, Any]:
        period_start, period_end = _resolve_store_analysis_window(granularity, target_date)
        query = """
            SELECT period_start, period_end, visitor_count, page_views, conversion_rate, page_views_per_visitor
            FROM api.store_analysis_traffic_summary_module
            WHERE platform_code = :platform_code
              AND shop_id = :shop_id
              AND period_start >= :period_start
              AND period_end <= :period_end
        """
        rows = await self._fetch_rows(
            query,
            {
                "platform_code": str(platform or "").strip().lower(),
                "shop_id": str(shop_id or "").strip(),
                "period_start": period_start,
                "period_end": period_end,
            },
        )
        visitor_count = _sum_present_values(rows, "visitor_count")
        page_views = _sum_present_values(rows, "page_views")
        page_views_per_visitor = None
        if visitor_count is not None and page_views is not None:
            if visitor_count > 0:
                page_views_per_visitor = round(page_views / visitor_count, 2)
            elif visitor_count == 0 and page_views == 0:
                page_views_per_visitor = 0
        return {
            "platform_code": str(platform or "").strip().lower(),
            "shop_id": str(shop_id or "").strip(),
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "visitor_count": _round_or_none(visitor_count, 2),
            "page_views": _round_or_none(page_views, 2),
            "conversion_rate": None,
            "page_views_per_visitor": page_views_per_visitor,
        }

    async def get_store_analysis_traffic_trend(
        self,
        platform: str,
        shop_id: str,
        granularity: str,
        target_date: str,
    ) -> dict[str, Any]:
        normalized_platform = str(platform or "").strip().lower()
        normalized_shop_id = str(shop_id or "").strip()
        requested_granularity = str(granularity or "").strip().lower()
        effective_granularity = _resolve_store_analysis_effective_granularity(normalized_platform, requested_granularity)
        period_start, period_end = _resolve_store_analysis_window(requested_granularity, target_date)

        params: dict[str, Any] = {
            "platform_code": normalized_platform,
            "shop_id": normalized_shop_id,
            "requested_granularity": requested_granularity,
            "period_start": period_start,
        }

        if effective_granularity == "hourly":
            query = """
                SELECT requested_granularity, effective_granularity, period_key, visitor_count, page_views, conversion_rate
                FROM api.store_analysis_traffic_trend_module
                WHERE platform_code = :platform_code
                  AND shop_id = :shop_id
                  AND requested_granularity = :requested_granularity
                  AND period_key >= :period_start
                  AND period_key < :period_end_exclusive
                ORDER BY period_key
            """
            params["period_end_exclusive"] = period_end + timedelta(days=1)
        else:
            query = """
                SELECT requested_granularity, effective_granularity, period_key, visitor_count, page_views, conversion_rate
                FROM api.store_analysis_traffic_trend_module
                WHERE platform_code = :platform_code
                  AND shop_id = :shop_id
                  AND requested_granularity = :requested_granularity
                  AND period_key >= :period_start
                  AND period_key <= :period_end
                ORDER BY period_key
            """
            params["period_end"] = period_end

        rows = await self._fetch_rows(query, params)
        items = []
        for row in rows:
            visitor_count_value = _to_optional_float(row.get("visitor_count"))
            page_views_value = _to_optional_float(row.get("page_views"))
            if visitor_count_value is not None and page_views_value is not None:
                if visitor_count_value > 0:
                    page_views_per_visitor = round(page_views_value / visitor_count_value, 2)
                elif visitor_count_value == 0 and page_views_value == 0:
                    page_views_per_visitor = 0
                else:
                    page_views_per_visitor = None
            else:
                page_views_per_visitor = None

            items.append(
                {
                    "period_key": row.get("period_key").isoformat() if row.get("period_key") is not None else None,
                    "visitor_count": visitor_count_value,
                    "page_views": page_views_value,
                    "conversion_rate": None,
                    "page_views_per_visitor": page_views_per_visitor,
                }
            )
        return {
            "platform_code": normalized_platform,
            "shop_id": normalized_shop_id,
            "requested_granularity": requested_granularity,
            "effective_granularity": effective_granularity,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "items": items,
        }

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
        query = """
            SELECT *
            FROM api.annual_summary_kpi_module
            WHERE period_month >= :period_start
              AND period_month <= :period_end
            -- platform_month aggregate source
        """
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
