"""Partition fact tables by month (Phase 3)

Revision ID: 20251027_0008
Revises: 20251027_0007
Create Date: 2025-10-27 21:00:00

第三阶段优化：事实表按月 RANGE 分区
1. fact_sales_orders 按 order_date 月分区
2. fact_product_metrics 按 metric_date 月分区
3. 自动创建2024-2026年月分区
4. 每分区本地索引优化

注意：此迁移需要在低峰期（凌晨2-4点）执行，会锁表
"""
from typing import Sequence, Union
from datetime import date, timedelta

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20251027_0008'
down_revision: Union[str, None] = '20251027_0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级到分区表"""
    
    print("警告：此操作将重建事实表为分区表，请在低峰期执行！")
    print("开始分区迁移...")
    
    # ==================== fact_sales_orders 分区 ====================
    
    # 1. 重命名现有表
    op.rename_table('fact_sales_orders', 'fact_sales_orders_old')
    
    # 2. 创建分区父表
    # [FIX] PostgreSQL分区表要求：主键必须包含所有分区键列
    # 原主键是 id，分区键是 order_date，需要改为复合主键 (id, order_date)
    op.execute("""
        CREATE TABLE fact_sales_orders (
            LIKE fact_sales_orders_old INCLUDING DEFAULTS INCLUDING INDEXES
        ) PARTITION BY RANGE (order_date)
    """)
    
    # [FIX] 删除旧主键和唯一约束（如果存在），添加包含分区键的复合主键和唯一约束
    op.execute("""
        DO $$
        BEGIN
            -- 删除旧主键（如果存在）
            IF EXISTS (
                SELECT 1 FROM pg_constraint 
                WHERE conname = 'fact_sales_orders_pkey' 
                AND conrelid = 'fact_sales_orders'::regclass
            ) THEN
                ALTER TABLE fact_sales_orders DROP CONSTRAINT fact_sales_orders_pkey;
            END IF;
            
            -- 删除旧唯一约束（如果存在）- PostgreSQL分区表要求唯一约束必须包含分区键
            IF EXISTS (
                SELECT 1 FROM pg_constraint 
                WHERE conname = 'uq_fact_sales_orders_order' 
                AND conrelid = 'fact_sales_orders'::regclass
            ) THEN
                ALTER TABLE fact_sales_orders DROP CONSTRAINT uq_fact_sales_orders_order;
            END IF;
            
            -- 添加新的复合主键（包含分区键 order_date）
            ALTER TABLE fact_sales_orders 
            ADD PRIMARY KEY (id, order_date);
            
            -- 添加新的唯一约束（包含分区键 order_date）
            ALTER TABLE fact_sales_orders 
            ADD CONSTRAINT uq_fact_sales_orders_order 
            UNIQUE (platform_code, shop_id, order_id, order_date);
        END $$;
    """)
    
    # [FIX] 确保 order_date 列不为 NULL（分区键不能为 NULL）
    op.execute("""
        ALTER TABLE fact_sales_orders 
        ALTER COLUMN order_date SET NOT NULL;
    """)
    
    # 3. 创建月分区（2024-2026）
    start_year = 2024
    end_year = 2026
    
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            partition_name = f"fact_sales_orders_y{year}m{month:02d}"
            
            # 计算分区边界
            month_start = date(year, month, 1)
            if month == 12:
                month_end = date(year + 1, 1, 1)
            else:
                month_end = date(year, month + 1, 1)
            
            # 创建分区
            op.execute(f"""
                CREATE TABLE {partition_name}
                PARTITION OF fact_sales_orders
                FOR VALUES FROM ('{month_start}') TO ('{month_end}')
            """)
            
            # 创建本地索引
            op.execute(f"""
                CREATE INDEX idx_{partition_name}_shop_date 
                ON {partition_name} (shop_id, order_date)
            """)
            
            op.execute(f"""
                CREATE INDEX idx_{partition_name}_platform_shop 
                ON {partition_name} (platform_code, shop_id)
            """)
    
    # 4. 迁移数据（从旧表到分区表）
    # [FIX] 确保只迁移 order_date 不为 NULL 的记录（分区键不能为 NULL）
    op.execute("""
        INSERT INTO fact_sales_orders 
        SELECT * FROM fact_sales_orders_old
        WHERE order_date IS NOT NULL
    """)
    
    # [FIX] 检查是否有 order_date 为 NULL 的记录需要处理
    op.execute("""
        DO $$
        DECLARE
            null_count INTEGER;
        BEGIN
            SELECT COUNT(*) INTO null_count 
            FROM fact_sales_orders_old 
            WHERE order_date IS NULL;
            
            IF null_count > 0 THEN
                RAISE WARNING '发现 % 条 order_date 为 NULL 的记录，已跳过迁移', null_count;
            END IF;
        END $$;
    """)
    
    print("fact_sales_orders 分区迁移完成")
    
    # ==================== fact_product_metrics 分区 ====================
    
    # 1. 重命名现有表
    op.rename_table('fact_product_metrics', 'fact_product_metrics_old')
    
    # 2. 创建分区父表
    # [NOTE] fact_product_metrics 的主键已经包含 metric_date，符合分区表要求
    op.execute("""
        CREATE TABLE fact_product_metrics (
            LIKE fact_product_metrics_old INCLUDING ALL
        ) PARTITION BY RANGE (metric_date)
    """)
    
    # [FIX] 确保 metric_date 列不为 NULL（分区键不能为 NULL）
    op.execute("""
        ALTER TABLE fact_product_metrics 
        ALTER COLUMN metric_date SET NOT NULL;
    """)
    
    # 3. 创建月分区（2024-2026）
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            partition_name = f"fact_product_metrics_y{year}m{month:02d}"
            
            month_start = date(year, month, 1)
            if month == 12:
                month_end = date(year + 1, 1, 1)
            else:
                month_end = date(year, month + 1, 1)
            
            # 创建分区
            op.execute(f"""
                CREATE TABLE {partition_name}
                PARTITION OF fact_product_metrics
                FOR VALUES FROM ('{month_start}') TO ('{month_end}')
            """)
            
            # 本地索引
            op.execute(f"""
                CREATE INDEX idx_{partition_name}_shop_date 
                ON {partition_name} (shop_id, metric_date)
            """)
            
            op.execute(f"""
                CREATE INDEX idx_{partition_name}_platform_sku 
                ON {partition_name} (platform_code, platform_sku, metric_date)
            """)
    
    # 4. 迁移数据
    # [FIX] 确保只迁移 metric_date 不为 NULL 的记录（分区键不能为 NULL）
    op.execute("""
        INSERT INTO fact_product_metrics 
        SELECT * FROM fact_product_metrics_old
        WHERE metric_date IS NOT NULL
    """)
    
    # [FIX] 检查是否有 metric_date 为 NULL 的记录需要处理
    op.execute("""
        DO $$
        DECLARE
            null_count INTEGER;
        BEGIN
            SELECT COUNT(*) INTO null_count 
            FROM fact_product_metrics_old 
            WHERE metric_date IS NULL;
            
            IF null_count > 0 THEN
                RAISE WARNING '发现 % 条 metric_date 为 NULL 的记录，已跳过迁移', null_count;
            END IF;
        END $$;
    """)
    
    print("fact_product_metrics 分区迁移完成")
    print("分区表创建完成！旧表保留为 *_old，可手动验证后删除")


def downgrade() -> None:
    """回滚分区表（恢复为普通表）"""
    
    print("警告：此操作将删除分区表并恢复旧表！")
    
    # 删除分区表
    op.drop_table('fact_sales_orders')
    op.drop_table('fact_product_metrics')
    
    # 恢复旧表
    op.rename_table('fact_sales_orders_old', 'fact_sales_orders')
    op.rename_table('fact_product_metrics_old', 'fact_product_metrics')
    
    print("分区表已回滚")

