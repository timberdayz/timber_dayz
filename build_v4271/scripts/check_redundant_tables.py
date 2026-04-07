#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查冗余表的使用情况（v4.11.2）

检查以下表：
1. data_files - 是否与catalog_files功能重复
2. fact_sales_orders - 是否与fact_orders功能重复
3. field_mappings_deprecated - 确认废弃状态
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import engine, SessionLocal
from sqlalchemy import text, inspect
from modules.core.logger import get_logger
import re

logger = get_logger(__name__)


def check_table_exists(db, table_name):
    """检查表是否存在"""
    result = db.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = :table_name
        )
    """), {"table_name": table_name})
    return result.scalar()


def get_table_info(db, table_name):
    """获取表信息"""
    if not check_table_exists(db, table_name):
        return None
    
    # 获取表结构
    result = db.execute(text("""
        SELECT 
            column_name,
            data_type,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = :table_name
        ORDER BY ordinal_position
    """), {"table_name": table_name})
    
    columns = []
    for row in result:
        columns.append({
            'name': row[0],
            'type': row[1],
            'nullable': row[2],
            'default': row[3]
        })
    
    # 获取行数
    result = db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
    row_count = result.scalar()
    
    # 获取表大小
    result = db.execute(text("""
        SELECT pg_size_pretty(pg_total_relation_size(:table_name))
    """), {"table_name": table_name})
    size = result.scalar()
    
    return {
        'columns': columns,
        'row_count': row_count,
        'size': size
    }


def search_code_references(table_name):
    """搜索代码中的引用"""
    references = []
    
    # 搜索Python文件
    codebase_path = Path(__file__).parent.parent
    patterns = [
        f"**/*.py",
        f"**/*.js",
        f"**/*.vue",
        f"**/*.sql"
    ]
    
    for pattern in patterns:
        for file_path in codebase_path.glob(pattern):
            if 'node_modules' in str(file_path) or '__pycache__' in str(file_path):
                continue
            
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                if table_name in content:
                    # 查找引用行
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        if table_name in line:
                            references.append({
                                'file': str(file_path.relative_to(codebase_path)),
                                'line': i,
                                'content': line.strip()[:100]
                            })
            except Exception:
                continue
    
    return references


def check_data_files_table(db):
    """检查data_files表"""
    logger.info("=" * 70)
    logger.info("检查 data_files 表")
    logger.info("=" * 70)
    
    table_name = 'data_files'
    
    if not check_table_exists(db, table_name):
        logger.info(f"[INFO] {table_name} 表不存在")
        return
    
    info = get_table_info(db, table_name)
    logger.info(f"表存在: {table_name}")
    logger.info(f"  行数: {info['row_count']}")
    logger.info(f"  大小: {info['size']}")
    logger.info(f"  列数: {len(info['columns'])}")
    
    # 检查catalog_files表
    catalog_exists = check_table_exists(db, 'catalog_files')
    if catalog_exists:
        catalog_info = get_table_info(db, 'catalog_files')
        logger.info(f"\n对比 catalog_files 表:")
        logger.info(f"  行数: {catalog_info['row_count']}")
        logger.info(f"  大小: {catalog_info['size']}")
        logger.info(f"  列数: {len(catalog_info['columns'])}")
        
        # 比较列结构
        data_cols = {col['name'] for col in info['columns']}
        catalog_cols = {col['name'] for col in catalog_info['columns']}
        
        common_cols = data_cols & catalog_cols
        unique_data_cols = data_cols - catalog_cols
        unique_catalog_cols = catalog_cols - data_cols
        
        logger.info(f"\n列对比:")
        logger.info(f"  共同列: {len(common_cols)} 个")
        logger.info(f"  data_files独有: {len(unique_data_cols)} 个 - {list(unique_data_cols)[:5]}")
        logger.info(f"  catalog_files独有: {len(unique_catalog_cols)} 个 - {list(unique_catalog_cols)[:5]}")
    
    # 搜索代码引用
    references = search_code_references(table_name)
    logger.info(f"\n代码引用: {len(references)} 处")
    for ref in references[:10]:
        logger.info(f"  - {ref['file']}:{ref['line']} - {ref['content']}")
    
    # 评估
    logger.info("\n评估:")
    if len(references) == 0:
        logger.warning("  [WARNING] 代码中未找到引用，可能已废弃")
    elif info['row_count'] == 0:
        logger.warning("  [WARNING] 表为空，可能已废弃")
    else:
        logger.info("  [INFO] 表仍在使用中")


def check_fact_sales_orders_table(db):
    """检查fact_sales_orders表"""
    logger.info("\n" + "=" * 70)
    logger.info("检查 fact_sales_orders 表")
    logger.info("=" * 70)
    
    table_name = 'fact_sales_orders'
    
    if not check_table_exists(db, table_name):
        logger.info(f"[INFO] {table_name} 表不存在")
        return
    
    info = get_table_info(db, table_name)
    logger.info(f"表存在: {table_name}")
    logger.info(f"  行数: {info['row_count']}")
    logger.info(f"  大小: {info['size']}")
    logger.info(f"  列数: {len(info['columns'])}")
    
    # 检查fact_orders表
    orders_exists = check_table_exists(db, 'fact_orders')
    if orders_exists:
        orders_info = get_table_info(db, 'fact_orders')
        logger.info(f"\n对比 fact_orders 表:")
        logger.info(f"  行数: {orders_info['row_count']}")
        logger.info(f"  大小: {orders_info['size']}")
        logger.info(f"  列数: {len(orders_info['columns'])}")
        
        # 比较列结构
        sales_cols = {col['name'] for col in info['columns']}
        orders_cols = {col['name'] for col in orders_info['columns']}
        
        common_cols = sales_cols & orders_cols
        unique_sales_cols = sales_cols - orders_cols
        unique_orders_cols = orders_cols - sales_cols
        
        logger.info(f"\n列对比:")
        logger.info(f"  共同列: {len(common_cols)} 个")
        logger.info(f"  fact_sales_orders独有: {len(unique_sales_cols)} 个 - {list(unique_sales_cols)[:10]}")
        logger.info(f"  fact_orders独有: {len(unique_orders_cols)} 个 - {list(unique_orders_cols)[:10]}")
    
    # 搜索代码引用
    references = search_code_references(table_name)
    logger.info(f"\n代码引用: {len(references)} 处")
    for ref in references[:10]:
        logger.info(f"  - {ref['file']}:{ref['line']} - {ref['content']}")
    
    # 评估
    logger.info("\n评估:")
    if len(references) == 0:
        logger.warning("  [WARNING] 代码中未找到引用，可能已废弃")
    elif info['row_count'] == 0:
        logger.warning("  [WARNING] 表为空，可能已废弃")
    else:
        logger.info("  [INFO] 表仍在使用中")


def check_field_mappings_deprecated_table(db):
    """检查field_mappings_deprecated表"""
    logger.info("\n" + "=" * 70)
    logger.info("检查 field_mappings_deprecated 表")
    logger.info("=" * 70)
    
    table_name = 'field_mappings_deprecated'
    
    if not check_table_exists(db, table_name):
        logger.info(f"[INFO] {table_name} 表不存在")
        return
    
    info = get_table_info(db, table_name)
    logger.info(f"表存在: {table_name}")
    logger.info(f"  行数: {info['row_count']}")
    logger.info(f"  大小: {info['size']}")
    logger.info(f"  列数: {len(info['columns'])}")
    
    # 搜索代码引用
    references = search_code_references(table_name)
    logger.info(f"\n代码引用: {len(references)} 处")
    for ref in references[:10]:
        logger.info(f"  - {ref['file']}:{ref['line']} - {ref['content']}")
    
    # 检查是否有新表替代
    new_table_exists = check_table_exists(db, 'field_mapping_templates')
    if new_table_exists:
        new_info = get_table_info(db, 'field_mapping_templates')
        logger.info(f"\n对比 field_mapping_templates 表（新表）:")
        logger.info(f"  行数: {new_info['row_count']}")
        logger.info(f"  大小: {new_info['size']}")
    
    # 评估
    logger.info("\n评估:")
    logger.info("  [INFO] 表已明确标记为废弃（v4.5.1）")
    if len(references) == 0:
        logger.info("  [INFO] 代码中未找到引用，符合废弃状态")
    else:
        logger.warning(f"  [WARNING] 代码中仍有 {len(references)} 处引用，需要清理")
    if info['row_count'] > 0:
        logger.info(f"  [INFO] 表中有 {info['row_count']} 条历史数据，保留用于历史查询")


def main():
    """主函数"""
    logger.info("=" * 70)
    logger.info("检查冗余表的使用情况（v4.11.2）")
    logger.info("=" * 70)
    
    db = SessionLocal()
    try:
        check_data_files_table(db)
        check_fact_sales_orders_table(db)
        check_field_mappings_deprecated_table(db)
        
        logger.info("\n" + "=" * 70)
        logger.info("检查完成")
        logger.info("=" * 70)
        
    except Exception as e:
        logger.error(f"检查失败: {e}", exc_info=True)
    finally:
        db.close()


if __name__ == '__main__':
    main()

