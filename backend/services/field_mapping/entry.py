"""
字段映射统一入口（单一真源）

对外仅暴露 get_mappings()，内部可自由组合模板/AI建议等策略，
以避免在路由或脚本层分散调用多个实现导致双维护。
"""

from __future__ import annotations

from typing import Dict, List

from backend.services.field_mapping.mapper import suggest_mappings
from backend.services.smart_field_mapper_v2 import SmartFieldMapperV2
from backend.services.field_mapping.normalizer import normalize_column_name


# 关键字段白名单（最小集）
KEY_FIELDS_BY_DOMAIN: Dict[str, List[str]] = {
    "orders": [
        "order_id",
        "order_date",
        "platform_sku",
        "quantity",
        "total_amount",
        "currency",
    ],
    "products": ["platform_sku", "product_name", "price", "currency"],
    "analytics": ["metric_date", "page_views", "unique_visitors"],
}


def get_mappings(
    columns: List[str],
    domain: str,
    source_platform: str | None = None,
) -> Dict[str, Dict]:
    """统一的字段映射入口。

    策略：
    1) 先尝试模板/词典规则（suggest_mappings）
    2) 对未命中的列，使用SmartFieldMapperV2补全候选
    """

    # 0) 列名标准化
    normalized_cols = [normalize_column_name(c) for c in columns]
    # 建立映射：标准化后仍需返回原列名键
    col_map = {normalize_column_name(c): c for c in columns}

    # 1) 规则/词典优先（用标准化列名）
    std_result = suggest_mappings(normalized_cols, domain)
    # 还原成原始列名为键
    result = {col_map.get(k, k): v for k, v in std_result.items()}

    # 2) 对未命中列使用AI建议补齐
    unmapped_cols = [c for c, m in result.items() if not m.get("standard")]
    if unmapped_cols:
        mapper = SmartFieldMapperV2()
        ai_mapped = mapper.map_fields(unmapped_cols, data_domain=domain, source_platform=source_platform or "")
        for col in unmapped_cols:
            mapped = ai_mapped.get(col)
            if mapped and mapped.get("standard"):
                result[col] = mapped

    return result


def get_key_fields(domain: str) -> List[str]:
    """返回该数据域的关键字段清单（用于审核阈值校验）。"""
    return KEY_FIELDS_BY_DOMAIN.get(domain, [])


