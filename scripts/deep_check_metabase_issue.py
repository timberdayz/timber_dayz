#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
深度检查 Metabase 问题

检查：
1. 数据库中是否有视图引用旧表名
2. 是否有表别名
3. 检查 b_class schema 中的所有表（Metabase 应该看到的）
4. 检查是否有跨 schema 的重复表名
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from sqlalchemy import text, inspect
from modules.core.logger import get_logger

logger = get_logger(__name__)

def check_views():
    """检查是否有视图引用旧表名"""
    logger.info("=" * 70)
    logger.info("检查是否有视图引用旧表名（fact_raw_data_*）")
    logger.info("=" * 70)
    
    db = next(get_db())
    
    try:
        result = db.execute(text("""
            SELECT 
                schemaname,
                viewname,
                definition
            FROM pg_views
            WHERE definition LIKE '%fact_raw_data%'
            ORDER BY schemaname, viewname
        """))
        
        views = list(result)
        
        if views:
            logger.warning(f"\n⚠️ 发现 {len(views)} 个视图引用旧表:")
            for schema, view_name, definition in views:
                logger.warning(f"\n[{schema}.{view_name}]")
                # 只显示定义的前300个字符
                logger.warning(f"  定义: {definition[:300]}...")
            return views
        else:
            logger.info("\n✅ 没有视图引用旧表")
            return []
    except Exception as e:
        logger.error(f"检查视图失败: {e}", exc_info=True)
        return []
    finally:
        db.close()

def check_b_class_all_tables():
    """检查 b_class schema 中的所有表"""
    logger.info("\n" + "=" * 70)
    logger.info("检查 b_class schema 中的所有表（Metabase 应该看到的）")
    logger.info("=" * 70)
    
    db = next(get_db())
    inspector = inspect(db.bind)
    
    try:
        tables = inspector.get_table_names(schema='b_class')
        
        logger.info(f"\nb_class schema 中共有 {len(tables)} 个表")
        
        # 分类显示
        fact_tables = [t for t in tables if t.startswith('fact_')]
        other_tables = [t for t in tables if not t.startswith('fact_')]
        
        logger.info(f"\n[fact_ 开头的表] {len(fact_tables)} 个:")
        for table in sorted(fact_tables):
            try:
                count = db.execute(
                    text(f'SELECT COUNT(*) FROM b_class."{table}"')
                ).scalar() or 0
                logger.info(f"  - {table}: {count} 行")
            except Exception as e:
                logger.warning(f"  - {table}: 查询失败 ({e})")
        
        if other_tables:
            logger.info(f"\n[其他表] {len(other_tables)} 个:")
            for table in sorted(other_tables):
                try:
                    count = db.execute(
                        text(f'SELECT COUNT(*) FROM b_class."{table}"')
                    ).scalar() or 0
                    logger.info(f"  - {table}: {count} 行")
                except Exception as e:
                    logger.warning(f"  - {table}: 查询失败 ({e})")
        
        # 检查是否有旧表名
        old_table_names = [
            "fact_raw_data_orders_daily",
            "fact_raw_data_orders_weekly",
            "fact_raw_data_orders_monthly",
            "fact_raw_data_products_daily",
            "fact_raw_data_products_weekly",
            "fact_raw_data_products_monthly",
            "fact_raw_data_traffic_daily",
            "fact_raw_data_traffic_weekly",
            "fact_raw_data_traffic_monthly",
            "fact_raw_data_services_daily",
            "fact_raw_data_services_weekly",
            "fact_raw_data_services_monthly",
            "fact_raw_data_inventory_snapshot",
        ]
        
        found_old_names = [t for t in tables if t in old_table_names]
        
        if found_old_names:
            logger.warning(f"\n⚠️ 发现 {len(found_old_names)} 个旧表名在 b_class schema 中:")
            for table in found_old_names:
                logger.warning(f"  - {table}")
            return found_old_names
        else:
            logger.info("\n✅ b_class schema 中没有旧表名")
            return []
            
    except Exception as e:
        logger.error(f"检查 b_class schema 失败: {e}", exc_info=True)
        return []
    finally:
        db.close()

