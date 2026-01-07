#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补充C类数据计算缺失的核心字段到字段映射辞典

根据C类数据核心字段优化计划，补充以下缺失字段：
1. orders域: order_id, order_date_local, total_amount_rmb, order_status, platform_code, shop_id
2. products域: unique_visitors, order_count, rating, metric_date, data_domain, sales_volume, sales_amount_rmb, conversion_rate
3. inventory域: available_stock, sales_volume_30d

复用现有add_missing_core_fields.py的补充逻辑，确保字段定义符合现有表结构
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from modules.core.db import FieldMappingDictionary
from modules.core.logger import get_logger
from sqlalchemy import select

logger = get_logger(__name__)

# C类数据核心字段定义（17个字段）
C_CLASS_FIELD_DEFINITIONS = [
    # ========== orders域（6个字段）==========
    {
        "field_code": "order_id",
        "cn_name": "订单号",
        "en_name": "Order ID",
        "description": "订单唯一标识（统计订单数，达成率计算核心）",
        "data_domain": "orders",
        "field_group": "dimension",
        "is_required": True,
        "data_type": "string",
        "synonyms": ["订单号", "order_id", "order_number", "订单编号", "ddh"],
        "platform_synonyms": {
            "shopee": ["订单号"],
            "tiktok": ["订单号"],
            "miaoshou": ["订单号"]
        },
        "example_values": ["SP123456789", "TT987654321"],
        "display_order": 1,
        "match_weight": 3.0,
        "is_mv_display": True,
    },
    {
        "field_code": "order_date_local",
        "cn_name": "订单日期",
        "en_name": "Order Date Local",
        "description": "订单创建的本地日期（不含时间，时间筛选，达成率计算核心）",
        "data_domain": "orders",
        "field_group": "datetime",
        "is_required": True,
        "data_type": "date",
        "synonyms": ["订单日期", "下单日期", "order_date", "order_date_local", "xdrq", "创建日期"],
        "platform_synonyms": {
            "shopee": ["下单日期"],
            "tiktok": ["订单日期"],
            "miaoshou": ["订单日期"]
        },
        "example_values": ["2024-09-25", "25/09/2024"],
        "display_order": 2,
        "match_weight": 2.0,
        "is_mv_display": True,
    },
    {
        "field_code": "total_amount_rmb",
        "cn_name": "订单总金额（CNY）",
        "en_name": "Total Amount RMB",
        "description": "订单总金额（人民币，销售额计算，达成率计算核心）",
        "data_domain": "orders",
        "field_group": "amount",
        "is_required": True,
        "data_type": "currency",
        "value_range": ">=0",
        "synonyms": ["订单总金额", "total_amount_rmb", "total_amount", "订单金额", "ddze"],
        "platform_synonyms": {
            "shopee": ["订单总金额"],
            "tiktok": ["订单金额"],
            "miaoshou": ["订单总金额（元）"]
        },
        "example_values": ["1234.56", "5678.90"],
        "display_order": 3,
        "match_weight": 3.0,
        "is_mv_display": True,
    },
    {
        "field_code": "order_status",
        "cn_name": "订单状态",
        "en_name": "Order Status",
        "description": "订单状态（筛选有效订单，达成率计算核心）",
        "data_domain": "orders",
        "field_group": "dimension",
        "is_required": True,
        "data_type": "string",
        "synonyms": ["订单状态", "order_status", "status", "订单状态码", "ddzt"],
        "platform_synonyms": {
            "shopee": ["订单状态"],
            "tiktok": ["订单状态"],
            "miaoshou": ["订单状态"]
        },
        "example_values": ["completed", "paid", "pending"],
        "display_order": 4,
        "match_weight": 2.0,
        "is_mv_display": False,
    },
    {
        "field_code": "platform_code",
        "cn_name": "平台代码",
        "en_name": "Platform Code",
        "description": "平台代码（维度聚合，达成率计算核心）",
        "data_domain": "general",
        "field_group": "dimension",
        "is_required": True,
        "data_type": "string",
        "synonyms": ["平台代码", "platform_code", "platform", "平台", "ptdm"],
        "platform_synonyms": {},
        "example_values": ["shopee", "tiktok", "miaoshou"],
        "display_order": 5,
        "match_weight": 2.0,
        "is_mv_display": True,
    },
    {
        "field_code": "shop_id",
        "cn_name": "店铺ID",
        "en_name": "Shop ID",
        "description": "店铺ID（维度聚合，达成率计算核心）",
        "data_domain": "general",
        "field_group": "dimension",
        "is_required": True,
        "data_type": "string",
        "synonyms": ["店铺ID", "shop_id", "shop", "店铺", "dp_id"],
        "platform_synonyms": {},
        "example_values": ["shop001", "shop002"],
        "display_order": 6,
        "match_weight": 2.0,
        "is_mv_display": True,
    },
    
    # ========== products域（8个字段）==========
    {
        "field_code": "unique_visitors",
        "cn_name": "独立访客数",
        "en_name": "Unique Visitors",
        "description": "独立访客数（转化率计算分母，健康度评分25分）",
        "data_domain": "products",
        "field_group": "quantity",
        "is_required": False,
        "data_type": "integer",
        "value_range": ">=0",
        "synonyms": ["独立访客数", "unique_visitors", "visitors", "uv", "独立访客", "dlfks"],
        "platform_synonyms": {
            "shopee": ["独立访客数"],
            "tiktok": ["访客数"],
            "miaoshou": ["独立访客数"]
        },
        "example_values": ["1000", "5000", "10000"],
        "display_order": 20,
        "match_weight": 2.0,
        "is_mv_display": True,
    },
    {
        "field_code": "order_count",
        "cn_name": "订单数",
        "en_name": "Order Count",
        "description": "订单数（转化率计算分子，健康度评分25分）",
        "data_domain": "products",
        "field_group": "quantity",
        "is_required": False,
        "data_type": "integer",
        "value_range": ">=0",
        "synonyms": ["订单数", "order_count", "orders_count", "订单数量", "dds"],
        "platform_synonyms": {
            "shopee": ["订单数"],
            "tiktok": ["订单数量"],
            "miaoshou": ["订单数"]
        },
        "example_values": ["50", "100", "200"],
        "display_order": 21,
        "match_weight": 2.0,
        "is_mv_display": True,
    },
    {
        "field_code": "rating",
        "cn_name": "评分",
        "en_name": "Rating",
        "description": "商品评分（0-5，客户满意度，健康度评分20分，预警系统核心）",
        "data_domain": "products",
        "field_group": "ratio",
        "is_required": False,
        "data_type": "float",
        "value_range": "0-5",
        "synonyms": ["评分", "商品评分", "rating", "star_rating", "pf", "星级评分", "评价分数"],
        "platform_synonyms": {
            "shopee": ["商品评分"],
            "tiktok": ["评分"],
            "miaoshou": ["评分"]
        },
        "example_values": ["4.5", "4.8", "5.0"],
        "display_order": 35,
        "match_weight": 1.5,
        "is_mv_display": True,
    },
    {
        "field_code": "metric_date",
        "cn_name": "指标日期",
        "en_name": "Metric Date",
        "description": "指标日期（时间维度聚合，健康度评分核心）",
        "data_domain": "products",
        "field_group": "datetime",
        "is_required": True,
        "data_type": "date",
        "synonyms": ["指标日期", "metric_date", "date", "日期", "zbxr"],
        "platform_synonyms": {
            "shopee": ["日期"],
            "tiktok": ["日期"],
            "miaoshou": ["日期"]
        },
        "example_values": ["2024-09-25"],
        "display_order": 7,
        "match_weight": 2.0,
        "is_mv_display": True,
    },
    {
        "field_code": "data_domain",
        "cn_name": "数据域",
        "en_name": "Data Domain",
        "description": "数据域标识（区分products/inventory域，健康度评分核心）",
        "data_domain": "general",
        "field_group": "dimension",
        "is_required": False,
        "data_type": "string",
        "synonyms": ["数据域", "data_domain", "domain", "sjl", "数据分类"],
        "platform_synonyms": {},
        "example_values": ["products", "inventory", "traffic", "orders"],
        "display_order": 999,
        "match_weight": 1.0,
        "is_mv_display": False,
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
        "platform_synonyms": {
            "shopee": ["销量"],
            "tiktok": ["销售数量"],
            "miaoshou": ["销量"]
        },
        "example_values": ["100", "500", "1000"],
        "display_order": 20,
        "match_weight": 2.0,
        "is_mv_display": True,
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
        "platform_synonyms": {
            "shopee": ["销售额"],
            "tiktok": ["销售额"],
            "miaoshou": ["销售额"]
        },
        "example_values": ["1234.56", "5678.90"],
        "display_order": 25,
        "match_weight": 2.0,
        "is_mv_display": True,
    },
    {
        "field_code": "conversion_rate",
        "cn_name": "转化率",
        "en_name": "Conversion Rate",
        "description": "转化率（排名计算核心，预警系统核心）",
        "data_domain": "products",
        "field_group": "ratio",
        "is_required": False,
        "data_type": "float",
        "value_range": "0-100",
        "synonyms": ["转化率", "conversion_rate", "conversion", "转化", "zhl"],
        "platform_synonyms": {
            "shopee": ["转化率"],
            "tiktok": ["转化率"],
            "miaoshou": ["转化率"]
        },
        "example_values": ["2.5", "5.0", "10.0"],
        "display_order": 30,
        "match_weight": 2.0,
        "is_mv_display": True,
    },
    
    # ========== inventory域（2个字段）==========
    {
        "field_code": "available_stock",
        "cn_name": "可用库存",
        "en_name": "Available Stock",
        "description": "可用库存数量（库存周转率计算，健康度评分25分，库存预警）",
        "data_domain": "inventory",
        "field_group": "quantity",
        "is_required": False,
        "data_type": "integer",
        "value_range": ">=0",
        "synonyms": ["可用库存", "available_stock", "stock", "inventory", "库存", "kykc"],
        "platform_synonyms": {
            "shopee": ["可用库存"],
            "tiktok": ["库存"],
            "miaoshou": ["可用库存"]
        },
        "example_values": ["100", "500", "1000"],
        "display_order": 10,
        "match_weight": 2.0,
        "is_mv_display": True,
    },
    {
        "field_code": "sales_volume_30d",
        "cn_name": "近30天销量",
        "en_name": "Sales Volume 30 Days",
        "description": "近30天销量（库存周转率计算，健康度评分25分）",
        "data_domain": "products",
        "field_group": "quantity",
        "is_required": False,
        "data_type": "integer",
        "value_range": ">=0",
        "synonyms": ["近30天销量", "sales_volume_30d", "sales_volume_30days", "30天销量", "j30txl"],
        "platform_synonyms": {
            "shopee": ["近30天销量"],
            "tiktok": ["30天销量"],
            "miaoshou": ["近30天销量"]
        },
        "example_values": ["50", "100", "200"],
        "display_order": 22,
        "match_weight": 2.0,
        "is_mv_display": True,
    },
]


