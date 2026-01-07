#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析财务域表的使用情况
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

def analyze_finance_tables():
    """分析财务域表"""
    db = SessionLocal()
    try:
        inspector = inspect(db.bind)
        all_tables = inspector.get_table_names(schema='public')
        
        # 财务域表列表
        finance_tables = [
            'po_headers', 'po_lines',
            'grn_headers', 'grn_lines',
            'invoice_headers', 'invoice_lines', 'invoice_attachments',
            'fact_expenses', 'fact_expenses_month', 'fact_expenses_allocated_day_shop_sku',
            'fact_inventory', 'fact_inventory_transactions', 'inventory_ledger',
            'fact_order_amounts', 'fact_sales_orders',
            'tax_vouchers', 'tax_reports',
            'gl_accounts', 'journal_entries', 'journal_entry_lines',
            'fact_accounts_receivable', 'fact_payment_receipts'
        ]
        
        safe_print("="*80)
        safe_print("财务域表分析")
        safe_print("="*80)
        
        found_tables = []
        empty_tables = []
        used_tables = []
        
        for table in finance_tables:
            if table in all_tables:
                found_tables.append(table)
                try:
                    count = db.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0
                    if count == 0:
                        empty_tables.append(table)
                    else:
                        used_tables.append((table, count))
                except:
                    pass
        
        safe_print(f"\n发现 {len(found_tables)} 张财务域表:")
        safe_print(f"  - 空表（0行）: {len(empty_tables)} 张")
        safe_print(f"  - 有数据: {len(used_tables)} 张")
        
        if used_tables:
            safe_print("\n有数据的表:")
            for table, count in used_tables:
                safe_print(f"  - {table}: {count} 行")
        
        safe_print(f"\n空表列表（{len(empty_tables)} 张）:")
        for table in sorted(empty_tables):
            safe_print(f"  - {table}")
        
        safe_print("\n" + "="*80)
        safe_print("建议")
        safe_print("="*80)
        safe_print("\n财务域表情况:")
        safe_print("  1. 这些表在schema.py中已定义（v4.4.0版本）")
        safe_print("  2. 有API路由代码（backend/routers/finance.py, procurement.py）")
        safe_print("  3. 但所有表都是空的（0行），说明还没有实际业务数据")
        safe_print("\n选项:")
        safe_print("  A. 保留这些表（未来可能会使用）")
        safe_print("  B. 删除这些表（如果确定不会使用）")
        safe_print("\n如果选择删除，可以运行:")
        safe_print("  python scripts/cleanup_finance_tables.py --execute")
        
    except Exception as e:
        safe_print(f"[ERROR] 分析过程出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    analyze_finance_tables()

