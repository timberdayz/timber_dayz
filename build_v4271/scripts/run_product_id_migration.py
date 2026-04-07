#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运行product_id字段迁移脚本

使用方法：
    python scripts/run_product_id_migration.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from backend.models.database import get_db, engine
from modules.core.logger import get_logger

logger = get_logger(__name__)


def safe_print(text):
    """Windows兼容的安全打印"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))


def check_column_exists(db, table_name, column_name):
    """检查字段是否存在"""
    result = db.execute(text(f"""
        SELECT COUNT(*) 
        FROM information_schema.columns 
        WHERE table_name = :table_name 
          AND column_name = :column_name
    """), {"table_name": table_name, "column_name": column_name})
    return result.scalar() > 0


def run_migration():
    """运行迁移"""
    safe_print("=" * 70)
    safe_print("运行product_id字段迁移")
    safe_print("=" * 70)
    
    db = next(get_db())
    try:
        # 检查字段是否已存在
        if check_column_exists(db, 'fact_order_items', 'product_id'):
            safe_print("[INFO] product_id字段已存在，跳过迁移")
            return True
        
        safe_print("[INFO] 开始添加product_id字段...")
        
        # 1. 添加product_id字段
        db.execute(text("""
            ALTER TABLE fact_order_items 
            ADD COLUMN product_id INTEGER
        """))
        safe_print("[OK] 已添加product_id字段")
        
        # 2. 添加外键约束
        try:
            db.execute(text("""
                ALTER TABLE fact_order_items 
                ADD CONSTRAINT fk_fact_order_items_product_id 
                FOREIGN KEY (product_id) 
                REFERENCES dim_product_master(product_id) 
                ON DELETE SET NULL
            """))
            safe_print("[OK] 已添加外键约束")
        except Exception as e:
            safe_print(f"[WARN] 添加外键约束失败（可能已存在）: {e}")
        
        # 3. 创建索引
        try:
            db.execute(text("""
                CREATE INDEX ix_fact_items_product_id 
                ON fact_order_items(product_id)
            """))
            safe_print("[OK] 已创建索引")
        except Exception as e:
            safe_print(f"[WARN] 创建索引失败（可能已存在）: {e}")
        
        # 提交事务
        db.commit()
        safe_print("\n[SUCCESS] 迁移完成！")
        
        # 验证
        if check_column_exists(db, 'fact_order_items', 'product_id'):
            safe_print("[OK] 验证通过：product_id字段已存在")
            return True
        else:
            safe_print("[ERROR] 验证失败：product_id字段不存在")
            return False
        
    except Exception as e:
        db.rollback()
        safe_print(f"\n[ERROR] 迁移失败: {e}")
        logger.error("迁移失败", exc_info=True)
        return False
    finally:
        db.close()


if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)

