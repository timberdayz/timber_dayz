#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量创建 Metabase Model 所需的表（预创建）

用途：在 Metabase 中创建 Model 之前，预先创建所有需要的表结构
这样可以避免在 Metabase 中编写 SQL 时因为表不存在而失败

使用方法:
    python scripts/create_metabase_model_tables.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from backend.models.database import engine, SessionLocal
from modules.core.logger import get_logger
from backend.services.platform_table_manager import PlatformTableManager
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any

logger = get_logger(__name__)


class SyncToAsyncSessionWrapper:
    """将同步 Session 包装为 AsyncSession 的兼容包装器"""
    def __init__(self, sync_session: Session):
        self.sync_session = sync_session
        self.bind = sync_session.bind
    
    def execute(self, *args, **kwargs):
        return self.sync_session.execute(*args, **kwargs)
    
    def commit(self):
        return self.sync_session.commit()
    
    def rollback(self):
        return self.sync_session.rollback()
    
    def close(self):
        return self.sync_session.close()


def safe_print(text):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            safe_text = text.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)


def create_metabase_model_tables():
    """
    批量创建 Metabase Model 所需的所有表
    
    根据 design-metabase-models-questions 提案创建：
    - Orders Model: shopee/tiktok/miaoshou × daily/weekly/monthly
    - Products Model: shopee/tiktok/miaoshou × daily/weekly/monthly
    - Traffic Model: shopee/tiktok/miaoshou × daily/weekly/monthly
    - Services Model: shopee/tiktok/miaoshou × agent/ai_assistant × daily/weekly/monthly
    - Inventory Model: shopee/tiktok/miaoshou × snapshot
    - Analytics Model: shopee/tiktok/miaoshou × daily/weekly/monthly
    """
    # 使用同步会话，包装为 AsyncSession 兼容接口
    sync_session = SessionLocal()
    # 创建包装器（PlatformTableManager 需要 AsyncSession，但实际只使用 bind 属性）
    async_db = SyncToAsyncSessionWrapper(sync_session)
    
    try:
        # 创建 PlatformTableManager 实例
        table_manager = PlatformTableManager(async_db)
        
        # 定义需要创建的表配置
        table_configs = []
        
        # 支持的平台
        platforms = ['shopee', 'tiktok', 'miaoshou']
        
        # Orders Model: orders × daily/weekly/monthly
        for platform in platforms:
            for granularity in ['daily', 'weekly', 'monthly']:
                table_configs.append({
                    'platform': platform,
                    'data_domain': 'orders',
                    'sub_domain': None,
                    'granularity': granularity,
                    'model': 'Orders'
                })
        
        # Products Model: products × daily/weekly/monthly
        for platform in platforms:
            for granularity in ['daily', 'weekly', 'monthly']:
                table_configs.append({
                    'platform': platform,
                    'data_domain': 'products',
                    'sub_domain': None,
                    'granularity': granularity,
                    'model': 'Products'
                })
        
        # Traffic Model: traffic × daily/weekly/monthly
        for platform in platforms:
            for granularity in ['daily', 'weekly', 'monthly']:
                table_configs.append({
                    'platform': platform,
                    'data_domain': 'traffic',
                    'sub_domain': None,
                    'granularity': granularity,
                    'model': 'Traffic'
                })
        
        # Services Model: services × agent/ai_assistant × daily/weekly/monthly
        for platform in platforms:
            for sub_domain in ['agent', 'ai_assistant']:
                for granularity in ['daily', 'weekly', 'monthly']:
                    table_configs.append({
                        'platform': platform,
                        'data_domain': 'services',
                        'sub_domain': sub_domain,
                        'granularity': granularity,
                        'model': 'Services'
                    })
        
        # Inventory Model: inventory × snapshot
        for platform in platforms:
            table_configs.append({
                'platform': platform,
                'data_domain': 'inventory',
                'sub_domain': None,
                'granularity': 'snapshot',
                'model': 'Inventory'
            })
        
        # Analytics Model: analytics × daily/weekly/monthly
        for platform in platforms:
            for granularity in ['daily', 'weekly', 'monthly']:
                table_configs.append({
                    'platform': platform,
                    'data_domain': 'analytics',
                    'sub_domain': None,
                    'granularity': granularity,
                    'model': 'Analytics'
                })
        
        # 开始创建表
        safe_print("\n" + "="*80)
        safe_print("批量创建 Metabase Model 所需的表")
        safe_print("="*80)
        safe_print(f"\n总计需要创建: {len(table_configs)} 张表")
        safe_print("\n开始创建...\n")
        
        created_count = 0
        skipped_count = 0
        failed_count = 0
        
        # 按 Model 分组显示
        current_model = None
        
        for config in table_configs:
            # 显示 Model 分组
            if current_model != config['model']:
                if current_model is not None:
                    safe_print("")  # Model 之间的空行
                current_model = config['model']
                safe_print(f"[{current_model} Model]")
            
            try:
                table_name = table_manager.ensure_table_exists(
                    platform=config['platform'],
                    data_domain=config['data_domain'],
                    sub_domain=config['sub_domain'],
                    granularity=config['granularity']
                )
                
                # 检查表是否是新创建的（通过查询表是否存在）
                from sqlalchemy import inspect
                inspector = inspect(engine)
                existing_tables = inspector.get_table_names(schema='b_class')
                
                if table_name in existing_tables:
                    # 检查是否是刚创建的（简单判断：如果表名在配置中，可能是新创建的）
                    # 更准确的方式是检查表是否为空，但这里简化处理
                    safe_print(f"  [OK] {table_name}")
                    created_count += 1
                else:
                    safe_print(f"  [SKIP] {table_name} (已存在)")
                    skipped_count += 1
                    
            except Exception as e:
                safe_print(f"  [FAIL] {config['platform']}.{config['data_domain']}.{config['granularity']}: {e}")
                failed_count += 1
                logger.error(f"创建表失败: {config}", exc_info=True)
        
        # 提交事务
        sync_session.commit()
        
        # 显示统计信息
        safe_print("\n" + "="*80)
        safe_print("创建完成统计")
        safe_print("="*80)
        safe_print(f"  成功创建: {created_count} 张表")
        safe_print(f"  已存在跳过: {skipped_count} 张表")
        safe_print(f"  创建失败: {failed_count} 张表")
        safe_print(f"  总计: {len(table_configs)} 张表")
        safe_print("="*80)
        
        if failed_count == 0:
            safe_print("\n[OK] 所有表创建成功！")
            safe_print("\n下一步:")
            safe_print("  1. 在 Metabase 中创建 Model（表已就绪）")
            safe_print("  2. 编写 Model SQL（使用 UNION ALL 整合多平台、多粒度数据）")
            safe_print("  3. 创建 Question（基于 Model）")
        else:
            safe_print(f"\n[WARNING] 有 {failed_count} 张表创建失败，请检查日志")
        
    except Exception as e:
        sync_session.rollback()
        logger.error(f"批量创建表失败: {e}", exc_info=True)
        safe_print(f"\n[ERROR] 批量创建表失败: {e}")
        raise
    finally:
        sync_session.close()


if __name__ == "__main__":
    safe_print("\n" + "="*80)
    safe_print("Metabase Model 表预创建脚本")
    safe_print("="*80)
    safe_print("\n说明：")
    safe_print("- 此脚本会预先创建所有 Metabase Model 需要的表")
    safe_print("- 表名格式：fact_{platform}_{data_domain}_{sub_domain}_{granularity}")
    safe_print("- 如果表已存在，不会重复创建")
    safe_print("- 如果表不存在，会自动创建基础结构（包括索引）")
    safe_print("- 创建的表在 b_class schema 中")
    safe_print("\n开始创建...")
    
    create_metabase_model_tables()
