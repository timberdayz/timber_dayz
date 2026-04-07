#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理废弃表脚本（Cleanup Deprecated Tables）

v4.17.0新增：
- 清理按平台分表架构中不再使用的旧表
- 开发环境不需要备份，直接删除

废弃表清单：
1. fact_raw_data_traffic_* - traffic域已迁移到analytics
2. fact_raw_data_services_* - 已按sub_domain分表（fact_raw_data_services_ai_assistant_*, fact_raw_data_services_agent_*）
3. fact_orders, fact_order_items, fact_product_metrics - 已被fact_raw_data_*替代

注意：
- 本脚本仅删除表结构，不删除数据（数据已迁移或不再使用）
- 开发环境直接删除，生产环境需要先备份
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, inspect
from sqlalchemy.orm import Session

from modules.core.db import get_engine
from modules.core.logger import get_logger

logger = get_logger(__name__)


# 废弃表清单
DEPRECATED_TABLES = [
    # traffic域表（已迁移到analytics）
    'fact_raw_data_traffic_daily',
    'fact_raw_data_traffic_weekly',
    'fact_raw_data_traffic_monthly',
    
    # services域旧表（已按sub_domain分表）
    'fact_raw_data_services_daily',
    'fact_raw_data_services_weekly',
    'fact_raw_data_services_monthly',
    
    # 旧事实表（已被fact_raw_data_*替代）
    'fact_orders',
    'fact_order_items',
    'fact_product_metrics',
]


def cleanup_deprecated_tables(dry_run: bool = True):
    """
    清理废弃表
    
    Args:
        dry_run: 如果为True，只显示将要删除的表，不实际删除
    """
    engine = get_engine()
    session = Session(engine)
    
    try:
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())
        
        # 找出实际存在的废弃表
        tables_to_drop = []
        for table_name in DEPRECATED_TABLES:
            if table_name in existing_tables:
                tables_to_drop.append(table_name)
                logger.info(f"[Cleanup] 发现废弃表: {table_name}")
            else:
                logger.debug(f"[Cleanup] 表不存在（已删除）: {table_name}")
        
        if not tables_to_drop:
            logger.info("[Cleanup] 没有需要清理的废弃表")
            return
        
        logger.info(f"[Cleanup] 共发现 {len(tables_to_drop)} 个废弃表需要清理")
        
        if dry_run:
            logger.info("[Cleanup] [DRY RUN] 以下表将被删除（实际未执行）:")
            for table_name in tables_to_drop:
                logger.info(f"  - {table_name}")
            return
        
        # 实际删除表
        logger.info("[Cleanup] 开始删除废弃表...")
        for table_name in tables_to_drop:
            try:
                # 删除表（CASCADE会自动删除依赖的索引、约束等）
                drop_sql = text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')
                session.execute(drop_sql)
                session.commit()
                logger.info(f"[Cleanup] ✓ 成功删除表: {table_name}")
            except Exception as e:
                session.rollback()
                logger.error(
                    f"[Cleanup] ✗ 删除表失败: {table_name}, 错误: {e}",
                    exc_info=True
                )
        
        logger.info(f"[Cleanup] 清理完成: 共删除 {len(tables_to_drop)} 个废弃表")
        
    except Exception as e:
        session.rollback()
        logger.error(f"[Cleanup] 清理过程出错: {e}", exc_info=True)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="清理废弃表脚本")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="实际执行删除（默认只显示将要删除的表）"
    )
    
    args = parser.parse_args()
    
    dry_run = not args.execute
    
    if dry_run:
        logger.info("[Cleanup] 运行模式: DRY RUN（只显示，不删除）")
        logger.info("[Cleanup] 要实际删除，请使用 --execute 参数")
    else:
        logger.warning("[Cleanup] 运行模式: EXECUTE（将实际删除表）")
        logger.warning("[Cleanup] 请确认这是开发环境，生产环境需要先备份！")
    
    cleanup_deprecated_tables(dry_run=dry_run)

