from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError, SQLAlchemyError

from backend.models.database import AsyncSessionLocal, apply_statement_timeout
from backend.services.inventory.inventory_dos_service import compute_dos
from backend.services.inventory.inventory_restock_service import (
    DEEP_STAGNANT_MIN_DAYS,
    MID_STAGNANT_MIN_DAYS,
    build_restock_tier_buckets,
    classify_restock_tier,
)
from backend.services.labor_cost_projection_service import (
    LABOR_COST_CALCULATION_VERSION,
)
from backend.utils.config import get_settings
from modules.core.logger import get_logger

logger = get_logger(__name__)

#: Dashboard 家族请求内的 DB 语句超时预算(毫秒)。
#: 前端 axios 对 /dashboard/* 的超时是 70 秒,这里必须严格小于它。
_DASHBOARD_STATEMENT_TIMEOUT_MS: int = get_settings().DB_STATEMENT_TIMEOUT_MS


def _to_float(value: Any) -> float:
    return float(value)


def _to_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


# ── 身份告警的原因归类（P2-3）────────────────────────────────────────
#
# 为什么要在**返回体里**就拆开
# ------------------------------
# 身份健康度原先把三类原因混在一个 ``warning_count`` 里:
# ``identity_conflict`` / ``traffic_without_order_match_due_to_identity`` /
# 行级的 ``identity_warning_code``。
#
# 混在一起会让排查方向跑偏 —— 实测 738 行 unknown 里 **93% 是 unmatched**
# (TikTok 改名没留曾用名别名), 只有 7% 是 ambiguous; 而 conflict 又是另一回事
# (同一个账号出现了多个 shop_id)。三者对应的处置完全不同:
#   unmatched ⇒ 去补别名/账号绑定;  ambiguous ⇒ 去消歧;  conflict ⇒ 去查数据串了。
#
# 所以这里给出**按原因分组**的 UV / PV / 订单数, 让人一眼看出该查哪一头。
IDENTITY_WARNING_REASONS = ("unmatched", "ambiguous", "conflict", "other")

_IDENTITY_WARNING_REASON_BY_CODE = {
    # 「认不出是哪家店」: 候选数 = 0
    "unmatched_shop_label": "unmatched",
    "missing_identity": "unmatched",
    # 「有多家候选」: 候选数 > 1 —— 不猜, 落 unknown
    "ambiguous_shop_label": "ambiguous",
    # 「同一个账号出现了多个 shop_id」: 流量与订单对不上 / 账号被多个键认领
    "identity_conflict": "conflict",
    "traffic_without_order_match_due_to_identity": "conflict",
    # [*] 2026-11 新增: 「行内编号与行内标签指向不同账号」。
    #     这是 2026-06 那批 Shopee 错配数据的原貌 —— 采集侧算错编号,
    #     标签被整组贴到别的店上。归到 conflict 类(「去查数据串了」),
    #     因为它的处置方向与 unmatched(去补别名)完全不同。
    "platform_shop_id_conflict": "conflict",
}


def _identity_warning_reason(warning_code: Any) -> str:
    """把一条身份告警的 ``warning_code`` 归到三大原因之一(外加 other)。"""
    code = str(warning_code or "").strip()
    return _IDENTITY_WARNING_REASON_BY_CODE.get(code, "other")


def _empty_identity_warning_breakdown() -> dict[str, dict[str, float]]:
    return {
        reason: {
            "warning_count": 0,
            "visitor_count": 0.0,
            "page_views": 0.0,
            "order_count": 0.0,
        }
        for reason in IDENTITY_WARNING_REASONS
    }


# ── 采集期的身份异常（P2-2）───────────────────────────────────────────
#
# 语义层告警是**事后**信号: 数据已经落错、已经进了看板。
# 探测状态机是**事前**信号: 采集时读到的平台店铺编号就对不上账号了。
#
# 两层都要看 —— 事后信号告诉你「哪块数据不可信」, 事前信号告诉你
# 「下一次采集还会继续错」。只留事后信号, 问题会反复出现。
def _empty_discovery_issue_summary() -> dict[str, Any]:
    return {
        "issue_count": 0,
        "by_status": {},
        "issues": [],
    }


