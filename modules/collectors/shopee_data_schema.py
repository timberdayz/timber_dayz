#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Shopee数据架构定义
基于妙手ERP实际销售数据分析的完整字段映射和数据结构
数据规模: 4130条记录, 118个字段
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from enum import Enum

class DataCategory(Enum):
    """数据分类"""
    BASIC_INFO = "basic_info"           # 基础信息 (9个字段)
    ORDER_INFO = "order_info"           # 订单信息
    PRODUCT_INFO = "product_info"       # 商品信息 (6个字段)
    PRICING = "pricing"                 # 价格信息 (6个字段)
    DISCOUNT = "discount"               # 折扣优惠 (12个字段)
    PAYMENT = "payment"                 # 支付信息 (4个字段)
    SHIPPING = "shipping"               # 运费信息 (14个字段)
    COMMISSION_FEE = "commission_fee"   # 佣金手续费 (10个字段)
    COST_PROFIT = "cost_profit"         # 成本利润 (16个字段)
    TAX = "tax"                         # 税费信息 (24个字段)
    SETTLEMENT = "settlement"           # 结算信息 (4个字段)
    RETURN_REFUND = "return_refund"     # 退货退款 (14个字段)

@dataclass
class FieldDefinition:
    """字段定义"""
    name: str                          # 字段名
    category: DataCategory             # 数据分类
    data_type: str                     # 数据类型
    required: bool = False             # 是否必填
    description: str = ""              # 字段描述
    example: Any = None                # 示例值
    collection_priority: int = 3       # 采集优先级 (1=最高, 5=最低)

# 核心必采集字段定义 (优先级1)
CORE_FIELDS = {
    "platform": FieldDefinition(
        name="平台", category=DataCategory.BASIC_INFO, data_type="str", 
        required=True, description="电商平台名称", example="Shopee", collection_priority=1
    ),
    "site": FieldDefinition(
        name="站点", category=DataCategory.BASIC_INFO, data_type="str",
        required=True, description="平台站点", example="新加坡", collection_priority=1
    ),
    "store_name": FieldDefinition(
        name="店铺名称", category=DataCategory.BASIC_INFO, data_type="str",
        required=True, description="店铺名称", example="4店包包", collection_priority=1
    ),
    "order_id": FieldDefinition(
        name="订单编号", category=DataCategory.ORDER_INFO, data_type="str",
        required=True, description="订单唯一标识", example="250524Q3JJ6HUQ", collection_priority=1
    ),
    "package_id": FieldDefinition(
        name="包裹号", category=DataCategory.ORDER_INFO, data_type="str",
        required=True, description="包裹编号", example="MS20250524215520019", collection_priority=1
    ),
    "currency": FieldDefinition(
        name="币种", category=DataCategory.BASIC_INFO, data_type="str",
        required=True, description="交易币种", example="SGD", collection_priority=1
    ),
    "order_time": FieldDefinition(
        name="下单时间", category=DataCategory.ORDER_INFO, data_type="datetime",
        required=True, description="订单创建时间", example="2025-05-24 21:55:18", collection_priority=1
    ),
    "order_status": FieldDefinition(
        name="交易状态", category=DataCategory.ORDER_INFO, data_type="str",
        required=True, description="订单当前状态", example="待发货", collection_priority=1
    ),
    "product_title": FieldDefinition(
        name="产品标题", category=DataCategory.PRODUCT_INFO, data_type="str",
        required=True, description="商品标题", example="Paint Runner Pro Roller Brush", collection_priority=1
    ),
    "quantity": FieldDefinition(
        name="购买数量", category=DataCategory.PRODUCT_INFO, data_type="float",
        required=True, description="商品购买数量", example=1.0, collection_priority=1
    ),
    "unit_price": FieldDefinition(
        name="产品单价", category=DataCategory.PRICING, data_type="float",
        required=True, description="商品单价(原币种)", example=11.47, collection_priority=1
    ),
    "unit_price_rmb": FieldDefinition(
        name="产品单价(RMB)", category=DataCategory.PRICING, data_type="float",
        required=True, description="商品单价(人民币)", example=64.29, collection_priority=1
    ),
    "original_amount": FieldDefinition(
        name="订单原始金额", category=DataCategory.PRICING, data_type="float",
        required=True, description="订单原始金额(原币种)", example=11.47, collection_priority=1
    ),
    "original_amount_rmb": FieldDefinition(
        name="订单原始金额(RMB)", category=DataCategory.PRICING, data_type="float",
        required=True, description="订单原始金额(人民币)", example=64.29, collection_priority=1
    ),
    "buyer_payment": FieldDefinition(
        name="买家支付", category=DataCategory.PAYMENT, data_type="float",
        required=True, description="买家实际支付金额", example=11.44, collection_priority=1
    ),
    "buyer_payment_rmb": FieldDefinition(
        name="买家支付(RMB)", category=DataCategory.PAYMENT, data_type="float",
        required=True, description="买家实际支付金额(人民币)", example=64.13, collection_priority=1
    ),
    "platform_commission": FieldDefinition(
        name="平台佣金", category=DataCategory.COMMISSION_FEE, data_type="float",
        required=True, description="平台收取的佣金", example=1.61, collection_priority=1
    ),
    "platform_commission_rmb": FieldDefinition(
        name="平台佣金(RMB)", category=DataCategory.COMMISSION_FEE, data_type="float",
        required=True, description="平台收取的佣金(人民币)", example=9.02, collection_priority=1
    ),
    "transaction_fee": FieldDefinition(
        name="交易手续费", category=DataCategory.COMMISSION_FEE, data_type="float",
        required=True, description="交易手续费", example=0.34, collection_priority=1
    ),
    "transaction_fee_rmb": FieldDefinition(
        name="交易手续费(RMB)", category=DataCategory.COMMISSION_FEE, data_type="str",
        required=True, description="交易手续费(人民币)", example="1.91", collection_priority=1
    ),
    "estimated_settlement": FieldDefinition(
        name="预估回款金额", category=DataCategory.COST_PROFIT, data_type="float",
        required=True, description="预估回款金额", example=7.49, collection_priority=1
    ),
    "estimated_settlement_rmb": FieldDefinition(
        name="预估回款金额(RMB)", category=DataCategory.COST_PROFIT, data_type="float",
        required=True, description="预估回款金额(人民币)", example=41.98, collection_priority=1
    ),
    "profit": FieldDefinition(
        name="利润", category=DataCategory.COST_PROFIT, data_type="float",
        required=True, description="订单利润", example=3.92, collection_priority=1
    ),
    "profit_rmb": FieldDefinition(
        name="利润(RMB)", category=DataCategory.COST_PROFIT, data_type="float",
        required=True, description="订单利润(人民币)", example=21.98, collection_priority=1
    ),
}

