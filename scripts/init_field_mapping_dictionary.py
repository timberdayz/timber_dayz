#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
初始化字段映射辞典数据 - v4.3.7
构建初始中文同义词数据（orders/products/traffic）
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from modules.core.db import FieldMappingDictionary
from modules.core.logger import get_logger
from sqlalchemy import text

logger = get_logger(__name__)

# 初始字段辞典数据（精选高频字段 + 中文同义词）
INITIAL_DICTIONARY = [
    # ========== Orders 数据域 ==========
    {
        "field_code": "order_id",
        "cn_name": "订单号",
        "en_name": "Order ID",
        "description": "订单唯一标识符",
        "data_domain": "orders",
        "field_group": "dimension",
        "is_required": True,
        "data_type": "string",
        "synonyms": ["订单号", "订单编号", "order_id", "order_no", "ddh", "订单ID"],
        "platform_synonyms": {"shopee": ["订单编号"], "tiktok": ["订单号"], "miaoshou": ["订单号"]},
        "example_values": ["240925AB12345", "ORD-2024-001"],
        "display_order": 1,
        "match_weight": 2.0,
    },
    {
        "field_code": "order_date_local",
        "cn_name": "下单时间",
        "en_name": "Order Date",
        "description": "订单创建的本地时间",
        "data_domain": "orders",
        "field_group": "datetime",
        "is_required": True,
        "data_type": "datetime",
        "synonyms": ["下单时间", "订单时间", "创建时间", "order_date", "order_time", "xdsj", "创单时间"],
        "platform_synonyms": {"shopee": ["下单时间"], "miaoshou": ["订单时间"]},
        "example_values": ["2024-09-25 10:30:00", "25/09/2024"],
        "display_order": 2,
        "match_weight": 2.0,
    },
    {
        "field_code": "shop_id",
        "cn_name": "店铺",
        "en_name": "Shop ID",
        "description": "店铺标识",
        "data_domain": "orders",
        "field_group": "dimension",
        "is_required": True,
        "data_type": "string",
        "synonyms": ["店铺", "店铺ID", "shop", "shop_id", "dp", "店铺编号"],
        "example_values": ["shop_sg_001", "the_king_s_lucky_shop__1242912097"],
        "display_order": 3,
        "match_weight": 2.0,
    },
    {
        "field_code": "platform_code",
        "cn_name": "平台",
        "en_name": "Platform",
        "description": "电商平台代码",
        "data_domain": "orders",
        "field_group": "dimension",
        "is_required": True,
        "data_type": "string",
        "synonyms": ["平台", "平台代码", "platform", "platform_code", "pt"],
        "example_values": ["shopee", "tiktok", "miaoshou"],
        "display_order": 4,
        "match_weight": 2.0,
    },
    {
        "field_code": "total_amount",
        "cn_name": "订单金额",
        "en_name": "Total Amount",
        "description": "订单总金额（含运费、优惠后）",
        "data_domain": "orders",
        "field_group": "amount",
        "is_required": True,
        "data_type": "currency",
        "value_range": ">=0",
        "synonyms": ["订单金额", "总金额", "实收金额", "金额", "total_amount", "gmv", "je", "amount", "销售额"],
        "platform_synonyms": {"shopee": ["实收金额"], "tiktok": ["订单金额"], "miaoshou": ["销售额"]},
        "example_values": ["123.45", "456.78 BRL"],
        "display_order": 5,
        "match_weight": 2.0,
    },
    {
        "field_code": "buyer_paid_amount",
        "cn_name": "买家实付",
        "en_name": "Buyer Paid Amount",
        "description": "买家实际支付的金额",
        "data_domain": "orders",
        "field_group": "amount",
        "is_required": False,
        "data_type": "currency",
        "value_range": ">=0",
        "synonyms": ["买家实付", "实付金额", "buyer_paid", "paid_amount", "买家支付"],
        "example_values": ["100.00", "99.99 USD"],
        "display_order": 10,
        "match_weight": 1.5,
    },
    {
        "field_code": "currency",
        "cn_name": "币种",
        "en_name": "Currency",
        "description": "货币代码（ISO 4217）",
        "data_domain": "orders",
        "field_group": "dimension",
        "is_required": False,
        "data_type": "string",
        "synonyms": ["币种", "货币", "currency", "bz"],
        "example_values": ["BRL", "USD", "CNY", "SGD"],
        "display_order": 6,
        "match_weight": 1.5,
    },
    {
        "field_code": "quantity",
        "cn_name": "数量",
        "en_name": "Quantity",
        "description": "商品数量",
        "data_domain": "orders",
        "field_group": "quantity",
        "is_required": False,
        "data_type": "integer",
        "value_range": ">0",
        "synonyms": ["数量", "商品数量", "quantity", "qty", "sl", "件数"],
        "example_values": ["1", "10", "100"],
        "display_order": 15,
        "match_weight": 1.5,
    },
    {
        "field_code": "shipping_fee",
        "cn_name": "运费",
        "en_name": "Shipping Fee",
        "description": "运费金额",
        "data_domain": "orders",
        "field_group": "amount",
        "is_required": False,
        "data_type": "currency",
        "value_range": ">=0",
        "synonyms": ["运费", "物流费", "shipping_fee", "yf", "shipping", "配送费"],
        "example_values": ["5.00", "0.00"],
        "display_order": 20,
        "match_weight": 1.0,
    },
    {
        "field_code": "platform_discount",
        "cn_name": "平台优惠",
        "en_name": "Platform Discount",
        "description": "平台承担的优惠金额",
        "data_domain": "orders",
        "field_group": "amount",
        "is_required": False,
        "data_type": "currency",
        "value_range": ">=0",
        "synonyms": ["平台优惠", "平台折扣", "platform_discount", "ptyh", "平台补贴"],
        "example_values": ["10.00", "0.00"],
        "display_order": 25,
        "match_weight": 1.0,
    },
    {
        "field_code": "seller_discount",
        "cn_name": "商家优惠",
        "en_name": "Seller Discount",
        "description": "商家承担的优惠金额",
        "data_domain": "orders",
        "field_group": "amount",
        "is_required": False,
        "data_type": "currency",
        "value_range": ">=0",
        "synonyms": ["商家优惠", "商家折扣", "seller_discount", "sjyh", "卖家优惠"],
        "example_values": ["5.00", "0.00"],
        "display_order": 30,
        "match_weight": 1.0,
    },
    {
        "field_code": "order_status",
        "cn_name": "订单状态",
        "en_name": "Order Status",
        "description": "订单当前状态",
        "data_domain": "orders",
        "field_group": "dimension",
        "is_required": False,
        "data_type": "string",
        "synonyms": ["订单状态", "状态", "order_status", "status", "zt"],
        "example_values": ["已付款", "已完成", "已取消", "completed", "cancelled"],
        "display_order": 35,
        "match_weight": 1.0,
    },
    {
        "field_code": "site",
        "cn_name": "站点",
        "en_name": "Site",
        "description": "销售站点或区域",
        "data_domain": "orders",
        "field_group": "dimension",
        "is_required": False,
        "data_type": "string",
        "synonyms": ["站点", "区域", "site", "region", "zd", "国家"],
        "example_values": ["菲律宾", "新加坡", "巴西", "BR", "SG"],
        "display_order": 40,
        "match_weight": 1.0,
    },
    
    # ========== Products 数据域 ==========
    {
        "field_code": "platform_sku",
        "cn_name": "商品编号",
        "en_name": "Platform SKU",
        "description": "平台商品SKU",
        "data_domain": "products",
        "field_group": "dimension",
        "is_required": True,
        "data_type": "string",
        "synonyms": ["商品编号", "SKU", "sku", "platform_sku", "spbh", "商品ID", "产品编号"],
        "example_values": ["SKU12345", "PROD-001"],
        "display_order": 1,
        "match_weight": 2.0,
    },
    {
        "field_code": "variant_id",
        "cn_name": "规格编号",
        "en_name": "Variant ID",
        "description": "商品规格/变体ID",
        "data_domain": "products",
        "field_group": "dimension",
        "is_required": False,
        "data_type": "string",
        "synonyms": ["规格编号", "变体ID", "variant", "variant_id", "ggbh", "规格ID", "sku细分"],
        "example_values": ["VAR123", "12345678"],
        "display_order": 2,
        "match_weight": 1.5,
    },
    {
        "field_code": "product_title",
        "cn_name": "商品标题",
        "en_name": "Product Title",
        "description": "商品名称或标题",
        "data_domain": "products",
        "field_group": "text",
        "is_required": False,
        "data_type": "string",
        "synonyms": ["商品标题", "商品名称", "标题", "title", "product_title", "name", "spmc"],
        "example_values": ["LED灯泡 10W", "智能手表"],
        "display_order": 5,
        "match_weight": 1.0,
    },
    {
        "field_code": "price",
        "cn_name": "价格",
        "en_name": "Price",
        "description": "商品价格",
        "data_domain": "products",
        "field_group": "amount",
        "is_required": False,
        "data_type": "currency",
        "value_range": ">=0",
        "synonyms": ["价格", "售价", "price", "jg", "单价"],
        "example_values": ["99.90", "29.99 USD"],
        "display_order": 10,
        "match_weight": 1.5,
    },
    {
        "field_code": "stock",
        "cn_name": "库存",
        "en_name": "Stock",
        "description": "库存数量",
        "data_domain": "products",
        "field_group": "quantity",
        "is_required": False,
        "data_type": "integer",
        "value_range": ">=0",
        "synonyms": ["库存", "库存数量", "stock", "inventory", "kc"],
        "example_values": ["100", "0", "9999"],
        "display_order": 15,
        "match_weight": 1.0,
    },
    {
        "field_code": "visitors",
        "cn_name": "访客数",
        "en_name": "Visitors",
        "description": "访客数量",
        "data_domain": "products",
        "field_group": "quantity",
        "is_required": False,
        "data_type": "integer",
        "value_range": ">=0",
        "synonyms": ["访客数", "访客", "visitors", "uv", "fks", "商品访问数量"],
        "example_values": ["1000", "500"],
        "display_order": 20,
        "match_weight": 1.0,
    },
    {
        "field_code": "page_views",
        "cn_name": "浏览量",
        "en_name": "Page Views",
        "description": "页面浏览量",
        "data_domain": "products",
        "field_group": "quantity",
        "is_required": False,
        "data_type": "integer",
        "value_range": ">=0",
        "synonyms": ["浏览量", "访问量", "page_views", "pv", "lll", "点击量"],
        "example_values": ["5000", "1500"],
        "display_order": 25,
        "match_weight": 1.0,
    },
    {
        "field_code": "conversion_rate",
        "cn_name": "转化率",
        "en_name": "Conversion Rate",
        "description": "转化率（0-1或百分比）",
        "data_domain": "products",
        "field_group": "ratio",
        "is_required": False,
        "data_type": "ratio",
        "value_range": "0-1",
        "synonyms": ["转化率", "conversion_rate", "cvr", "zhl", "成交率"],
        "example_values": ["0.05", "5%", "0.125"],
        "display_order": 30,
        "match_weight": 1.0,
    },
    {
        "field_code": "category",
        "cn_name": "类目",
        "en_name": "Category",
        "description": "商品类目或分类",
        "data_domain": "products",
        "field_group": "dimension",
        "is_required": False,
        "data_type": "string",
        "synonyms": ["类目", "分类", "category", "lm", "品类"],
        "example_values": ["电子产品", "服装", "家居"],
        "display_order": 35,
        "match_weight": 0.8,
    },
    
    # ========== Traffic 数据域 ==========
    {
        "field_code": "metric_date",
        "cn_name": "日期",
        "en_name": "Metric Date",
        "description": "指标日期",
        "data_domain": "traffic",
        "field_group": "datetime",
        "is_required": True,
        "data_type": "date",
        "synonyms": ["日期", "统计日期", "metric_date", "date", "rq"],
        "example_values": ["2024-09-25", "25/09/2024"],
        "display_order": 1,
        "match_weight": 2.0,
    },
    {
        "field_code": "granularity",
        "cn_name": "粒度",
        "en_name": "Granularity",
        "description": "数据粒度（daily/weekly/monthly）",
        "data_domain": "traffic",
        "field_group": "dimension",
        "is_required": True,
        "data_type": "string",
        "synonyms": ["粒度", "granularity", "ld", "周期"],
        "example_values": ["daily", "weekly", "monthly"],
        "display_order": 2,
        "match_weight": 1.5,
    },
    # traffic域复用products的visitors, page_views, conversion_rate
    
    # ========== Services 数据域（客服/服务） ==========
    {
        "field_code": "metric_date",
        "cn_name": "日期",
        "en_name": "Metric Date",
        "description": "统计日期",
        "data_domain": "services",
        "field_group": "datetime",
        "is_required": True,
        "data_type": "date",
        "synonyms": ["日期", "统计日期", "metric_date", "date"],
        "example_values": ["2024-09-25", "25/09/2024"],
        "display_order": 1,
        "match_weight": 2.0,
    },
    {
        "field_code": "granularity",
        "cn_name": "粒度",
        "en_name": "Granularity",
        "description": "数据粒度（daily/weekly/monthly）",
        "data_domain": "services",
        "field_group": "dimension",
        "is_required": True,
        "data_type": "string",
        "synonyms": ["粒度", "granularity", "周期"],
        "example_values": ["daily", "weekly", "monthly"],
        "display_order": 2,
        "match_weight": 1.5,
    },
    {
        "field_code": "service_category",
        "cn_name": "服务分类",
        "en_name": "Service Category",
        "description": "服务/客服分类（如Customer Service、AI Assistant）",
        "data_domain": "services",
        "field_group": "dimension",
        "is_required": False,
        "data_type": "string",
        "synonyms": ["服务分类", "客服分类", "category", "服务类型"],
        "example_values": ["Customer Service", "AI Assistant"],
        "display_order": 3,
        "match_weight": 1.0,
    },
    {
        "field_code": "tickets",
        "cn_name": "工单数",
        "en_name": "Tickets",
        "description": "客服工单数量/会话数",
        "data_domain": "services",
        "field_group": "quantity",
        "is_required": False,
        "data_type": "integer",
        "value_range": ">=0",
        "synonyms": ["工单数", "会话数", "tickets", "cases"],
        "example_values": ["10", "120"],
        "display_order": 10,
        "match_weight": 1.0,
    },
    {
        "field_code": "response_time_minutes",
        "cn_name": "平均响应时长(分钟)",
        "en_name": "Avg Response Time (min)",
        "description": "平均响应耗时（分钟）",
        "data_domain": "services",
        "field_group": "amount",
        "is_required": False,
        "data_type": "float",
        "value_range": ">=0",
        "synonyms": ["平均响应时长", "响应时间", "response_time"],
        "example_values": ["3.5", "12.0"],
        "display_order": 15,
        "match_weight": 1.0,
    },
    {
        "field_code": "satisfaction_rate",
        "cn_name": "满意度",
        "en_name": "Satisfaction Rate",
        "description": "客户满意度（0-1或百分比）",
        "data_domain": "services",
        "field_group": "ratio",
        "is_required": False,
        "data_type": "ratio",
        "value_range": "0-1",
        "synonyms": ["满意度", "satisfaction", "满意比例"],
        "example_values": ["0.95", "95%"],
        "display_order": 20,
        "match_weight": 1.0,
    },
    {
        "field_code": "agent_name",
        "cn_name": "客服人员",
        "en_name": "Agent Name",
        "description": "客服坐席/代理人",
        "data_domain": "services",
        "field_group": "dimension",
        "is_required": False,
        "data_type": "string",
        "synonyms": ["客服人员", "坐席", "agent", "客服"],
        "example_values": ["Alice", "Bob"],
        "display_order": 25,
        "match_weight": 0.8,
    },
    {
        "field_code": "ai_assistant_usage",
        "cn_name": "AI助手使用次数",
        "en_name": "AI Assistant Usage",
        "description": "AI助手调用次数/会话数",
        "data_domain": "services",
        "field_group": "quantity",
        "is_required": False,
        "data_type": "integer",
        "value_range": ">=0",
        "synonyms": ["AI助手次数", "AI使用次数", "assistant_usage"],
        "example_values": ["5", "23"],
        "display_order": 30,
        "match_weight": 0.8,
    },

    # ========== 通用字段（多域共享） ==========
    {
        "field_code": "metric_date",
        "cn_name": "指标日期",
        "en_name": "Metric Date",
        "description": "指标统计日期",
        "data_domain": "products",  # 也适用于其他域
        "field_group": "datetime",
        "is_required": True,
        "data_type": "date",
        "synonyms": ["指标日期", "统计日期", "日期", "metric_date", "date", "rq"],
        "example_values": ["2024-09-25", "25/09/2024"],
        "display_order": 3,
        "match_weight": 2.0,
    },
]