def _round_or_none(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _sum_present_values(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [
        _to_optional_float(row.get(key)) for row in rows if row.get(key) is not None
    ]
    if not values:
        return None
    return sum(values)


def _to_optional_int(value: float | None) -> int | None:
    if value is None:
        return None
    return int(value)


def _percent_or_none(
    numerator: int | float | None, denominator: int | float | None
) -> float | None:
    if numerator is None or denominator is None:
        return None
    if denominator > 0:
        return round(float(numerator) * 100.0 / float(denominator), 2)
    if denominator == 0 and numerator == 0:
        return 0
    return None


def _ratio_or_none(
    numerator: int | float | None, denominator: int | float | None
) -> float | None:
    if numerator is None or denominator is None:
        return None
    if denominator > 0:
        return round(float(numerator) / float(denominator), 2)
    if denominator == 0 and numerator == 0:
        return 0
    return None


def _sort_numeric(value: Any) -> float:
    maybe_value = _to_optional_float(value)
    return maybe_value if maybe_value is not None else float("-inf")


def _parse_datetimeish(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text_value = str(value).strip()
    if not text_value:
        return None
    normalized = text_value[:-1] + "+00:00" if text_value.endswith("Z") else text_value
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _month_time_progress_pct(
    period_month: date_cls, today: date_cls | None = None
) -> float:
    current_day = today or date_cls.today()
    selected_month = (period_month.year, period_month.month)
    current_month = (current_day.year, current_day.month)
    if selected_month < current_month:
        return 100.0
    if selected_month > current_month:
        return 0.0

    next_month = (period_month + timedelta(days=31)).replace(day=1)
    days_in_month = (next_month - period_month).days
    return round(current_day.day * 100.0 / days_in_month, 2)


def _is_empty_period_rows(
    rows: list[dict[str, Any]], *, core_keys: tuple[str, ...]
) -> bool:
    if not rows:
        return True
    for row in rows:
        for key in core_keys:
            if row.get(key) is not None:
                return False
    return True


def reduce_business_overview_kpi_rows(
    rows: list[dict[str, Any]],
    labor_efficiency: float | None = 0,
) -> dict[str, Any]:
    if _is_empty_period_rows(
        rows,
        core_keys=(
            "gmv",
            "order_count",
            "visitor_count",
            "page_views",
            "impressions",
            "profit",
        ),
    ):
        return {
            "gmv": 0,
            "order_count": 0,
            "visitor_count": 0,
            "page_views": 0,
            "impressions": 0,
            "conversion_rate": None,
            "uv_conversion_rate": None,
            "pv_conversion_rate": None,
            "visit_rate": None,
            "browse_depth": None,
            "exposure_order_rate": None,
            "avg_order_value": None,
            "attach_rate": None,
            "labor_efficiency": 0,
            "profit": 0,
        }

    total_gmv = _sum_present_values(rows, "gmv")
    total_orders_raw = _sum_present_values(rows, "order_count")
    total_visitors_raw = _sum_present_values(rows, "visitor_count")
    total_page_views_raw = _sum_present_values(rows, "page_views")
    total_impressions_raw = _sum_present_values(rows, "impressions")
    total_items = _sum_present_values(rows, "total_items")
    total_profit = _sum_present_values(rows, "profit")

    total_orders = _to_optional_int(total_orders_raw)
    total_visitors = _to_optional_int(total_visitors_raw)
    total_page_views = _to_optional_int(total_page_views_raw)
    total_impressions = _to_optional_int(total_impressions_raw)

    uv_conversion_rate = _percent_or_none(total_orders, total_visitors)
    pv_conversion_rate = _percent_or_none(total_orders, total_page_views)
    visit_rate = _percent_or_none(total_visitors, total_impressions)
    browse_depth = _ratio_or_none(total_page_views, total_visitors)
    exposure_order_rate = _percent_or_none(total_orders, total_impressions)

    if total_orders is None or total_gmv is None:
        avg_order_value = None
    elif total_orders > 0:
        avg_order_value = round((total_gmv / total_orders), 2)
    else:
        avg_order_value = None

    if total_orders is None or total_items is None:
        attach_rate = None
    elif total_orders > 0:
        attach_rate = round((total_items / total_orders), 2)
    else:
        attach_rate = None

    return {
        "gmv": _round_or_none(total_gmv, 2) or 0,
        "order_count": total_orders if total_orders is not None else 0,
        "visitor_count": total_visitors,
        "page_views": total_page_views,
        "impressions": total_impressions,
        "conversion_rate": uv_conversion_rate,
        "uv_conversion_rate": uv_conversion_rate,
        "pv_conversion_rate": pv_conversion_rate,
        "visit_rate": visit_rate,
        "browse_depth": browse_depth,
        "exposure_order_rate": exposure_order_rate,
        "avg_order_value": avg_order_value,
        "attach_rate": attach_rate,
        "labor_efficiency": _round_or_none(labor_efficiency, 2),
        "profit": _round_or_none(total_profit, 2) or 0,
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

    platform_codes = {
        str(row.get("platform_code"))
        for row in rows
        if row.get("platform_code") is not None
    }
    currency_codes = {
        str(row.get("currency_code"))
        for row in rows
        if row.get("currency_code") is not None
    }

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


def _point_change(current: Any, previous: Any) -> float | None:
    current_value = _to_optional_float(current)
    previous_value = _to_optional_float(previous)
    if current_value is None or previous_value is None:
        return None
    return round(current_value - previous_value, 2)


def _profit_margin_value(profit: Any, gmv: Any) -> float | None:
    profit_value = _to_optional_float(profit)
    gmv_value = _to_optional_float(gmv)
    if profit_value is None or gmv_value is None or gmv_value == 0:
        return None
    return round((profit_value * 100.0) / gmv_value, 2)


def _row_period_key(row: dict[str, Any]) -> date_cls | None:
    value = row.get("period_key")
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date_cls):
        return value
    return _normalize_period_start(str(value))


def _shop_racing_identity_key(row: dict[str, Any]) -> tuple[Any, Any]:
    return (row.get("platform_code"), row.get("shop_id"))


def _traffic_identity_key(row: dict[str, Any]) -> tuple[Any, Any]:
    return (row.get("platform_code"), row.get("shop_id"))


def _attach_shop_racing_change_fields(
    current: dict[str, Any],
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    previous = previous or {}
    current_profit_margin = _profit_margin_value(
        current.get("profit"), current.get("gmv")
    )
    previous_profit_margin = _profit_margin_value(
        previous.get("profit"), previous.get("gmv")
    )
    current["gmv_previous"] = _to_optional_float(previous.get("gmv"))
    current["profit_previous"] = _to_optional_float(previous.get("profit"))
    current["order_count_previous"] = _to_optional_float(previous.get("order_count"))
    current["avg_order_value_previous"] = _to_optional_float(
        previous.get("avg_order_value")
    )
    current["profit_margin_previous"] = previous_profit_margin
    current["achievement_rate_previous"] = _to_optional_float(
        previous.get("achievement_rate")
    )
    current["gmv_change_rate"] = _change_pct(
        _to_optional_float(current.get("gmv")),
        _to_optional_float(previous.get("gmv")),
    )
    current["profit_change_rate"] = _change_pct(
        _to_optional_float(current.get("profit")),
        _to_optional_float(previous.get("profit")),
    )
    current["order_count_change_rate"] = _change_pct(
        _to_optional_float(current.get("order_count")),
        _to_optional_float(previous.get("order_count")),
    )
    current["avg_order_value_change_rate"] = _change_pct(
        _to_optional_float(current.get("avg_order_value")),
        _to_optional_float(previous.get("avg_order_value")),
    )
    current["profit_margin_change_value"] = _point_change(
        current_profit_margin,
        previous_profit_margin,
    )
    current["achievement_rate_change_value"] = _point_change(
        current.get("achievement_rate"),
        previous.get("achievement_rate"),
    )
    return current


def _attach_traffic_change_fields(
    current: dict[str, Any],
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    previous = previous or {}
    current["visitor_count_previous"] = _to_optional_float(
        previous.get("visitor_count")
    )
    current["page_views_previous"] = _to_optional_float(previous.get("page_views"))
    current["uv_conversion_rate_previous"] = _to_optional_float(
        previous.get("uv_conversion_rate")
    )
    current["pv_conversion_rate_previous"] = _to_optional_float(
        previous.get("pv_conversion_rate")
    )
    current["visitor_count_change_rate"] = _change_pct(
        _to_optional_float(current.get("visitor_count")),
        _to_optional_float(previous.get("visitor_count")),
    )
    current["page_views_change_rate"] = _change_pct(
        _to_optional_float(current.get("page_views")),
        _to_optional_float(previous.get("page_views")),
    )
    current["uv_conversion_rate_change_value"] = _point_change(
        current.get("uv_conversion_rate"),
        previous.get("uv_conversion_rate"),
    )
    current["pv_conversion_rate_change_value"] = _point_change(
        current.get("pv_conversion_rate"),
        previous.get("pv_conversion_rate"),
    )
    return current


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
        achievement_rate = round(
            metrics["sales_amount"]["today"] * 100.0 / target_sales_amount, 2
        )
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
    if not rows:
        return {
            "sales_amount": 0,
            "sales_quantity": 0,
            "order_count": 0,
            "total_items": 0,
            "traffic": 0,
            "conversion_rate": None,
            "avg_order_value": None,
            "attach_rate": None,
            "profit": 0,
            "target_sales_amount": None,
            "target_sales_quantity": None,
        }

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
    else:
        conversion_rate = None

    if sales_amount is None or effective_order_count is None:
        avg_order_value = None
    elif effective_order_count > 0:
        avg_order_value = round((sales_amount / effective_order_count), 2)
    else:
        avg_order_value = None

    if effective_total_items is None or effective_order_count is None:
        attach_rate = None
    elif effective_order_count > 0:
        attach_rate = round((effective_total_items / effective_order_count), 2)
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


def _filter_rows_by_period_key(
    rows: list[dict[str, Any]], target_period: date_cls
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
    """按「距上次进货时长」筛选与排序。

    2026-10-24：判据从 DOS 换成距上次进货时长——DOS 的分母（窗口销量）在增量模式下
    只会刷新 13.6% 的 SKU，不能当判定依据；距上次进货时长是事件时刻，始终准确。
    ``min_days`` 现在指**距上次进货天数门槛**。
    """
    filtered = [
        dict(row)
        for row in rows
        if (_to_optional_float(row.get("days_since_restock")) or float("-inf"))
        >= min_days
    ]
    for row in filtered:
        row["restock_tier"] = _classify_inventory_backlog_restock_tier(row)
    filtered.sort(
        key=lambda row: (
            _sort_numeric(row.get("days_since_restock")),
            _sort_numeric(row.get("inventory_value")),
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


def _classify_inventory_backlog_restock_tier(row: dict[str, Any]) -> str:
    """滞销档位：**走 inventory_restock_service 的唯一实现**，不在这里重写阈值。"""
    days_since_restock = _to_optional_float(row.get("days_since_restock"))
    return classify_restock_tier(
        int(days_since_restock) if days_since_restock is not None else None
    )


def _compute_checklist_dos_sales90(row: dict[str, Any]) -> float | None:
    """DOS 参考值：**走 inventory_dos_service 的唯一实现**。

    只作展示参考，不参与任何判定（分母在增量模式下不新鲜）。
    """
    value = compute_dos(
        available_stock=row.get("available_stock"),
        window_sales=row.get("checklist_sales_90d"),
        window_days=90,
    )
    return float(value) if value is not None else None


def _normalize_inventory_backlog_sold_units_30d(row: dict[str, Any]) -> int | None:
    """近30天销量：**库存数据域口径**，不是订单数据域口径。

    数值来自 `mart.inventory_state.checklist_sales_30d`
    （妙手仓库清单里每个「仓库×SKU」自带的「近30天销量数据」），
    与库存**同一次采集、同一份文件** ⇒ 库存和销量不会互相打架。

    刷新时机：库存数据域**增量更新一次，它才刷新一次** —— 这是**采集时点**的
    窗口销量，**不是实时动销速度**，也不是订单事实口径。

    归一化规则（与 SKU 级滞销清单 `sku_clearance_service` 逐字一致）：
      - 取不到 → None（**不是 0**）：None = 没有这个数，0 = 确实一件没卖；
      - 有值 → 整数件数（源列是 NUMERIC(18,2)）。
    """
    value = _to_optional_float(row.get("checklist_sales_30d"))
    if value is None:
        return None
    return int(value)


def summarize_inventory_backlog_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """滞销汇总：总库存价值 + **业务定价档位**分组（0/60/90/120，SKU 级）。

    2026-11-29：口径从「看板自造的 <30 / 90~180 / >=180」改成
    **业务定价档位**（``finance.sku_pricing_policies``：0/60/90/120）——
    与商品中心定价档**同一套**，30~90 天不再无档。

    为什么
    ------
    旧口径把 30~90 天整段**漏掉**（无档）：业务上 60 天起就要打折（滞销），
    看板却显示「活跃」；而且行数 / SKU 数只覆盖 <30 的行，
    与「货值是全量」自相矛盾。

    分组实现
    --------
    ``build_restock_tier_buckets``（``inventory_restock_service``，**唯一实现**）——
    SKU 级库龄取各仓最长，与商品中心定价档完全一致；
    SQL 视图那份分组由守护测试逐档锁定一致。

    旧标准指标（``deep_stagnant_value`` ≥180 天等）**保留原义**：
    它们是「深度积压」这一**独立指标**（见指标词典），不是档位分组。
    """
    tier_summary = build_restock_tier_buckets(rows)
    total_value = float(tier_summary["total_value"])

    deep_value = sum(
        (_to_optional_float(row.get("inventory_value")) or 0.0)
        for row in rows
        if (_to_optional_float(row.get("days_since_restock")) or 0.0)
        >= DEEP_STAGNANT_MIN_DAYS
    )
    mid_value = sum(
        (_to_optional_float(row.get("inventory_value")) or 0.0)
        for row in rows
        if MID_STAGNANT_MIN_DAYS
        <= (_to_optional_float(row.get("days_since_restock")) or 0.0)
        < DEEP_STAGNANT_MIN_DAYS
    )
    backlog_value = deep_value + mid_value

    buckets: list[dict[str, Any]] = []
    for bucket in tier_summary["buckets"]:
        item = dict(bucket)
        item["ratio"] = (
            round(float(item["value"]) * 100.0 / total_value, 2) if total_value else 0
        )
        buckets.append(item)

    return {
        "total_value": round(total_value, 2),
        "total_quantity": int(tier_summary["total_quantity"]),
        # **全量**行数 / SKU 数：与 total_value 同口径
        "total_row_count": int(tier_summary["total_row_count"]),
        "total_sku_count": int(tier_summary["total_sku_count"]),
        # 距上次进货时长取不到的行：单独暴露，不静默当成「活跃」
        "unknown_restock_row_count": int(tier_summary["unknown_row_count"]),
        # 业务定价档位分组（4 档互斥，货值与 SKU 数都能加起来）
        "restock_tiers": buckets,
        # 旧标准指标（口径不变）
        "deep_stagnant_value": round(deep_value, 2),
        "deep_stagnant_ratio": (
            round(deep_value * 100.0 / total_value, 2) if total_value else 0
        ),
        "mid_stagnant_value": round(mid_value, 2),
        "mid_stagnant_ratio": (
            round(mid_value * 100.0 / total_value, 2) if total_value else 0
        ),
        "backlog_value": round(backlog_value, 2),
        "backlog_ratio": (
            round(backlog_value * 100.0 / total_value, 2) if total_value else 0
        ),
    }


def rank_shop_racing_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = [dict(row) for row in rows]
    ordered.sort(
        key=lambda row: (
            _sort_numeric(row.get("gmv")),
            _sort_numeric(row.get("profit")),
            _sort_numeric(row.get("order_count")),
        ),
        reverse=True,
    )
    for index, row in enumerate(ordered, start=1):
        row["rank"] = index
    return ordered


def rank_traffic_rows(
    rows: list[dict[str, Any]], dimension: str = "visitor"
) -> list[dict[str, Any]]:
    ordered = [dict(row) for row in rows]
    if dimension in {"pv", "page_views", "traffic", "shop", "account"}:
        ordered.sort(key=lambda row: _sort_numeric(row.get("page_views")), reverse=True)
    else:
        ordered.sort(
            key=lambda row: _sort_numeric(row.get("visitor_count")), reverse=True
        )
    for index, row in enumerate(ordered, start=1):
        row["rank"] = index
    return ordered


def _business_overview_identity_select_sql() -> str:
    return """
                sa.shop_account_id,
                sa.main_account_id,
                ma.main_account_name,
                sa.store_name AS account_store_name,
                NULLIF(
                    TRIM(
                        CONCAT_WS(
                            ' / ',
                            NULLIF(TRIM(ma.main_account_name), ''),
                            NULLIF(TRIM(sa.store_name), '')
                        )
                    ),
                    ''
                ) AS account_display_name,
                COALESCE(
                    NULLIF(TRIM(ds.shop_name), ''),
                    NULLIF(TRIM(sa.store_name), ''),
                    CASE
                        WHEN LOWER(COALESCE(src.shop_id, '')) IN ('', 'none', 'unknown')
                        THEN NULL
                        ELSE src.shop_id
                    END
                ) AS display_name"""


def _business_overview_identity_join_sql() -> str:
    return """
            LEFT JOIN core.dim_shops ds
              ON LOWER(COALESCE(ds.platform_code, '')) = LOWER(COALESCE(src.platform_code, ''))
             AND COALESCE(ds.shop_id, '') = COALESCE(src.shop_id, '')
            LEFT JOIN core.shop_accounts sa
              ON LOWER(COALESCE(sa.platform, '')) = LOWER(COALESCE(src.platform_code, ''))
             AND (
                  COALESCE(sa.platform_shop_id, '') = COALESCE(src.shop_id, '')
                  OR COALESCE(sa.shop_account_id, '') = COALESCE(src.shop_id, '')
                  OR sa.id::text = COALESCE(src.shop_id, '')
             )
            LEFT JOIN core.main_accounts ma
              ON ma.main_account_id = sa.main_account_id"""


def _business_overview_shop_racing_source_table(granularity: str) -> str:
    if str(granularity or "").strip().lower() == "monthly":
        return "api.business_overview_shop_racing_monthly_module"
    return "api.business_overview_shop_racing_module"


def _normalize_period_start(value: str) -> date_cls:
    value = value.strip()
    if len(value) == 7:
        return datetime.strptime(f"{value}-01", "%Y-%m-%d").date()
    if len(value) == 10:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    if len(value) == 4:
        return datetime.strptime(f"{value}-01-01", "%Y-%m-%d").date()
    raise ValueError("Unsupported period/date format")


def _resolve_business_overview_window(
    granularity: str, target_date: str
) -> tuple[date_cls, date_cls]:
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


def _start_of_next_month(day: date_cls) -> date_cls:
    if day.month == 12:
        return date_cls(day.year + 1, 1, 1)
    return date_cls(day.year, day.month + 1, 1)


class PostgresqlDashboardService:
    def __init__(self) -> None:
        import asyncio

        self._column_cache: dict[tuple[str, str], set[str]] = {}
        self._column_cache_lock = asyncio.Lock()

    async def _get_table_columns(self, table_schema: str, table_name: str) -> set[str]:
        cache_key = (table_schema, table_name)
        cached = self._column_cache.get(cache_key)
        if cached is not None:
            return cached

        async with self._column_cache_lock:
            cached = self._column_cache.get(cache_key)
            if cached is not None:
                return cached

            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = :table_schema
                          AND table_name = :table_name
                        """
                    ),
                    {"table_schema": table_schema, "table_name": table_name},
                )
                columns = {
                    str(row[0])
                    for row in result.fetchall()
                    if row and row[0] is not None
                }

            self._column_cache[cache_key] = columns
            return columns

    async def _fetch_rows(
        self, query: str, params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        async with AsyncSessionLocal() as session:
            # [*] 2026-10-30: 请求内局部收紧 DB 语句超时。
            # Dashboard 家族的端 axios 超时是 70 秒,DB 必须严格小于它,
            # 否则前端先报「网络连接失败」而后端还在跑(超时预算倒置)。
            await apply_statement_timeout(session, _DASHBOARD_STATEMENT_TIMEOUT_MS)
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
            await session.execute(
                text(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
            )
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
                if "employee_identity_type" in orig_message:
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
                if (
                    "a_class.employees" in orig_message
                    or 'relation "a_class.employees"' in orig_message
                ):
                    return 0
                raise
            value = result.scalar_one_or_none()
            return int(value or 0)

    async def _load_inventory_backlog_summary(
        self,
        period_start: date_cls | None = None,
        period_end: date_cls | None = None,
    ) -> dict[str, Any]:
        """滞销汇总：**取行 → Python 按业务定价档位分组**。

        为什么改成「取行」
        ------------------
        旧实现有**两条 SQL 路径**（带期间走一段 CASE、不带期间读视图），
        两份 CASE 各写一遍阈值 ⇒ 迟早漂移；而且阈值写死在 SQL 里，
        与商品中心的档位表对不上。

        现在两条路径**共用同一个 Python 汇总**（唯一实现
        ``build_restock_tier_buckets``）⇒ 带不带期间、SQL 视图还是 Python，
        口径都一模一样。
        """
        where_clauses: list[str] = []
        params: dict[str, Any] = {}
        if period_start is not None and period_end is not None:
            where_clauses.append("snapshot_date >= :period_start")
            where_clauses.append("snapshot_date <= :period_end")
            params = {"period_start": period_start, "period_end": period_end}

        rows = await self._fetch_rows(
            """
            SELECT
                platform_code,
                product_sku,
                available_stock,
                inventory_value,
                days_since_restock
            FROM api.business_overview_inventory_backlog_module
            {where_clause}
            """.format(
                where_clause=(
                    ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
                )
            ),
            params,
        )
        return summarize_inventory_backlog_rows(rows)

    async def _load_ranked_inventory_backlog_module_rows(
        self,
        *,
        source_table: str,
        min_days: int,
        limit: int,
        period_start: date_cls | None = None,
        period_end: date_cls | None = None,
    ) -> list[dict[str, Any]]:
        where_clauses = ["days_since_restock >= :min_days"]
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
            ORDER BY days_since_restock DESC, inventory_value DESC
            LIMIT :limit
            """.format(
                source_table=source_table, where_clause=" AND ".join(where_clauses)
            ),
            params,
        )
        ranked: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            normalized = dict(row)
            normalized["restock_tier"] = _classify_inventory_backlog_restock_tier(
                normalized
            )
            # DOS 只作参考值：分母不新鲜，不参与判定，但运营需要这个量级感
            normalized["checklist_dos_sales90"] = _compute_checklist_dos_sales90(
                normalized
            )
            # 近30天销量（库存数据域口径）：库存增量更新时才刷新一次，
            # 不是订单口径、不是实时动销速度。缺失保留 None，不填 0。
            normalized["sold_units_30d"] = _normalize_inventory_backlog_sold_units_30d(
                normalized
            )
            normalized["rank"] = index
            ranked.append(normalized)
        return ranked

    async def _load_target_summary(
        self,
        granularity: str,
        period_start: date_cls,
        period_end: date_cls,
        platform: str | None = None,
        shop_id: str | None = None,
    ) -> dict[str, float]:
        async with AsyncSessionLocal() as session:
            if granularity == "monthly":
                if platform or shop_id:
                    try:
                        query = """
                            WITH matching_shop_rows AS (
                                SELECT
                                    tb.target_amount,
                                    tb.target_quantity,
                                    (
                                        tb.period_start IS NOT NULL
                                        AND tb.period_end IS NOT NULL
                                        AND tb.period_start <= :period_end
                                        AND tb.period_end >= :period_start
                                    ) AS is_period_scoped,
                                    (
                                        tb.period_start IS NULL
                                        AND tb.period_end IS NULL
                                    ) AS is_legacy_unscoped
                                FROM a_class.target_breakdown tb
                                INNER JOIN a_class.sales_targets st ON st.id = tb.target_id
                                WHERE st.status = 'active'
                                  AND st.period_start <= :period_start
                                  AND st.period_end >= :period_end
                                  AND tb.breakdown_type = 'shop'
                            """
                        params: dict[str, Any] = {
                            "period_start": period_start,
                            "period_end": period_end,
                        }
                        if platform:
                            query += " AND LOWER(COALESCE(tb.platform_code, '')) = LOWER(:platform)"
                            params["platform"] = platform
                        if shop_id:
                            query += " AND tb.shop_id = :shop_id"
                            params["shop_id"] = shop_id
                        query += """
                            ),
                            preferred_shop_rows AS (
                                SELECT target_amount, target_quantity
                                FROM matching_shop_rows
                                WHERE is_period_scoped
                                UNION ALL
                                SELECT target_amount, target_quantity
                                FROM matching_shop_rows
                                WHERE is_legacy_unscoped
                                  AND NOT EXISTS (
                                      SELECT 1
                                      FROM matching_shop_rows
                                      WHERE is_period_scoped
                                  )
                            )
                            SELECT
                                SUM(target_amount) AS target_amount,
                                SUM(target_quantity) AS target_quantity
                            FROM preferred_shop_rows
                        """
                        result = await session.execute(text(query), params)
                    except Exception:
                        await session.rollback()
                        columns = await self._get_table_columns(
                            "a_class", "sales_targets_a"
                        )
                        year_month_value = period_start.strftime("%Y-%m")
                        if {"year_month", "target_sales_amount"}.issubset(columns):
                            target_filters = ""
                            target_params: dict[str, Any] = {
                                "year_month": year_month_value
                            }
                            if platform and "platform_code" in columns:
                                target_filters += " AND LOWER(COALESCE(platform_code, '')) = LOWER(:platform)"
                                target_params["platform"] = platform
                            if shop_id and "shop_id" in columns:
                                target_filters += " AND shop_id = :shop_id"
                                target_params["shop_id"] = shop_id
                            result = await session.execute(
                                text(
                                    f"""
                                    SELECT
                                        SUM(target_sales_amount) AS target_amount,
                                        SUM(target_quantity) AS target_quantity
                                    FROM a_class.sales_targets_a
                                    WHERE year_month = :year_month
                                    {target_filters}
                                    """
                                ),
                                target_params,
                            )
                        else:
                            target_filters = ""
                            target_params = {"year_month": year_month_value}
                            if platform and "platform_code" in columns:
                                target_filters += " AND LOWER(COALESCE(platform_code, '')) = LOWER(:platform)"
                                target_params["platform"] = platform
                            if shop_id:
                                target_filters += ' AND "店铺ID" = :shop_id'
                                target_params["shop_id"] = shop_id
                            result = await session.execute(
                                text(
                                    f"""
                                    SELECT
                                        COALESCE(SUM("目标销售额"), 0) AS target_amount,
                                        COALESCE(SUM("目标订单数"), 0) AS target_quantity
                                    FROM a_class.sales_targets_a
                                    WHERE "年月" = :year_month
                                    {target_filters}
                                    """
                                ),
                                target_params,
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
                            columns = await self._get_table_columns(
                                "a_class", "sales_targets_a"
                            )
                            year_month_value = period_start.strftime("%Y-%m")
                            if {"year_month", "target_sales_amount"}.issubset(columns):
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
                                    {"year_month": year_month_value},
                                )
                            else:
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
                                    {"year_month": year_month_value},
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
                    query += (
                        " AND LOWER(COALESCE(tb.platform_code, '')) = LOWER(:platform)"
                    )
                    params["platform"] = platform
                if shop_id:
                    query += " AND tb.shop_id = :shop_id"
                    params["shop_id"] = shop_id

                result = await session.execute(text(query), params)

            row = result.fetchone()
            return {
                "target_amount": _to_optional_float(row[0]) if row else None,
                "target_quantity": _to_optional_float(row[1]) if row else None,
            }

    async def _load_operating_expenses_summary(
        self,
        period_month: date_cls,
        *,
        platform: str | None = None,
        shop_id: str | None = None,
    ) -> float | None:
        """Use the same persisted expense and projected-labor sources as expense management."""
        year_month = period_month.strftime("%Y-%m")
        async with AsyncSessionLocal() as session:
            params: dict[str, Any] = {"year_month": year_month}
            filters = ['"年月" = :year_month', '"删除时间" IS NULL']
            if platform:
                filters.append("LOWER(COALESCE(platform_code, '')) = :platform_code")
                params["platform_code"] = platform.lower()
            if shop_id:
                filters.append('"店铺ID" = :shop_id')
                params["shop_id"] = shop_id

            # ── 先查人力成本投影，再决定手工「人力费用」要不要被扣掉 ──
            #
            # 以前这里看的是 system_config.labor_cost_auto_effective_month：
            # 没配、或月份早于生效月 ⇒ 看板走手工人力费用，
            # 而薪资链路已经在往 V2 投影里写数 ⇒ **看板与利润基数两套口径**。
            # 现在改成**看数据本身**：这个月有 V2 投影行就用投影口径
            # （扣掉手工人力费用、加上投影金额，两边不会重复计）；
            # 没有投影行就保留手工人力费用 —— 不再依赖一个没人维护的配置开关。
            labor_filters = [
                "period_month = :year_month",
                "calculation_version = :labor_calculation_version",
            ]
            if platform:
                labor_filters.append(
                    "LOWER(COALESCE(platform_code, '')) = :platform_code"
                )
            if shop_id:
                labor_filters.append("shop_id = :shop_id")
            if platform or shop_id:
                labor_filters.append("allocation_scope = 'shop'")
            # ⚠️ **缺表必须降级而不是抛错**：
            # 人力成本分摊表属于薪资链路，在部分环境（未跑完迁移的库、
            # 精简测试库）里可能根本不存在。查不到就退回「手工人力费用」口径，
            # 而不是让整个看板接口 500 —— 与
            # ``LaborCostPolicyService.get_effective_month`` 的降级策略一致。
            try:
                labor_result = await session.execute(
                    text(
                        f"""
                        SELECT SUM(total_amount)
                        FROM finance.employee_labor_cost_allocations
                        WHERE {' AND '.join(labor_filters)}
                        """
                    ),
                    {
                        **params,
                        "labor_calculation_version": LABOR_COST_CALCULATION_VERSION,
                    },
                )
                projected_total = _to_optional_float(labor_result.scalar_one_or_none())
            except SQLAlchemyError as exc:
                logger.warning(
                    "[Dashboard] 读取 finance.employee_labor_cost_allocations 失败，"
                    "本次退回手工人力费用口径：%s",
                    exc,
                )
                await session.rollback()
                projected_total = None
            use_projected_labor = projected_total is not None

            manual_result = await session.execute(
                text(
                    f"""
                    SELECT SUM(
                        CASE WHEN COALESCE("成本合计", 0) <> 0
                            THEN "成本合计"
                            ELSE COALESCE("租金", 0)
                                + COALESCE("营销费用", 0)
                                + COALESCE("水电费", 0)
                                + COALESCE("AI Token费用", 0)
                                + COALESCE("人力费用", 0)
                                + COALESCE("其他成本", 0)
                        END
                        - CASE WHEN :use_projected_labor THEN COALESCE("人力费用", 0) ELSE 0 END
                    )
                    FROM a_class.operating_costs
                    WHERE {' AND '.join(filters)}
                    """
                ),
                {**params, "use_projected_labor": use_projected_labor},
            )
            # ⚠️ 这里**不能**用 COALESCE(SUM(...), 0)：
            # 「没有可见费用行」和「费用合计为 0」是两回事，前端要的是 None（显示 "--"，
            # 并隐藏成本明细块），见 frontend/src/domains/business/views/BusinessOverview.vue。
            # SUM 在无行时返回 NULL，正好用来区分这两种情况。
            manual_total = _to_optional_float(manual_result.scalar_one_or_none())
            if not use_projected_labor:
                return manual_total
            if manual_total is None and projected_total is None:
                return None
            return round((manual_total or 0.0) + (projected_total or 0.0), 2)

    def _business_overview_kpi_period_key(
        self, granularity: str, period_key: date_cls
    ) -> date_cls:
        if granularity == "daily":
            return period_key
        if granularity == "weekly":
            return period_key - timedelta(days=period_key.weekday())
        if granularity == "monthly":
            return date_cls(period_key.year, period_key.month, 1)
        raise ValueError("granularity must be daily, weekly or monthly")

    def _previous_business_overview_kpi_period_key(
        self, granularity: str, period_key: date_cls
    ) -> date_cls:
        current = self._business_overview_kpi_period_key(granularity, period_key)
        if granularity == "daily":
            return current - timedelta(days=1)
        if granularity == "weekly":
            return current - timedelta(days=7)
        if granularity == "monthly":
            return (current - timedelta(days=1)).replace(day=1)
        raise ValueError("granularity must be daily, weekly or monthly")

    def _business_overview_kpi_source(
        self,
        granularity: str,
        shop_id: str | None = None,
    ) -> tuple[str, str, bool]:
        if shop_id:
            source_table, period_column = _comparison_source_for_granularity(
                granularity
            )
            return source_table, period_column, True
        if granularity == "monthly":
            return "api.business_overview_kpi_module", "period_month", False
        source_table, period_column = _platform_kpi_source_for_granularity(granularity)
        return source_table, period_column, False

    async def _fetch_business_overview_kpi_rows(
        self,
        granularity: str,
        period_key: date_cls,
        platform: str | None = None,
        shop_id: str | None = None,
    ) -> list[dict[str, Any]]:
        source_table, period_column, includes_shop_id = (
            self._business_overview_kpi_source(
                granularity,
                shop_id=shop_id,
            )
        )
        shop_select = "shop_id," if includes_shop_id else "NULL::text AS shop_id,"
        query = """
            SELECT
                {period_column} AS period_key,
                platform_code,
                {shop_select}
                gmv,
                order_count,
                visitor_count,
                page_views,
                impressions,
                conversion_rate,
                uv_conversion_rate,
                pv_conversion_rate,
                visit_rate,
                browse_depth,
                exposure_order_rate,
                avg_order_value,
                attach_rate,
                total_items,
                profit
            FROM {source_table}
            WHERE {period_column} = :period_key
        """.format(
            period_column=period_column,
            shop_select=shop_select,
            source_table=source_table,
        )
        params: dict[str, Any] = {"period_key": period_key}
        if platform:
            query += " AND platform_code = :platform_code"
            params["platform_code"] = platform
        if shop_id:
            query += " AND shop_id = :shop_id"
            params["shop_id"] = shop_id
        return await self._fetch_rows(query, params)

    async def _reduce_business_overview_kpi_snapshot(
        self,
        rows: list[dict[str, Any]],
        period_key: date_cls,
    ) -> dict[str, Any]:
        reduced = reduce_business_overview_kpi_rows(rows)
        employee_count = await self._load_active_employee_count(period_key)
        gmv = reduced.get("gmv")
        if employee_count > 0 and gmv is not None:
            reduced["labor_efficiency"] = round(float(gmv) / employee_count, 2)
        else:
            reduced["labor_efficiency"] = 0
        return reduced

    def _attach_business_overview_kpi_changes(
        self,
        current: dict[str, Any],
        previous: dict[str, Any],
    ) -> dict[str, Any]:
        change_fields = (
            "gmv",
            "order_count",
            "impressions",
            "page_views",
            "visitor_count",
            "visit_rate",
            "browse_depth",
            "conversion_rate",
            "uv_conversion_rate",
            "pv_conversion_rate",
            "exposure_order_rate",
            "avg_order_value",
            "attach_rate",
            "labor_efficiency",
        )
        result = dict(current)
        for field_name in change_fields:
            result[f"{field_name}_change"] = _change_pct(
                _to_optional_float(current.get(field_name)),
                _to_optional_float(previous.get(field_name)),
            )
        return result

    async def _fetch_existing_b_class_tables(self, table_names: list[str]) -> set[str]:
        if not table_names:
            return set()
        rows = await self._fetch_rows(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'b_class'
              AND table_name = ANY(:table_names)
            """,
            {"table_names": table_names},
        )
        return {str(row.get("table_name")) for row in rows if row.get("table_name")}

    async def _load_business_overview_freshness_side(
        self,
        *,
        side_name: str,
        table_names: list[str],
        platform: str | None = None,
        shop_id: str | None = None,
    ) -> dict[str, Any]:
        existing_tables = await self._fetch_existing_b_class_tables(table_names)
        selected_tables = [
            table_name for table_name in table_names if table_name in existing_tables
        ]
        if platform:
            platform_prefix = f"fact_{platform.lower()}_"
            selected_tables = [
                table_name
                for table_name in selected_tables
                if table_name.startswith(platform_prefix)
            ]
        if not selected_tables:
            return {
                "side": side_name,
                "tables": [],
                "row_count": 0,
                "period_start_date": None,
                "period_end_date": None,
                "latest_ingest_timestamp": None,
                "latest_metric_date": None,
            }

        params: dict[str, Any] = {}
        if platform:
            params["platform_code"] = platform
        if shop_id:
            params["shop_id"] = shop_id
        union_parts: list[str] = []
        for table_name in selected_tables:
            conditions: list[str] = []
            if platform:
                conditions.append("platform_code = :platform_code")
            if shop_id:
                conditions.append("shop_id = :shop_id")
            where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
            union_parts.append(
                f"""
                SELECT
                    period_start_date,
                    period_end_date,
                    metric_date,
                    ingest_timestamp
                FROM b_class.{table_name}
                {where_clause}
                """
            )
        aggregate_sql = f"""
            SELECT
                COUNT(*) AS row_count,
                MIN(period_start_date) AS period_start_date,
                MAX(period_end_date) AS period_end_date,
                MAX(metric_date) AS latest_metric_date,
                MAX(ingest_timestamp) AS latest_ingest_timestamp
            FROM (
                {' UNION ALL '.join(part.strip() for part in union_parts)}
            ) {side_name}_rows
        """
        rows = await self._fetch_rows(aggregate_sql, params)
        row = rows[0] if rows else {}
        return {
            "side": side_name,
            "tables": selected_tables,
            "row_count": int(row.get("row_count") or 0),
            "period_start_date": row.get("period_start_date"),
            "period_end_date": row.get("period_end_date"),
            "latest_ingest_timestamp": row.get("latest_ingest_timestamp"),
            "latest_metric_date": row.get("latest_metric_date"),
        }

    async def get_business_overview_data_freshness(
        self,
        platform: str | None = None,
        shop_id: str | None = None,
    ) -> dict[str, Any]:
        orders = await self._load_business_overview_freshness_side(
            side_name="orders",
            table_names=[
                "fact_shopee_orders_monthly",
                "fact_tiktok_orders_monthly",
                "fact_miaoshou_orders_monthly",
            ],
            platform=platform,
            shop_id=shop_id,
        )
        traffic = await self._load_business_overview_freshness_side(
            side_name="traffic",
            table_names=[
                "fact_shopee_analytics_monthly",
                "fact_tiktok_analytics_monthly",
                "fact_miaoshou_analytics_monthly",
            ],
            platform=platform,
            shop_id=shop_id,
        )

        warnings: list[str] = []
        orders_end = orders.get("period_end_date")
        traffic_end = traffic.get("period_end_date")
        if orders_end is None:
            warnings.append("orders freshness unavailable")
        if traffic_end is None:
            warnings.append("traffic freshness unavailable")
        if (
            orders_end is not None
            and traffic_end is not None
            and orders_end != traffic_end
        ):
            warnings.append(
                f"orders period_end_date {orders_end} lags traffic {traffic_end}"
            )

        table_checks = []
        for side in (orders, traffic):
            latest_ingest_timestamp = side.get("latest_ingest_timestamp")
            stale_hours = None
            is_side_stale = False
            if latest_ingest_timestamp is not None:
                parsed_ingest = _as_utc(_parse_datetimeish(latest_ingest_timestamp))
                if parsed_ingest is not None:
                    stale_hours = round(
                        (datetime.now(timezone.utc) - parsed_ingest).total_seconds()
                        / 3600,
                        2,
                    )
                    is_side_stale = stale_hours > 24
            for table_name in side.get("tables", []):
                table_checks.append(
                    {
                        "table_name": table_name,
                        "side": side.get("side"),
                        "latest_ingest_timestamp": latest_ingest_timestamp,
                        "latest_business_date": side.get("period_end_date")
                        or side.get("latest_metric_date"),
                        "stale_hours": stale_hours,
                        "is_stale": is_side_stale,
                    }
                )
                if is_side_stale:
                    warnings.append(
                        f"{table_name} has no new ingest for {stale_hours}h"
                    )

        return {
            "orders": orders,
            "traffic": traffic,
            "table_checks": table_checks,
            "is_stale": bool(warnings),
            "warnings": warnings,
        }

    async def get_business_overview_kpi(
        self,
        month: str | None = None,
        platform: str | None = None,
        granularity: str = "monthly",
        target_date: str | None = None,
        shop_id: str | None = None,
    ) -> dict[str, Any]:
        effective_granularity = str(granularity or "monthly").strip().lower()
        effective_target_date = target_date or month
        if effective_target_date is None:
            raise ValueError("target_date or month is required")
        normalized_period = _normalize_period_start(effective_target_date)
        period_key = self._business_overview_kpi_period_key(
            effective_granularity, normalized_period
        )
        previous_period_key = self._previous_business_overview_kpi_period_key(
            effective_granularity, period_key
        )

        rows = await self._fetch_business_overview_kpi_rows(
            effective_granularity,
            period_key,
            platform=platform,
            shop_id=shop_id,
        )
        previous_rows = await self._fetch_business_overview_kpi_rows(
            effective_granularity,
            previous_period_key,
            platform=platform,
            shop_id=shop_id,
        )
        reduced = await self._reduce_business_overview_kpi_snapshot(rows, period_key)
        previous_reduced = await self._reduce_business_overview_kpi_snapshot(
            previous_rows, previous_period_key
        )
        return self._attach_business_overview_kpi_changes(reduced, previous_reduced)

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
            else (
                current_start + timedelta(days=6)
                if granularity == "weekly"
                else (current_start + timedelta(days=31)).replace(day=1)
                - timedelta(days=1)
            )
        )
        target_summary = await self._load_target_summary(
            granularity=granularity,
            period_start=current_start,
            period_end=current_end,
            platform=platform,
        )
        reduced["target"]["sales_amount"] = _round_or_none(
            target_summary["target_amount"], 2
        )
        reduced["target"]["sales_quantity"] = _round_or_none(
            target_summary["target_quantity"], 2
        )
        reduced["target"]["achievement_rate"] = (
            round(
                reduced["metrics"]["sales_amount"]["today"]
                * 100.0
                / target_summary["target_amount"],
                2,
            )
            if target_summary["target_amount"]
            and reduced["metrics"]["sales_amount"]["today"] is not None
            else None
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
            period_start, period_end = _resolve_business_overview_window(
                granularity, target_date
            )
        return {
            "summary": await (
                self._load_inventory_backlog_summary(
                    period_start=period_start, period_end=period_end
                )
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

    async def get_business_overview_shop_racing(
        self,
        granularity: str,
        target_date: str,
        group_by: str = "shop",
        platform: str | None = None,
    ) -> list[dict[str, Any]]:
        normalized_target_date = _normalize_period_start(target_date)
        normalized_granularity = str(granularity or "").strip().lower()
        period_key = self._business_overview_kpi_period_key(
            normalized_granularity, normalized_target_date
        )
        previous_period_key = self._previous_business_overview_kpi_period_key(
            normalized_granularity, period_key
        )
        source_table = _business_overview_shop_racing_source_table(
            normalized_granularity
        )
        where_clause = "src.granularity = :granularity AND src.period_key IN (:period_key, :previous_period_key)"
        params: dict[str, Any] = {
            "granularity": normalized_granularity,
            "period_key": period_key,
            "previous_period_key": previous_period_key,
        }

        query = f"""
            SELECT
                :granularity AS granularity,
                src.period_key AS period_key,
                src.platform_code,
                src.shop_id,
{_business_overview_identity_select_sql()},
                src.gmv,
                src.order_count,
                src.avg_order_value,
                src.attach_rate,
                src.profit,
                src.target_amount,
                src.achievement_rate
            FROM {source_table} src
{_business_overview_identity_join_sql()}
            WHERE {where_clause}
        """
        if platform:
            query += " AND src.platform_code = :platform_code"
            params["platform_code"] = platform

        try:
            rows = await self._fetch_rows(query, params)
        except Exception:
            rows = await self._fetch_rows_with_statement_timeout(
                query, params, timeout_ms=120000
            )

        current_rows = [row for row in rows if _row_period_key(row) == period_key]
        previous_rows = [
            row for row in rows if _row_period_key(row) == previous_period_key
        ]

        if group_by == "platform":

            def group_platform(
                source_rows: list[dict[str, Any]],
            ) -> dict[str, dict[str, Any]]:
                grouped: dict[str, dict[str, Any]] = {}
                for row in source_rows:
                    key = row["platform_code"]
                    grouped.setdefault(
                        key,
                        {
                            "name": key,
                            "platform_code": key,
                            "shop_id": "ALL",
                            "gmv": 0.0,
                            "profit": 0.0,
                            "order_count": 0.0,
                            "avg_order_value": 0.0,
                            "attach_rate": 0.0,
                            "target_amount": 0.0,
                            "achievement_rate": 0.0,
                        },
                    )
                    grouped[key]["gmv"] += _to_optional_float(row.get("gmv")) or 0.0
                    grouped[key]["profit"] += (
                        _to_optional_float(row.get("profit")) or 0.0
                    )
                    grouped[key]["order_count"] += (
                        _to_optional_float(row.get("order_count")) or 0.0
                    )
                    grouped[key]["target_amount"] += (
                        _to_optional_float(row.get("target_amount")) or 0.0
                    )
                for value in grouped.values():
                    if value["order_count"]:
                        value["avg_order_value"] = round(
                            value["gmv"] / value["order_count"], 2
                        )
                    if value["target_amount"]:
                        value["achievement_rate"] = round(
                            value["gmv"] * 100.0 / value["target_amount"], 2
                        )
                return grouped

            grouped = group_platform(current_rows)
            previous_grouped = group_platform(previous_rows)
            for key, value in grouped.items():
                _attach_shop_racing_change_fields(value, previous_grouped.get(key))
            return rank_shop_racing_rows(list(grouped.values()))

        if group_by == "account":

            def group_account(
                source_rows: list[dict[str, Any]],
            ) -> dict[str, dict[str, Any]]:
                grouped: dict[str, dict[str, Any]] = {}
                for row in source_rows:
                    account_id = row.get("shop_account_id")
                    main_account_id = row.get("main_account_id")
                    account_store_name = row.get("account_store_name")
                    main_account_name = row.get("main_account_name")
                    display_name = row.get("account_display_name") or " / ".join(
                        [
                            part
                            for part in (
                                (
                                    str(main_account_name).strip()
                                    if main_account_name
                                    else None
                                ),
                                (
                                    str(account_store_name).strip()
                                    if account_store_name
                                    else None
                                ),
                            )
                            if part
                        ]
                    )
                    fallback_name = (
                        display_name or account_store_name or account_id or "未匹配账号"
                    )
                    key = (
                        account_id
                        or f"unmatched::{row.get('platform_code') or 'unknown'}"
                    )
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
                            "profit": 0.0,
                            "order_count": 0.0,
                            "avg_order_value": 0.0,
                            "attach_rate": 0.0,
                            "target_amount": 0.0,
                            "achievement_rate": 0.0,
                        },
                    )
                    grouped[key]["gmv"] += _to_optional_float(row.get("gmv")) or 0.0
                    grouped[key]["profit"] += (
                        _to_optional_float(row.get("profit")) or 0.0
                    )
                    grouped[key]["order_count"] += (
                        _to_optional_float(row.get("order_count")) or 0.0
                    )
                    grouped[key]["target_amount"] += (
                        _to_optional_float(row.get("target_amount")) or 0.0
                    )
                for value in grouped.values():
                    if value["order_count"]:
                        value["avg_order_value"] = round(
                            value["gmv"] / value["order_count"], 2
                        )
                    if value["target_amount"]:
                        value["achievement_rate"] = round(
                            value["gmv"] * 100.0 / value["target_amount"], 2
                        )
                return grouped

            grouped = group_account(current_rows)
            previous_grouped = group_account(previous_rows)
            for key, value in grouped.items():
                _attach_shop_racing_change_fields(value, previous_grouped.get(key))
            return rank_shop_racing_rows(list(grouped.values()))

        previous_normalized_rows = [
            {
                "platform_code": row.get("platform_code"),
                "shop_id": row.get("shop_id") or "unknown",
                "gmv": _to_optional_float(row.get("gmv")),
                "order_count": _to_optional_float(row.get("order_count")),
                "avg_order_value": _to_optional_float(row.get("avg_order_value")),
                "profit": _to_optional_float(row.get("profit")),
                "achievement_rate": _to_optional_float(row.get("achievement_rate")),
            }
            for row in previous_rows
        ]
        previous_by_key = {
            _shop_racing_identity_key(row): row for row in previous_normalized_rows
        }

        normalized_rows = []
        for row in current_rows:
            normalized = {
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
            normalized_rows.append(
                _attach_shop_racing_change_fields(
                    normalized,
                    previous_by_key.get(_shop_racing_identity_key(normalized)),
                )
            )
        return rank_shop_racing_rows(normalized_rows)

    async def get_business_overview_traffic_ranking(
        self,
        granularity: str,
        target_date: str,
        dimension: str = "visitor",
        platform: str | None = None,
    ) -> list[dict[str, Any]]:
        normalized_granularity = str(granularity or "").strip().lower()
        normalized_target_date = _normalize_period_start(target_date)
        period_key = self._business_overview_kpi_period_key(
            normalized_granularity, normalized_target_date
        )
        previous_period_key = self._previous_business_overview_kpi_period_key(
            normalized_granularity, period_key
        )
        query = """
            SELECT
                :granularity AS granularity,
                src.period_key AS period_key,
                src.platform_code,
                src.shop_id,
{identity_select},
                src.order_count,
                src.visitor_count,
                src.page_views,
                src.conversion_rate,
                src.uv_conversion_rate,
                src.pv_conversion_rate
            FROM api.business_overview_traffic_ranking_module src
{identity_join}
            WHERE src.granularity = :granularity
              AND src.period_key IN (:period_key, :previous_period_key)
            """.format(
            identity_select=_business_overview_identity_select_sql(),
            identity_join=_business_overview_identity_join_sql(),
        )
        params = {
            "granularity": normalized_granularity,
            "period_key": period_key,
            "previous_period_key": previous_period_key,
        }
        if platform:
            query += " AND src.platform_code = :platform_code"
            params["platform_code"] = platform
        rows = await self._fetch_rows(query, params)

        current_rows = [row for row in rows if _row_period_key(row) == period_key]
        previous_rows = [
            row for row in rows if _row_period_key(row) == previous_period_key
        ]

        if dimension == "account":

            def group_account(
                source_rows: list[dict[str, Any]],
            ) -> dict[str, dict[str, Any]]:
                grouped: dict[str, dict[str, Any]] = {}
                for row in source_rows:
                    account_id = row.get("shop_account_id")
                    main_account_id = row.get("main_account_id")
                    account_store_name = row.get("account_store_name")
                    main_account_name = row.get("main_account_name")
                    display_name = row.get("account_display_name") or " / ".join(
                        [
                            part
                            for part in (
                                (
                                    str(main_account_name).strip()
                                    if main_account_name
                                    else None
                                ),
                                (
                                    str(account_store_name).strip()
                                    if account_store_name
                                    else None
                                ),
                            )
                            if part
                        ]
                    )
                    fallback_name = (
                        display_name or account_store_name or account_id or "未匹配账号"
                    )
                    key = (
                        account_id
                        or f"unmatched::{row.get('platform_code') or 'unknown'}"
                    )
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
                            "order_count": 0.0,
                            "conversion_rate": None,
                            "uv_conversion_rate": None,
                            "pv_conversion_rate": None,
                            "_has_order_count": False,
                            "_has_visitor_count": False,
                            "_has_page_views": False,
                        },
                    )
                    visitor_count = _to_optional_float(row.get("visitor_count"))
                    page_views = _to_optional_float(row.get("page_views"))
                    order_count = _to_optional_float(row.get("order_count"))
                    if visitor_count is not None:
                        grouped[key]["visitor_count"] += visitor_count
                        grouped[key]["_has_visitor_count"] = True
                    if page_views is not None:
                        grouped[key]["page_views"] += page_views
                        grouped[key]["_has_page_views"] = True
                    if order_count is not None:
                        grouped[key]["order_count"] += order_count
                        grouped[key]["_has_order_count"] = True
                for value in grouped.values():
                    rate_order_count = (
                        value.get("order_count")
                        if value.pop("_has_order_count")
                        else None
                    )
                    rate_visitor_count = (
                        value.get("visitor_count")
                        if value.pop("_has_visitor_count")
                        else None
                    )
                    rate_page_views = (
                        value.get("page_views")
                        if value.pop("_has_page_views")
                        else None
                    )
                    value["uv_conversion_rate"] = _percent_or_none(
                        rate_order_count, rate_visitor_count
                    )
                    value["pv_conversion_rate"] = _percent_or_none(
                        rate_order_count, rate_page_views
                    )
                    value["conversion_rate"] = value["uv_conversion_rate"]
                return grouped

            grouped = group_account(current_rows)
            previous_grouped = group_account(previous_rows)
            normalized_rows = [
                _attach_traffic_change_fields(value, previous_grouped.get(key))
                for key, value in grouped.items()
            ]
        else:
            previous_normalized_rows = [
                {
                    "platform_code": row.get("platform_code"),
                    "shop_id": row.get("shop_id") or "unknown",
                    "visitor_count": _to_optional_float(row.get("visitor_count")),
                    "page_views": _to_optional_float(row.get("page_views")),
                    "uv_conversion_rate": _to_optional_float(
                        row.get("uv_conversion_rate")
                    ),
                    "pv_conversion_rate": _to_optional_float(
                        row.get("pv_conversion_rate")
                    ),
                }
                for row in previous_rows
            ]
            previous_by_key = {
                _traffic_identity_key(row): row for row in previous_normalized_rows
            }
            normalized_rows = []
            for row in current_rows:
                normalized = {
                    "name": row.get("display_name")
                    or (
                        row.get("shop_id")
                        if str(row.get("shop_id") or "").strip().lower()
                        not in {"", "none", "unknown"}
                        else "未匹配店铺"
                    ),
                    "platform_code": row.get("platform_code"),
                    "shop_id": row.get("shop_id") or "unknown",
                    "shop_account_id": row.get("shop_account_id"),
                    "main_account_id": row.get("main_account_id"),
                    "main_account_name": row.get("main_account_name"),
                    "is_unmatched": not bool(row.get("shop_account_id")),
                    "order_count": _to_optional_float(row.get("order_count")),
                    "visitor_count": _to_optional_float(row.get("visitor_count")),
                    "page_views": _to_optional_float(row.get("page_views")),
                    "conversion_rate": _to_optional_float(row.get("conversion_rate")),
                    "uv_conversion_rate": _to_optional_float(
                        row.get("uv_conversion_rate")
                    ),
                    "pv_conversion_rate": _to_optional_float(
                        row.get("pv_conversion_rate")
                    ),
                }
                normalized_rows.append(
                    _attach_traffic_change_fields(
                        normalized,
                        previous_by_key.get(_traffic_identity_key(normalized)),
                    )
                )
        return rank_traffic_rows(normalized_rows, dimension="pv")

    async def _load_discovery_issue_summary(
        self,
        platform: str | None = None,
    ) -> dict[str, Any]:
        """采集期身份异常(探测状态机)—— 语义层告警之外的**第二层**信号。

        语义层告警是事后信号(数据已经落错), 这里是事前信号(采集时读到的
        平台店铺编号就对不上账号了)。两者都要有: 事后信号告诉你哪块数据
        不可信, 事前信号告诉你下一次采集还会继续错。
        """
        from backend.services.platform_shop_discovery_service import (
            PLATFORM_SHOP_DISCOVERY_ISSUE_STATUSES,
        )

        issue_statuses = sorted(PLATFORM_SHOP_DISCOVERY_ISSUE_STATUSES)
        params: dict[str, Any] = {"issue_statuses": issue_statuses}
        platform_clause = ""
        if platform:
            platform_clause = " AND lower(platform) = :platform"
            params["platform"] = str(platform).strip().lower()

        count_query = f"""
            SELECT status, count(*)::int AS issue_count
            FROM core.platform_shop_discoveries
            WHERE status = ANY(CAST(:issue_statuses AS text[]))
            {platform_clause}
            GROUP BY status
        """
        detail_query = f"""
            SELECT
                id,
                platform,
                main_account_id,
                detected_store_name,
                detected_platform_shop_id,
                candidate_shop_account_ids,
                status,
                created_at
            FROM core.platform_shop_discoveries
            WHERE status = ANY(CAST(:issue_statuses AS text[]))
            {platform_clause}
            ORDER BY created_at DESC
            LIMIT 20
        """

        try:
            count_rows = await self._fetch_rows(count_query, params)
            detail_rows = await self._fetch_rows(detail_query, params)
        except SQLAlchemyError:
            # 表不存在 / 连接异常 ⇒ 这层信号拿不到, 但不能把整个身份健康度带崩
            return _empty_discovery_issue_summary()

        by_status = {
            str(row.get("status")): int(row.get("issue_count") or 0)
            for row in count_rows
        }
        issues = []
        for row in detail_rows:
            created_at = row.get("created_at")
            issues.append(
                {
                    "id": row.get("id"),
                    "platform": row.get("platform"),
                    "main_account_id": row.get("main_account_id"),
                    "detected_store_name": row.get("detected_store_name"),
                    "detected_platform_shop_id": row.get("detected_platform_shop_id"),
                    "candidate_shop_account_ids": row.get("candidate_shop_account_ids")
                    or [],
                    "status": row.get("status"),
                    "created_at": created_at.isoformat() if created_at else None,
                }
            )

        return {
            "issue_count": sum(by_status.values()),
            "by_status": by_status,
            "issues": issues,
        }

    async def get_business_overview_identity_health(
        self,
        granularity: str,
        target_date: str,
        platform: str | None = None,
    ) -> dict[str, Any]:
        normalized_granularity = str(granularity or "").strip().lower()
        if normalized_granularity != "monthly":
            return {
                "status": "ok",
                "warning_count": 0,
                "warnings": [],
                "warning_breakdown": _empty_identity_warning_breakdown(),
                "discovery_issues": _empty_discovery_issue_summary(),
            }

        period_key = self._business_overview_kpi_period_key(
            normalized_granularity,
            _normalize_period_start(target_date),
        )
        params: dict[str, Any] = {"period_key": period_key}
        platform_filter = ""
        conflict_platform_filter = ""
        if platform:
            platform_filter = "AND platform_code = :platform_code"
            # 诊断 CTE 里同时 JOIN 了 owner / target 两张账号表, 裸列名有歧义 ⇒ 要带表别名
            conflict_platform_filter = "AND f.platform_code = :platform_code"
            params["platform_code"] = platform

        query = f"""
            WITH orders AS (
                SELECT
                    date_trunc('month', metric_date)::date AS period_month,
                    platform_code,
                    shop_id,
                    resolved_shop_account_id,
                    MAX(identity_warning_code) AS identity_warning_code,
                    COUNT(DISTINCT order_id)::numeric AS order_count
                FROM semantic.fact_orders_monthly_atomic
                WHERE metric_date >= :period_key
                  AND metric_date < (:period_key + INTERVAL '1 month')
                  {platform_filter}
                GROUP BY date_trunc('month', metric_date)::date, platform_code, shop_id, resolved_shop_account_id
            ),
            traffic AS (
                SELECT
                    date_trunc('month', metric_date)::date AS period_month,
                    platform_code,
                    shop_id,
                    resolved_shop_account_id,
                    MAX(identity_warning_code) AS identity_warning_code,
                    SUM(visitor_count) AS visitor_count,
                    SUM(page_views) AS page_views
                FROM semantic.fact_analytics_monthly_atomic
                WHERE metric_date >= :period_key
                  AND metric_date < (:period_key + INTERVAL '1 month')
                  {platform_filter}
                GROUP BY date_trunc('month', metric_date)::date, platform_code, shop_id, resolved_shop_account_id
            ),
            identity_conflicts AS (
                SELECT
                    period_month,
                    platform_code,
                    resolved_shop_account_id,
                    ARRAY_AGG(DISTINCT shop_id ORDER BY shop_id) AS shop_ids
                FROM (
                    SELECT period_month, platform_code, shop_id, resolved_shop_account_id FROM orders
                    UNION ALL
                    SELECT period_month, platform_code, shop_id, resolved_shop_account_id FROM traffic
                ) unioned
                WHERE resolved_shop_account_id IS NOT NULL
                GROUP BY period_month, platform_code, resolved_shop_account_id
                HAVING COUNT(DISTINCT shop_id) > 1
            ),
            platform_shop_id_conflicts AS (
                -- [*] 2026-11: 「行内编号与行内标签指向不同账号」的行。
                --
                -- 为什么直接查 b_class 事实表而不是语义层 MV:
                --   语义层只输出「候选数」, 不输出「编号命中了哪个账号」,
                --   分不出「歧义来自编号」还是「歧义来自两个店名」。
                --   而给 MV 加列需要**重建物化视图**(REFRESH 不能改定义),
                --   DROP ... CASCADE 会连删下游对象 ⇒ 风险远大于收益。
                --   这里用查询期诊断, 零迁移、零 MV 重建。
                --
                -- 判据与历史订正迁移(20261117)完全一致:
                --   行内 shop_id 能反查到账号 B, 而行内 shop_account_id 指向账号 A,
                --   A ≠ B ⇒ 编号与标签打架。
                SELECT
                    date_trunc('month', f.metric_date)::date AS period_month,
                    f.platform_code,
                    f.raw_data ->> 'shop_account_id' AS shop_account_id,
                    f.shop_id::text AS shop_id,
                    target.shop_account_id AS conflicting_shop_account_id,
                    COUNT(*)::int AS conflict_row_count,
                    SUM(
                        NULLIF(
                            REGEXP_REPLACE(
                                COALESCE(f.raw_data ->> '访客数', ''),
                                '[^0-9.]',
                                '',
                                'g'
                            ),
                            ''
                        )::numeric
                    ) AS visitor_count
                FROM b_class.fact_shopee_analytics_monthly f
                INNER JOIN core.shop_accounts owner
                        ON owner.shop_account_id = f.raw_data ->> 'shop_account_id'
                INNER JOIN core.shop_accounts target
                        ON LOWER(NULLIF(TRIM(target.platform_shop_id), ''))
                           = LOWER(NULLIF(TRIM(f.shop_id), ''))
                       AND LOWER(TRIM(COALESCE(target.platform, '')))
                           = LOWER(TRIM(COALESCE(f.platform_code, '')))
                WHERE owner.enabled IS TRUE
                  AND owner.business_role = 'operating_store'
                  AND target.enabled IS TRUE
                  AND target.business_role = 'operating_store'
                  AND owner.id <> target.id
                  AND f.metric_date >= :period_key
                  AND f.metric_date < (:period_key + INTERVAL '1 month')
                  {conflict_platform_filter}
                GROUP BY 1, 2, 3, 4, 5
            ),
            warnings AS (
                SELECT
                    'identity_conflict'::varchar AS warning_code,
                    platform_code,
                    resolved_shop_account_id AS shop_account_id,
                    NULL::text AS shop_id,
                    shop_ids::text AS related_shop_ids,
                    NULL::numeric AS order_count,
                    NULL::numeric AS visitor_count,
                    NULL::numeric AS page_views
                FROM identity_conflicts

                UNION ALL

                SELECT
                    'platform_shop_id_conflict'::varchar AS warning_code,
                    platform_code,
                    shop_account_id,
                    shop_id,
                    conflicting_shop_account_id::text AS related_shop_ids,
                    NULL::numeric AS order_count,
                    visitor_count,
                    NULL::numeric AS page_views
                FROM platform_shop_id_conflicts

                UNION ALL

                SELECT
                    'traffic_without_order_match_due_to_identity'::varchar AS warning_code,
                    t.platform_code,
                    t.resolved_shop_account_id AS shop_account_id,
                    t.shop_id,
                    ARRAY_AGG(DISTINCT o.shop_id ORDER BY o.shop_id)::text AS related_shop_ids,
                    SUM(o.order_count) AS order_count,
                    t.visitor_count,
                    t.page_views
                FROM traffic t
                INNER JOIN orders o
                  ON o.platform_code = t.platform_code
                 AND o.period_month = t.period_month
                 AND o.resolved_shop_account_id = t.resolved_shop_account_id
                 AND COALESCE(o.shop_id, '') <> COALESCE(t.shop_id, '')
                LEFT JOIN orders exact_o
                  ON exact_o.platform_code = t.platform_code
                 AND exact_o.period_month = t.period_month
                 AND COALESCE(exact_o.shop_id, '') = COALESCE(t.shop_id, '')
                WHERE t.resolved_shop_account_id IS NOT NULL
                  AND exact_o.shop_id IS NULL
                  AND COALESCE(t.visitor_count, 0) > 0
                GROUP BY t.platform_code, t.resolved_shop_account_id, t.shop_id, t.visitor_count, t.page_views

                UNION ALL

                SELECT
                    COALESCE(identity_warning_code, 'identity_warning')::varchar AS warning_code,
                    platform_code,
                    resolved_shop_account_id AS shop_account_id,
                    shop_id,
                    NULL::text AS related_shop_ids,
                    order_count,
                    NULL::numeric AS visitor_count,
                    NULL::numeric AS page_views
                FROM orders
                WHERE identity_warning_code IS NOT NULL

                UNION ALL

                SELECT
                    COALESCE(identity_warning_code, 'identity_warning')::varchar AS warning_code,
                    platform_code,
                    resolved_shop_account_id AS shop_account_id,
                    shop_id,
                    NULL::text AS related_shop_ids,
                    NULL::numeric AS order_count,
                    visitor_count,
                    page_views
                FROM traffic
                WHERE identity_warning_code IS NOT NULL
            )
            SELECT *
            FROM warnings
            ORDER BY warning_code, platform_code, shop_account_id NULLS LAST, shop_id NULLS LAST
        """
        try:
            rows = await self._fetch_rows(query, params)
        except ProgrammingError:
            return {
                "status": "unavailable",
                "warning_count": 0,
                "warnings": [],
                "warning_breakdown": _empty_identity_warning_breakdown(),
                "discovery_issues": _empty_discovery_issue_summary(),
            }

        warnings = [dict(row) for row in rows]
        breakdown = _empty_identity_warning_breakdown()
        for warning in warnings:
            reason = _identity_warning_reason(warning.get("warning_code"))
            warning["warning_reason"] = reason
            bucket = breakdown[reason]
            bucket["warning_count"] += 1
            for metric in ("visitor_count", "page_views", "order_count"):
                value = _to_optional_float(warning.get(metric))
                if value:
                    bucket[metric] += value

        warning_count = len(warnings)
        discovery_issues = await self._load_discovery_issue_summary(platform)
        return {
            "status": "warning" if warning_count else "ok",
            "warning_count": warning_count,
            # 列表只给前 50 条做展示, 但 ``warning_count`` 与
            # ``warning_breakdown`` 统计的是**全部**告警 —— 截断只发生在展示层。
            "warnings": warnings[:50],
            "warning_breakdown": breakdown,
            # 采集期(事前)信号: 与上面的语义层(事后)告警是两层, 不能互相替代。
            "discovery_issues": discovery_issues,
        }

    async def get_business_overview_operational_metrics(
        self,
        month: str,
        platform: str | None = None,
        shop_id: str | None = None,
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
        if shop_id:
            query += " AND shop_id = :shop_id"
            params["shop_id"] = shop_id

        rows = await self._fetch_rows(query, params)
        total = {
            "monthly_target": None,
            "monthly_total_achieved": None,
            "today_sales": None,
            "monthly_achievement_rate": None,
            "time_gap": None,
            "estimated_gross_profit": None,
            "other_operating_cost": None,
            "pre_commission_labor_cost": None,
            "performance_labor_cost": None,
            "commission_labor_cost": None,
            "total_labor_cost": None,
            "company_public_labor_cost": 0.0,
            "estimated_expenses": None,
            "operating_result": None,
            "monthly_order_count": None,
            "today_order_count": None,
        }
        meta: dict[str, Any] = {
            "profit_source": "orders_raw_profit_field",
            "target_source": "sql_operational_metrics_module",
            "expenses_source": "shop_month_rows_sum",
            "operating_result_source": "sql_operational_metrics_module",
            "service_enriched_fields": [],
            "warnings": [],
        }
        numeric_total_keys = tuple(
            key for key in total if key != "company_public_labor_cost"
        )
        cost_statuses: list[str] = []
        for row in rows:
            for key in numeric_total_keys:
                value = _to_optional_float(row.get(key))
                if value is None:
                    continue
                total[key] = value if total[key] is None else total[key] + value
            if row.get("cost_status"):
                cost_statuses.append(str(row["cost_status"]))
        total["cost_status"] = (
            "confirmed"
            if cost_statuses and all(status == "confirmed" for status in cost_statuses)
            else "projected" if cost_statuses else "legacy"
        )

        month_end = (period_month + timedelta(days=31)).replace(day=1) - timedelta(
            days=1
        )
        target_summary = await self._load_target_summary(
            granularity="monthly",
            period_start=period_month,
            period_end=month_end,
            platform=platform,
            shop_id=shop_id,
        )
        if target_summary["target_amount"] is not None:
            total["monthly_target"] = round(target_summary["target_amount"], 2)
            meta["target_source"] = "service_target_summary"
            meta["service_enriched_fields"].append("monthly_target")
        loaded_expenses = await self._load_operating_expenses_summary(
            period_month,
            platform=platform,
            shop_id=shop_id,
        )
        if platform is None and shop_id is None:
            public_labor_rows = await self._fetch_rows(
                """
                SELECT
                    COALESCE(SUM(total_amount), 0) AS company_public_labor_cost
                FROM finance.employee_labor_cost_allocations
                WHERE period_month = :period_month
                  AND allocation_scope = 'company'
                  AND calculation_version = :labor_calculation_version
                """,
                {
                    "period_month": period_month.strftime("%Y-%m"),
                    "labor_calculation_version": LABOR_COST_CALCULATION_VERSION,
                },
            )
            if public_labor_rows:
                public_labor_cost = (
                    _to_optional_float(
                        public_labor_rows[0].get("company_public_labor_cost")
                    )
                    or 0.0
                )
                total["company_public_labor_cost"] = public_labor_cost
                if total["total_labor_cost"] is not None:
                    total["total_labor_cost"] += public_labor_cost
                meta["service_enriched_fields"].append("company_public_labor_cost")
        if loaded_expenses is not None:
            total["estimated_expenses"] = loaded_expenses
            meta["expenses_source"] = "expense_management_month_summary"
            meta["service_enriched_fields"].append("estimated_expenses")
        if (
            total["estimated_gross_profit"] is not None
            and total["estimated_expenses"] is not None
        ):
            total["operating_result"] = round(
                total["estimated_gross_profit"] - total["estimated_expenses"], 2
            )
            meta["operating_result_source"] = (
                "service_calculated_from_profit_and_expenses"
            )
            meta["service_enriched_fields"].append("operating_result")

        if (
            total["monthly_total_achieved"] is not None
            and total["monthly_target"] is not None
        ):
            if total["monthly_target"] > 0:
                total["monthly_achievement_rate"] = round(
                    total["monthly_total_achieved"] * 100.0 / total["monthly_target"], 2
                )
                meta["service_enriched_fields"].append("monthly_achievement_rate")
            elif total["monthly_target"] == 0 and total["monthly_total_achieved"] == 0:
                total["monthly_achievement_rate"] = 0
                meta["service_enriched_fields"].append("monthly_achievement_rate")
            else:
                total["monthly_achievement_rate"] = None
        else:
            total["monthly_achievement_rate"] = _round_or_none(
                total["monthly_achievement_rate"], 2
            )
        if total["monthly_achievement_rate"] is not None:
            total["time_gap"] = round(
                total["monthly_achievement_rate"]
                - _month_time_progress_pct(period_month),
                2,
            )
            meta["service_enriched_fields"].append("time_gap")
        else:
            total["time_gap"] = None
        operating_result_missing = total["operating_result"] is None
        if operating_result_missing:
            total["operating_result"] = float("-inf")
        total["operating_result_text"] = (
            "盈利" if total["operating_result"] > 0 else "亏损"
        )
        total["monthly_order_count"] = (
            int(total["monthly_order_count"])
            if total["monthly_order_count"] is not None
            else None
        )
        total["today_order_count"] = (
            int(total["today_order_count"])
            if total["today_order_count"] is not None
            else None
        )
        if operating_result_missing:
            total["operating_result"] = None
            total["operating_result_text"] = None
        total["meta"] = meta
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


_service: PostgresqlDashboardService | None = None


def get_postgresql_dashboard_service() -> PostgresqlDashboardService:
    global _service
    if _service is None:
        _service = PostgresqlDashboardService()
    return _service
