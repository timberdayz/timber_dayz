#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建平台表示例脚本（Create Platform Tables Demo）

演示如何使用PlatformTableManager创建按平台分表的表结构
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from modules.core.db import get_engine
from modules.core.logger import get_logger
from backend.services.platform_table_manager import get_platform_table_manager

logger = get_logger(__name__)


def create_platform_tables_demo():
    """
    演示如何创建按平台分表的表结构
    
    表名格式：fact_{platform}_{data_domain}_{sub_domain}_{granularity}
    """
    engine = get_engine()
    session = Session(engine)
    
    try:
        table_manager = get_platform_table_manager(session)
        
        # 示例1：Shopee订单数据（daily粒度）
        print("\n" + "="*60)
        print("示例1: Shopee订单数据（daily粒度）")
        print("="*60)
        table_name1 = table_manager.ensure_table_exists(
            platform='shopee',
            data_domain='orders',
            sub_domain=None,
            granularity='daily'
        )
        print(f"✓ 表名: {table_name1}")
        print(f"  预期: fact_shopee_orders_daily")
        
        # 示例2：TikTok产品数据（weekly粒度）
        print("\n" + "="*60)
        print("示例2: TikTok产品数据（weekly粒度）")
        print("="*60)
        table_name2 = table_manager.ensure_table_exists(
            platform='tiktok',
            data_domain='products',
            sub_domain=None,
            granularity='weekly'
        )
        print(f"✓ 表名: {table_name2}")
        print(f"  预期: fact_tiktok_products_weekly")
        
        # 示例3：Shopee服务数据（AI助手，monthly粒度）
        print("\n" + "="*60)
        print("示例3: Shopee服务数据（AI助手，monthly粒度）")
        print("="*60)
        table_name3 = table_manager.ensure_table_exists(
            platform='shopee',
            data_domain='services',
            sub_domain='ai_assistant',
            granularity='monthly'
        )
        print(f"✓ 表名: {table_name3}")
        print(f"  预期: fact_shopee_services_ai_assistant_monthly")
        
        # 示例4：TikTok服务数据（无sub_domain，使用默认值）
        print("\n" + "="*60)
        print("示例4: TikTok服务数据（无sub_domain）")
        print("="*60)
        # ⚠️ 注意：services域通常需要sub_domain，这里演示如何处理
        # 如果TikTok的服务数据没有sub_domain，可以传入None（但表名会不包含sub_domain）
        table_name4 = table_manager.ensure_table_exists(
            platform='tiktok',
            data_domain='services',
            sub_domain=None,  # TikTok服务数据可能没有sub_domain
            granularity='daily'
        )
        print(f"✓ 表名: {table_name4}")
        print(f"  预期: fact_tiktok_services_daily")
        
        # 示例5：妙手ERP库存数据（snapshot粒度）
        print("\n" + "="*60)
        print("示例5: 妙手ERP库存数据（snapshot粒度）")
        print("="*60)
        table_name5 = table_manager.ensure_table_exists(
            platform='miaoshou',
            data_domain='inventory',
            sub_domain=None,
            granularity='snapshot'
        )
        print(f"✓ 表名: {table_name5}")
        print(f"  预期: fact_miaoshou_inventory_snapshot")
        
        # 提交事务
        session.commit()
        
        print("\n" + "="*60)
        print("✓ 所有表创建完成！")
        print("="*60)
        
        # 显示表结构信息
        print("\n表结构说明：")
        print("- 基础字段：id, platform_code, shop_id, data_domain, granularity,")
        print("            metric_date, file_id, template_id, raw_data, header_columns,")
        print("            data_hash, ingest_timestamp, currency_code")
        print("- services域额外字段：sub_domain（NOT NULL）")
        print("- 动态列：根据模板的header_columns自动添加")
        print("- 索引：自动创建平台、店铺、数据域、粒度、日期等索引")
        
    except Exception as e:
        session.rollback()
        logger.error(f"创建表失败: {e}", exc_info=True)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    print("\n" + "="*60)
    print("按平台分表 - 表创建演示")
    print("="*60)
    print("\n说明：")
    print("- 表名格式：fact_{platform}_{data_domain}_{sub_domain}_{granularity}")
    print("- 如果表已存在，不会重复创建")
    print("- 如果表不存在，会自动创建基础结构")
    print("- 动态列会根据模板的header_columns自动添加（数据入库时）")
    print("\n开始创建表...")
    
    create_platform_tables_demo()




























