"""
数据库现状分析脚本
分析当前数据库表结构，与计划的ERP架构对比
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from backend.models.database import Base
from sqlalchemy import inspect

def analyze_current_schema():
    """分析当前数据库schema"""
    
    print("=" * 80)
    print("[DATABASE ANALYSIS] Current Schema Analysis")
    print("=" * 80)
    print()
    
    tables = Base.metadata.sorted_tables
    
    print(f"[OK] Total tables: {len(tables)}")
    print()
    
    # 按类别分类
    dim_tables = []
    fact_tables = []
    staging_tables = []
    management_tables = []
    
    for table in tables:
        table_name = table.name
        if table_name.startswith('dim_'):
            dim_tables.append(table_name)
        elif table_name.startswith('fact_'):
            fact_tables.append(table_name)
        elif table_name.startswith('staging_'):
            staging_tables.append(table_name)
        else:
            management_tables.append(table_name)
    
    # 维度表
    print("[DIMENSION TABLES]:")
    for table_name in dim_tables:
        table = next(t for t in tables if t.name == table_name)
        columns = [col.name for col in table.columns]
        print(f"  - {table_name}: {len(columns)} fields")
    print()
    
    # 事实表
    print("[FACT TABLES]:")
    for table_name in fact_tables:
        table = next(t for t in tables if t.name == table_name)
        columns = [col.name for col in table.columns]
        indexes = [idx.name for idx in table.indexes if idx.name]
        print(f"  - {table_name}: {len(columns)} fields, {len(indexes)} indexes")
    print()
    
    # 暂存表
    print("[STAGING TABLES]:")
    for table_name in staging_tables:
        table = next(t for t in tables if t.name == table_name)
        columns = [col.name for col in table.columns]
        print(f"  - {table_name}: {len(columns)} fields")
    print()
    
    # 管理表
    print("[MANAGEMENT TABLES]:")
    for table_name in management_tables:
        table = next(t for t in tables if t.name == table_name)
        columns = [col.name for col in table.columns]
        print(f"  - {table_name}: {len(columns)} fields")
    print()
    
    # 与计划对比
    print("=" * 80)
    print("[COMPARISON] vs ERP Architecture Plan")
    print("=" * 80)
    print()
    
    # 计划中的表
    planned_tables = {
        'Dimension': [
            ('dim_products', 'Product Master Data', 'MISSING'),
            ('dim_shops', 'Shop Dimension', 'EXISTS'),
            ('dim_platform', 'Platform Dimension', 'EXISTS'),
            ('dim_users', 'User Table', 'MISSING'),
            ('dim_roles', 'Role Table', 'MISSING')
        ],
        'Inventory': [
            ('fact_inventory', 'Real-time Inventory', 'MISSING'),
            ('fact_inventory_transactions', 'Inventory Transactions', 'MISSING')
        ],
        'Orders': [
            ('fact_sales_orders', 'Sales Orders', 'ENHANCE_NEEDED'),
            ('fact_order_items', 'Order Items', 'MISSING')
        ],
        'Finance': [
            ('fact_accounts_receivable', 'Accounts Receivable', 'MISSING'),
            ('fact_payment_receipts', 'Payment Receipts', 'MISSING'),
            ('fact_expenses', 'Expenses', 'MISSING')
        ],
        'Other': [
            ('fact_product_metrics', 'Product Metrics', 'EXISTS'),
            ('fact_audit_logs', 'Audit Logs', 'MISSING')
        ]
    }
    
    for category, table_list in planned_tables.items():
        print(f"[{category}]:")
        for table_name, desc, status in table_list:
            if status == 'MISSING':
                print(f"  [X] {table_name} ({desc}) - MISSING")
            elif status == 'ENHANCE_NEEDED':
                print(f"  [!] {table_name} ({desc}) - NEED ENHANCEMENT")
            else:
                print(f"  [OK] {table_name} ({desc})")
        print()
    
    # 需要修改的表
    print("=" * 80)
    print("[MODIFICATIONS] Required Changes to Existing Tables")
    print("=" * 80)
    print()
    
    modifications = {
        'fact_sales_orders': [
            '+ Add finance fields: is_invoiced, invoice_id, is_payment_received, payment_voucher_id',
            '+ Add inventory field: inventory_deducted',
            '+ Add cost/profit fields: cost_amount_cny, gross_profit_cny, net_profit_cny',
            '+ Add exchange_rate field',
            '+ Add platform fee fields: platform_commission, payment_fee'
        ],
        'dim_product': [
            '+ Rename to dim_products (plural)',
            '+ Add fields: internal_sku, cost_price, cost_currency',
            '+ Add fields: category_l1, category_l2, category_l3, brand',
            '+ Add fields: weight_kg, length_cm, product_status'
        ]
    }
    
    for table_name, changes in modifications.items():
        print(f"[{table_name}]:")
        for change in changes:
            print(f"   {change}")
        print()
    
    # 统计摘要
    print("=" * 80)
    print("[SUMMARY]")
    print("=" * 80)
    print()
    print(f"Current tables: {len(tables)}")
    print(f"Planned new tables: 10 (Inventory:2, Finance:3, User:2, Audit:1, OrderItems:1)")
    print(f"Tables to modify: 2 (fact_sales_orders, dim_product)")
    print(f"Completion rate: {len(tables)}/{len(tables) + 10} = {len(tables)/(len(tables) + 10) * 100:.1f}%")
    print()
    
    # 详细字段分析 - fact_sales_orders
    print("=" * 80)
    print("[DETAIL] fact_sales_orders Field Analysis")
    print("=" * 80)
    print()
    
    fact_orders_table = next(t for t in tables if t.name == 'fact_sales_orders')
    print("Existing fields:")
    for col in fact_orders_table.columns:
        print(f"  - {col.name}: {col.type}")
    
    print()
    print("Planned new fields:")
    new_fields = [
        "exchange_rate DECIMAL(10,4) - Exchange rate",
        "platform_commission DECIMAL(15,2) - Platform commission",
        "payment_fee DECIMAL(15,2) - Payment fee",
        "cost_amount_cny DECIMAL(15,2) - Total cost",
        "gross_profit_cny DECIMAL(15,2) - Gross profit",
        "net_profit_cny DECIMAL(15,2) - Net profit",
        "is_invoiced BOOLEAN - Invoiced flag",
        "invoice_id BIGINT - Invoice ID",
        "is_payment_received BOOLEAN - Payment received flag",
        "payment_voucher_id BIGINT - Payment voucher ID",
        "inventory_deducted BOOLEAN - Inventory deducted flag"
    ]
    for field in new_fields:
        print(f"  + {field}")
    
    print()
    print("[OK] Database analysis completed")
    print()

if __name__ == "__main__":
    analyze_current_schema()

