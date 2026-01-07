#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
v4.11.0 数据库表初始化脚本

用途：直接使用SQLAlchemy创建新表（如果Alembic迁移有问题时使用）
注意：此脚本仅用于开发环境，生产环境应使用Alembic迁移
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import inspect
from backend.models.database import engine, Base
from modules.core.db import (
    SalesCampaign,
    SalesCampaignShop,
    SalesTarget,
    TargetBreakdown,
    ShopHealthScore,
    ShopAlert,
    PerformanceScore,
    PerformanceConfig,
    ClearanceRanking
)
from modules.core.logger import get_logger

logger = get_logger(__name__)


def check_table_exists(table_name: str) -> bool:
    """检查表是否存在"""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def create_tables():
    """创建新表"""
    tables_to_create = [
        ("sales_campaigns", SalesCampaign),
        ("sales_campaign_shops", SalesCampaignShop),
        ("sales_targets", SalesTarget),
        ("target_breakdown", TargetBreakdown),
        ("shop_health_scores", ShopHealthScore),
        ("shop_alerts", ShopAlert),
        ("performance_scores", PerformanceScore),
        ("performance_config", PerformanceConfig),
        ("clearance_rankings", ClearanceRanking),
    ]
    
    created_count = 0
    existing_count = 0
    
    for table_name, model_class in tables_to_create:
        if check_table_exists(table_name):
            logger.info(f"[SKIP] 表 {table_name} 已存在")
            existing_count += 1
        else:
            try:
                model_class.__table__.create(engine, checkfirst=True)
                logger.info(f"[OK] 表 {table_name} 创建成功")
                created_count += 1
            except Exception as e:
                logger.error(f"[ERROR] 表 {table_name} 创建失败: {e}")
    
    logger.info(f"\n创建结果: 新建 {created_count} 张表, 已存在 {existing_count} 张表")
    return created_count, existing_count


if __name__ == "__main__":
    logger.info("开始初始化 v4.11.0 数据库表...")
    
    try:
        created, existing = create_tables()
        
        if created > 0:
            logger.info(f"\n[OK] 成功创建 {created} 张新表")
        else:
            logger.info("\n[OK] 所有表已存在，无需创建")
        
        logger.info("\n数据库表初始化完成！")
    except Exception as e:
        logger.error(f"\n❌ 数据库表初始化失败: {e}", exc_info=True)
        sys.exit(1)

