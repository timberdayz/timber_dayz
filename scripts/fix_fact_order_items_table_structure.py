#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复fact_order_items表结构，使其符合代码模型定义

问题：
- 数据库表使用item_id作为主键，缺少platform_code和shop_id字段
- 代码模型使用(platform_code, shop_id, order_id, platform_sku)作为主键
- 这是严重的表结构不一致问题

修复方案：
1. 检查当前表结构
2. 如果表结构不正确，创建新表并迁移数据
3. 删除旧表，重命名新表
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import engine, SessionLocal
from sqlalchemy import text, inspect
from modules.core.logger import get_logger

logger = get_logger(__name__)

def check_table_structure():
    """检查表结构"""
    db = SessionLocal()
    try:
        inspector = inspect(engine)
        columns = inspector.get_columns('fact_order_items')
        column_names = [c['name'] for c in columns]
        
        # 检查是否有platform_code和shop_id字段
        has_platform_code = 'platform_code' in column_names
        has_shop_id = 'shop_id' in column_names
        has_item_id = 'item_id' in column_names
        
        # 检查主键
        pk_constraint = inspector.get_pk_constraint('fact_order_items')
        pk_columns = pk_constraint.get('constrained_columns', [])
        
        return {
            'has_platform_code': has_platform_code,
            'has_shop_id': has_shop_id,
            'has_item_id': has_item_id,
            'pk_columns': pk_columns,
            'column_names': column_names
        }
    finally:
        db.close()

def fix_table_structure():
    """修复表结构"""
    db = SessionLocal()
    try:
        structure = check_table_structure()
        
        print(f"[INFO] 当前表结构检查:")
        print(f"  - 有platform_code字段: {structure['has_platform_code']}")
        print(f"  - 有shop_id字段: {structure['has_shop_id']}")
        print(f"  - 有item_id字段: {structure['has_item_id']}")
        print(f"  - 主键字段: {structure['pk_columns']}")
        
        # 如果表结构正确，不需要修复
        if structure['has_platform_code'] and structure['has_shop_id'] and 'item_id' not in structure['pk_columns']:
            print("\n[OK] 表结构正确，无需修复")
            return True
        
        # 如果表结构不正确，需要修复
        print("\n[WARNING] 表结构不正确，需要修复")
        print("[INFO] 修复方案：")
        print("  1. 创建临时表（新结构）")
        print("  2. 从旧表迁移数据（如果可能）")
        print("  3. 删除旧表")
        print("  4. 重命名临时表")
        
        # 检查是否有数据
        count = db.execute(text("SELECT COUNT(*) FROM fact_order_items")).scalar()
        print(f"\n[INFO] 当前表中有 {count} 条数据")
        
        if count > 0:
            print("[WARNING] 表中有数据，需要迁移数据")
            print("[INFO] 由于表结构差异较大，建议：")
            print("  1. 备份现有数据")
            print("  2. 清空旧表数据（如果数据不重要）")
            print("  3. 重新创建表结构")
            print("  4. 重新入库数据")
            
            # 询问是否继续
            response = input("\n是否继续修复？(yes/no): ")
            if response.lower() != 'yes':
                print("[INFO] 用户取消修复")
                return False
        
        # 创建新表结构
        print("\n[INFO] 开始修复表结构...")
        
        # 步骤1: 创建临时表（新结构）
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS fact_order_items_new (
                platform_code VARCHAR(32) NOT NULL,
                shop_id VARCHAR(64) NOT NULL,
                order_id VARCHAR(128) NOT NULL,
                platform_sku VARCHAR(128) NOT NULL,
                product_title VARCHAR(512),
                quantity INTEGER DEFAULT 1,
                currency VARCHAR(8),
                unit_price FLOAT DEFAULT 0.0,
                unit_price_rmb FLOAT DEFAULT 0.0,
                line_amount FLOAT DEFAULT 0.0,
                line_amount_rmb FLOAT DEFAULT 0.0,
                attributes JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                PRIMARY KEY (platform_code, shop_id, order_id, platform_sku)
            )
        """))
        db.commit()
        print("[OK] 创建临时表成功")
        
        # 步骤2: 创建索引
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_fact_items_plat_shop_order 
            ON fact_order_items_new (platform_code, shop_id, order_id)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_fact_items_plat_shop_sku 
            ON fact_order_items_new (platform_code, shop_id, platform_sku)
        """))
        db.commit()
        print("[OK] 创建索引成功")
        
        # 步骤3: 如果有数据，尝试迁移（但表结构差异太大，可能无法迁移）
        if count > 0 and structure['has_item_id']:
            print("[WARNING] 由于表结构差异较大，无法自动迁移数据")
            print("[INFO] 建议清空旧表数据，重新入库")
        
        # 步骤4: 删除旧表
        db.execute(text("DROP TABLE IF EXISTS fact_order_items CASCADE"))
        db.commit()
        print("[OK] 删除旧表成功")
        
        # 步骤5: 重命名新表
        db.execute(text("ALTER TABLE fact_order_items_new RENAME TO fact_order_items"))
        db.commit()
        print("[OK] 重命名表成功")
        
        print("\n[OK] 表结构修复完成！")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"[ERROR] 修复表结构失败: {e}", exc_info=True)
        print(f"\n[ERROR] 修复失败: {e}")
        return False
    finally:
        db.close()

if __name__ == '__main__':
    print("=" * 60)
    print("fact_order_items表结构修复脚本")
    print("=" * 60)
    
    # 检查表结构
    structure = check_table_structure()
    
    # 如果表结构不正确，修复
    if not (structure['has_platform_code'] and structure['has_shop_id']):
        fix_table_structure()
    else:
        print("\n[OK] 表结构正确，无需修复")

