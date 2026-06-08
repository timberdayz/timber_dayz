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
from modules.core.logger import get_logger
from backend.services.semantic_field_registry import is_canonical_semantic_key, normalize_semantic_key

logger = get_logger(__name__)

# [*] v4.15.0新增:去重策略配置
# [*] v4.16.0更新:所有数据域统一使用UPSERT策略(更新而非跳过)
# 原因:核心关键字字段名的原因,如果有重复数据,都应该是更新的数据
# 例如:库存数量、销售数量等指标字段应该更新,而不是跳过
DEDUPLICATION_STRATEGY: Dict[str, str] = {
    'inventory': 'UPSERT',  # 库存数据域使用UPSERT(更新而非重复插入)
    'orders': 'UPSERT',     # [*] v4.16.0更新:订单数据域使用UPSERT(更新订单金额、数量等)
    'products': 'UPSERT',  # [*] v4.16.0更新:产品数据域使用UPSERT(更新产品指标)
    'traffic': 'UPSERT',   # [*] v4.16.0更新:流量数据域使用UPSERT(更新流量指标)
    'services': 'UPSERT',  # [*] v4.16.0更新:服务数据域使用UPSERT(更新服务指标)
    'analytics': 'UPSERT', # [*] v4.16.0更新:分析数据域使用UPSERT(更新分析指标)
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
    'inventory': ['raw_data', 'ingest_timestamp', 'file_id', 'header_columns', 'currency_code'],
    'orders': ['raw_data', 'ingest_timestamp', 'file_id', 'header_columns', 'currency_code'],
    'products': [
        'raw_data',
        'ingest_timestamp',
        'file_id',
        'header_columns',
        'currency_code',
        'metric_date',
        'period_start_date',
        'period_end_date',
        'period_start_time',
        'period_end_time',
    ],
    'traffic': ['raw_data', 'ingest_timestamp', 'file_id', 'header_columns', 'currency_code'],
    'services': ['raw_data', 'ingest_timestamp', 'file_id', 'header_columns', 'currency_code'],
    'analytics': ['raw_data', 'ingest_timestamp', 'file_id', 'header_columns', 'currency_code'],
}

# 默认核心字段配置(data_domain -> [核心字段列表])
DEFAULT_DEDUPLICATION_FIELDS: Dict[str, List[str]] = {
    'orders': ['order_id'],
    'products': ['platform_sku', 'product_id', 'metric_date'],
    'inventory': ['platform_sku', 'product_id', 'warehouse_name', 'metric_date'],
    'traffic': ['metric_date'],
    'services': ['service_id', 'metric_date'],
    'analytics': ['metric_date'],
}

# 子类型特定配置(sub_domain -> [核心字段列表])
SUB_DOMAIN_DEDUPLICATION_FIELDS: Dict[str, List[str]] = {
    # 可以添加子类型特定的配置
    # 例如:'ai_assistant': ['assistant_id', 'date', 'platform_code', 'shop_id'],
}


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


def get_default_deduplication_fields(
    data_domain: str,
    sub_domain: Optional[str] = None
) -> List[str]:
    """
    获取默认核心字段配置
    
    Args:
        data_domain: 数据域(如 'orders', 'products')
        sub_domain: 子类型(可选,如 'ai_assistant')
    
    Returns:
        核心字段列表
    """
    # 优先使用子类型特定配置
    if sub_domain and sub_domain in SUB_DOMAIN_DEDUPLICATION_FIELDS:
        fields = SUB_DOMAIN_DEDUPLICATION_FIELDS[sub_domain]
        logger.debug(
            f"[DedupFields] 使用子类型配置: {sub_domain} -> {fields}"
        )
        return fields
    
    # 使用数据域默认配置
    if data_domain in DEFAULT_DEDUPLICATION_FIELDS:
        fields = DEFAULT_DEDUPLICATION_FIELDS[data_domain]
        logger.debug(
            f"[DedupFields] 使用数据域默认配置: {data_domain} -> {fields}"
        )
        return fields
    
    # 如果没有配置,返回空列表(将使用所有业务字段)
    logger.warning(
        f"[DedupFields] 未找到数据域 {data_domain} 的默认配置,"
        f"将使用所有业务字段计算data_hash"
    )
    return []


def get_deduplication_fields(
    data_domain: str,
    template_fields: Optional[List[str]] = None,
    sub_domain: Optional[str] = None,
    header_bindings: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    """
    获取核心字段(优先级:模板配置 > 默认配置 > 所有字段)
    
    Args:
        data_domain: 数据域
        template_fields: 模板配置的核心字段(可选)
        sub_domain: 子类型(可选)
    
    Returns:
        核心字段列表
    """
    # 1. 优先使用模板配置
    if template_fields:
        normalized_template_fields: List[str] = []
        for field in template_fields:
            if is_canonical_semantic_key(field):
                normalized_template_fields.append(normalize_semantic_key(field) or str(field).strip())
            else:
                normalized_template_fields.append(str(field).strip())
        merged_fields = _append_required_identity_fields(
            normalized_template_fields,
            data_domain=data_domain,
            sub_domain=sub_domain,
        )
        logger.debug(
            f"[DedupFields] 使用模板配置的核心字段: {merged_fields}"
        )
        return merged_fields
    
    # 2. 使用默认配置
    default_fields = get_default_deduplication_fields(data_domain, sub_domain)
    if default_fields:
        merged_fields = _append_required_identity_fields(
            default_fields,
            data_domain=data_domain,
            sub_domain=sub_domain,
        )
        logger.debug(
            f"[DedupFields] 使用默认配置的核心字段: {merged_fields}"
        )
        return merged_fields
    
    # 3. 如果没有配置,返回空列表(表示使用所有业务字段)
    logger.debug(
        f"[DedupFields] 未配置核心字段,将使用所有业务字段计算data_hash"
    )
    return []


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
    strategy = DEDUPLICATION_STRATEGY.get(data_domain, 'UPSERT')  # [*] v4.16.0更新:默认策略改为UPSERT
    logger.debug(
        f"[DedupStrategy] 数据域 {data_domain} 使用策略: {strategy}"
    )
    return strategy


def get_upsert_update_fields(data_domain: str) -> List[str]:
    """
    获取UPSERT更新字段列表(统一接口)
    
    Args:
        data_domain: 数据域(如 'orders', 'inventory')
    
    Returns:
        更新字段列表
    """
    fields = UPSERT_UPDATE_FIELDS.get(data_domain, [
        'raw_data', 'ingest_timestamp', 'file_id', 'header_columns', 'currency_code'
    ])
    logger.debug(
        f"[UpsertFields] 数据域 {data_domain} 的更新字段: {fields}"
    )
    return fields
