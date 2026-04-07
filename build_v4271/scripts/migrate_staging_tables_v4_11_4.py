#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库迁移脚本 - v4.11.4

添加staging表的ingest_task_id和file_id字段
创建staging_inventory表
创建mv_refresh_log表（如果不存在）
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal, engine
from sqlalchemy import text
from modules.core.logger import get_logger

logger = get_logger(__name__)

def migrate():
    """执行迁移"""
    db = SessionLocal()
    try:
        logger.info("开始数据库迁移 v4.11.4...")
        
        # 1. 检查并添加staging_orders字段
        logger.info("检查staging_orders表...")
        cols = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'staging_orders'
        """)).fetchall()
        col_names = [c[0] for c in cols]
        
        if 'ingest_task_id' not in col_names:
            logger.info("添加staging_orders.ingest_task_id字段...")
            db.execute(text("ALTER TABLE staging_orders ADD COLUMN ingest_task_id VARCHAR(64)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_staging_orders_task ON staging_orders(ingest_task_id)"))
            db.commit()
            logger.info("staging_orders.ingest_task_id字段添加成功")
        else:
            logger.info("staging_orders.ingest_task_id字段已存在，跳过")
        
        if 'file_id' not in col_names:
            logger.info("添加staging_orders.file_id字段...")
            db.execute(text("ALTER TABLE staging_orders ADD COLUMN file_id INTEGER REFERENCES catalog_files(id) ON DELETE SET NULL"))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_staging_orders_file ON staging_orders(file_id)"))
            db.commit()
            logger.info("staging_orders.file_id字段添加成功")
        else:
            logger.info("staging_orders.file_id字段已存在，跳过")
        
        # 2. 检查并添加staging_product_metrics字段
        logger.info("检查staging_product_metrics表...")
        cols = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'staging_product_metrics'
        """)).fetchall()
        col_names = [c[0] for c in cols]
        
        if 'ingest_task_id' not in col_names:
            logger.info("添加staging_product_metrics.ingest_task_id字段...")
            db.execute(text("ALTER TABLE staging_product_metrics ADD COLUMN ingest_task_id VARCHAR(64)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_staging_metrics_task ON staging_product_metrics(ingest_task_id)"))
            db.commit()
            logger.info("staging_product_metrics.ingest_task_id字段添加成功")
        else:
            logger.info("staging_product_metrics.ingest_task_id字段已存在，跳过")
        
        if 'file_id' not in col_names:
            logger.info("添加staging_product_metrics.file_id字段...")
            db.execute(text("ALTER TABLE staging_product_metrics ADD COLUMN file_id INTEGER REFERENCES catalog_files(id) ON DELETE SET NULL"))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_staging_metrics_file ON staging_product_metrics(file_id)"))
            db.commit()
            logger.info("staging_product_metrics.file_id字段添加成功")
        else:
            logger.info("staging_product_metrics.file_id字段已存在，跳过")
        
        # 3. 检查并创建staging_inventory表
        logger.info("检查staging_inventory表...")
        exists = db.execute(text("""
            SELECT EXISTS(
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'staging_inventory'
            )
        """)).scalar()
        
        if not exists:
            logger.info("创建staging_inventory表...")
            db.execute(text("""
                CREATE TABLE staging_inventory (
                    id SERIAL PRIMARY KEY,
                    platform_code VARCHAR(32),
                    shop_id VARCHAR(64),
                    platform_sku VARCHAR(128),
                    warehouse_id VARCHAR(64),
                    inventory_data JSONB NOT NULL,
                    ingest_task_id VARCHAR(64),
                    file_id INTEGER REFERENCES catalog_files(id) ON DELETE SET NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            db.execute(text("CREATE INDEX ix_staging_inventory_platform ON staging_inventory(platform_code)"))
            db.execute(text("CREATE INDEX ix_staging_inventory_task ON staging_inventory(ingest_task_id)"))
            db.execute(text("CREATE INDEX ix_staging_inventory_file ON staging_inventory(file_id)"))
            db.execute(text("CREATE INDEX ix_staging_inventory_sku ON staging_inventory(platform_code, shop_id, platform_sku)"))
            db.commit()
            logger.info("staging_inventory表创建成功")
        else:
            logger.info("staging_inventory表已存在，跳过")
        
        # 4. 检查并创建mv_refresh_log表
        logger.info("检查mv_refresh_log表...")
        exists = db.execute(text("""
            SELECT EXISTS(
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'mv_refresh_log'
            )
        """)).scalar()
        
        if not exists:
            logger.info("创建mv_refresh_log表...")
            db.execute(text("""
                CREATE TABLE mv_refresh_log (
                    id SERIAL PRIMARY KEY,
                    view_name VARCHAR(128) NOT NULL,
                    refresh_started_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    refresh_completed_at TIMESTAMP,
                    duration_seconds FLOAT,
                    row_count INTEGER,
                    status VARCHAR(20) DEFAULT 'running' NOT NULL,
                    error_message TEXT,
                    triggered_by VARCHAR(64) DEFAULT 'scheduler' NOT NULL,
                    CONSTRAINT chk_mv_refresh_status CHECK (status IN ('running', 'success', 'failed'))
                )
            """))
            db.execute(text("CREATE INDEX ix_mv_refresh_log_view ON mv_refresh_log(view_name, refresh_started_at)"))
            db.execute(text("CREATE INDEX ix_mv_refresh_log_status ON mv_refresh_log(status, refresh_started_at)"))
            db.commit()
            logger.info("mv_refresh_log表创建成功")
        else:
            logger.info("mv_refresh_log表已存在，跳过")
        
        logger.info("数据库迁移完成！")
        return True
        
    except Exception as e:
        logger.error(f"迁移失败: {e}", exc_info=True)
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == '__main__':
    success = migrate()
    sys.exit(0 if success else 1)

