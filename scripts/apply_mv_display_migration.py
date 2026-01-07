# -*- coding: utf-8 -*-
"""
直接执行SQL迁移：添加is_mv_display字段
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from sqlalchemy import text

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def apply_migration():
    """执行迁移"""
    safe_print("=" * 70)
    safe_print("执行迁移：添加is_mv_display字段")
    safe_print("=" * 70)
    
    db = next(get_db())
    try:
        # 1. 检查字段是否已存在
        safe_print("\n[1] 检查字段是否已存在...")
        result = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'field_mapping_dictionary' 
              AND column_name = 'is_mv_display'
        """)).fetchone()
        
        if result:
            safe_print("  字段已存在，跳过迁移")
            return
        
        # 2. 添加字段
        safe_print("\n[2] 添加is_mv_display字段...")
        db.execute(text("""
            ALTER TABLE field_mapping_dictionary 
            ADD COLUMN is_mv_display BOOLEAN NOT NULL DEFAULT false
        """))
        db.execute(text("""
            COMMENT ON COLUMN field_mapping_dictionary.is_mv_display IS '是否需要在物化视图中显示（true=核心字段，false=辅助字段）'
        """))
        db.commit()
        safe_print("  [OK] 字段添加成功")
        
        # 3. 创建索引
        safe_print("\n[3] 创建索引...")
        try:
            db.execute(text("""
                CREATE INDEX ix_dictionary_mv_display 
                ON field_mapping_dictionary(is_mv_display, data_domain)
            """))
            db.commit()
            safe_print("  [OK] 索引创建成功")
        except Exception as e:
            safe_print(f"  [WARNING] 索引可能已存在: {e}")
            db.rollback()
        
        # 4. 初始化核心字段的is_mv_display值
        safe_print("\n[4] 初始化核心字段的is_mv_display值...")
        result = db.execute(text("""
            UPDATE field_mapping_dictionary 
            SET is_mv_display = true 
            WHERE is_required = true 
               OR field_group IN ('dimension', 'amount', 'quantity')
               OR field_code IN (
                   'order_id', 'platform_code', 'shop_id', 'order_time_utc', 'order_date_local',
                   'currency', 'subtotal', 'total_amount', 'shipping_fee', 'tax_amount',
                   'platform_sku', 'product_name', 'sales_volume', 'sales_amount_rmb',
                   'metric_date', 'granularity'
               )
        """))
        db.commit()
        updated_count = result.rowcount
        safe_print(f"  [OK] 已更新 {updated_count} 个核心字段")
        
        # 5. 验证结果
        safe_print("\n[5] 验证结果...")
        stats = db.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN is_mv_display = true THEN 1 END) as mv_display_true,
                COUNT(CASE WHEN is_mv_display = false THEN 1 END) as mv_display_false
            FROM field_mapping_dictionary
        """)).fetchone()
        
        if stats:
            total, mv_true, mv_false = stats
            safe_print(f"  总字段数: {total}")
            safe_print(f"  物化视图显示字段: {mv_true}")
            safe_print(f"  物化视图不显示字段: {mv_false}")
        
        safe_print("\n" + "=" * 70)
        safe_print("迁移完成！")
        safe_print("=" * 70)
        
    except Exception as e:
        db.rollback()
        safe_print(f"迁移失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    apply_migration()

