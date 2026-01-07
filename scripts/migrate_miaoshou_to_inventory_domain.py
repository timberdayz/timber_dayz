#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据迁移脚本：将miaoshou的products域数据迁移到inventory域
时间: 2025-11-05
版本: v4.10.0
说明: 批量更新catalog_files表和field_mapping_template表
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from modules.core.db import CatalogFile, FieldMappingTemplate
from modules.core.logger import get_logger
from sqlalchemy import text

logger = get_logger(__name__)


def migrate_miaoshou_to_inventory_domain():
    """迁移miaoshou的products域到inventory域"""
    db = next(get_db())
    
    try:
        logger.info("=" * 70)
        logger.info("开始迁移miaoshou的products域到inventory域")
        logger.info("=" * 70)
        
        # Step 1: 更新catalog_files表
        logger.info("\n[Step 1] 更新catalog_files表...")
        update_query = text("""
            UPDATE catalog_files
            SET data_domain = 'inventory'
            WHERE platform_code = 'miaoshou'
              AND data_domain = 'products'
              AND (granularity = 'snapshot' OR file_name LIKE '%库存%' OR file_name LIKE '%inventory%')
        """)
        result = db.execute(update_query)
        updated_files = result.rowcount
        db.commit()
        logger.info(f"  [OK] 更新了{updated_files}个文件记录")
        
        # Step 2: 迁移字段映射模板
        logger.info("\n[Step 2] 迁移字段映射模板...")
        template_query = text("""
            SELECT id, template_name, platform_code, data_domain
            FROM field_mapping_template
            WHERE platform_code = 'miaoshou'
              AND data_domain = 'products'
        """)
        templates = db.execute(template_query).fetchall()
        
        migrated_templates = 0
        for template in templates:
            template_id, template_name, platform_code, data_domain = template
            
            # 复制模板并更新data_domain
            copy_query = text("""
                INSERT INTO field_mapping_template (
                    template_name, platform_code, data_domain, granularity,
                    created_at, updated_at
                )
                SELECT 
                    template_name || '_inventory' as template_name,
                    platform_code,
                    'inventory' as data_domain,
                    granularity,
                    NOW() as created_at,
                    NOW() as updated_at
                FROM field_mapping_template
                WHERE id = :template_id
                ON CONFLICT DO NOTHING
            """)
            db.execute(copy_query, {"template_id": template_id})
            
            # 复制模板项
            copy_items_query = text("""
                INSERT INTO field_mapping_template_item (
                    template_id, original_field, standard_field, 
                    data_type, is_required, display_order
                )
                SELECT 
                    (SELECT id FROM field_mapping_template 
                     WHERE template_name = :new_template_name 
                     AND platform_code = 'miaoshou' 
                     AND data_domain = 'inventory' LIMIT 1) as template_id,
                    original_field,
                    standard_field,
                    data_type,
                    is_required,
                    display_order
                FROM field_mapping_template_item
                WHERE template_id = :old_template_id
            """)
            new_template_name = f"{template_name}_inventory"
            db.execute(copy_items_query, {
                "new_template_name": new_template_name,
                "old_template_id": template_id
            })
            
            migrated_templates += 1
        
        db.commit()
        logger.info(f"  [OK] 迁移了{migrated_templates}个模板")
        
        # Step 3: 更新fact_product_metrics表中现有数据的data_domain
        logger.info("\n[Step 3] 更新fact_product_metrics表中现有数据...")
        # 注意：这里需要谨慎，只更新miaoshou平台且granularity='snapshot'的数据
        update_metrics_query = text("""
            UPDATE fact_product_metrics
            SET data_domain = 'inventory'
            WHERE platform_code = 'miaoshou'
              AND COALESCE(data_domain, 'products') = 'products'
              AND granularity = 'snapshot'
        """)
        result = db.execute(update_metrics_query)
        updated_metrics = result.rowcount
        db.commit()
        logger.info(f"  [OK] 更新了{updated_metrics}条产品指标记录")
        
        logger.info("=" * 70)
        logger.info("迁移完成！")
        logger.info(f"  - 文件记录: {updated_files}个")
        logger.info(f"  - 模板: {migrated_templates}个")
        logger.info(f"  - 产品指标记录: {updated_metrics}条")
        logger.info("=" * 70)
        
        return {
            "success": True,
            "updated_files": updated_files,
            "migrated_templates": migrated_templates,
            "updated_metrics": updated_metrics
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"迁移失败: {e}", exc_info=True)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate_miaoshou_to_inventory_domain()