def check_duplicate_table_names():
    """检查是否有多个 schema 中有同名表"""
    logger.info("\n" + "=" * 70)
    logger.info("检查是否有多个 schema 中有同名表")
    logger.info("=" * 70)
    
    db = next(get_db())
    
    try:
        result = db.execute(text("""
            SELECT 
                table_name,
                COUNT(DISTINCT table_schema) as schema_count,
                STRING_AGG(DISTINCT table_schema, ', ' ORDER BY table_schema) as schemas
            FROM information_schema.tables
            WHERE table_schema IN ('public', 'b_class', 'a_class', 'c_class', 'core', 'finance')
            AND table_name LIKE 'fact_%'
            GROUP BY table_name
            HAVING COUNT(DISTINCT table_schema) > 1
            ORDER BY table_name
        """))
        
        duplicates = list(result)
        
        if duplicates:
            logger.warning(f"\n⚠️ 发现 {len(duplicates)} 个表在多个 schema 中存在:")
            for table_name, schema_count, schemas in duplicates:
                logger.warning(f"  - {table_name}: 存在于 {schemas} ({schema_count} 个 schema)")
            return duplicates
        else:
            logger.info("\n✅ 没有发现跨 schema 的重复表名")
            return []
    except Exception as e:
        logger.error(f"检查重复表名失败: {e}", exc_info=True)
        return []
    finally:
        db.close()

def check_table_aliases():
    """检查是否有表别名（PostgreSQL 不支持，但检查是否有类似结构）"""
    logger.info("\n" + "=" * 70)
    logger.info("检查是否有表别名或同义词")
    logger.info("=" * 70)
    
    db = next(get_db())
    
    try:
        # PostgreSQL 不支持表别名（synonyms），但检查是否有类似的结构
        result = db.execute(text("""
            SELECT 
                schemaname,
                tablename
            FROM pg_tables
            WHERE tablename LIKE '%synonym%'
            OR tablename LIKE '%alias%'
            OR tablename LIKE '%fact_raw_data%'
            ORDER BY schemaname, tablename
        """))
        
        tables = list(result)
        
        if tables:
            logger.info(f"\n发现 {len(tables)} 个可能的别名或相关表:")
            for schema, table_name in tables:
                logger.info(f"  - {schema}.{table_name}")
        else:
            logger.info("\n✅ 没有发现别名表")
        
        return tables
    except Exception as e:
        logger.error(f"检查别名失败: {e}", exc_info=True)
        return []
    finally:
        db.close()

def main():
    """主函数"""
    logger.info("=" * 70)
    logger.info("深度检查 Metabase 问题")
    logger.info("=" * 70)
    
    # 1. 检查视图
    views = check_views()
    
    # 2. 检查 b_class schema 中的所有表
    old_names = check_b_class_all_tables()
    
    # 3. 检查重复表名
    duplicates = check_duplicate_table_names()
    
    # 4. 检查别名
    aliases = check_table_aliases()
    
    # 总结
    logger.info("\n" + "=" * 70)
    logger.info("检查总结")
    logger.info("=" * 70)
    
    if views:
        logger.warning(f"\n⚠️ 发现 {len(views)} 个视图引用旧表")
        logger.warning("这些视图可能导致 Metabase 显示旧表名")
    
    if old_names:
        logger.warning(f"\n⚠️ 发现 {len(old_names)} 个旧表名在 b_class schema 中")
        logger.warning("这些表需要删除")
    
    if duplicates:
        logger.warning(f"\n⚠️ 发现 {len(duplicates)} 个跨 schema 的重复表名")
        logger.warning("这可能导致 Metabase 查询到错误的表")
    
    if not views and not old_names and not duplicates:
        logger.info("\n✅ 数据库检查通过，没有发现旧表、视图或重复表名")
        logger.info("\n问题可能出在 Metabase 的配置或缓存")
        logger.info("建议：")
        logger.info("1. 检查 Metabase 的 Schema filters 配置")
        logger.info("2. 确保选择了 '全部' / 'All schemas'")
        logger.info("3. 再次同步 Schema")
        logger.info("4. 如果还是不行，可能需要检查 Metabase 的 H2 数据库")
    
    logger.info("\n" + "=" * 70)
    logger.info("检查完成")
    logger.info("=" * 70)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n[INFO] 用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"[ERROR] 脚本执行异常: {e}", exc_info=True)
        sys.exit(1)

