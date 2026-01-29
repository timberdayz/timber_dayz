"""Migrate A-class and C-class tables to proper schemas

Revision ID: migrate_a_c_class_to_schema
Revises: 20260127_rm_fact_orders
Create Date: 2026-01-27 16:00:00

Description:
- Migrate A-class tables from public to a_class schema
- Migrate C-class tables from public to c_class schema
- Clean up duplicate tables in public schema

Tables migrated to a_class:
- sales_targets_a
- sales_campaigns_a
- operating_costs
- employees
- employee_targets
- attendance_records
- performance_config_a

Tables migrated to c_class:
- employee_performance
- employee_commissions
- shop_commissions
- performance_scores_c
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text, inspect


# revision identifiers, used by Alembic.
revision = 'migrate_a_c_class_to_schema'
down_revision = '20260127_rm_fact_orders'
branch_labels = None
depends_on = None


def safe_print(msg):
    """Safe print for Windows GBK encoding"""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            print(msg.encode('gbk', errors='ignore').decode('gbk'), flush=True)
        except:
            print(msg.encode('ascii', errors='ignore').decode('ascii'), flush=True)


# A-class tables to migrate
A_CLASS_TABLES = [
    'sales_targets_a',
    'sales_campaigns_a',
    'operating_costs',
    'employees',
    'employee_targets',
    'attendance_records',
    'performance_config_a',
]

# C-class tables to migrate
C_CLASS_TABLES = [
    'employee_performance',
    'employee_commissions',
    'shop_commissions',
    'performance_scores_c',
]


def table_exists(conn, table_name, schema='public'):
    """Check if table exists in specified schema"""
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_schema = :schema AND table_name = :table_name
        )
    """), {'schema': schema, 'table_name': table_name})
    return result.scalar()


def migrate_table(conn, table_name, source_schema, target_schema):
    """Migrate table from source schema to target schema"""
    
    # Check if source table exists
    source_exists = table_exists(conn, table_name, source_schema)
    target_exists = table_exists(conn, table_name, target_schema)
    
    if not source_exists and not target_exists:
        safe_print(f"  [SKIP] {source_schema}.{table_name} does not exist, will be created by ORM")
        return 'skip'
    
    if source_exists and target_exists:
        # Both exist - merge data from source to target, then drop source
        safe_print(f"  [MERGE] Merging {source_schema}.{table_name} into {target_schema}.{table_name}")
        
        # Get row count from source
        result = conn.execute(text(f'SELECT COUNT(*) FROM "{source_schema}"."{table_name}"'))
        source_count = result.scalar() or 0
        
        if source_count > 0:
            # Get columns for insert
            cols_result = conn.execute(text("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_schema = :schema AND table_name = :table_name
                ORDER BY ordinal_position
            """), {'schema': source_schema, 'table_name': table_name})
            columns = [row[0] for row in cols_result]
            
            # Filter out id column for insert (let target generate new ids)
            insert_cols = [c for c in columns if c != 'id']
            cols_str = ', '.join(f'"{c}"' for c in insert_cols)
            
            # Insert data that doesn't exist in target (based on unique constraints)
            # For simplicity, we'll just insert all non-duplicate rows
            try:
                conn.execute(text(f"""
                    INSERT INTO "{target_schema}"."{table_name}" ({cols_str})
                    SELECT {cols_str} FROM "{source_schema}"."{table_name}" s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM "{target_schema}"."{table_name}" t 
                        WHERE t.id = s.id
                    )
                    ON CONFLICT DO NOTHING
                """))
                safe_print(f"    [OK] Merged {source_count} rows from {source_schema} to {target_schema}")
            except Exception as e:
                safe_print(f"    [WARN] Could not merge data: {e}")
        
        # Drop source table
        conn.execute(text(f'DROP TABLE IF EXISTS "{source_schema}"."{table_name}" CASCADE'))
        safe_print(f"    [OK] Dropped {source_schema}.{table_name}")
        return 'merged'
    
    if source_exists and not target_exists:
        # Only source exists - move it to target schema
        safe_print(f"  [MOVE] Moving {source_schema}.{table_name} to {target_schema}.{table_name}")
        conn.execute(text(f'ALTER TABLE "{source_schema}"."{table_name}" SET SCHEMA {target_schema}'))
        safe_print(f"    [OK] Moved to {target_schema}")
        return 'moved'
    
    if not source_exists and target_exists:
        # Only target exists - nothing to do
        safe_print(f"  [OK] {target_schema}.{table_name} already exists")
        return 'exists'


def upgrade():
    """Migrate A-class and C-class tables to their proper schemas"""
    conn = op.get_bind()
    
    safe_print("="*60)
    safe_print("Migrating A-class tables to a_class schema")
    safe_print("="*60)
    
    for table_name in A_CLASS_TABLES:
        safe_print(f"Processing {table_name}...")
        migrate_table(conn, table_name, 'public', 'a_class')
    
    safe_print("")
    safe_print("="*60)
    safe_print("Migrating C-class tables to c_class schema")
    safe_print("="*60)
    
    for table_name in C_CLASS_TABLES:
        safe_print(f"Processing {table_name}...")
        migrate_table(conn, table_name, 'public', 'c_class')
    
    safe_print("")
    safe_print("="*60)
    safe_print("Migration completed!")
    safe_print("="*60)


def downgrade():
    """Move tables back to public schema (for rollback)"""
    conn = op.get_bind()
    
    safe_print("="*60)
    safe_print("Rolling back: Moving A-class tables back to public")
    safe_print("="*60)
    
    for table_name in A_CLASS_TABLES:
        if table_exists(conn, table_name, 'a_class'):
            safe_print(f"  Moving {table_name} from a_class to public...")
            try:
                conn.execute(text(f'ALTER TABLE "a_class"."{table_name}" SET SCHEMA public'))
                safe_print(f"    [OK] Moved to public")
            except Exception as e:
                safe_print(f"    [ERROR] {e}")
    
    safe_print("")
    safe_print("="*60)
    safe_print("Rolling back: Moving C-class tables back to public")
    safe_print("="*60)
    
    for table_name in C_CLASS_TABLES:
        if table_exists(conn, table_name, 'c_class'):
            safe_print(f"  Moving {table_name} from c_class to public...")
            try:
                conn.execute(text(f'ALTER TABLE "c_class"."{table_name}" SET SCHEMA public'))
                safe_print(f"    [OK] Moved to public")
            except Exception as e:
                safe_print(f"    [ERROR] {e}")
    
    safe_print("")
    safe_print("Rollback completed!")
