#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查模板数据脚本
用于诊断本地数据库和容器数据库中的模板数据情况
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

logger = get_logger(__name__)

async def check_database(database_url: str, name: str):
    """检查数据库中的模板数据"""
    try:
        engine = create_async_engine(database_url, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with async_session() as db:
            # 检查数据库连接
            result = await db.execute(text("SELECT current_database(), current_user"))
            db_info = result.fetchone()
            logger.info(f"[{name}] 数据库: {db_info[0]}, 用户: {db_info[1]}")
            
            # 检查模板表
            result = await db.execute(
                select(FieldMappingTemplate)
            )
            templates = result.scalars().all()
            
            logger.info(f"[{name}] 模板总数: {len(templates)}")
            
            if templates:
                # 统计已发布模板
                published = [t for t in templates if t.status == 'published']
                logger.info(f"[{name}] 已发布模板: {len(published)}")
                
                # 显示前5个模板
                logger.info(f"[{name}] 前5个模板:")
                for i, t in enumerate(templates[:5], 1):
                    logger.info(f"  {i}. {t.template_name} (平台: {t.platform}, 数据域: {t.data_domain}, 状态: {t.status})")
                
                # 检查模板项
                result = await db.execute(
                    select(FieldMappingTemplateItem)
                )
                items = result.scalars().all()
                logger.info(f"[{name}] 模板项总数: {len(items)}")
            else:
                logger.warning(f"[{name}] 未找到任何模板数据")
            
            return {
                "database": db_info[0],
                "user": db_info[1],
                "template_count": len(templates),
                "published_count": len([t for t in templates if t.status == 'published']),
                "templates": templates
            }
    except Exception as e:
        logger.error(f"[{name}] 检查失败: {e}", exc_info=True)
        return None
    finally:
        await engine.dispose()

async def main():
    """主函数"""
    print("\n" + "="*80)
    print("模板数据检查脚本")
    print("="*80 + "\n")
    
    # 本地数据库配置（从环境变量或默认值）
    local_db_url = os.getenv(
        "LOCAL_DATABASE_URL",
        "postgresql+asyncpg://erp_user:erp_pass_2025@localhost:5432/xihong_erp"
    )
    
    # 容器数据库配置
    container_db_url = os.getenv(
        "CONTAINER_DATABASE_URL",
        "postgresql+asyncpg://erp_dev:dev_pass_2025@localhost:15432/xihong_erp_dev"
    )
    
    print("检查本地数据库...")
    local_data = await check_database(local_db_url, "本地数据库")
    
    print("\n检查容器数据库...")
    container_data = await check_database(container_db_url, "容器数据库")
    
    print("\n" + "="*80)
    print("检查结果总结")
    print("="*80)
    
    if local_data:
        print(f"\n本地数据库 ({local_data['database']}):")
        print(f"  - 模板总数: {local_data['template_count']}")
        print(f"  - 已发布模板: {local_data['published_count']}")
    
    if container_data:
        print(f"\n容器数据库 ({container_data['database']}):")
        print(f"  - 模板总数: {container_data['template_count']}")
        print(f"  - 已发布模板: {container_data['published_count']}")
    
    if local_data and container_data:
        if local_data['template_count'] > 0 and container_data['template_count'] == 0:
            print("\n[诊断] 本地数据库有模板数据，但容器数据库为空")
            print("[建议] 需要将本地模板数据迁移到容器数据库")
            print("\n迁移步骤:")
            print("  1. 运行迁移脚本: python scripts/migrate_templates_to_container.py")
            print("  2. 或者手动导出导入: 使用 pg_dump 和 psql 命令")
        elif local_data['template_count'] == 0 and container_data['template_count'] == 0:
            print("\n[诊断] 两个数据库都没有模板数据")
            print("[建议] 需要在系统中创建模板")
        elif local_data['template_count'] > 0 and container_data['template_count'] > 0:
            print("\n[诊断] 两个数据库都有模板数据")
            if local_data['template_count'] != container_data['template_count']:
                print(f"[提示] 模板数量不一致（本地: {local_data['template_count']}, 容器: {container_data['template_count']}）")
    
    print("\n" + "="*80 + "\n")

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

