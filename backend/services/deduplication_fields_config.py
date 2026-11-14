#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
默认核心字段配置(Default Deduplication Fields Config)

v4.14.0新增:
- 定义各数据域+子类型的默认核心字段
- 用于data_hash计算(基于核心字段,不受表头变化影响)

职责:
- 根据data_domain和sub_domain返回默认核心字段
- 支持模板配置覆盖默认配置
"""

from typing import List, Optional, Dict, Any
from modules.core.data_domains import normalize_data_domain
from modules.core.logger import get_logger
from backend.services.semantic_field_registry import (
    is_canonical_semantic_key,
    normalize_semantic_key,
)

logger = get_logger(__name__)

# [*] v4.15.0新增:去重策略配置
# [*] v4.16.0更新:所有数据域统一使用UPSERT策略(更新而非跳过)
# 原因:核心关键字字段名的原因,如果有重复数据,都应该是更新的数据
# 例如:库存数量、销售数量等指标字段应该更新,而不是跳过
DEDUPLICATION_STRATEGY: Dict[str, str] = {
    "inventory": "UPSERT",  # 库存数据域使用UPSERT(更新而非重复插入)
    "orders": "UPSERT",  # [*] v4.16.0更新:订单数据域使用UPSERT(更新订单金额、数量等)
    "products": "UPSERT",  # [*] v4.16.0更新:产品数据域使用UPSERT(更新产品指标)
    "services": "UPSERT",  # [*] v4.16.0更新:服务数据域使用UPSERT(更新服务指标)
    "analytics": "UPSERT",  # [*] v4.16.0更新:分析数据域使用UPSERT(更新分析指标)
    # [D8] 原 "traffic" 条目已并入 "analytics"(traffic 域已废弃并入 analytics)
}

# [*] v4.15.0新增:UPSERT更新字段配置(统一配置,保持一致性)
# [*] v4.16.0更新:所有数据域统一使用UPSERT策略,此配置定义冲突时更新的字段
# 更新字段说明:
# - raw_data: 业务数据(JSONB格式,包含所有指标字段,如库存数量、销售数量等)
# - ingest_timestamp: 入库时间戳(记录最新更新时间)
# - file_id: 文件ID(记录数据来源)
# - header_columns: 表头字段列表(记录表头信息)
# - currency_code: 货币代码(记录货币信息)
UPSERT_UPDATE_FIELDS: Dict[str, List[str]] = {
    "inventory": [
        "raw_data",
        "ingest_timestamp",
        "file_id",
        "header_columns",
        "currency_code",
    ],
    "orders": [
        "raw_data",
        "ingest_timestamp",
        "file_id",
        "header_columns",
        "currency_code",
    ],
    "products": [
        "raw_data",
        "ingest_timestamp",
        "file_id",
        "header_columns",
        "currency_code",
        "metric_date",
        "period_start_date",
        "period_end_date",
        "period_start_time",
        "period_end_time",
    ],
    # [D8] 原独立的 "traffic" 条目已并入 "analytics"(traffic 域已废弃并入 analytics)
    "services": [
        "raw_data",
        "ingest_timestamp",
        "file_id",
        "header_columns",
        "currency_code",
    ],
    "analytics": [
        "raw_data",
        "ingest_timestamp",
        "file_id",
        "header_columns",
        "currency_code",
    ],
}

# 推荐核心字段配置(data_domain -> [核心字段列表])
#
# ⚠️ 这是**推荐值**，不是权威，更**不是回落**（2026-11-14 起）。
#
# 权威 = 模板的去重字段表（``core.field_mapping_templates.deduplication_fields``）。
# 本表只有两个用途：
#   1. 工作台给用户的**建议**（用户可以改，也可以全不采纳）；
#   2. 模板保存时用户没勾选时的**填充建议**。
#
# 为什么不能拿它当回落（历史教训）
# --------------------------------
# 它曾经是 ``get_deduplication_fields`` 的回落分支：模板没配去重字段时，
# 静默用本表算指纹。而本表的内容是**标准字段键**
# （``platform_sku`` / ``product_id`` / ``warehouse_name``），
# 妙手的中文表头里根本没有这些名字 ⇒ 一个都取不到
# ⇒ 实测 3 个不同 SKU 算出**完全相同**的指纹 ⇒ 同一天所有行互相覆盖
# ⇒ **一天只剩一行，而且全程不报错**。
#
# ⇒ 现在模板没配去重字段**直接报错**（见
#   :class:`DeduplicationFieldsNotConfiguredError`），不再有静默回落。
#   27 个维度的模板全部配了去重字段（``backend/tests/data_pipeline/
#   test_core_fields_hash_consistency.py`` 守护），生产 27 个 published
#   模板也全部非空 ⇒ 这条报错只在**真的漏配**时触发。
RECOMMENDED_DEDUPLICATION_FIELDS: Dict[str, List[str]] = {
    "orders": ["order_id"],
    "products": ["platform_sku", "product_id", "metric_date"],
    "inventory": ["platform_sku", "product_id", "warehouse_name", "metric_date"],
    # [D8] 原独立的 "traffic" 条目已并入 "analytics"(traffic 域已废弃并入 analytics)
    "services": ["service_id", "metric_date"],
    "analytics": ["metric_date"],
}

AUTO_DATE_IDENTITY_FIELD_ORDER = [
    "metric_date",
    "period_start_date",
    "period_end_date",
    "period_start_time",
    "period_end_time",
]
AUTO_DATE_IDENTITY_FIELDS = set(AUTO_DATE_IDENTITY_FIELD_ORDER)


class DeduplicationFieldsNotConfiguredError(ValueError):
    """该维度没有配置去重字段 —— 必须先配置模板，**不许静默算错身份**。

    为什么必须报错而不是回落
    ------------------------
    回落到域默认表 = 用**标准字段键**去原始数据里取值
    ⇒ 中文表头一个都取不到 ⇒ 所有行算出同一个指纹 ⇒ 同一天互相覆盖
    ⇒ 一天只剩一行，**而且不报错**（2026-11-14 开发库实测）。
    """


def _append_required_identity_fields(
    fields: List[str],
    *,
    data_domain: str,
    sub_domain: Optional[str] = None,
) -> List[str]:
    """
    为 data_hash 计算补齐最小身份字段，避免不同平台/店铺发生跨文件冲突。
    """
    required_fields = ["platform_code", "shop_id"]
    if sub_domain:
        required_fields.append("sub_domain")

    merged: List[str] = []
    seen = set()
    for field in [*(fields or []), *required_fields]:
        normalized = str(field).strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        merged.append(normalized)
    return merged


def get_recommended_deduplication_fields(data_domain: str) -> List[str]:
    """获取**推荐**核心字段（工作台建议用，不是权威，也不是回落）。

    Args:
        data_domain: 数据域(如 'orders', 'products')

    Returns:
        推荐字段列表；该数据域没有推荐值时返回空列表
        （**空列表不代表可以回落** —— 见
        :func:`get_deduplication_fields` 的报错语义）。
    """
    # [D8] 归一数据域(traffic -> analytics),避免别名落到"未找到配置"分支
    data_domain = normalize_data_domain(data_domain)
    fields = RECOMMENDED_DEDUPLICATION_FIELDS.get(data_domain) or []
    if fields:
        logger.debug(f"[DedupFields] 数据域 {data_domain} 的推荐核心字段: {fields}")
    else:
        logger.debug(f"[DedupFields] 数据域 {data_domain} 没有推荐核心字段")
    return list(fields)


def get_deduplication_fields(
    data_domain: str,
    template_fields: Optional[List[str]] = None,
    sub_domain: Optional[str] = None,
    header_bindings: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    """获取核心字段（**唯一路径 = 模板配置**）。

    Args:
        data_domain: 数据域
        template_fields: 模板配置的核心字段（**权威**）
        sub_domain: 子类型
        header_bindings: 表头绑定（预留）

    Returns:
        核心字段列表

    Raises:
        DeduplicationFieldsNotConfiguredError: 模板没有配置去重字段。
            **这是刻意的 fail-closed**：见该异常类的说明 ——
            静默回落会算出「所有行同一个指纹」，一天只剩一行且不报错。
    """
    if not template_fields:
        raise DeduplicationFieldsNotConfiguredError(
            "数据域 {domain}{sub}没有配置去重字段，无法计算行身份（data_hash）。"
            "请先在模板工作台配置该维度的去重字段（核心字段清单里勾选参与去重的列）。"
            "系统**不会**回落到域默认配置 —— 那会让所有行算出同一个指纹、"
            "同一天互相覆盖，而且不报错。".format(
                domain=data_domain,
                sub="/{0}".format(sub_domain) if sub_domain else "",
            )
        )

    normalized_template_fields: List[str] = []
    for field in template_fields:
        if is_canonical_semantic_key(field):
            normalized_template_fields.append(
                normalize_semantic_key(field) or str(field).strip()
            )
        else:
            normalized_template_fields.append(str(field).strip())
    merged_fields = _append_required_identity_fields(
        normalized_template_fields,
        data_domain=data_domain,
        sub_domain=sub_domain,
    )
    logger.debug(f"[DedupFields] 使用模板配置的核心字段: {merged_fields}")
    return merged_fields


def append_auto_date_identity_fields(
    deduplication_fields: Optional[List[str]],
    field_parse_rules: Optional[List[Dict[str, Any]]],
) -> List[str]:
    """
    Append date/time identities produced by template rules to Data Hash fields.

    Users select source-file business identity fields. Date and time identities
    are system identities produced by field_parse_rules and must participate in
    hash without requiring manual selection.
    """
    merged: List[str] = []
    seen = set()
    for field in deduplication_fields or []:
        text = str(field or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(text)

    auto_fields = set()
    for rule in field_parse_rules or []:
        if not isinstance(rule, dict):
            continue
        semantic_key = normalize_semantic_key(
            rule.get("target_field") or rule.get("semantic_key") or rule.get("field")
        )
        if semantic_key in AUTO_DATE_IDENTITY_FIELDS:
            auto_fields.add(semantic_key)

    for field in AUTO_DATE_IDENTITY_FIELD_ORDER:
        if field not in auto_fields or field.lower() in seen:
            continue
        seen.add(field.lower())
        merged.append(field)
    return merged


def get_deduplication_strategy(data_domain: str) -> str:
    """
    获取去重策略(INSERT vs UPSERT)

    [*] v4.16.0更新:所有数据域统一使用UPSERT策略(更新而非跳过)
    原因:核心关键字字段名的原因,如果有重复数据,都应该是更新的数据
    例如:库存数量、销售数量等指标字段应该更新,而不是跳过

    Args:
        data_domain: 数据域(如 'orders', 'inventory')

    Returns:
        策略名称:'INSERT' 或 'UPSERT'(v4.16.0后默认返回'UPSERT')
    """
    strategy = DEDUPLICATION_STRATEGY.get(
        normalize_data_domain(data_domain), "UPSERT"
    )  # [*] v4.16.0更新:默认策略改为UPSERT
    logger.debug(f"[DedupStrategy] 数据域 {data_domain} 使用策略: {strategy}")
    return strategy


def get_upsert_update_fields(data_domain: str) -> List[str]:
    """
    获取UPSERT更新字段列表(统一接口)

    Args:
        data_domain: 数据域(如 'orders', 'inventory')

    Returns:
        更新字段列表
    """
    fields = UPSERT_UPDATE_FIELDS.get(
        normalize_data_domain(data_domain),
        ["raw_data", "ingest_timestamp", "file_id", "header_columns", "currency_code"],
    )
    logger.debug(f"[UpsertFields] 数据域 {data_domain} 的更新字段: {fields}")
    return fields
