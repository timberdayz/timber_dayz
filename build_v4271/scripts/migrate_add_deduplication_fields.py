#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库迁移脚本：添加deduplication_fields字段到FieldMappingTemplate表（v4.14.0）

功能：
- 添加 `deduplication_fields` JSONB 字段到 `field_mapping_templates` 表
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


def migrate_add_deduplication_fields():
    """
    添加deduplication_fields字段到FieldMappingTemplate表
    """
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.connect() as conn:
        # 开始事务
        trans = conn.begin()
        
        try:
            # 检查字段是否已存在
            check_column_sql = text("""
                SELECT COUNT(*) 
                FROM information_schema.columns 
                WHERE table_name = 'field_mapping_templates' 
                AND column_name = 'deduplication_fields'
            """)
            column_exists = conn.execute(check_column_sql).scalar() > 0
            
            if column_exists:
                logger.info("[Migration] deduplication_fields字段已存在，跳过添加")
            else:
                # 添加字段（PostgreSQL不支持COMMENT在ALTER TABLE中，需要单独执行）
                add_column_sql = text("""
                    ALTER TABLE field_mapping_templates 
                    ADD COLUMN deduplication_fields JSONB NULL
                """)
                conn.execute(add_column_sql)
                
                # 添加注释（PostgreSQL使用COMMENT ON COLUMN）
                comment_sql = text("""
                    COMMENT ON COLUMN field_mapping_templates.deduplication_fields 
                    IS '核心去重字段列表（JSONB数组），用于data_hash计算，不受表头变化影响'
                """)
                conn.execute(comment_sql)
                
                logger.info("[Migration] 成功添加deduplication_fields字段到field_mapping_templates表")
            
            # 提交事务
            trans.commit()
            logger.info("[Migration] 迁移完成：deduplication_fields字段已添加")
            
        except Exception as e:
            # 回滚事务
            trans.rollback()
            logger.error(f"[Migration] 迁移失败: {e}", exc_info=True)
            raise


if __name__ == "__main__":
    migrate_add_deduplication_fields()

