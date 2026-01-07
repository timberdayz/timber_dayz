#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据迁移脚本：将traffic域统一迁移到analytics域（v4.15.0）
时间: 2025-12-05
版本: v4.15.0
说明: 批量更新catalog_files表、field_mapping_templates表和field_mapping_dictionary表
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from modules.core.db import CatalogFile, FieldMappingTemplate, FieldMappingDictionary
from modules.core.logger import get_logger
from sqlalchemy import text, select
import shutil

logger = get_logger(__name__)


def safe_print(text_str):
    """安全打印（Windows兼容）"""
    try:
        print(text_str)
    except UnicodeEncodeError:
        print(text_str.encode('gbk', errors='ignore').decode('gbk'))


def rename_file_name(old_name: str) -> str:
    """将文件名中的traffic替换为analytics"""
    new_name = old_name.replace('_traffic_', '_analytics_')
    new_name = new_name.replace('traffic_', 'analytics_')
    new_name = new_name.replace('_traffic.', '_analytics.')
    return new_name


def migrate_traffic_to_analytics():
    """将traffic域统一迁移到analytics域"""
    db = next(get_db())
    
    try:
        safe_print("\n" + "="*70)
        safe_print("Traffic域统一迁移到Analytics域（v4.15.0）")
        safe_print("="*70)
        
        # Step 1: 检查traffic域的文件记录
        safe_print("\n[Step 1] 检查traffic域的文件记录...")
        files_query = select(CatalogFile).where(
            CatalogFile.data_domain == 'traffic'
        )
        traffic_files = db.execute(files_query).scalars().all()
        safe_print(f"  找到 {len(traffic_files)} 个traffic域文件记录")
        
        # Step 2: 重命名文件并更新catalog_files表
        if len(traffic_files) > 0:
            safe_print("\n[Step 2] 重命名文件并更新catalog_files表...")
            renamed_count = 0
            failed_count = 0
            
            for file_record in traffic_files:
                try:
                    old_path = Path(file_record.file_path) if file_record.file_path else None
                    old_name = file_record.file_name
                    
                    # 生成新文件名
                    new_name = rename_file_name(old_name)
                    
                    # 如果文件存在，重命名文件
                    if old_path and old_path.exists():
                        new_path = old_path.parent / new_name
                        if old_path != new_path:
                            shutil.move(str(old_path), str(new_path))
                            safe_print(f"  [OK] 文件重命名: {old_name} -> {new_name}")
                        else:
                            safe_print(f"  [SKIP] 文件名无需修改: {old_name}")
                    else:
                        safe_print(f"  [WARN] 文件不存在，仅更新数据库: {old_name}")
                    
                    # 更新数据库记录
                    file_record.file_name = new_name
                    file_record.data_domain = 'analytics'
                    if old_path:
                        file_record.file_path = str(old_path.parent / new_name) if old_path.exists() else file_record.file_path
                    
                    renamed_count += 1
                    
                except Exception as e:
                    safe_print(f"  [FAIL] 处理失败 {file_record.file_name}: {e}")
                    failed_count += 1
                    db.rollback()
            
            db.commit()
            safe_print(f"  [OK] 成功处理 {renamed_count} 个文件，失败 {failed_count} 个")
        else:
            safe_print("  [INFO] 没有需要处理的文件记录")
        
        # Step 3: 批量更新catalog_files表（处理所有遗留记录）
        safe_print("\n[Step 3] 批量更新catalog_files表中的traffic域记录...")
        update_files_query = text("""
            UPDATE catalog_files
            SET data_domain = 'analytics',
                file_name = REPLACE(REPLACE(REPLACE(file_name, '_traffic_', '_analytics_'), 'traffic_', 'analytics_'), '_traffic.', '_analytics.'),
                file_path = REPLACE(REPLACE(REPLACE(file_path, '_traffic_', '_analytics_'), 'traffic_', 'analytics_'), '_traffic.', '_analytics.')
            WHERE data_domain = 'traffic'
        """)
        result = db.execute(update_files_query)
        updated_files_count = result.rowcount
        db.commit()
        safe_print(f"  [OK] 批量更新了 {updated_files_count} 条文件记录")
        
        # Step 4: 迁移字段映射模板
        safe_print("\n[Step 4] 迁移字段映射模板...")
        templates_query = select(FieldMappingTemplate).where(
            FieldMappingTemplate.data_domain == 'traffic'
        )
        traffic_templates = db.execute(templates_query).scalars().all()
        safe_print(f"  找到 {len(traffic_templates)} 个traffic域模板")
        
        migrated_templates = 0
        deleted_templates = 0
        for template in traffic_templates:
            try:
                # 检查是否已存在相同的analytics域模板（使用first()处理多个匹配的情况）
                existing_query = select(FieldMappingTemplate).where(
                    FieldMappingTemplate.platform == template.platform,
                    FieldMappingTemplate.data_domain == 'analytics',
                    FieldMappingTemplate.granularity == template.granularity,
                    FieldMappingTemplate.sub_domain == template.sub_domain
                )
                existing = db.execute(existing_query).scalars().first()
                
                if existing:
                    safe_print(f"  [SKIP] 模板已存在（analytics域）: {template.platform}/{template.granularity}/{template.sub_domain} (ID: {existing.id})")
                    # 删除traffic域模板（避免重复）
                    db.delete(template)
                    deleted_templates += 1
                else:
                    # 直接更新模板的data_domain
                    template.data_domain = 'analytics'
                    if template.template_name:
                        template.template_name = template.template_name.replace('traffic', 'analytics')
                    migrated_templates += 1
                    safe_print(f"  [OK] 迁移模板: {template.platform}/{template.granularity}/{template.sub_domain} (ID: {template.id})")
                
            except Exception as e:
                safe_print(f"  [FAIL] 迁移模板失败 {template.id}: {e}")
                db.rollback()
        
        db.commit()
        safe_print(f"  [OK] 成功迁移 {migrated_templates} 个模板，删除重复 {deleted_templates} 个")
        
        # Step 5: 更新字段映射辞典（如果有traffic域的字段）
        safe_print("\n[Step 5] 更新字段映射辞典...")
        dictionary_query = select(FieldMappingDictionary).where(
            FieldMappingDictionary.data_domain == 'traffic'
        )
        traffic_fields = db.execute(dictionary_query).scalars().all()
        safe_print(f"  找到 {len(traffic_fields)} 个traffic域字段")
        
        updated_fields = 0
        deleted_fields = 0
        for field in traffic_fields:
            try:
                # 检查是否已存在相同的analytics域字段
                existing_query = select(FieldMappingDictionary).where(
                    FieldMappingDictionary.field_code == field.field_code,
                    FieldMappingDictionary.data_domain == 'analytics'
                )
                existing = db.execute(existing_query).scalar_one_or_none()
                
                if existing:
                    safe_print(f"  [SKIP] 字段已存在（analytics域）: {field.field_code}")
                    # 删除traffic域字段（避免重复）
                    db.delete(field)
                    deleted_fields += 1
                else:
                    # 直接更新字段的data_domain
                    field.data_domain = 'analytics'
                    updated_fields += 1
                    safe_print(f"  [OK] 更新字段: {field.field_code}")
                
            except Exception as e:
                safe_print(f"  [FAIL] 更新字段失败 {field.id}: {e}")
                db.rollback()
        
        db.commit()
        safe_print(f"  [OK] 成功更新 {updated_fields} 个字段，删除重复 {deleted_fields} 个")
        
        # Step 6: 验证结果
        safe_print("\n[Step 6] 验证迁移结果...")
        
        # 检查是否还有traffic域的文件
        remaining_files = db.execute(select(CatalogFile).where(
            CatalogFile.data_domain == 'traffic'
        )).scalars().all()
        
        # 检查是否还有traffic域的模板
        remaining_templates = db.execute(select(FieldMappingTemplate).where(
            FieldMappingTemplate.data_domain == 'traffic'
        )).scalars().all()
        
        # 检查是否还有traffic域的字段
        remaining_fields = db.execute(select(FieldMappingDictionary).where(
            FieldMappingDictionary.data_domain == 'traffic'
        )).scalars().all()
        
        # 统计analytics域的数量
        analytics_files = db.execute(select(CatalogFile).where(
            CatalogFile.data_domain == 'analytics'
        )).scalars().all()
        
        analytics_templates = db.execute(select(FieldMappingTemplate).where(
            FieldMappingTemplate.data_domain == 'analytics'
        )).scalars().all()
        
        safe_print(f"  剩余traffic域文件: {len(remaining_files)} 个")
        safe_print(f"  剩余traffic域模板: {len(remaining_templates)} 个")
        safe_print(f"  剩余traffic域字段: {len(remaining_fields)} 个")
        safe_print(f"  analytics域文件: {len(analytics_files)} 个")
        safe_print(f"  analytics域模板: {len(analytics_templates)} 个")
        
        # 总结
        safe_print("\n" + "="*70)
        safe_print("[SUCCESS] Traffic域迁移完成！")
        safe_print("="*70)
        safe_print(f"  文件记录更新: {updated_files_count} 条")
        safe_print(f"  模板迁移: {migrated_templates} 个（删除重复 {deleted_templates} 个）")
        safe_print(f"  字段更新: {updated_fields} 个（删除重复 {deleted_fields} 个）")
        safe_print(f"  analytics域文件总数: {len(analytics_files)} 个")
        safe_print(f"  analytics域模板总数: {len(analytics_templates)} 个")
        
        if len(remaining_files) > 0 or len(remaining_templates) > 0 or len(remaining_fields) > 0:
            safe_print("\n  [WARN] 仍有遗留的traffic域记录，请手动检查")
        
        return {
            "success": True,
            "updated_files": updated_files_count,
            "migrated_templates": migrated_templates,
            "deleted_templates": deleted_templates,
            "updated_fields": updated_fields,
            "deleted_fields": deleted_fields,
            "remaining_files": len(remaining_files),
            "remaining_templates": len(remaining_templates),
            "remaining_fields": len(remaining_fields)
        }
        
    except Exception as e:
        db.rollback()
        safe_print(f"\n[ERROR] 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate_traffic_to_analytics()

