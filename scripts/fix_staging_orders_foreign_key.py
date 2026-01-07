#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复staging_orders表的外键约束（v4.12.1）

问题：数据库中的外键约束指向data_files表，但应该指向catalog_files表
解决方案：删除旧的外键约束，创建新的外键约束指向catalog_files表
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal, engine
from sqlalchemy import text
from modules.core.logger import get_logger

logger = get_logger(__name__)


def fix_foreign_key():
    """修复staging_orders表的外键约束"""
    db = SessionLocal()
    try:
        logger.info("开始修复staging_orders表的外键约束...")
        
        # 1. 检查当前的外键约束
        fk_constraints = db.execute(text("""
            SELECT 
                tc.constraint_name,
                tc.table_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.table_name = 'staging_orders'
                AND tc.constraint_type = 'FOREIGN KEY'
                AND kcu.column_name = 'file_id'
        """)).fetchall()
        
        logger.info(f"当前外键约束: {fk_constraints}")
        
        # 2. 删除指向data_files的外键约束
        for constraint in fk_constraints:
            constraint_name = constraint[0]
            foreign_table = constraint[3]
            
            if foreign_table == 'data_files':
                logger.info(f"删除旧的外键约束: {constraint_name} (指向data_files表)")
                db.execute(text(f"ALTER TABLE staging_orders DROP CONSTRAINT IF EXISTS {constraint_name}"))
                db.commit()
                logger.info(f"已删除外键约束: {constraint_name}")
        
        # 3. 创建新的外键约束指向catalog_files表
        logger.info("创建新的外键约束指向catalog_files表...")
        db.execute(text("""
            ALTER TABLE staging_orders 
            ADD CONSTRAINT staging_orders_file_id_fkey 
            FOREIGN KEY (file_id) 
            REFERENCES catalog_files(id) 
            ON DELETE SET NULL
        """))
        db.commit()
        logger.info("已创建新的外键约束: staging_orders_file_id_fkey (指向catalog_files表)")
        
        # 4. 验证修复结果
        new_fk = db.execute(text("""
            SELECT 
                tc.constraint_name,
                ccu.table_name AS foreign_table_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.table_name = 'staging_orders'
                AND tc.constraint_type = 'FOREIGN KEY'
                AND tc.constraint_name = 'staging_orders_file_id_fkey'
        """)).fetchone()
        
        if new_fk and new_fk[1] == 'catalog_files':
            logger.info("[OK] 外键约束修复成功！现在指向catalog_files表")
        else:
            logger.error("[ERROR] 外键约束修复失败！")
            
    except Exception as e:
        logger.error(f"修复外键约束失败: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    fix_foreign_key()

