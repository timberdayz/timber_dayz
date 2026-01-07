# -*- coding: utf-8 -*-
"""
字段映射统一性检查脚本
检查不同平台的字段映射是否统一映射到相同的标准字段
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from sqlalchemy import text
from collections import defaultdict

def safe_print(text_str):
    try:
        print(text_str)
    except UnicodeEncodeError:
        print(text_str.encode('gbk', errors='ignore').decode('gbk'))

def check_field_mapping_unification():
    """检查字段映射统一性"""
    safe_print("=" * 80)
    safe_print("字段映射统一性检查")
    safe_print("=" * 80)
    
    db = next(get_db())
    try:
        # 1. 检查各平台的字段映射模板
        safe_print("\n[1] 检查各平台的字段映射模板...")
        
        templates_sql = """
            SELECT 
                t.platform,
                t.data_domain,
                t.granularity,
                t.template_name,
                COUNT(DISTINCT ti.original_column) as original_fields,
                COUNT(DISTINCT ti.standard_field) as standard_fields
            FROM field_mapping_templates t
            LEFT JOIN field_mapping_template_items ti ON t.id = ti.template_id
            WHERE t.status = 'published'
            GROUP BY t.id, t.platform, t.data_domain, t.granularity, t.template_name
            ORDER BY t.platform, t.data_domain, t.granularity
        """
        templates_result = db.execute(text(templates_sql)).fetchall()
        
        if templates_result:
            safe_print(f"\n找到 {len(templates_result)} 个已发布的模板:")
            safe_print("-" * 80)
            for row in templates_result:
                platform, domain, granularity, name, orig_fields, std_fields = row
                safe_print(f"  - {platform}/{domain}/{granularity}: {name}")
                safe_print(f"    原始字段: {orig_fields}个, 标准字段: {std_fields}个")
        else:
            safe_print("\n[WARNING] 未找到已发布的模板")
        
        # 2. 检查各平台映射到标准字段的情况
        safe_print("\n[2] 检查各平台映射到标准字段的情况...")
        
        platform_mappings_sql = """
            SELECT 
                t.platform,
                t.data_domain,
                ti.original_column,
                ti.standard_field,
                COUNT(*) as usage_count
            FROM field_mapping_templates t
            JOIN field_mapping_template_items ti ON t.id = ti.template_id
            WHERE t.status = 'published'
            GROUP BY t.platform, t.data_domain, ti.original_column, ti.standard_field
            ORDER BY t.platform, t.data_domain, ti.standard_field, ti.original_column
        """
        platform_mappings_result = db.execute(text(platform_mappings_sql)).fetchall()
        
        if platform_mappings_result:
            # 按标准字段分组，查看不同平台的映射
            standard_field_map = defaultdict(lambda: defaultdict(list))
            
            for row in platform_mappings_result:
                platform, domain, orig_column, std_field, count = row
                key = f"{platform}/{domain}"
                standard_field_map[std_field][key].append({
                    'original': orig_column,
                    'count': count
                })
            
            safe_print(f"\n标准字段映射统计（共{len(standard_field_map)}个标准字段）:")
            safe_print("-" * 80)
            
            unified_fields = []
            inconsistent_fields = []
            
            for std_field, platform_mappings in sorted(standard_field_map.items()):
                platforms = list(platform_mappings.keys())
                if len(platforms) > 1:
                    # 多个平台都映射到这个标准字段
                    safe_print(f"\n标准字段: {std_field}")
                    safe_print(f"  映射平台数: {len(platforms)}")
                    for platform_key, mappings in platform_mappings.items():
                        orig_fields = [m['original'] for m in mappings]
                        safe_print(f"    - {platform_key}: {', '.join(orig_fields)}")
                    
                    # 检查是否统一
                    all_same = len(set(tuple(m['original'] for m in mappings) for mappings in platform_mappings.values())) == 1
                    if all_same:
                        unified_fields.append(std_field)
                        safe_print(f"    [OK] 所有平台的原始字段名相同，映射统一")
                    else:
                        inconsistent_fields.append(std_field)
                        safe_print(f"    [WARNING] 不同平台的原始字段名不同，但都映射到{std_field}（这是正常的）")
                else:
                    # 只有一个平台映射到这个标准字段
                    safe_print(f"\n标准字段: {std_field}")
                    safe_print(f"  映射平台: {platforms[0]}")
                    safe_print(f"    [INFO] 仅一个平台使用此字段")
            
            safe_print("\n" + "=" * 80)
            safe_print("统一性分析结果")
            safe_print("=" * 80)
            safe_print(f"""
