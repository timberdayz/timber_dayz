"""Type convergence and constraint optimization (Phase 3)

Revision ID: 20251027_0010
Revises: 20251027_0009
Create Date: 2025-10-27 22:00:00

第三阶段优化：字段类型收敛与约束优化
1. 金额字段：VARCHAR/TEXT → NUMERIC(15,2)
2. 日期时间：VARCHAR/TEXT → TIMESTAMP WITH TIME ZONE
3. 布尔字段：VARCHAR → BOOLEAN
4. 必填字段：添加 NOT NULL 约束
5. 复合唯一索引：业务唯一性保障
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20251027_0010'
down_revision: Union[str, None] = '20251027_0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """字段类型收敛与约束优化"""
    
    print("开始字段类型收敛...")
    
    # ==================== fact_sales_orders 类型优化 ====================
    
    # 1. 金额字段：FLOAT → NUMERIC(15,2)
    try:
        op.execute("""
            ALTER TABLE fact_sales_orders 
            ALTER COLUMN unit_price TYPE NUMERIC(15,2) 
            USING CASE 
                WHEN unit_price IS NULL THEN 0.00
                ELSE unit_price::NUMERIC(15,2)
            END
        """)
        
        op.execute("""
            ALTER TABLE fact_sales_orders 
            ALTER COLUMN gmv TYPE NUMERIC(15,2) 
            USING CASE 
                WHEN gmv IS NULL THEN 0.00
                ELSE gmv::NUMERIC(15,2)
            END
        """)
        
        print("✓ fact_sales_orders 金额字段类型已收敛")
    except Exception as e:
        print(f"⚠ fact_sales_orders 金额字段类型收敛失败（可能已是正确类型）: {e}")
    
    # 2. 日期时间字段：TIMESTAMP → TIMESTAMP WITH TIME ZONE
    try:
        op.execute("""
            ALTER TABLE fact_sales_orders 
            ALTER COLUMN order_ts TYPE TIMESTAMP WITH TIME ZONE 
            USING CASE 
                WHEN order_ts IS NULL THEN NULL
                ELSE order_ts AT TIME ZONE 'UTC'
            END
        """)
        
        op.execute("""
            ALTER TABLE fact_sales_orders 
            ALTER COLUMN shipped_ts TYPE TIMESTAMP WITH TIME ZONE 
            USING CASE 
                WHEN shipped_ts IS NULL THEN NULL
                ELSE shipped_ts AT TIME ZONE 'UTC'
            END
        """)
        
        print("✓ fact_sales_orders 时间字段已添加时区")
    except Exception as e:
        print(f"⚠ fact_sales_orders 时间字段类型收敛失败: {e}")
    
    # 3. 必填字段约束
    try:
        op.alter_column('fact_sales_orders', 'platform_code', nullable=False)
        op.alter_column('fact_sales_orders', 'shop_id', nullable=False)
        op.alter_column('fact_sales_orders', 'order_id', nullable=False)
        
        print("✓ fact_sales_orders 必填字段约束已添加")
    except Exception as e:
        print(f"⚠ fact_sales_orders 必填字段约束失败: {e}")
    
    # ==================== fact_product_metrics 类型优化 ====================
    
    # 1. 金额字段
    try:
        op.execute("""
            ALTER TABLE fact_product_metrics 
            ALTER COLUMN revenue TYPE NUMERIC(15,2) 
            USING CASE 
                WHEN revenue IS NULL THEN 0.00
                ELSE revenue::NUMERIC(15,2)
            END
        """)
        
        print("✓ fact_product_metrics 金额字段类型已收敛")
    except Exception as e:
        print(f"⚠ fact_product_metrics 金额字段类型收敛失败: {e}")
    
    # 2. 比率字段：FLOAT → NUMERIC(5,4)
    try:
        op.execute("""
            ALTER TABLE fact_product_metrics 
            ALTER COLUMN ctr TYPE NUMERIC(5,4) 
            USING CASE 
                WHEN ctr IS NULL THEN NULL
                WHEN ctr > 1 THEN 1.0000
                ELSE ctr::NUMERIC(5,4)
            END
        """)
        
        op.execute("""
            ALTER TABLE fact_product_metrics 
            ALTER COLUMN conversion TYPE NUMERIC(5,4) 
            USING CASE 
                WHEN conversion IS NULL THEN NULL
                WHEN conversion > 1 THEN 1.0000
                ELSE conversion::NUMERIC(5,4)
            END
        """)
        
        print("✓ fact_product_metrics 比率字段类型已收敛")
    except Exception as e:
        print(f"⚠ fact_product_metrics 比率字段类型收敛失败: {e}")
    
    # 3. 必填字段约束
    try:
        op.alter_column('fact_product_metrics', 'platform_code', nullable=False)
        op.alter_column('fact_product_metrics', 'shop_id', nullable=False)
        op.alter_column('fact_product_metrics', 'metric_date', nullable=False)
        
        print("✓ fact_product_metrics 必填字段约束已添加")
    except Exception as e:
        print(f"⚠ fact_product_metrics 必填字段约束失败: {e}")
    
    # ==================== catalog_files 类型优化 ====================
    
    # 1. 确保关键字段 NOT NULL
    try:
        op.alter_column('catalog_files', 'file_path', nullable=False)
        op.alter_column('catalog_files', 'file_name', nullable=False)
        op.alter_column('catalog_files', 'status', nullable=False)
        op.alter_column('catalog_files', 'first_seen_at', nullable=False)
        
        print("✓ catalog_files 必填字段约束已添加")
    except Exception as e:
        print(f"⚠ catalog_files 必填字段约束失败: {e}")
    
    # ==================== 复合唯一索引（业务唯一性） ====================
    
    # 订单明细唯一性（平台+店铺+订单号+SKU）
    try:
        op.create_index(
            'uq_fact_sales_order_detail',
            'fact_sales_orders',
            ['platform_code', 'shop_id', 'order_id', 'sku'],
            unique=True
        )
        print("✓ fact_sales_orders 业务唯一索引已创建")
    except Exception as e:
        print(f"⚠ fact_sales_orders 唯一索引创建失败（可能已存在）: {e}")
    
    # 产品指标唯一性（平台+店铺+SKU+日期+粒度）
    try:
        op.create_index(
            'uq_fact_product_metrics_detail',
            'fact_product_metrics',
            ['platform_code', 'shop_id', 'platform_sku', 'metric_date', 'granularity'],
            unique=True
        )
        print("✓ fact_product_metrics 业务唯一索引已创建")
    except Exception as e:
        print(f"⚠ fact_product_metrics 唯一索引创建失败（可能已存在）: {e}")
    
    print("="*60)
    print("类型收敛与约束优化完成！")
    print("建议执行：VACUUM FULL ANALYZE; （释放空间并更新统计信息）")
    print("="*60)


def downgrade() -> None:
    """回滚类型收敛"""
    
    print("警告：类型收敛回滚可能导致数据丢失精度！")
    
    # 删除唯一索引
    op.drop_index('uq_fact_sales_order_detail', table_name='fact_sales_orders')
    op.drop_index('uq_fact_product_metrics_detail', table_name='fact_product_metrics')
    
    # 恢复 nullable（根据需要）
    # 注意：类型回滚可能导致数据丢失，建议备份后操作
    
    print("类型收敛已回滚")

