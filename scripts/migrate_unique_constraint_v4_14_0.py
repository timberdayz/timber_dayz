#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库迁移脚本：更新fact_raw_data_*表的唯一约束（v4.14.0）

功能：
- 删除旧的唯一约束（data_domain, granularity, data_hash）
- 创建新的唯一索引（包含platform_code和COALESCE(shop_id, '')）

注意：
- 由于shop_id可能为NULL，使用COALESCE(shop_id, '')处理
- PostgreSQL唯一约束不支持表达式，需要使用唯一索引（UNIQUE INDEX）
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from backend.utils.config import get_settings
from modules.core.logger import get_logger

logger = get_logger(__name__)

# 所有fact_raw_data_*表
FACT_RAW_DATA_TABLES = [
    'fact_raw_data_orders_daily',
    'fact_raw_data_orders_weekly',
    'fact_raw_data_orders_monthly',
    'fact_raw_data_products_daily',
    'fact_raw_data_products_weekly',
    'fact_raw_data_products_monthly',
    'fact_raw_data_traffic_daily',
    'fact_raw_data_traffic_weekly',
    'fact_raw_data_traffic_monthly',
    'fact_raw_data_services_daily',
    'fact_raw_data_services_weekly',
    'fact_raw_data_services_monthly',
    'fact_raw_data_inventory_snapshot',
]


def migrate_unique_constraints():
    """
    迁移唯一约束
    
    步骤：
    1. 删除旧的唯一约束
    2. 创建新的唯一索引（包含platform_code和COALESCE(shop_id, '')）
    """
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.connect() as conn:
        # 开始事务
        trans = conn.begin()
        
        try:
            for table_name in FACT_RAW_DATA_TABLES:
                logger.info(f"[Migration] 处理表: {table_name}")
                
                # 1. 删除旧的唯一约束
                old_constraint_name = f"uq_{table_name}_hash"
                try:
                    drop_constraint_sql = text(
                        f'ALTER TABLE "{table_name}" '
                        f'DROP CONSTRAINT IF EXISTS "{old_constraint_name}"'
                    )
                    conn.execute(drop_constraint_sql)
                    logger.info(f"[Migration] 删除旧唯一约束: {old_constraint_name}")
                except Exception as e:
                    logger.warning(f"[Migration] 删除旧唯一约束失败（可能不存在）: {e}")
                
                # 2. 创建新的唯一索引（包含platform_code和COALESCE(shop_id, '')）
                new_index_name = f"uq_{table_name}_hash_v2"
                try:
                    create_index_sql = text(
                        f'CREATE UNIQUE INDEX IF NOT EXISTS "{new_index_name}" '
                        f'ON "{table_name}" '
                        f'(platform_code, COALESCE(shop_id, \'\'), data_domain, granularity, data_hash)'
                    )
                    conn.execute(create_index_sql)
                    logger.info(f"[Migration] 创建新唯一索引: {new_index_name}")
                except Exception as e:
                    logger.error(f"[Migration] 创建新唯一索引失败: {e}")
                    raise
            
            # 提交事务
            trans.commit()
            logger.info("[Migration] 迁移完成：所有表的唯一约束已更新")
            
        except Exception as e:
            # 回滚事务
            trans.rollback()
            logger.error(f"[Migration] 迁移失败: {e}", exc_info=True)
            raise


if __name__ == "__main__":
    migrate_unique_constraints()

