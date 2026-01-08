#!/usr/bin/env python3
"""
标准字段到数据库列名映射表（向后兼容层）

关键说明：
- 标准字段（field_code）现在直接使用数据库列名（简化设计）
- 本模块仅作为向后兼容层，处理旧的field_code（如order_ts, account_id）
- 新生成的field_code应该直接使用数据库列名，不需要转换
- 未来可以逐步移除此模块，全部使用field_code=数据库列名
"""

from typing import Dict, Optional

# 标准字段 -> 数据库列名映射表（Orders域）
FIELD_TO_COLUMN_ORDERS: Dict[str, str] = {
    # 英文标准字段（直接映射）
    "order_id": "order_id",
    "order_ts": "order_time_utc",
    "order_date_local": "order_date_local",
    "platform_sku": "platform_sku",
    "quantity": "quantity",
    "total_amount": "total_amount",
    "currency": "currency",
    "platform_code": "platform_code",
    "shop_id": "shop_id",
    "account_id": "account",
    
    # 中文标准字段（需要转换）
    "订单号": "order_id",
    "下单时间": "order_time_utc",
    "订单日期": "order_date_local",
    "平台SKU": "platform_sku",
    "数量": "quantity",
    "订单金额": "total_amount",
    "金额": "total_amount",
    "币种": "currency",
    "平台": "platform_code",
    "店铺": "shop_id",
    "账号": "account",
}

# 标准字段 -> 数据库列名映射表（Products域）
FIELD_TO_COLUMN_PRODUCTS: Dict[str, str] = {
    "platform_sku": "platform_sku",
    "product_name": "product_name",
    "price": "price",
    "stock": "stock",
    "平台SKU": "platform_sku",
    "商品名称": "product_name",
    "价格": "price",
    "库存": "stock",
}

# 标准字段 -> 数据库列名映射表（Analytics/Traffic域）
FIELD_TO_COLUMN_ANALYTICS: Dict[str, str] = {
    "metric_date": "metric_date",
    "page_views": "page_views",
    "unique_visitors": "unique_visitors",
    "conversion_rate": "conversion_rate",
    "统计日期": "metric_date",
    "浏览量": "page_views",
    "访客数": "unique_visitors",
    "转化率": "conversion_rate",
}

# 标准字段 -> 数据库列名映射表（Services域）
FIELD_TO_COLUMN_SERVICES: Dict[str, str] = {
    "service_date": "service_date",
    "service_type": "service_type",
    "amount": "amount",
    "费用日期": "service_date",
    "费用类型": "service_type",
    "金额": "amount",
}

# 统一映射表（按域）
FIELD_TO_COLUMN_MAP: Dict[str, Dict[str, str]] = {
    "orders": FIELD_TO_COLUMN_ORDERS,
    "products": FIELD_TO_COLUMN_PRODUCTS,
    "analytics": FIELD_TO_COLUMN_ANALYTICS,
    "traffic": FIELD_TO_COLUMN_ANALYTICS,  # traffic复用analytics映射
    "services": FIELD_TO_COLUMN_SERVICES,
}


def convert_standard_field_to_column(standard_field: str, domain: str) -> Optional[str]:
    """
    将标准字段转换为数据库列名（向后兼容层）
    
    注意：新设计下，field_code应该直接使用数据库列名，不需要转换。
    此函数仅用于向后兼容旧的field_code（如order_ts, account_id）。
    
    Args:
        standard_field: 标准字段代码（新的应该直接是数据库列名，旧的可能是order_ts等）
        domain: 数据域（orders/products/analytics/services/traffic）
    
    Returns:
        数据库列名（英文），如果找不到映射则返回原值（假设已经是数据库列名）
    
    Examples:
        >>> convert_standard_field_to_column("order_ts", "orders")  # 旧字段
        'order_time_utc'
        >>> convert_standard_field_to_column("order_time_utc", "orders")  # 新字段（已经是数据库列名）
        'order_time_utc'  # 直接返回原值
        >>> convert_standard_field_to_column("account_id", "orders")  # 旧字段
        'account'
        >>> convert_standard_field_to_column("account", "orders")  # 新字段（已经是数据库列名）
        'account'  # 直接返回原值
    """
    domain_map = FIELD_TO_COLUMN_MAP.get(domain, {})
    # 如果找到映射，使用映射值（向后兼容）
    # 如果没有找到映射，假设已经是数据库列名，直接返回
    return domain_map.get(standard_field, standard_field)


def convert_row_fields_to_columns(row: Dict[str, any], domain: str) -> Dict[str, any]:
    """
    将数据行中的标准字段转换为数据库列名（向后兼容层）
    
    注意：新设计下，field_code应该直接使用数据库列名，row的键已经是数据库列名。
    此函数仅用于向后兼容旧的field_code（如order_ts, account_id）。
    
    策略：
    - 核心字段：转换为数据库列名（向后兼容），直接写入标准列
    - 未映射字段：保留原字段名，进入attributes JSONB列
    
    Args:
        row: 数据行字典（键为标准字段名，新设计下应该已经是数据库列名）
        domain: 数据域
    
    Returns:
        转换后的数据行（键为数据库列名）
    """
    converted = {}
    attributes = {}
    
    for field_name, value in row.items():
        # 转换（向后兼容旧的field_code）
        db_column = convert_standard_field_to_column(field_name, domain)
        if db_column:
            # 映射到数据库列
            converted[db_column] = value
        else:
            # 未映射字段进入attributes
            attributes[field_name] = value
    
    # 如果有attributes，添加到行中
    if attributes:
        converted["attributes"] = attributes
    
    return converted

