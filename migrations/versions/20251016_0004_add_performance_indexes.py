"""Add performance optimization indexes

Revision ID: 20251016_0004
Revises: 20251016_0003
Create Date: 2025-10-16 15:30:00

This migration adds additional indexes to optimize common query patterns:
- dim_products: status index for filtering active products
- fact_product_metrics: (platform, shop, sku) composite for single-product queries
- catalog_files: (status, first_seen_at) for time-ordered pending queries
- catalog_files: data_domain index for domain filtering
- fact_orders: payment_status and is_cancelled indexes
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251016_0004'
down_revision = '20251016_0003'
branch_labels = None
depends_on = None


def upgrade():
    """Add performance optimization indexes"""
    
    # 1. dim_products: Add status index for filtering
    op.create_index(
        'ix_dim_products_status',
        'dim_products',
        ['status'],
        unique=False
    )
    
    # 2. fact_product_metrics: Add composite index for single-product queries
    # This helps when querying all metrics for a specific product
    op.create_index(
        'ix_metrics_plat_shop_sku',
        'fact_product_metrics',
        ['platform_code', 'shop_id', 'platform_sku'],
        unique=False
    )
    
    # 3. catalog_files: Add composite index for time-ordered pending queries
    # This is critical for ingestion_worker.run_once() which queries:
    # WHERE status='pending' ORDER BY first_seen_at
    op.create_index(
        'ix_catalog_status_time',
        'catalog_files',
        ['status', 'first_seen_at'],
        unique=False
    )
    
    # 4. catalog_files: Add data_domain index for domain filtering
    op.create_index(
        'ix_catalog_domain',
        'catalog_files',
        ['data_domain'],
        unique=False
    )
    
    # 5. catalog_files: Add source index for filtering by data source
    op.create_index(
        'ix_catalog_source',
        'catalog_files',
        ['source'],
        unique=False
    )
    
    # 6. fact_orders: Add payment_status index
    op.create_index(
        'ix_fact_orders_payment_status',
        'fact_orders',
        ['payment_status'],
        unique=False
    )
    
    # 7. fact_orders: Add is_cancelled index for filtering
    op.create_index(
        'ix_fact_orders_is_cancelled',
        'fact_orders',
        ['is_cancelled'],
        unique=False
    )
    
    # 8. fact_orders: Add is_refunded index for filtering
    op.create_index(
        'ix_fact_orders_is_refunded',
        'fact_orders',
        ['is_refunded'],
        unique=False
    )
    
    # 9. dim_products: Add platform_code index for platform-level queries
    op.create_index(
        'ix_dim_products_platform',
        'dim_products',
        ['platform_code'],
        unique=False
    )


def downgrade():
    """Remove performance optimization indexes"""
    
    # Remove indexes in reverse order
    op.drop_index('ix_dim_products_platform', table_name='dim_products')
    op.drop_index('ix_fact_orders_is_refunded', table_name='fact_orders')
    op.drop_index('ix_fact_orders_is_cancelled', table_name='fact_orders')
    op.drop_index('ix_fact_orders_payment_status', table_name='fact_orders')
    op.drop_index('ix_catalog_source', table_name='catalog_files')
    op.drop_index('ix_catalog_domain', table_name='catalog_files')
    op.drop_index('ix_catalog_status_time', table_name='catalog_files')
    op.drop_index('ix_metrics_plat_shop_sku', table_name='fact_product_metrics')
    op.drop_index('ix_dim_products_status', table_name='dim_products')

