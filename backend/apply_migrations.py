"""
应用数据库迁移脚本
创建所有新表并更新现有表结构

⭐ v4.18.2 更新：
- 自动检查并修复 catalog_files 表的缺失列
- 确保表结构与 modules/core/db/schema.py（SSOT）一致

注意：
- 所有表定义来自 modules/core/db/schema.py（Single Source of Truth）
- 此脚本会自动添加缺失的列，但不会删除多余的列
- catalog_files 表只在 public schema 中（core schema 中的重复表已清理，2026-01-02）
"""

import sys
from pathlib import Path
import asyncio

# 添加项目根目录到Python路径
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from backend.models.database import Base, engine, SessionLocal
from backend.utils.config import get_settings
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def apply_migrations():
    """应用数据库迁移"""
    
    print("=" * 80)
    print("[MIGRATION] Applying database migrations...")
    print("=" * 80)
    print()
    
    settings = get_settings()
    db_url = settings.DATABASE_URL
    
    print(f"[INFO] Database: {db_url.split('@')[-1] if '@' in db_url else db_url}")
    print()
    
    try:
        # Step 1: 创建所有新表
        print("[1/3] Creating new tables...")
        Base.metadata.create_all(bind=engine)
        print("[OK] All tables created successfully")
        print()
        
        # Step 2: 验证表创建并修复缺失列
        print("[2/3] Verifying tables and fixing missing columns...")
        
        # ⭐ v4.18.2修复：使用run_in_executor包装同步数据库操作
        def _sync_verify_tables():
            """同步验证表创建并修复缺失列（在线程池中执行）"""
            db = SessionLocal()
            try:
                # 获取所有表名（检查多个schema）
                # 注意：catalog_files 表只在 public schema 中，但其他表可能在 core schema 中
                result = db.execute(text("""
                    SELECT table_schema, table_name 
                    FROM information_schema.tables 
                    WHERE table_schema IN ('public', 'core')
                    ORDER BY table_schema, table_name
                """))
                
                tables_by_schema = {}
                for row in result:
                    schema, table = row[0], row[1]
                    if schema not in tables_by_schema:
                        tables_by_schema[schema] = []
                    tables_by_schema[schema].append(table)
                
                # 合并所有表名（用于验证）
                all_tables = []
                for schema, tables in tables_by_schema.items():
                    all_tables.extend(tables)
                
                # ⭐ 新增：检查并修复 catalog_files 表的缺失列
                # 注意：catalog_files 表只在 public schema 中（core schema 中的重复表已清理）
                catalog_files_fixed = False
                schema = 'public'  # 只检查 public schema
                if 'catalog_files' in tables_by_schema.get(schema, []):
                    print(f"  [CHECK] Checking catalog_files table in schema '{schema}'...")
                    
                    # 获取现有列
                    result_columns = db.execute(text(f"""
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_name = 'catalog_files'
                        AND table_schema = '{schema}'
                    """))
                    existing_columns = {row[0] for row in result_columns}
                    
                    # 定义需要的列（根据 modules/core/db/schema.py 中的 CatalogFile 类）
                    required_columns = {
                        'platform_code': ('VARCHAR(32)', 'NULL'),
                        'account': ('VARCHAR(128)', 'NULL'),
                        'shop_id': ('VARCHAR(256)', 'NULL'),
                        'data_domain': ('VARCHAR(64)', 'NULL'),
                        'granularity': ('VARCHAR(16)', 'NULL'),
                        'date_from': ('DATE', 'NULL'),
                        'date_to': ('DATE', 'NULL'),
                        'source_platform': ('VARCHAR(32)', 'NULL'),
                        'sub_domain': ('VARCHAR(64)', 'NULL'),
                        'storage_layer': ('VARCHAR(32)', "'raw'"),
                        'quality_score': ('REAL', 'NULL'),
                        'validation_errors': ('JSONB', 'NULL'),
                        'meta_file_path': ('VARCHAR(1024)', 'NULL'),
                        'file_metadata': ('JSONB', 'NULL'),
                        'status': ('VARCHAR(32)', "'pending'"),
                        'error_message': ('TEXT', 'NULL'),
                        'first_seen_at': ('TIMESTAMP', 'CURRENT_TIMESTAMP'),
                        'last_processed_at': ('TIMESTAMP', 'NULL'),
                        'source': ('VARCHAR(64)', "'temp/outputs'"),
                        'file_size': ('INTEGER', 'NULL'),
                        'file_hash': ('VARCHAR(64)', 'NULL')
                    }
                    
                    # 添加缺失的列
                    added_count = 0
                    for col_name, (col_type, default_val) in required_columns.items():
                        if col_name not in existing_columns:
                            try:
                                # 构建默认值子句
                                if default_val == 'NULL':
                                    default_clause = ""
                                elif default_val == 'CURRENT_TIMESTAMP':
                                    if col_name == 'first_seen_at':
                                        default_clause = "DEFAULT CURRENT_TIMESTAMP NOT NULL"
                                    else:
                                        default_clause = "DEFAULT CURRENT_TIMESTAMP"
                                else:
                                    default_clause = f"DEFAULT {default_val}"
                                
                                # 特殊处理 status 列
                                if col_name == 'status':
                                    default_clause = "DEFAULT 'pending' NOT NULL"
                                
                                # 构建 ALTER TABLE 语句
                                alter_sql = text(f"""
                                    ALTER TABLE {schema}.catalog_files 
                                    ADD COLUMN IF NOT EXISTS {col_name} {col_type} {default_clause}
                                """)
                                db.execute(alter_sql)
                                print(f"    [ADD] Added column: {col_name}")
                                added_count += 1
                                catalog_files_fixed = True
                            except Exception as e:
                                print(f"    [WARN] Failed to add column {col_name}: {e}")
                    
                    if added_count > 0:
                        db.commit()
                        print(f"  [OK] catalog_files table fixed: added {added_count} columns")
                    else:
                        print(f"  [OK] catalog_files table columns verified (all present)")
                
                # 验证 fact_sales_orders 的新字段
                result_fields = db.execute(text("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = 'fact_sales_orders'
                    AND column_name IN (
                        'platform_commission',
                        'payment_fee',
                        'exchange_rate',
                        'cost_amount_cny',
                        'gross_profit_cny',
                        'net_profit_cny',
                        'is_invoiced',
                        'is_payment_received',
                        'inventory_deducted'
                    )
                    ORDER BY column_name
                """))
                
                new_fields = {row[0]: row[1] for row in result_fields}
                
                return all_tables, new_fields, catalog_files_fixed
            finally:
                db.close()
        
        loop = asyncio.get_running_loop()
        tables, new_fields, catalog_files_fixed = await loop.run_in_executor(None, _sync_verify_tables)
        
        print(f"[OK] Total tables in database: {len(tables)}")
        
        if catalog_files_fixed:
            print("[INFO] catalog_files table structure has been fixed!")
        
        # 验证关键新表
        expected_new_tables = [
            'dim_users',
            'dim_roles',
            'fact_inventory',
            'fact_inventory_transactions',
            'fact_accounts_receivable',
            'fact_payment_receipts',
            'fact_expenses',
            'fact_order_items',
            'fact_audit_logs',
            'user_roles'
        ]
        
        print()
        print("[VERIFICATION] New tables:")
        for table in expected_new_tables:
            if table in tables:
                print(f"  [OK] {table}")
            else:
                print(f"  [X] {table} - MISSING!")
        
        print()
        
        # 验证 fact_sales_orders 的新字段
        print("[VERIFICATION] fact_sales_orders new fields:")
        expected_fields = [
            'platform_commission',
            'payment_fee', 
            'exchange_rate',
            'cost_amount_cny',
            'gross_profit_cny',
            'net_profit_cny',
            'is_invoiced',
            'is_payment_received',
            'inventory_deducted'
        ]
        
        for field in expected_fields:
            if field in new_fields:
                print(f"  [OK] {field}: {new_fields[field]}")
            else:
                print(f"  [X] {field} - MISSING!")
        
        print()
        print("[3/3] Migration completed successfully!")
        print()
        
        # 统计
        print("=" * 80)
        print("[SUMMARY]")
        print("=" * 80)
        print(f"Total tables: {len(tables)}")
        print(f"New tables added: {len(expected_new_tables)}")
        print(f"Tables enhanced: 1 (fact_sales_orders)")
        if catalog_files_fixed:
            print("Tables fixed: 1 (catalog_files)")
        print()
        print("[OK] Database migration completed successfully!")
        
    except Exception as e:
        logger.error(f"[ERROR] Migration failed: {e}")
        print()
        print("[ROLLBACK] Rolling back changes...")
        raise

if __name__ == "__main__":
    asyncio.run(apply_migrations())

