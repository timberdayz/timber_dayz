#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模板数据迁移脚本
将本地数据库中的模板数据迁移到容器数据库
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text
from modules.core.db import FieldMappingTemplate, FieldMappingTemplateItem
from modules.core.logger import get_logger
from datetime import datetime

logger = get_logger(__name__)

async def migrate_templates(
    source_db_url: str,
    target_db_url: str,
    dry_run: bool = False
):
    """迁移模板数据"""
    source_engine = create_async_engine(source_db_url, echo=False)
    source_session = sessionmaker(source_engine, class_=AsyncSession, expire_on_commit=False)
    
    target_engine = create_async_engine(target_db_url, echo=False)
    target_session = sessionmaker(target_engine, class_=AsyncSession, expire_on_commit=False)
    
    try:
        async with source_session() as source_db:
            # 从源数据库读取所有模板
            result = await source_db.execute(
                select(FieldMappingTemplate)
            )
            templates = result.scalars().all()
            
            logger.info(f"[迁移] 源数据库中找到 {len(templates)} 个模板")
            
            if not templates:
                logger.warning("[迁移] 源数据库中没有模板数据，无需迁移")
                return 0
            
            if dry_run:
                logger.info("[DRY-RUN] 模拟模式，不会实际修改目标数据库")
            
            async with target_session() as target_db:
                migrated_count = 0
                skipped_count = 0
                error_count = 0
                
                for template in templates:
                    try:
                        # 检查目标数据库是否已存在该模板
                        result = await target_db.execute(
                            select(FieldMappingTemplate).where(
                                FieldMappingTemplate.template_name == template.template_name,
                                FieldMappingTemplate.platform == template.platform,
                                FieldMappingTemplate.data_domain == template.data_domain,
                                FieldMappingTemplate.granularity == template.granularity,
                                FieldMappingTemplate.version == template.version
                            )
                        )
                        existing = result.scalar_one_or_none()
                        
                        if existing:
                            logger.info(f"[跳过] 模板已存在: {template.template_name} (v{template.version})")
                            skipped_count += 1
                            continue
                        
                        # 创建新模板对象
                        new_template = FieldMappingTemplate(
                            platform=template.platform,
                            data_domain=template.data_domain,
                            granularity=template.granularity,
                            account=template.account,
                            sub_domain=template.sub_domain,
                            header_row=template.header_row,
                            sheet_name=template.sheet_name,
                            encoding=template.encoding,
                            header_columns=template.header_columns,
                            deduplication_fields=template.deduplication_fields,
                            template_name=template.template_name,
                            version=template.version,
                            status=template.status,
                            field_count=template.field_count,
                            usage_count=template.usage_count,
                            success_rate=template.success_rate,
                            created_by=template.created_by,
                            notes=template.notes,
                            created_at=template.created_at or datetime.utcnow(),
                            updated_at=template.updated_at or datetime.utcnow()
                        )
                        
                        if not dry_run:
                            target_db.add(new_template)
                            await target_db.flush()  # 获取新模板的ID
                            
                            # 迁移模板项
                            items_result = await source_db.execute(
                                select(FieldMappingTemplateItem).where(
                                    FieldMappingTemplateItem.template_id == template.id
                                )
                            )
                            items = items_result.scalars().all()
                            
                            for item in items:
                                new_item = FieldMappingTemplateItem(
                                    template_id=new_template.id,
                                    original_field=item.original_field,
                                    standard_field=item.standard_field,
                                    confidence=item.confidence,
                                    mapping_rule=item.mapping_rule,
                                    created_at=item.created_at or datetime.utcnow(),
                                    updated_at=item.updated_at or datetime.utcnow()
                                )
                                target_db.add(new_item)
                            
                            await target_db.commit()
                        
                        logger.info(f"[{'DRY-RUN: ' if dry_run else ''}迁移成功] {template.template_name} (v{template.version})")
                        migrated_count += 1
                        
                    except Exception as e:
                        await target_db.rollback()
                        logger.error(f"[错误] 迁移模板失败 {template.template_name}: {e}", exc_info=True)
                        error_count += 1
                
                logger.info("\n" + "="*80)
                logger.info("迁移完成")
                logger.info("="*80)
                logger.info(f"成功迁移: {migrated_count} 个模板")
                logger.info(f"跳过（已存在）: {skipped_count} 个模板")
                logger.info(f"失败: {error_count} 个模板")
                
                return migrated_count
                
    except Exception as e:
        logger.error(f"[错误] 迁移过程失败: {e}", exc_info=True)
        raise
    finally:
        await source_engine.dispose()
        await target_engine.dispose()

async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="迁移模板数据到容器数据库")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="模拟模式，不实际修改数据库"
    )
    parser.add_argument(
        "--source-url",
        type=str,
        default=None,
        help="源数据库URL（默认: 本地数据库）"
    )
    parser.add_argument(
        "--target-url",
        type=str,
        default=None,
        help="目标数据库URL（默认: 容器数据库）"
    )
    
    args = parser.parse_args()
    
    print("\n" + "="*80)
    print("模板数据迁移脚本")
    print("="*80 + "\n")
    
    # 数据库配置
    source_db_url = args.source_url or os.getenv(
        "LOCAL_DATABASE_URL",
        "postgresql+asyncpg://erp_user:erp_pass_2025@localhost:5432/xihong_erp"
    )
    
    target_db_url = args.target_url or os.getenv(
        "CONTAINER_DATABASE_URL",
        "postgresql+asyncpg://erp_dev:dev_pass_2025@localhost:15432/xihong_erp_dev"
    )
    
    if args.dry_run:
        print("[模式] DRY-RUN（模拟模式，不会实际修改数据库）\n")
    
    print(f"源数据库: {source_db_url.split('@')[1] if '@' in source_db_url else source_db_url}")
    print(f"目标数据库: {target_db_url.split('@')[1] if '@' in target_db_url else target_db_url}")
    
    if not args.dry_run:
        confirm = input("\n确认开始迁移？(yes/no): ").strip().lower()
        if confirm != 'yes':
            print("[取消] 用户取消迁移")
            return
    
    try:
        count = await migrate_templates(source_db_url, target_db_url, dry_run=args.dry_run)
        if not args.dry_run:
            print(f"\n[成功] 已迁移 {count} 个模板到容器数据库")
    except Exception as e:
        print(f"\n[错误] 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n[INFO] 操作被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