def add_c_class_missing_fields(db):
    """添加C类数据计算缺失的核心字段到字段映射辞典"""
    logger.info("=" * 70)
    logger.info("补充C类数据计算缺失的核心字段到字段映射辞典")
    logger.info("=" * 70)
    
    success_count = 0
    failed_count = 0
    skipped_count = 0
    
    for field_def in C_CLASS_FIELD_DEFINITIONS:
        field_code = field_def["field_code"]
        
        try:
            # 检查字段是否已存在
            existing = db.execute(
                select(FieldMappingDictionary).where(
                    FieldMappingDictionary.field_code == field_code
                )
            ).scalar_one_or_none()
            
            if existing:
                logger.info(f"  [SKIP] {field_code} ({field_def['cn_name']}) - 已存在，跳过")
                skipped_count += 1
                continue
            
            # 创建新字段（设置默认值，确保向后兼容）
            entry = FieldMappingDictionary(
                field_code=field_def["field_code"],
                cn_name=field_def["cn_name"],
                en_name=field_def.get("en_name"),
                description=field_def.get("description"),
                data_domain=field_def["data_domain"],
                field_group=field_def.get("field_group"),
                is_required=field_def.get("is_required", False),
                data_type=field_def.get("data_type"),
                value_range=field_def.get("value_range"),
                synonyms=field_def.get("synonyms"),
                platform_synonyms=field_def.get("platform_synonyms"),
                example_values=field_def.get("example_values"),
                display_order=field_def.get("display_order", 999),
                match_weight=field_def.get("match_weight", 1.0),
                is_mv_display=field_def.get("is_mv_display", False),
                # 默认值设置（向后兼容）
                active=True,
                version=1,
                status="active",
                created_by="system",
            )
            
            db.add(entry)
            db.commit()
            
            success_count += 1
            logger.info(f"  [OK] {field_code}: {field_def['cn_name']} ({field_def['data_domain']})")
            
        except Exception as e:
            logger.error(f"  [FAIL] {field_code}: {e}")
            db.rollback()
            failed_count += 1
    
    logger.info("=" * 70)
    logger.info(
        f"补充完成: 成功 {success_count} 个, 失败 {failed_count} 个, "
        f"跳过 {skipped_count} 个"
    )
    logger.info("=" * 70)
    
    return success_count, failed_count, skipped_count


if __name__ == '__main__':
    db = next(get_db())
    try:
        add_c_class_missing_fields(db)
        
        # 重新验证
        logger.info("\n重新验证C类数据核心字段完整性...")
        from scripts.verify_c_class_core_fields import verify_c_class_core_fields
        verification_result = verify_c_class_core_fields(db)
        
        if verification_result["all_passed"]:
            logger.info("\n[OK] 所有C类数据核心字段验证通过")
        else:
            logger.warning(
                f"\n[WARN] 仍有 {verification_result['total_missing']} 个字段缺失, "
                f"{verification_result['total_domain_mismatch']} 个字段数据域不匹配"
            )
        
    finally:
        db.close()

