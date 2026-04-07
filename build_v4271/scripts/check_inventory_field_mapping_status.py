# -*- coding: utf-8 -*-
"""
检查inventory域字段映射情况，解释为什么物化视图只显示部分字段
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from sqlalchemy import text

def safe_print(text_str):
    try:
        print(text_str)
    except UnicodeEncodeError:
        print(text_str.encode('gbk', errors='ignore').decode('gbk'))

def check_inventory_field_mapping():
    """检查inventory域字段映射情况"""
    safe_print("=" * 80)
    safe_print("检查inventory域字段映射情况")
    safe_print("=" * 80)
    
    db = next(get_db())
    try:
        # 1. 查询inventory域总共有多少字段
        safe_print("\n[1] inventory域字段总数统计...")
        total_fields_sql = """
            SELECT COUNT(*) as total_count
            FROM field_mapping_dictionary
            WHERE data_domain = 'inventory'
              AND active = true
              AND status = 'active'
        """
        total_count = db.execute(text(total_fields_sql)).scalar()
        safe_print(f"inventory域总字段数: {total_count}个")
        
        # 2. 查询有多少字段标记为is_mv_display=true
        safe_print("\n[2] 物化视图显示字段统计...")
        mv_display_sql = """
            SELECT COUNT(*) as mv_count
            FROM field_mapping_dictionary
            WHERE data_domain = 'inventory'
              AND active = true
              AND status = 'active'
              AND is_mv_display = true
        """
        mv_count = db.execute(text(mv_display_sql)).scalar()
        safe_print(f"标记为'物化视图需要显示内容'的字段数: {mv_count}个")
        safe_print(f"未标记的字段数: {total_count - mv_count}个")
        
        # 3. 列出所有字段及其is_mv_display状态
        safe_print("\n[3] 所有字段列表（按is_mv_display分组）...")
        
        # 标记为MV显示的字段
        mv_fields_sql = """
            SELECT field_code, cn_name, field_group, is_required
            FROM field_mapping_dictionary
            WHERE data_domain = 'inventory'
              AND active = true
              AND status = 'active'
              AND is_mv_display = true
            ORDER BY field_group, field_code
        """
        mv_fields_result = db.execute(text(mv_fields_sql)).fetchall()
        
        safe_print(f"\n[物化视图显示字段] ({len(mv_fields_result)}个):")
        safe_print("-" * 80)
        for row in mv_fields_result:
            field_code, cn_name, field_group, is_required = row
            required_mark = "[必填]" if is_required else ""
            safe_print(f"  ✓ {field_code:30} ({cn_name:20}) [{field_group:10}] {required_mark}")
        
        # 未标记为MV显示的字段
        non_mv_fields_sql = """
            SELECT field_code, cn_name, field_group, is_required
            FROM field_mapping_dictionary
            WHERE data_domain = 'inventory'
              AND active = true
              AND status = 'active'
              AND (is_mv_display = false OR is_mv_display IS NULL)
            ORDER BY field_group, field_code
        """
        non_mv_fields_result = db.execute(text(non_mv_fields_sql)).fetchall()
        
        safe_print(f"\n[未标记为物化视图显示] ({len(non_mv_fields_result)}个):")
        safe_print("-" * 80)
        if non_mv_fields_result:
            for row in non_mv_fields_result:
                field_code, cn_name, field_group, is_required = row
                required_mark = "[必填]" if is_required else ""
                safe_print(f"  ✗ {field_code:30} ({cn_name:20}) [{field_group:10}] {required_mark}")
        else:
            safe_print("  (无)")
        
        # 4. 检查物化视图实际包含的字段
        safe_print("\n[4] 物化视图实际字段...")
        mv_columns_sql = """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'mv_inventory_by_sku'
            ORDER BY ordinal_position
        """
        mv_columns_result = db.execute(text(mv_columns_sql)).fetchall()
        mv_columns = [row[0] for row in mv_columns_result]
        
        safe_print(f"mv_inventory_by_sku视图字段数: {len(mv_columns)}个")
        safe_print("字段列表:")
        for col in mv_columns:
            safe_print(f"  - {col}")
        
        # 5. 解释说明
        safe_print("\n" + "=" * 80)
        safe_print("说明")
        safe_print("=" * 80)
        safe_print(f"""
物化视图的设计原则：
1. 您总共映射了 {total_count} 个inventory域字段
2. 但只有 {mv_count} 个字段标记为"物化视图需要显示内容"（is_mv_display=true）
3. 物化视图只包含标记为显示的字段，以优化性能和聚焦核心数据

为什么这样设计？
- 性能优化：物化视图只包含核心字段，查询更快
- 数据聚焦：避免物化视图包含过多辅助字段
- 灵活配置：您可以在字段映射界面中随时调整哪些字段需要显示

如何添加更多字段到物化视图？
1. 在字段映射界面中，找到需要显示的字段
2. 将"物化视图需要显示内容"开关设置为"是"
3. 运行更新脚本重新生成物化视图

未标记的字段会丢失吗？
- 不会！未标记的字段仍然存储在 fact_product_metrics 表中
- 只是不在物化视图中显示，需要时可以直接查询原表
- 或者通过 attributes JSONB 列访问
        """)
        
        safe_print("\n" + "=" * 80)
        safe_print("检查完成！")
        safe_print("=" * 80)
        
    except Exception as e:
        safe_print(f"检查失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_inventory_field_mapping()

