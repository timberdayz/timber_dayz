#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理历史遗留的包含货币代码的列（v4.16.0）

功能：
1. 检查指定表中是否存在包含货币代码的列（如 "销售_SGD"）
2. 检查这些列是否有数据
3. 如果没有数据，删除这些列
4. 如果有数据，给出警告（需要手动处理）

使用方法：
    python scripts/cleanup_legacy_currency_columns.py [table_name] [--dry-run]
    
示例：
    # 检查所有fact_raw_data表
    python scripts/cleanup_legacy_currency_columns.py
    
    # 检查特定表（干运行模式，不实际删除）
    python scripts/cleanup_legacy_currency_columns.py fact_raw_data_services_agent_daily --dry-run
    
    # 检查特定表（实际删除）
    python scripts/cleanup_legacy_currency_columns.py fact_raw_data_services_agent_daily
"""

import sys
import argparse
from pathlib import Path
from typing import List, Dict, Set

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, inspect
from backend.models.database import get_db
from modules.core.logger import get_logger

logger = get_logger(__name__)

# 货币代码列表（用于检测列名中的货币代码）
CURRENCY_CODES = {
    'SGD', 'BRL', 'USD', 'CNY', 'EUR', 'GBP', 'JPY', 'KRW', 'HKD', 'TWD',
    'MYR', 'IDR', 'THB', 'PHP', 'VND', 'BND', 'MMK', 'KHR', 'LAK',
    'COP', 'ARS', 'CLP', 'PEN', 'UYU', 'VES', 'CAD', 'MXN',
    'CHF', 'SEK', 'NOK', 'DKK', 'RUB', 'TRY', 'PLN',
    'INR', 'PKR', 'BDT', 'AUD', 'NZD',
    'AED', 'SAR', 'EGP', 'ZAR', 'NGN', 'KES'
}


def find_currency_columns(table_name: str, db) -> List[Dict[str, any]]:
    """
    查找表中包含货币代码的列
    
    Returns:
        List[Dict]: [{'column_name': '销售_SGD', 'has_data': False}, ...]
    """
    try:
        inspector = inspect(db.bind)
        columns = inspector.get_columns(table_name)
        column_names = [col['name'] for col in columns]
        
        currency_columns = []
        for col_name in column_names:
            # 检查列名是否包含货币代码
            col_upper = col_name.upper()
            for currency_code in CURRENCY_CODES:
                if currency_code in col_upper:
                    # 检查列是否有数据
                    check_sql = text(f'SELECT COUNT(*) FROM "{table_name}" WHERE "{col_name}" IS NOT NULL')
                    result = db.execute(check_sql).scalar()
                    has_data = result > 0
                    
                    currency_columns.append({
                        'column_name': col_name,
                        'currency_code': currency_code,
                        'has_data': has_data,
                        'row_count': result
                    })
                    break  # 找到一个货币代码就足够了
        
        return currency_columns
        
    except Exception as e:
        logger.error(f"查找表 {table_name} 的货币列失败: {e}", exc_info=True)
        return []


def drop_column(table_name: str, column_name: str, db, dry_run: bool = False) -> bool:
    """
    删除列
    
    Args:
        table_name: 表名
        column_name: 列名
        db: 数据库会话
        dry_run: 是否只是预览（不实际删除）
    
    Returns:
        bool: 是否成功
    """
    try:
        if dry_run:
            logger.info(f"[DRY-RUN] 将删除列: {table_name}.{column_name}")
            return True
        
        drop_sql = text(f'ALTER TABLE "{table_name}" DROP COLUMN IF EXISTS "{column_name}"')
        db.execute(drop_sql)
        db.commit()
        logger.info(f"✅ 成功删除列: {table_name}.{column_name}")
        return True
        
    except Exception as e:
        logger.error(f"❌ 删除列 {table_name}.{column_name} 失败: {e}", exc_info=True)
        db.rollback()
        return False


def cleanup_table(table_name: str, db, dry_run: bool = False) -> Dict[str, any]:
    """
    清理指定表的货币列
    
    Returns:
        Dict: {
            'table_name': str,
            'found_columns': List[Dict],
            'dropped_columns': List[str],
            'skipped_columns': List[str],
            'errors': List[str]
        }
    """
    result = {
        'table_name': table_name,
        'found_columns': [],
        'dropped_columns': [],
        'skipped_columns': [],
        'errors': []
    }
    
    # 查找包含货币代码的列
    currency_columns = find_currency_columns(table_name, db)
    result['found_columns'] = currency_columns
    
    if not currency_columns:
        logger.info(f"表 {table_name} 中没有找到包含货币代码的列")
        return result
    
    logger.info(f"表 {table_name} 中找到 {len(currency_columns)} 个包含货币代码的列:")
    for col_info in currency_columns:
        status = "有数据" if col_info['has_data'] else "无数据"
        logger.info(f"  - {col_info['column_name']} ({col_info['currency_code']}): {status} ({col_info['row_count']}行)")
    
    # 删除无数据的列
    for col_info in currency_columns:
        if col_info['has_data']:
            logger.warning(
                f"⚠️  跳过列 {col_info['column_name']}（有 {col_info['row_count']} 行数据，需要手动处理）"
            )
            result['skipped_columns'].append(col_info['column_name'])
        else:
            if drop_column(table_name, col_info['column_name'], db, dry_run):
                result['dropped_columns'].append(col_info['column_name'])
            else:
                result['errors'].append(col_info['column_name'])
    
    return result


def find_all_fact_raw_data_tables(db) -> List[str]:
    """查找所有fact_raw_data_*表"""
    try:
        inspector = inspect(db.bind)
        all_tables = inspector.get_table_names()
        fact_tables = [t for t in all_tables if t.startswith('fact_raw_data_')]
        return sorted(fact_tables)
    except Exception as e:
        logger.error(f"查找表失败: {e}", exc_info=True)
        return []


def main():
    parser = argparse.ArgumentParser(description='清理历史遗留的包含货币代码的列')
    parser.add_argument('table_name', nargs='?', help='表名（如 fact_raw_data_services_agent_daily），如果不指定则检查所有fact_raw_data_*表')
    parser.add_argument('--dry-run', action='store_true', help='干运行模式（只预览，不实际删除）')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("清理历史遗留的包含货币代码的列（v4.16.0）")
    print("=" * 60)
    
    if args.dry_run:
        print("\n⚠️  干运行模式：只预览，不实际删除列")
    
    db = next(get_db())
    
    try:
        if args.table_name:
            # 清理指定表
            tables = [args.table_name]
        else:
            # 清理所有fact_raw_data_*表
            tables = find_all_fact_raw_data_tables(db)
            print(f"\n找到 {len(tables)} 个fact_raw_data_*表:")
            for t in tables:
                print(f"  - {t}")
        
        print("\n开始清理...")
        print("-" * 60)
        
        all_results = []
        for table_name in tables:
            try:
                result = cleanup_table(table_name, db, args.dry_run)
                all_results.append(result)
            except Exception as e:
                logger.error(f"清理表 {table_name} 失败: {e}", exc_info=True)
                all_results.append({
                    'table_name': table_name,
                    'found_columns': [],
                    'dropped_columns': [],
                    'skipped_columns': [],
                    'errors': [str(e)]
                })
        
        # 汇总结果
        print("\n" + "=" * 60)
        print("清理结果汇总")
        print("=" * 60)
        
        total_found = 0
        total_dropped = 0
        total_skipped = 0
        total_errors = 0
        
        for result in all_results:
            if result['found_columns']:
                print(f"\n表: {result['table_name']}")
                print(f"  找到列: {len(result['found_columns'])}")
                print(f"  删除列: {len(result['dropped_columns'])}")
                if result['dropped_columns']:
                    for col in result['dropped_columns']:
                        print(f"    ✅ {col}")
                print(f"  跳过列: {len(result['skipped_columns'])}")
                if result['skipped_columns']:
                    for col in result['skipped_columns']:
                        print(f"    ⚠️  {col}（有数据，需要手动处理）")
                print(f"  错误: {len(result['errors'])}")
                if result['errors']:
                    for col in result['errors']:
                        print(f"    ❌ {col}")
                
                total_found += len(result['found_columns'])
                total_dropped += len(result['dropped_columns'])
                total_skipped += len(result['skipped_columns'])
                total_errors += len(result['errors'])
        
        print("\n" + "-" * 60)
        print(f"总计:")
        print(f"  找到列: {total_found}")
        print(f"  删除列: {total_dropped}")
        print(f"  跳过列: {total_skipped}（有数据，需要手动处理）")
        print(f"  错误: {total_errors}")
        
        if args.dry_run:
            print("\n⚠️  这是干运行模式，没有实际删除任何列")
            print("   要实际删除，请移除 --dry-run 参数")
        else:
            print("\n✅ 清理完成！")
        
    finally:
        db.close()


if __name__ == "__main__":
    main()