def init_dictionary(db):
    """初始化字段映射辞典"""
    logger.info("=" * 70)
    logger.info("初始化字段映射辞典数据")
    logger.info("=" * 70)
    
    # 清空现有数据（可选）
    try:
        db.execute(text("DELETE FROM field_mapping_dictionary"))
        db.commit()
        logger.info("  [OK] 清空现有辞典数据")
    except Exception as e:
        logger.warning(f"  [WARN] 清空辞典失败（可能表未创建）: {e}")
        db.rollback()
    
    # 插入初始数据
    success_count = 0
    failed_count = 0
    
    for item in INITIAL_DICTIONARY:
        try:
            entry = FieldMappingDictionary(**item)
            db.add(entry)
            db.commit()
            success_count += 1
            logger.info(f"  [OK] {item['field_code']}: {item['cn_name']}")
        except Exception as e:
            logger.error(f"  [FAIL] {item['field_code']}: {e}")
            db.rollback()
            failed_count += 1
    
    logger.info("=" * 70)
    logger.info(f"辞典初始化完成: 成功{success_count}个, 失败{failed_count}个")
    logger.info("=" * 70)
    
    # 统计
    total = db.query(FieldMappingDictionary).count()
    logger.info(f"  当前辞典总数: {total}条")
    
    # 按数据域统计
    for domain in ['orders', 'products', 'traffic']:
        count = db.query(FieldMappingDictionary).filter(
            FieldMappingDictionary.data_domain == domain
        ).count()
        logger.info(f"  {domain}: {count}条")
    
    return success_count, failed_count


if __name__ == '__main__':
    db = next(get_db())
    try:
        init_dictionary(db)
    finally:
        db.close()

