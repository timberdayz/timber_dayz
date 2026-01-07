#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查 b_class schema 中的所有表

用于诊断 Metabase 显示旧数据的问题
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from sqlalchemy import text, inspect
from modules.core.logger import get_logger

logger = get_logger(__name__)


def check_b_class_tables():
    """检查 b_class schema 中的所有表"""
    db = next(get_db())
    inspector = inspect(db.bind)
    
    try:
        # 获取所有表
        tables = inspector.get_table_names(schema='b_class')
        
        logger.info("=" * 70)
        logger.info(f"b_class schema 中的表（共 {len(tables)} 个）")
        logger.info("=" * 70)
        
        # 按类型分组
        fact_tables = [t for t in tables if t.startswith('fact_')]
        other_tables = [t for t in tables if not t.startswith('fact_')]
        
        logger.info(f"\n[fact_ 开头的表] {len(fact_tables)} 个（B类数据表）")
        logger.info("-" * 70)
        
        # 按平台分组显示
        platforms = {}
        for table in sorted(fact_tables):
            # 解析表名：fact_{platform}_{domain}_{granularity}
            parts = table.replace('fact_', '').split('_')
            if len(parts) >= 2:
                platform = parts[0]
                if platform not in platforms:
                    platforms[platform] = []
                platforms[platform].append(table)
            else:
                if 'unknown' not in platforms:
                    platforms['unknown'] = []
                platforms['unknown'].append(table)
        
        for platform in sorted(platforms.keys()):
            platform_tables = platforms[platform]
            logger.info(f"\n[{platform.upper()}] {len(platform_tables)} 个表:")
            for table in sorted(platform_tables):
                try:
                    count = db.execute(
                        text(f'SELECT COUNT(*) FROM b_class."{table}"')
                    ).scalar() or 0
                    logger.info(f"  - {table}: {count} 行")
                except Exception as e:
                    logger.warning(f"  - {table}: 查询失败 ({e})")
        
        if other_tables:
            logger.info(f"\n[其他表] {len(other_tables)} 个")
            logger.info("-" * 70)
            for table in sorted(other_tables):
                try:
                    count = db.execute(
                        text(f'SELECT COUNT(*) FROM b_class."{table}"')
                    ).scalar() or 0
                    logger.info(f"  - {table}: {count} 行")
                except Exception as e:
                    logger.warning(f"  - {table}: 查询失败 ({e})")
        
        # 检查是否有旧的表名（fact_raw_data_*）
        old_tables = [t for t in tables if t.startswith('fact_raw_data_')]
        if old_tables:
            logger.warning("\n" + "=" * 70)
            logger.warning("⚠️ 发现旧的表名（fact_raw_data_*）")
            logger.warning("=" * 70)
            for table in sorted(old_tables):
                logger.warning(f"  - {table}")
            logger.warning("\n这些表应该已经迁移到按平台分表的架构（fact_{platform}_*）")
        else:
            logger.info("\n" + "=" * 70)
            logger.info("✅ 没有发现旧的表名（fact_raw_data_*）")
            logger.info("数据库已更新到按平台分表架构（v4.17.0+）")
            logger.info("=" * 70)
        
        logger.info("\n" + "=" * 70)
        logger.info("Metabase 同步建议")
        logger.info("=" * 70)
        logger.info("\n1. 登录 Metabase: http://localhost:8080")
        logger.info("2. Admin → Databases → XIHONG_ERP")
        logger.info("3. 点击 'Sync database schema now' 按钮")
        logger.info("4. 等待同步完成（30-60秒）")
        logger.info("5. 验证 b_class schema 中应该看到上述表")
        logger.info("\n如果还是显示旧表，请检查:")
        logger.info("- Schema filters 是否包含 b_class")
        logger.info("- 是否选择了 '全部' / 'All schemas'")
        logger.info("- 可能需要清除 Metabase 缓存或重启 Metabase 容器")
        
    except Exception as e:
        logger.error(f"检查失败: {e}", exc_info=True)
    finally:
        db.close()


if __name__ == "__main__":
    check_b_class_tables()

