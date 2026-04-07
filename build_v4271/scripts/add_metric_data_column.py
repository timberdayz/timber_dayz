#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
添加staging_product_metrics表的metric_data字段（v4.12.1）

问题：数据库表缺少metric_data字段，但代码中需要使用
解决方案：添加metric_data JSON字段
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from sqlalchemy import text
from modules.core.logger import get_logger

logger = get_logger(__name__)


def add_metric_data_column():
    """添加metric_data字段"""
    db = SessionLocal()
    try:
        logger.info("检查staging_product_metrics表结构...")
        
        # 检查是否已有metric_data字段
        cols = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'staging_product_metrics'
        """)).fetchall()
        col_names = [c[0] for c in cols]
        
        if 'metric_data' not in col_names:
            logger.info("添加metric_data字段...")
            db.execute(text("""
                ALTER TABLE staging_product_metrics 
                ADD COLUMN metric_data JSONB NOT NULL DEFAULT '{}'::jsonb
            """))
            db.commit()
            logger.info("[OK] metric_data字段添加成功")
        else:
            logger.info("metric_data字段已存在，跳过")
            
    except Exception as e:
        logger.error(f"添加字段失败: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    add_metric_data_column()

