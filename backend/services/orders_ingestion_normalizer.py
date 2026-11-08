#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Orders-specific B-class ingestion helpers."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

from backend.services.semantic_field_registry import (
    ORDER_LEVEL_AMOUNT_FIELDS,
)

# [*] `ORDER_LEVEL_AMOUNT_FIELDS` **从字典派生**(单一事实源):
#   `backend/services/semantic_field_registry.py` 里带
#   `order_level_amount=True` 标记的标准字段 → 其在 orders 域登记的源表列名
#   (含各平台列名) → 裸表头 / `(RMB)` 变体 / snake_case 变体。
#   以前这里是手写的 40+ 条清单, 与字典各写各的 ⇒ 字典加字段时清单不跟着变,
#   漏掉的订单级列会被**重复计入**(多 SKU 订单金额虚增)。
#   ⇒ 这里只 import, 不再手工维护。

SOURCE_LINE_INDEX_FIELD = "_source_line_index"

#: [*] 订单号缺失时的**确定性占位符前缀**。
#:
#: 占位符带**行号** ⇒ 每个缺订单号的行都拿到**独立**的占位符 ⇒
#: 不会被当成同一张订单的多行, 也不会被并进相邻的真实订单。
MISSING_ORDER_ID_PREFIX = "__missing_order_id__:"

ORDER_ID_FIELDS = (
    "order_id",
    "Order ID",
    "order_no",
    "订单编号",
    "订单号",
    "订单ID",
)


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

    Rows whose order id is missing stay **independent**: they get a
    deterministic placeholder (``__missing_order_id__:<行号>``) instead of
    inheriting the previous row's order id.
    """
    if not rows:
        return [], []

    order_ids: list[str] = []
    for index, row in enumerate(rows):
        order_id = _first_present(row, ORDER_ID_FIELDS)
        # [*] 订单号缺失 ⇒ 该行**独立成行**, 不继承上一行的订单号。
        #
        # 继承会有两个后果, 都是错的:
        #   1) **跨单错配** —— 缺订单号的行被算进上一张订单(金额、hash 作用域
        #      都挂到别人的订单号上);
        #   2) **少算** —— 它被当成那张订单的第 2+ 行 ⇒ 订单级金额被清空。
        #
        # ⇒ 用带行号的确定性占位符, 每个缺订单号的行都**独立**:
        #   不会被并进相邻的真实订单, 订单级金额也**原样保留**(宁可多算,
        #   也不错配/不少算)。
        order_ids.append(order_id or f"{MISSING_ORDER_ID_PREFIX}{index}")

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
    """给 orders 域的 hash 口径补上「明细行号」。

    [*] 不依赖「继承上一行订单号」: 订单号缺失的行现在是**独立**的行,
        拿不到 ``_source_line_index`` ⇒ 它的 hash 只能靠自身内容区分。
        这不影响本函数 —— 本函数只负责把行号列**加进 hash 的取值列**。
    """
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
        return [{**base_identity_values, **extra} for extra in extra_identity_values]

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
    """合并同一 hash 的两批 raw_data: 订单级字段**取非空的那个**。

    [*] 不依赖「继承上一行订单号」: 本函数只看**字段名**逐个比对, 不看行序、
        也不看订单号 ⇒ 订单号缺失的行独立入库后, 合并行为不变。
    """
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
