#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量修复 b_class schema 中动态表包含日期的 shop_id

v4.17.0修复：对于miaoshou平台的inventory和orders数据域的动态表，
如果shop_id包含日期格式（如 products_snapshot_20250926），
统一设置为 'none'，避免去重失败。

使用方法：
    python scripts/fix_b_class_shop_id_with_dates.py --execute
"""

import sys
import re
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import Session
from modules.core.logger import get_logger

logger = get_logger(__name__)


def fix_b_class_shop_id_with_dates(dry_run: bool = True):
    """
    批量修复 b_class schema 中动态表包含日期的 shop_id
    
    Args:
        dry_run: 如果为True，只显示将要修复的记录，不实际修改
    """
    # 获取数据库引擎
    from backend.utils.config import get_settings
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL)
    
    session = Session(engine)
    
    try:
        # 获取所有 b_class schema 中的表
        inspector = inspect(engine)
        all_tables = inspector.get_table_names(schema='b_class')
        
        # 筛选出 miaoshou 平台的 inventory 和 orders 数据域的表
        target_tables = []
        for table_name in all_tables:
            # 表名格式：fact_miaoshou_inventory_snapshot 或 fact_miaoshou_orders_daily
            if (table_name.startswith('fact_miaoshou_') or table_name.startswith('fact_shou_')) and (
                'inventory' in table_name or 'orders' in table_name
            ):
                target_tables.append(table_name)
        
        logger.info(f"找到 {len(target_tables)} 个需要检查的表: {', '.join(target_tables)}")
        
        total_fixed = 0
        
        for table_name in target_tables:
            # 检查表是否有 shop_id 列
            columns = inspector.get_columns(table_name, schema='b_class')
            has_shop_id = any(col['name'] == 'shop_id' for col in columns)
            
            if not has_shop_id:
                logger.debug(f"表 {table_name} 没有 shop_id 列，跳过")
                continue
            
            # 查询包含日期的 shop_id
            # 查找包含8位数字或snapshot关键字的shop_id
            query = text(f"""
                SELECT DISTINCT shop_id, COUNT(*) as count
                FROM b_class."{table_name}"
                WHERE shop_id IS NOT NULL
                  AND (
                    shop_id ~ '\\d{{8}}'  -- 包含8位数字（日期格式）
                    OR shop_id ILIKE '%snapshot%'  -- 包含snapshot关键字
                  )
                GROUP BY shop_id
            """)
            
            result = session.execute(query).fetchall()
            
            if not result:
                logger.debug(f"表 {table_name} 没有需要修复的记录")
                continue
            
            logger.info(f"\n表 {table_name}:")
            for row in result:
                old_shop_id = row[0]
                count = row[1]
                
                if dry_run:
                    logger.info(
                        f"  [DRY RUN] 将修复 {count} 条记录: "
                        f"old_shop_id={old_shop_id} → new_shop_id='none'"
                    )
                else:
                    # 实际修复
                    update_query = text(f"""
                        UPDATE b_class."{table_name}"
                        SET shop_id = 'none'
                        WHERE shop_id = :old_shop_id
                    """)
                    session.execute(update_query, {'old_shop_id': old_shop_id})
                    session.commit()
                    
                    logger.info(
                        f"  [FIXED] 已修复 {count} 条记录: "
                        f"old_shop_id={old_shop_id} → new_shop_id='none'"
                    )
                    total_fixed += count
        
        if not dry_run:
            logger.info(f"\n[完成] 总共修复了 {total_fixed} 条记录")
        else:
            logger.info(f"\n[DRY RUN] 将修复 {total_fixed} 条记录")
            logger.info("[提示] 运行脚本时添加 --execute 参数来实际执行修复")
        
        return total_fixed
        
    except Exception as e:
        session.rollback()
        logger.error(f"修复过程中出错: {e}", exc_info=True)
        raise
    finally:
        session.close()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='批量修复 b_class schema 中动态表包含日期的 shop_id')
    parser.add_argument(
        '--execute',
        action='store_true',
        help='实际执行修复（默认只显示将要修复的记录）'
    )
    
    args = parser.parse_args()
    
    dry_run = not args.execute
    
    if dry_run:
        logger.info("=" * 60)
        logger.info("DRY RUN 模式：只显示将要修复的记录，不实际修改")
        logger.info("=" * 60)
    else:
        logger.info("=" * 60)
        logger.info("执行模式：将实际修改数据库")
        logger.info("=" * 60)
    
    try:
        fixed_count = fix_b_class_shop_id_with_dates(dry_run=dry_run)
        
        if dry_run and fixed_count > 0:
            print("\n" + "=" * 60)
            print(f"发现 {fixed_count} 条需要修复的记录")
            print("运行以下命令来实际执行修复：")
            print("  python scripts/fix_b_class_shop_id_with_dates.py --execute")
            print("=" * 60)
        elif not dry_run:
            print("\n" + "=" * 60)
            print(f"成功修复 {fixed_count} 条记录")
            print("=" * 60)
    except Exception as e:
        logger.error(f"脚本执行失败: {e}", exc_info=True)
        sys.exit(1)

