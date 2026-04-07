#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查所有 schema 中的旧表（fact_raw_data_*）

检查所有 schema（public, b_class, a_class, c_class, core, finance）
中是否存在旧的 fact_raw_data_* 表
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from sqlalchemy import text, inspect
from modules.core.logger import get_logger

logger = get_logger(__name__)

def check_all_schemas():
    """检查所有 schema 中的旧表"""
    db = next(get_db())
    inspector = inspect(db.bind)
    
    schemas = ['public', 'b_class', 'a_class', 'c_class', 'core', 'finance']
    old_tables_found = []
    
    logger.info("=" * 70)
    logger.info("检查所有 schema 中的旧表（fact_raw_data_*）")
    logger.info("=" * 70)
    
    for schema in schemas:
        try:
            tables = inspector.get_table_names(schema=schema)
            old_tables = [t for t in tables if t.startswith('fact_raw_data_')]
            
            if old_tables:
                logger.warning(f"\n[{schema}] schema 中发现 {len(old_tables)} 个旧表:")
                for table in sorted(old_tables):
                    try:
                        count = db.execute(
                            text(f'SELECT COUNT(*) FROM {schema}."{table}"')
                        ).scalar() or 0
                        logger.warning(f"  - {table}: {count} 行")
                        old_tables_found.append((schema, table))
                    except Exception as e:
                        logger.warning(f"  - {table}: 查询失败 ({e})")
                        old_tables_found.append((schema, table))
            else:
                logger.info(f"[{schema}] schema: 没有旧表")
        except Exception as e:
            logger.warning(f"[{schema}] schema 检查失败: {e}")
    
    if old_tables_found:
        logger.warning("\n" + "=" * 70)
        logger.warning(f"⚠️ 总共发现 {len(old_tables_found)} 个旧表！")
        logger.warning("这些表可能是 Metabase 显示旧表名的原因")
        logger.warning("=" * 70)
        logger.warning("\n旧表列表:")
        for schema, table in old_tables_found:
            logger.warning(f"  - {schema}.{table}")
        return old_tables_found
    else:
        logger.info("\n" + "=" * 70)
        logger.info("✅ 所有 schema 中都没有旧表")
        logger.info("=" * 70)
        return []
    
    db.close()

if __name__ == "__main__":
    try:
        old_tables = check_all_schemas()
        if old_tables:
            logger.warning("\n" + "=" * 70)
            logger.warning("下一步：运行删除脚本")
            logger.warning("python scripts/delete_old_fact_raw_data_tables.py")
            logger.warning("=" * 70)
    except Exception as e:
        logger.error(f"检查失败: {e}", exc_info=True)
        sys.exit(1)

