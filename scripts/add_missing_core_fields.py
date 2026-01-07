#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补充缺失的核心字段到字段映射辞典

根据后端优化和C类数据计算支撑计划，补充以下缺失字段：
1. order_date_local - 订单日期
2. sales_volume - 销量
3. sales_amount_rmb - 销售额（CNY）
4. add_to_cart_count - 加购数
5. rating - 评分
6. review_count - 评价数
7. data_domain - 数据域
8. price_rmb - 单价（CNY）
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from modules.core.db import FieldMappingDictionary
from modules.core.logger import get_logger
from sqlalchemy import select, text

logger = get_logger(__name__)

# 缺失字段定义
MISSING_FIELDS = [
    {
        "field_code": "order_date_local",
        "cn_name": "订单日期",
        "en_name": "Order Date Local",
        "description": "订单创建的本地日期（不含时间）",
        "data_domain": "orders",
        "field_group": "datetime",
        "is_required": True,
        "data_type": "date",
        "synonyms": ["订单日期", "下单日期", "order_date", "order_date_local", "xdrq", "创建日期"],
        "platform_synonyms": {"shopee": ["下单日期"], "tiktok": ["订单日期"], "miaoshou": ["订单日期"]},
        "example_values": ["2024-09-25", "25/09/2024"],
        "display_order": 2,
        "match_weight": 2.0,
    },
    {
        "field_code": "sales_volume",
        "cn_name": "销量",
        "en_name": "Sales Volume",
        "description": "商品销售数量（排名计算核心）",
        "data_domain": "products",
        "field_group": "quantity",
        "is_required": False,
        "data_type": "integer",
        "value_range": ">=0",
        "synonyms": ["销量", "销售数量", "sales_volume", "sales_qty", "xl", "销售件数", "成交件数"],
        "platform_synonyms": {"shopee": ["销量"], "tiktok": ["销售数量"], "miaoshou": ["销量"]},
        "example_values": ["100", "500", "1000"],
        "display_order": 20,
        "match_weight": 2.0,
    },
    {
        "field_code": "sales_amount_rmb",
        "cn_name": "销售额（CNY）",
        "en_name": "Sales Amount RMB",
        "description": "销售额（人民币，排名计算核心）",
        "data_domain": "products",
        "field_group": "amount",
        "is_required": False,
        "data_type": "currency",
        "value_range": ">=0",
        "synonyms": ["销售额（CNY）", "销售额人民币", "sales_amount_rmb", "sales_revenue_rmb", "xse_rmb", "销售额"],
        "platform_synonyms": {"shopee": ["销售额"], "tiktok": ["销售额"], "miaoshou": ["销售额"]},
        "example_values": ["1234.56", "5678.90"],
        "display_order": 25,
        "match_weight": 2.0,
    },
    {
        "field_code": "add_to_cart_count",
        "cn_name": "加购数",
        "en_name": "Add to Cart Count",
        "description": "加入购物车数量（转化漏斗）",
        "data_domain": "products",
        "field_group": "quantity",
        "is_required": False,
        "data_type": "integer",
        "value_range": ">=0",
        "synonyms": ["加购数", "加购次数", "add_to_cart_count", "add_to_cart", "cart_add_count", "jgs", "加入购物车次数"],
        "platform_synonyms": {"shopee": ["加购次数"], "tiktok": ["加购数"], "miaoshou": ["加购数"]},
        "example_values": ["50", "100", "200"],
        "display_order": 30,
        "match_weight": 1.5,
    },
    {
        "field_code": "rating",
        "cn_name": "评分",
        "en_name": "Rating",
        "description": "商品评分（0-5，客户满意度，服务得分）",
        "data_domain": "products",
        "field_group": "ratio",
        "is_required": False,
        "data_type": "float",
        "value_range": "0-5",
        "synonyms": ["评分", "商品评分", "rating", "star_rating", "pf", "星级评分", "评价分数"],
        "platform_synonyms": {"shopee": ["商品评分"], "tiktok": ["评分"], "miaoshou": ["评分"]},
        "example_values": ["4.5", "4.8", "5.0"],
        "display_order": 35,
        "match_weight": 1.5,
    },
    {
        "field_code": "review_count",
        "cn_name": "评价数",
        "en_name": "Review Count",
        "description": "评价数量（服务指标）",
        "data_domain": "products",
        "field_group": "quantity",
        "is_required": False,
        "data_type": "integer",
        "value_range": ">=0",
        "synonyms": ["评价数", "评论数", "review_count", "reviews", "pjs", "评价数量", "评论数量"],
        "platform_synonyms": {"shopee": ["评价数"], "tiktok": ["评论数"], "miaoshou": ["评价数"]},
        "example_values": ["10", "100", "1000"],
        "display_order": 40,
        "match_weight": 1.0,
    },
    {
        "field_code": "data_domain",
        "cn_name": "数据域",
        "en_name": "Data Domain",
        "description": "数据域标识（区分products/inventory/traffic等）",
        "data_domain": "general",
        "field_group": "dimension",
        "is_required": False,
        "data_type": "string",
        "synonyms": ["数据域", "data_domain", "domain", "sjl", "数据分类"],
        "platform_synonyms": {},
        "example_values": ["products", "inventory", "traffic", "orders"],
        "display_order": 999,
        "match_weight": 1.0,
    },
    {
        "field_code": "price_rmb",
        "cn_name": "单价（CNY）",
        "en_name": "Price RMB",
        "description": "商品单价（人民币，库存价值计算）",
        "data_domain": "inventory",
        "field_group": "amount",
        "is_required": False,
        "data_type": "currency",
        "value_range": ">=0",
        "synonyms": ["单价（CNY）", "单价人民币", "price_rmb", "unit_price_rmb", "dj_rmb", "单价"],
        "platform_synonyms": {"shopee": ["单价"], "tiktok": ["单价"], "miaoshou": ["单价（元）"]},
        "example_values": ["99.90", "199.00"],
        "display_order": 15,
        "match_weight": 1.5,
    },
]


def add_missing_fields(db):
    """添加缺失字段到字段映射辞典"""
    logger.info("=" * 70)
    logger.info("补充缺失的核心字段到字段映射辞典")
    logger.info("=" * 70)
    
    success_count = 0
    failed_count = 0
    skipped_count = 0
    
    for field_def in MISSING_FIELDS:
        field_code = field_def["field_code"]
        
        try:
            # 检查字段是否已存在
            existing = db.execute(
                select(FieldMappingDictionary).where(
                    FieldMappingDictionary.field_code == field_code
                )
            ).scalar_one_or_none()
            
            if existing:
                logger.info(f"  [SKIP] {field_code} - 已存在，跳过")
                skipped_count += 1
                continue
            
            # 创建新字段
            entry = FieldMappingDictionary(**field_def)
            db.add(entry)
            db.commit()
            
            success_count += 1
            logger.info(f"  [OK] {field_code}: {field_def['cn_name']}")
            
        except Exception as e:
            logger.error(f"  [FAIL] {field_code}: {e}")
            db.rollback()
            failed_count += 1
    
    logger.info("=" * 70)
    logger.info(f"补充完成: 成功 {success_count} 个, 失败 {failed_count} 个, 跳过 {skipped_count} 个")
    logger.info("=" * 70)
    
    return success_count, failed_count, skipped_count


if __name__ == '__main__':
    db = next(get_db())
    try:
        add_missing_fields(db)
        
        # 重新验证
        logger.info("\n重新验证字段完整性...")
        from scripts.verify_core_fields import verify_core_fields
        verify_core_fields(db)
        
    finally:
        db.close()

