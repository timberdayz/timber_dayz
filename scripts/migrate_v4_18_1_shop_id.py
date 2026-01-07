#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v4.18.1 数据库迁移脚本：添加shop_id字段到platform_accounts表

执行：
    python scripts/migrate_v4_18_1_shop_id.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from backend.models.database import engine, SessionLocal
from modules.core.logger import get_logger

logger = get_logger(__name__)


def migrate_platform_accounts_shop_id():
    """添加shop_id字段到platform_accounts表"""
    db = SessionLocal()
    try:
        logger.info("[Migration] 开始添加shop_id字段到platform_accounts表...")
        
        # 检查列是否已存在（可能在public或core schema）
        check_sql = text("""
            SELECT table_schema, column_name 
            FROM information_schema.columns 
            WHERE table_schema IN ('public', 'core')
            AND table_name = 'platform_accounts'
            AND column_name = 'shop_id'
        """)
        result = db.execute(check_sql).fetchone()
        
        if result:
            schema_name = result[0]
            logger.info(f"[Migration] shop_id列已存在 (schema={schema_name})，跳过添加")
            return True
        
        # 确定表所在的schema（优先core，否则public）
        table_schema_sql = text("""
            SELECT table_schema 
            FROM information_schema.tables 
            WHERE table_schema IN ('public', 'core')
            AND table_name = 'platform_accounts'
            LIMIT 1
        """)
        schema_result = db.execute(table_schema_sql).fetchone()
        schema_name = schema_result[0] if schema_result else 'public'
        
        # 添加shop_id列
        add_column_sql = text(f"""
            ALTER TABLE {schema_name}.platform_accounts 
            ADD COLUMN shop_id VARCHAR(256) NULL
        """)
        db.execute(add_column_sql)
        
        # 添加注释（需要单独执行）
        comment_sql = text(f"""
            COMMENT ON COLUMN {schema_name}.platform_accounts.shop_id IS '店铺ID（用于关联数据同步中的shop_id，可编辑）'
        """)
        db.execute(comment_sql)
        logger.info("[Migration] 成功添加shop_id列")
        
        # 创建索引
        check_index_sql = text(f"""
            SELECT indexname 
            FROM pg_indexes 
            WHERE schemaname = '{schema_name}'
            AND tablename = 'platform_accounts'
            AND indexname = 'ix_platform_accounts_shop_id'
        """)
        index_result = db.execute(check_index_sql).fetchone()
        
        if not index_result:
            create_index_sql = text(f"""
                CREATE INDEX ix_platform_accounts_shop_id 
                ON {schema_name}.platform_accounts(shop_id)
            """)
            db.execute(create_index_sql)
            logger.info("[Migration] 成功创建shop_id索引")
        else:
            logger.info("[Migration] shop_id索引已存在，跳过创建")
        
        db.commit()
        logger.info("[Migration] platform_accounts表迁移完成")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"[Migration] 迁移失败: {e}", exc_info=True)
        return False
    finally:
        db.close()


def migrate_period_columns():
    """
    为所有已存在的fact_raw_data_*表添加period列
    
    注意：这个功能已经在platform_table_manager.py中自动处理，
    但为了确保所有表都已更新，这里提供一个手动迁移脚本
    """
    db = SessionLocal()
    try:
        logger.info("[Migration] 开始检查fact_raw_data_*表的period列...")
        
        # 获取所有fact_raw_data_*表
        get_tables_sql = text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'b_class' 
            AND table_name LIKE 'fact_%'
        """)
        tables = db.execute(get_tables_sql).fetchall()
        
        updated_count = 0
        for (table_name,) in tables:
            # 检查period列是否存在
            check_columns_sql = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_schema = 'b_class' 
                AND table_name = :table_name
                AND column_name IN ('period_start_date', 'period_end_date', 'period_start_time', 'period_end_time')
            """)
            existing_columns = {row[0] for row in db.execute(check_columns_sql, {'table_name': table_name}).fetchall()}
            
            columns_to_add = []
            if 'period_start_date' not in existing_columns:
                columns_to_add.append(('period_start_date', 'DATE', 'CURRENT_DATE'))
            if 'period_end_date' not in existing_columns:
                columns_to_add.append(('period_end_date', 'DATE', 'CURRENT_DATE'))
            if 'period_start_time' not in existing_columns:
                columns_to_add.append(('period_start_time', 'TIMESTAMP', None))
            if 'period_end_time' not in existing_columns:
                columns_to_add.append(('period_end_time', 'TIMESTAMP', None))
            
            if columns_to_add:
                logger.info(f"[Migration] 表 {table_name} 需要添加 {len(columns_to_add)} 个period列")
                for col_name, col_type, default_value in columns_to_add:
                    try:
                        if default_value:
                            alter_sql = text(f'''
                                ALTER TABLE b_class."{table_name}" 
                                ADD COLUMN {col_name} {col_type} DEFAULT {default_value}
                            ''')
                        else:
                            alter_sql = text(f'''
                                ALTER TABLE b_class."{table_name}" 
                                ADD COLUMN {col_name} {col_type}
                            ''')
                        db.execute(alter_sql)
                        logger.info(f"[Migration] 表 {table_name} 添加列 {col_name}")
                    except Exception as e:
                        logger.warning(f"[Migration] 表 {table_name} 添加列 {col_name} 失败: {e}")
                
                # 创建索引
                try:
                    index_sql = text(f'''
                        CREATE INDEX IF NOT EXISTS "ix_{table_name}_period_date" 
                        ON b_class."{table_name}" (period_start_date, period_end_date)
                    ''')
                    db.execute(index_sql)
                except Exception as e:
                    logger.warning(f"[Migration] 表 {table_name} 创建索引失败: {e}")
                
                updated_count += 1
        
        db.commit()
        logger.info(f"[Migration] period列迁移完成，更新了 {updated_count} 个表")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"[Migration] period列迁移失败: {e}", exc_info=True)
        return False
    finally:
        db.close()


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("v4.18.1 数据库迁移开始")
    logger.info("=" * 60)
    
    success = True
    
    # 1. 迁移platform_accounts表
    if not migrate_platform_accounts_shop_id():
        success = False
    
    # 2. 迁移period列（可选，代码中已自动处理）
    # 如果需要手动确保所有表都已更新，可以取消注释
    # if not migrate_period_columns():
    #     success = False
    
    logger.info("=" * 60)
    if success:
        logger.info("[Migration] 所有迁移完成！")
    else:
        logger.error("[Migration] 部分迁移失败，请检查日志")
    logger.info("=" * 60)
    
    sys.exit(0 if success else 1)

