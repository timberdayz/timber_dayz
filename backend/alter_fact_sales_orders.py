"""
修改 fact_sales_orders 表，添加新字段
包含：财务字段、库存字段、成本利润字段
"""

import sys
from pathlib import Path

root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from backend.models.database import SessionLocal
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def alter_fact_sales_orders():
    """为 fact_sales_orders 表添加新字段"""
    
    print("=" * 80)
    print("[ALTER TABLE] Adding new fields to fact_sales_orders")
    print("=" * 80)
    print()
    
    db = SessionLocal()
    
    try:
        # 定义要添加的字段
        new_fields = [
            # 平台费用字段
            ("platform_commission", "DECIMAL(15,2)", "Platform commission"),
            ("payment_fee", "DECIMAL(15,2)", "Payment fee"),
            ("shipping_fee", "DECIMAL(15,2)", "Shipping fee"),
            
            # 汇率和人民币金额
            ("exchange_rate", "DECIMAL(10,4)", "Exchange rate"),
            ("gmv_cny", "DECIMAL(15,2)", "GMV in CNY"),
            
            # 成本和利润字段
            ("cost_amount_cny", "DECIMAL(15,2)", "Total cost in CNY"),
            ("gross_profit_cny", "DECIMAL(15,2)", "Gross profit in CNY"),
            ("net_profit_cny", "DECIMAL(15,2)", "Net profit in CNY"),
            
            # 财务关联字段
            ("is_invoiced", "BOOLEAN DEFAULT FALSE", "Invoiced flag"),
            ("invoice_id", "INTEGER", "Invoice ID"),
            ("is_payment_received", "BOOLEAN DEFAULT FALSE", "Payment received flag"),
            ("payment_voucher_id", "INTEGER", "Payment voucher ID"),
            
            # 库存关联字段
            ("inventory_deducted", "BOOLEAN DEFAULT FALSE", "Inventory deducted flag"),
            
            # 时间戳
            ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "Updated timestamp"),
        ]
        
        # 首先检查哪些字段已存在
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'fact_sales_orders'
        """))
        existing_fields = {row[0] for row in result}
        
        # 添加不存在的字段
        added_count = 0
        skipped_count = 0
        
        for field_name, field_type, description in new_fields:
            if field_name in existing_fields:
                print(f"  [SKIP] {field_name} - already exists")
                skipped_count += 1
            else:
                try:
                    sql = f"ALTER TABLE fact_sales_orders ADD COLUMN {field_name} {field_type}"
                    db.execute(text(sql))
                    db.commit()
                    print(f"  [OK] Added {field_name} ({description})")
                    added_count += 1
                except Exception as e:
                    print(f"  [ERROR] Failed to add {field_name}: {e}")
                    db.rollback()
        
        # 添加新索引
        print()
        print("[INDEXES] Creating new indexes...")
        
        indexes = [
            ("ix_fact_sales_time", "fact_sales_orders", ["platform_code", "shop_id", "order_ts"]),
            ("ix_fact_sales_financial", "fact_sales_orders", ["is_invoiced", "is_payment_received"]),
        ]
        
        for idx_name, table_name, columns in indexes:
            try:
                # 检查索引是否已存在
                check_sql = text("""
                    SELECT 1 FROM pg_indexes 
                    WHERE indexname = :idx_name
                """)
                result = db.execute(check_sql, {"idx_name": idx_name})
                if result.fetchone():
                    print(f"  [SKIP] {idx_name} - already exists")
                else:
                    col_list = ", ".join(columns)
                    create_idx_sql = f"CREATE INDEX {idx_name} ON {table_name} ({col_list})"
                    db.execute(text(create_idx_sql))
                    db.commit()
                    print(f"  [OK] Created index {idx_name}")
            except Exception as e:
                print(f"  [ERROR] Failed to create index {idx_name}: {e}")
                db.rollback()
        
        print()
        print("=" * 80)
        print("[SUMMARY]")
        print("=" * 80)
        print(f"Fields added: {added_count}")
        print(f"Fields skipped: {skipped_count}")
        print()
        print("[OK] Table alteration completed!")
        
    except Exception as e:
        logger.error(f"[ERROR] Table alteration failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    alter_fact_sales_orders()

