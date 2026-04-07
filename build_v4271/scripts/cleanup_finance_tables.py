#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理财务域空表脚本

功能：
- 删除21张空的财务域表（0行）
- 保留fact_order_amounts（有数据，375行）
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, inspect
from backend.models.database import SessionLocal

def safe_print(text):
    """安全打印（Windows兼容）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

# 财务域空表列表（21张，都是0行）
FINANCE_EMPTY_TABLES = [
    'po_headers', 'po_lines',
    'grn_headers', 'grn_lines',
    'invoice_headers', 'invoice_lines', 'invoice_attachments',
    'fact_expenses', 'fact_expenses_month', 'fact_expenses_allocated_day_shop_sku',
    'fact_inventory', 'fact_inventory_transactions', 'inventory_ledger',
    'fact_sales_orders',
    'tax_vouchers', 'tax_reports',
    'gl_accounts', 'journal_entries', 'journal_entry_lines',
    'fact_accounts_receivable', 'fact_payment_receipts'
]

# 保留的表（有数据）
KEEP_TABLES = [
    'fact_order_amounts'  # 有375行数据，应保留
]

def cleanup_finance_tables(dry_run: bool = True):
    """清理财务域空表"""
    db = SessionLocal()
    try:
        inspector = inspect(db.bind)
        existing_tables = set(inspector.get_table_names(schema='public'))
        
        # 找出实际存在的可删除表
        tables_to_drop = []
        for table_name in FINANCE_EMPTY_TABLES:
            if table_name in existing_tables:
                tables_to_drop.append(table_name)
        
        safe_print("="*80)
        safe_print("清理财务域空表")
        safe_print("="*80)
        safe_print(f"\n发现 {len(tables_to_drop)} 张财务域空表（0行）:")
        
        # 按类别显示
        categories = {
            '采购管理': ['po_headers', 'po_lines'],
            '入库管理': ['grn_headers', 'grn_lines'],
            '发票管理': ['invoice_headers', 'invoice_lines', 'invoice_attachments'],
            '费用管理': ['fact_expenses', 'fact_expenses_month', 'fact_expenses_allocated_day_shop_sku'],
            '库存管理': ['fact_inventory', 'fact_inventory_transactions', 'inventory_ledger'],
            '税务管理': ['tax_vouchers', 'tax_reports'],
            '总账管理': ['gl_accounts', 'journal_entries', 'journal_entry_lines'],
            '其他': ['fact_sales_orders', 'fact_accounts_receivable', 'fact_payment_receipts']
        }
        
        for category, tables in categories.items():
            category_tables = [t for t in tables_to_drop if t in tables]
            if category_tables:
                safe_print(f"\n[{category}] {len(category_tables)} 张:")
                for table in sorted(category_tables):
                    safe_print(f"  - {table}")
        
        safe_print(f"\n保留的表（有数据）:")
        for table in KEEP_TABLES:
            if table in existing_tables:
                try:
                    count = db.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0
                    safe_print(f"  - {table}: {count} 行")
                except:
                    pass
        
        if not tables_to_drop:
            safe_print("\n[OK] 没有需要清理的表")
            return
        
        if dry_run:
            safe_print(f"\n[DRY RUN] 以上 {len(tables_to_drop)} 张表将被删除（实际未执行）")
            safe_print("[提示] 要实际删除，请使用: python scripts/cleanup_finance_tables.py --execute")
            safe_print("\n注意:")
            safe_print("  - 这些表在schema.py中已定义（v4.4.0版本）")
            safe_print("  - 有API路由代码，但都是空表（0行）")
            safe_print("  - 删除后，如果未来需要使用，可以通过Alembic迁移重新创建")
            return
        
        # 实际删除
        safe_print(f"\n开始删除 {len(tables_to_drop)} 张表...")
        deleted_count = 0
        failed_count = 0
        
        for table_name in sorted(tables_to_drop):
            try:
                db.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))
                db.commit()
                safe_print(f"  [OK] 删除表: {table_name}")
                deleted_count += 1
            except Exception as e:
                db.rollback()
                safe_print(f"  [FAIL] 删除表失败: {table_name}, 错误: {e}")
                failed_count += 1
        
        safe_print(f"\n删除完成: 成功 {deleted_count} 张, 失败 {failed_count} 张")
        
        # 验证剩余表数
        remaining_tables = inspector.get_table_names(schema='public')
        safe_print(f"\n剩余表数: {len(remaining_tables)} 张")
        
    except Exception as e:
        safe_print(f"[ERROR] 清理过程出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="清理财务域空表脚本")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="实际执行删除（默认只显示将要删除的表）"
    )
    
    args = parser.parse_args()
    
    dry_run = not args.execute
    
    if dry_run:
        safe_print("[DRY RUN] 运行模式: 只显示，不删除")
    else:
        safe_print("[EXECUTE] 运行模式: 将实际删除表")
        safe_print("[警告] 请确认这是开发环境，生产环境需要先备份！")
    
    cleanup_finance_tables(dry_run=dry_run)

