#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将fact_raw_data_*表从public schema移动到b_class schema

执行前请确保：
1. 已备份数据库
2. 已停止所有数据同步任务
3. 已确认Metabase连接配置
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from backend.utils.config import get_settings
from modules.core.logger import get_logger

logger = get_logger(__name__)

def migrate_tables_to_b_class():
    """将fact_raw_data_*表移动到b_class schema"""
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL)
    
    # 需要移动的表列表
    tables_to_migrate = [
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
    
    with engine.connect() as conn:
        # 开始事务
        trans = conn.begin()
        
        try:
            # 1. 创建b_class schema（如果不存在）
            logger.info("创建b_class schema（如果不存在）...")
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS b_class"))
            logger.info("[OK] b_class schema已创建或已存在")
            
            # 2. 检查每个表是否存在，并移动
            migrated_tables = []
            skipped_tables = []
            
            for table_name in tables_to_migrate:
                # 检查表是否存在
                result = conn.execute(text("""
                    SELECT table_schema 
                    FROM information_schema.tables 
                    WHERE table_name = :table_name
                """), {"table_name": table_name})
                
                table_info = result.fetchone()
                
                if not table_info:
                    logger.warning(f"[跳过] 表 {table_name} 不存在")
                    skipped_tables.append(table_name)
                    continue
                
                current_schema = table_info[0]
                
                if current_schema == 'b_class':
                    logger.info(f"[跳过] 表 {table_name} 已在 b_class schema")
                    skipped_tables.append(table_name)
                    continue
                
                if current_schema != 'public':
                    logger.warning(f"[跳过] 表 {table_name} 在 {current_schema} schema，不在 public schema")
                    skipped_tables.append(table_name)
                    continue
                
                # 移动表到b_class schema
                logger.info(f"移动表 {table_name} 从 public 到 b_class...")
                conn.execute(text(f'ALTER TABLE public.{table_name} SET SCHEMA b_class'))
                logger.info(f"[OK] 表 {table_name} 已移动到 b_class schema")
                migrated_tables.append(table_name)
            
            # 提交事务
            trans.commit()
            
            # 输出总结
            logger.info("=" * 60)
            logger.info("迁移完成总结")
            logger.info("=" * 60)
            logger.info(f"已迁移的表 ({len(migrated_tables)}):")
            for table in migrated_tables:
                logger.info(f"  ✅ {table}")
            
            if skipped_tables:
                logger.info(f"\n跳过的表 ({len(skipped_tables)}):")
                for table in skipped_tables:
                    logger.info(f"  ⏭️  {table}")
            
            # 验证迁移结果
            logger.info("\n验证迁移结果...")
            for table_name in migrated_tables:
                # 检查表schema
                schema_result = conn.execute(text("""
                    SELECT table_schema 
                    FROM information_schema.tables 
                    WHERE table_name = :table_name
                """), {"table_name": table_name})
                
                schema_info = schema_result.fetchone()
                if schema_info:
                    schema = schema_info[0]
                    # 查询实际行数
                    count_result = conn.execute(text(f'SELECT COUNT(*) FROM b_class.{table_name}'))
                    row_count = count_result.scalar()
                    logger.info(f"  {table_name}: schema={schema}, 行数={row_count}")
            
            logger.info("\n[OK] 迁移完成！")
            logger.info("\n下一步：")
            logger.info("  1. 在 Metabase 中点击 'Sync database schema now'")
            logger.info("  2. 验证表在 b_class schema 中可见")
            logger.info("  3. 重新测试数据查询")
            
        except Exception as e:
            trans.rollback()
            logger.error(f"[ERROR] 迁移失败: {e}", exc_info=True)
            raise

if __name__ == "__main__":
    print("=" * 60)
    print("将fact_raw_data_*表从public移动到b_class schema")
    print("=" * 60)
    print("\n⚠️  警告：此操作会移动表，请确保：")
    print("  1. 已备份数据库")
    print("  2. 已停止所有数据同步任务")
    print("  3. 已确认Metabase连接配置")
    print("\n按 Ctrl+C 取消，或按 Enter 继续...")
    
    try:
        input()
    except KeyboardInterrupt:
        print("\n已取消")
        sys.exit(0)
    
    migrate_tables_to_b_class()

