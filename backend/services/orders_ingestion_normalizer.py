#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Orders-specific B-class ingestion helpers."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any


SOURCE_LINE_INDEX_FIELD = "_source_line_index"

ORDER_ID_FIELDS = (
    "order_id",
    "Order ID",
    "order_no",
    "订单编号",
    "订单号",
    "订单ID",
)

ORDER_LEVEL_AMOUNT_FIELDS = {
    "buyer_payment_rmb",
    "buyer_payment",
    "paid_amount_rmb",
    "paid_amount",
    "buyer_paid_amount_rmb",
    "buyer_paid_amount",
    "买家支付(RMB)",
    "买家支付",
    "买家实付金额(RMB)",
    "买家实付金额",
    "实付金额(RMB)",
    "实付金额",
    "profit_rmb",
    "profit",
    "Profit",
    "利润(RMB)",
    "利润",
    "settled_amount_rmb",
    "settled_amount",
    "已结算金额(RMB)",
    "已结算金额",
    "estimated_settlement_rmb",
    "estimated_settlement",
    "预计回款金额(RMB)",
    "预计回款金额",
    "original_amount_rmb",
    "original_amount",
    "order_original_amount_rmb",
    "order_original_amount",
    "订单原始金额(RMB)",
    "订单原始金额",
    "warehouse_operation_fee_rmb",
    "warehouse_operation_fee",
    "warehouse_fee",
    "仓库操作费(RMB)",
    "仓库操作费",
    "ad_cost_rmb",
    "ad_cost",
    "advertising_cost_rmb",
    "advertising_cost",
    "广告成本(RMB)",
    "广告成本",
    "platform_commission_rmb",
    "platform_commission",
    "平台佣金(RMB)",
    "平台佣金",
    "shipping_fee_rmb",
    "shipping_fee",
    "运费(RMB)",
    "运费",
    "platform_voucher_rmb",
    "platform_voucher",
    "平台优惠券(RMB)",
    "平台优惠券",
    "refund_amount_rmb",
    "refund_amount",
    "退款金额(RMB)",
    "退款金额",
}


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    try:
        if value != value:
            return True
    except Exception:
        pass
    if isinstance(value, str):
        return value.strip().lower() in {"", "nan", "none", "null"}
    return False


def _first_present(row: dict[str, Any], fields: tuple[str, ...]) -> str | None:
    for field in fields:
        value = row.get(field)
        if not _is_blank(value):
            return str(value).strip()
    return None


def prepare_orders_rows_for_b_class(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Prepare orders rows for B-class storage without changing metric grain.

    The first source row for an order keeps order-level amounts. Additional
    rows for the same order get a line index for hashing and keep order-level
    amount fields blank so mart SUMs remain order-level.
    """
    if not rows:
        return [], []

    order_ids: list[str] = []
    last_order_id: str | None = None
    for index, row in enumerate(rows):
        order_id = _first_present(row, ORDER_ID_FIELDS)
        if order_id:
            last_order_id = order_id
        order_ids.append(last_order_id or f"__missing_order_id__:{index}")

    order_counts = Counter(order_ids)
    line_counters: dict[str, int] = defaultdict(int)
    prepared_rows: list[dict[str, Any]] = []
    identity_values: list[dict[str, Any]] = []

    for row, order_id in zip(rows, order_ids):
        row_copy = dict(row)
        row_identity: dict[str, Any] = {}

        if order_counts[order_id] > 1:
            line_counters[order_id] += 1
            source_line_index = line_counters[order_id]
            if source_line_index > 1:
                row_identity[SOURCE_LINE_INDEX_FIELD] = source_line_index
                for field in ORDER_LEVEL_AMOUNT_FIELDS:
                    if field in row_copy:
                        row_copy[field] = ""

        prepared_rows.append(row_copy)
        identity_values.append(row_identity)

    return prepared_rows, identity_values


def extend_orders_deduplication_fields(
    data_domain: str | None,
    deduplication_fields: list[str],
) -> list[str]:
    if (data_domain or "").lower() != "orders" or not deduplication_fields:
        return list(deduplication_fields or [])

    merged = list(deduplication_fields)
    if SOURCE_LINE_INDEX_FIELD.lower() not in {field.lower() for field in merged}:
        merged.append(SOURCE_LINE_INDEX_FIELD)
    return merged


def merge_hash_identity_values(
    base_identity_values: list[dict[str, Any]] | dict[str, Any] | None,
    extra_identity_values: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | dict[str, Any] | None:
    if not extra_identity_values:
        return base_identity_values

    if isinstance(base_identity_values, dict):
        return [
            {**base_identity_values, **extra}
            for extra in extra_identity_values
        ]

    base_list = list(base_identity_values or [])
    if len(base_list) < len(extra_identity_values):
        base_list.extend({} for _ in range(len(extra_identity_values) - len(base_list)))

    merged: list[dict[str, Any]] = []
    for base, extra in zip(base_list, extra_identity_values):
        merged.append({**(base or {}), **(extra or {})})
    return merged


def _coerce_raw_data(raw_data: Any) -> dict[str, Any]:
    if isinstance(raw_data, dict):
        return dict(raw_data)
    if isinstance(raw_data, str) and raw_data.strip():
        try:
            loaded = json.loads(raw_data)
        except json.JSONDecodeError:
            return {}
        return dict(loaded) if isinstance(loaded, dict) else {}
    return {}


def merge_orders_raw_data_prefer_non_empty(
    existing_raw_data: Any,
    incoming_raw_data: dict[str, Any],
) -> dict[str, Any]:
    existing = _coerce_raw_data(existing_raw_data)
    merged = dict(incoming_raw_data or {})

    for field in ORDER_LEVEL_AMOUNT_FIELDS:
        if field not in existing:
            continue
        if _is_blank(existing.get(field)):
            continue
        if _is_blank(merged.get(field)):
            merged[field] = existing[field]

    return merged
