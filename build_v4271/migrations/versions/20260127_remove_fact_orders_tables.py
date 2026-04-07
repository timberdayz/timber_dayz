"""remove deprecated fact_orders and fact_order_items tables

Revision ID: 20260127_rm_fact_orders
Revises: 20260126_tb_cols
Create Date: 2026-01-27

v4.19.0: 删除已废弃的 fact_orders 和 fact_order_items 表

原因：
- v4.6.0 DSS架构重构后，订单数据已迁移到 b_class.fact_{platform}_orders_{granularity} 表
- 所有新数据都存储在 b_class schema 下的按平台分表中
- fact_orders 和 fact_order_items 表已不再使用

注意：
- 删除前会检查表是否存在
- 如果有外键依赖，会先删除依赖关系
- 此迁移不可逆（downgrade 为空）
"""

from alembic import op
from sqlalchemy import text, inspect


revision = "20260127_rm_fact_orders"
down_revision = "20260126_tb_cols"
branch_labels = None
depends_on = None


def upgrade():
    """删除废弃的 fact_orders 和 fact_order_items 表"""
    conn = op.get_bind()
    
    # 检查表是否存在
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())
    
    # 删除 fact_order_items 表（先删除，因为可能有外键依赖 fact_orders）
    if "fact_order_items" in existing_tables:
        safe_print("[Migration] 删除废弃表: fact_order_items")
        # 检查是否有外键约束
        try:
            # 删除可能的外键约束
            op.execute(text("""
                DO $$ 
                DECLARE
                    r RECORD;
                BEGIN
                    FOR r IN (
                        SELECT constraint_name, table_name
                        FROM information_schema.table_constraints
                        WHERE constraint_type = 'FOREIGN KEY'
                        AND table_name = 'fact_order_items'
                    ) LOOP
                        EXECUTE 'ALTER TABLE ' || quote_ident(r.table_name) || 
                                ' DROP CONSTRAINT IF EXISTS ' || quote_ident(r.constraint_name);
                    END LOOP;
                END $$;
            """))
        except Exception as e:
            safe_print(f"[Migration] 删除外键约束时出错（可能不存在）: {e}")
        
        # 删除表
        op.execute(text("DROP TABLE IF EXISTS fact_order_items CASCADE;"))
        safe_print("[Migration] fact_order_items 表已删除")
    
    # 删除 fact_orders 表
    if "fact_orders" in existing_tables:
        safe_print("[Migration] 删除废弃表: fact_orders")
        # 检查是否有外键约束
        try:
            # 删除可能的外键约束
            op.execute(text("""
                DO $$ 
                DECLARE
                    r RECORD;
                BEGIN
                    FOR r IN (
                        SELECT constraint_name, table_name
                        FROM information_schema.table_constraints
                        WHERE constraint_type = 'FOREIGN KEY'
                        AND table_name = 'fact_orders'
                    ) LOOP
                        EXECUTE 'ALTER TABLE ' || quote_ident(r.table_name) || 
                                ' DROP CONSTRAINT IF EXISTS ' || quote_ident(r.constraint_name);
                    END LOOP;
                END $$;
            """))
        except Exception as e:
            safe_print(f"[Migration] 删除外键约束时出错（可能不存在）: {e}")
        
        # 删除表
        op.execute(text("DROP TABLE IF EXISTS fact_orders CASCADE;"))
        safe_print("[Migration] fact_orders 表已删除")
    
    safe_print("[Migration] 废弃表删除完成")


def downgrade():
    """不可逆操作，不提供回滚"""
    pass


def safe_print(text):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            safe_text = text.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)