@dataclass
class ShopeeOrderData:
    """Shopee订单数据模型 - 核心字段版本"""
    # 基础信息
    platform: str = "Shopee"
    site: str = ""
    store_name: str = ""
    order_id: str = ""
    package_id: str = ""
    currency: str = ""
    order_time: Optional[datetime] = None
    order_status: str = ""
    
    # 商品信息
    product_title: str = ""
    quantity: float = 0.0
    
    # 价格信息
    unit_price: float = 0.0
    unit_price_rmb: float = 0.0
    original_amount: float = 0.0
    original_amount_rmb: float = 0.0
    
    # 支付信息
    buyer_payment: float = 0.0
    buyer_payment_rmb: float = 0.0
    
    # 佣金费用
    platform_commission: float = 0.0
    platform_commission_rmb: float = 0.0
    transaction_fee: float = 0.0
    transaction_fee_rmb: Union[float, str] = 0.0
    
    # 成本利润
    estimated_settlement: float = 0.0
    estimated_settlement_rmb: float = 0.0
    profit: float = 0.0
    profit_rmb: float = 0.0
    
    # 扩展数据
    extended_data: Dict[str, Any] = field(default_factory=dict)
    collection_time: datetime = field(default_factory=datetime.now)
    data_source: str = "shopee_collector"

def get_core_field_names() -> List[str]:
    """获取核心必采集字段名称列表"""
    return list(CORE_FIELDS.keys())

def get_field_definition(field_name: str) -> Optional[FieldDefinition]:
    """获取字段定义"""
    return CORE_FIELDS.get(field_name)

def validate_core_data(data: Dict[str, Any]) -> Dict[str, List[str]]:
    """验证核心数据完整性"""
    errors = {
        "missing_required": [],
        "invalid_types": [],
        "warnings": []
    }
    
    # 检查必填字段
    required_fields = [name for name, field in CORE_FIELDS.items() if field.required]
    for field_name in required_fields:
        if field_name not in data or data[field_name] is None:
            errors["missing_required"].append(field_name)
    
    return errors

# 数据采集策略配置
COLLECTION_STRATEGY = {
    "phase_1_core": {
        "description": "第一阶段：核心必采集字段",
        "fields": list(CORE_FIELDS.keys()),
        "priority": 1,
        "required_success_rate": 0.95
    },
    "phase_2_extended": {
        "description": "第二阶段：扩展有用字段",
        "fields": [
            "payment_time", "product_link", "platform_sku", "merchant_sku",
            "purchase_cost", "purchase_cost_rmb", "advertising_cost", "advertising_cost_rmb",
            "merchant_shipping_fee", "merchant_shipping_fee_rmb", "settled_amount", "settled_amount_rmb"
        ],
        "priority": 2,
        "required_success_rate": 0.80
    },
    "phase_3_complete": {
        "description": "第三阶段：完整118字段",
        "fields": "all_118_fields",
        "priority": 3,
        "required_success_rate": 0.60
    }
} 