统一映射字段数: {len(unified_fields)}
不一致但正常字段数: {len(inconsistent_fields)}

说明：
- 统一映射：所有平台使用相同的原始字段名映射到标准字段（理想情况）
- 不一致但正常：不同平台使用不同的原始字段名，但都映射到相同的标准字段（这是正常的，符合设计）
- 系统设计：不同平台的原始字段名可以不同，只要映射到相同的标准字段即可
            """)
        
        # 3. 检查字段映射字典的完整性
        safe_print("\n[3] 检查字段映射字典的完整性...")
        
        dictionary_sql = """
            SELECT 
                data_domain,
                COUNT(*) as total_fields,
                COUNT(CASE WHEN is_mv_display = true THEN 1 END) as mv_display_fields,
                COUNT(CASE WHEN is_required = true THEN 1 END) as required_fields
            FROM field_mapping_dictionary
            WHERE active = true AND status = 'active'
            GROUP BY data_domain
            ORDER BY data_domain
        """
        dict_result = db.execute(text(dictionary_sql)).fetchall()
        
        safe_print(f"\n字段映射字典统计（按数据域）:")
        safe_print("-" * 80)
        for row in dict_result:
            domain, total, mv_display, required = row
            safe_print(f"  - {domain}:")
            safe_print(f"    总字段数: {total}")
            safe_print(f"    MV显示字段: {mv_display}")
            safe_print(f"    必填字段: {required}")
        
        # 4. 检查是否有未映射的字段
        safe_print("\n[4] 检查字段映射覆盖率...")
        
        # 检查各平台模板的字段映射覆盖率
        coverage_sql = """
            SELECT 
                t.platform,
                t.data_domain,
                COUNT(DISTINCT ti.original_column) as mapped_fields,
                t.field_count as total_fields_in_template,
                CASE 
                    WHEN t.field_count > 0 THEN 
                        ROUND(COUNT(DISTINCT ti.original_column) * 100.0 / t.field_count, 2)
                    ELSE 0
                END as coverage_percent
            FROM field_mapping_templates t
            LEFT JOIN field_mapping_template_items ti ON t.id = ti.template_id
            WHERE t.status = 'published'
            GROUP BY t.id, t.platform, t.data_domain, t.field_count
            ORDER BY t.platform, t.data_domain
        """
        coverage_result = db.execute(text(coverage_sql)).fetchall()
        
        if coverage_result:
            safe_print(f"\n字段映射覆盖率:")
            safe_print("-" * 80)
            for row in coverage_result:
                platform, domain, mapped, total, coverage = row
                safe_print(f"  - {platform}/{domain}: {mapped}/{total} ({coverage}%)")
        
        safe_print("\n" + "=" * 80)
        safe_print("检查完成！")
        safe_print("=" * 80)
        
        # 5. 提供统一管理建议
        safe_print("\n" + "=" * 80)
        safe_print("统一管理建议")
        safe_print("=" * 80)
        safe_print("""
1. 使用字段映射模板系统
   - 为每个平台/数据域/粒度组合创建模板
   - 模板保存标准字段映射关系
   - 同类文件可以一键套用模板

2. 使用字段映射字典
   - 统一的标准字段定义（field_mapping_dictionary表）
   - 每个标准字段有唯一field_code
   - 支持同义词和平台特定同义词

3. 统一管理流程
   a) 入库时：不同平台的原始字段 → 统一的标准字段
   b) 存储时：所有数据存储在相同的fact表（使用标准字段）
   c) 查询时：前端查询物化视图（使用标准字段）
   d) 展示时：统一的数据格式和字段名

4. 最佳实践
   - ✅ 入库时：不同平台的原始字段 → 统一的标准字段
   - ✅ 存储时：所有数据存储在相同的fact表（使用标准字段）
   - ✅ 查询时：前端查询物化视图（使用标准字段）
   - ✅ 展示时：统一的数据格式和字段名

5. 当前系统的优势
   - ✅ 字段映射模板：支持平台/数据域/粒度维度的模板
   - ✅ 字段映射字典：统一的标准字段定义
   - ✅ 智能映射建议：自动识别字段并建议映射
   - ✅ 物化视图配置：通过is_mv_display字段控制显示
        """)
        
    except Exception as e:
        safe_print(f"检查失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_field_mapping_unification()

