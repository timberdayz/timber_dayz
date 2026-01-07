"""init unified star schema

Revision ID: 20250925_0001
Revises: 
Create Date: 2025-09-25 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20250925_0001'
down_revision: Union[str, None] = '0af13b84ba3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # dim_platforms
    op.create_table(
        'dim_platforms',
        sa.Column('platform_code', sa.String(length=32), primary_key=True),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('name', name='uq_dim_platforms_name'),
    )

    # dim_shops
    op.create_table(
        'dim_shops',
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=64), nullable=False),
        sa.Column('shop_slug', sa.String(length=128), nullable=True),
        sa.Column('shop_name', sa.String(length=256), nullable=True),
        sa.Column('region', sa.String(length=16), nullable=True),
        sa.Column('currency', sa.String(length=8), nullable=True),
        sa.Column('timezone', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('platform_code', 'shop_id'),
        sa.ForeignKeyConstraint(['platform_code'], ['dim_platforms.platform_code'], ondelete='CASCADE'),
    )
    op.create_index('ix_dim_shops_platform_shop', 'dim_shops', ['platform_code', 'shop_id'])
    op.create_index('ix_dim_shops_platform_slug', 'dim_shops', ['platform_code', 'shop_slug'])

    # dim_products
    op.create_table(
        'dim_products',
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=64), nullable=False),
        sa.Column('platform_sku', sa.String(length=128), nullable=False),
        sa.Column('product_title', sa.String(length=512), nullable=True),
        sa.Column('category', sa.String(length=128), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('platform_code', 'shop_id', 'platform_sku'),
    )
    op.create_index('ix_dim_products_platform_shop', 'dim_products', ['platform_code', 'shop_id'])

    # dim_currency_rates
    op.create_table(
        'dim_currency_rates',
        sa.Column('rate_date', sa.Date(), nullable=False),
        sa.Column('base_currency', sa.String(length=8), nullable=False),
        sa.Column('quote_currency', sa.String(length=8), nullable=False),
        sa.Column('rate', sa.Float(), nullable=False),
        sa.Column('source', sa.String(length=64), nullable=True),
        sa.Column('fetched_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('rate_date', 'base_currency', 'quote_currency'),
    )
    op.create_index('ix_currency_base_quote', 'dim_currency_rates', ['base_currency', 'quote_currency'])

    # fact_orders
    op.create_table(
        'fact_orders',
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=64), nullable=False),
        sa.Column('order_id', sa.String(length=128), nullable=False),
        sa.Column('order_time_utc', sa.DateTime(), nullable=True),
        sa.Column('order_date_local', sa.Date(), nullable=True),
        sa.Column('currency', sa.String(length=8), nullable=True),
        sa.Column('subtotal', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('subtotal_rmb', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('shipping_fee', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('shipping_fee_rmb', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('tax_amount', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('tax_amount_rmb', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('discount_amount', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('discount_amount_rmb', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('total_amount', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('total_amount_rmb', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('payment_method', sa.String(length=64), nullable=True),
        sa.Column('payment_status', sa.String(length=32), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('order_status', sa.String(length=32), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('shipping_status', sa.String(length=32), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('delivery_status', sa.String(length=32), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('is_cancelled', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('is_refunded', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('refund_amount', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('refund_amount_rmb', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('buyer_id', sa.String(length=128), nullable=True),
        sa.Column('buyer_name', sa.String(length=256), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('platform_code', 'shop_id', 'order_id'),
        sa.ForeignKeyConstraint(['platform_code', 'shop_id'], ['dim_shops.platform_code', 'dim_shops.shop_id']),
    )
    op.create_index('ix_fact_orders_plat_shop_date', 'fact_orders', ['platform_code', 'shop_id', 'order_date_local'])
    op.create_index('ix_fact_orders_status', 'fact_orders', ['platform_code', 'shop_id', 'order_status'])

    # fact_order_items
    op.create_table(
        'fact_order_items',
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=64), nullable=False),
        sa.Column('order_id', sa.String(length=128), nullable=False),
        sa.Column('platform_sku', sa.String(length=128), nullable=False),
        sa.Column('product_title', sa.String(length=512), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('currency', sa.String(length=8), nullable=True),
        sa.Column('unit_price', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('unit_price_rmb', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('line_amount', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('line_amount_rmb', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('platform_code', 'shop_id', 'order_id', 'platform_sku'),
        sa.ForeignKeyConstraint(['platform_code', 'shop_id', 'order_id'], ['fact_orders.platform_code', 'fact_orders.shop_id', 'fact_orders.order_id']),
    )
    op.create_index('ix_fact_items_plat_shop_order', 'fact_order_items', ['platform_code', 'shop_id', 'order_id'])
    op.create_index('ix_fact_items_plat_shop_sku', 'fact_order_items', ['platform_code', 'shop_id', 'platform_sku'])

    # fact_product_metrics
    op.create_table(
        'fact_product_metrics',
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=64), nullable=False),
        sa.Column('platform_sku', sa.String(length=128), nullable=False),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('metric_type', sa.String(length=64), nullable=False),
        sa.Column('granularity', sa.String(length=16), nullable=False, server_default=sa.text("'daily'")),
        sa.Column('metric_value', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('currency', sa.String(length=8), nullable=True),
        sa.Column('metric_value_rmb', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('platform_code', 'shop_id', 'platform_sku', 'metric_date', 'metric_type'),
        sa.ForeignKeyConstraint(['platform_code', 'shop_id', 'platform_sku'], ['dim_products.platform_code', 'dim_products.shop_id', 'dim_products.platform_sku']),
    )
    op.create_index('ix_metrics_plat_shop_date_gran', 'fact_product_metrics', ['platform_code', 'shop_id', 'metric_date', 'granularity'])
    op.create_index('ix_metrics_plat_shop_type', 'fact_product_metrics', ['platform_code', 'shop_id', 'metric_type'])

    # catalog_files
    op.create_table(
        'catalog_files',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('file_path', sa.String(length=1024), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('source', sa.String(length=64), nullable=False, server_default=sa.text("'temp/outputs'")),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('file_hash', sa.String(length=64), nullable=True),
        sa.Column('platform_code', sa.String(length=32), nullable=True),
        sa.Column('shop_id', sa.String(length=64), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=True),
        sa.Column('granularity', sa.String(length=16), nullable=True),
        sa.Column('date_from', sa.Date(), nullable=True),
        sa.Column('date_to', sa.Date(), nullable=True),
        sa.Column('file_metadata', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(), nullable=False),
        sa.Column('last_processed_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('file_hash', name='uq_catalog_files_hash'),
    )
    op.create_index('ix_catalog_files_status', 'catalog_files', ['status'])
    op.create_index('ix_catalog_files_platform_shop', 'catalog_files', ['platform_code', 'shop_id'])
    op.create_index('ix_catalog_files_dates', 'catalog_files', ['date_from', 'date_to'])


def downgrade() -> None:
    op.drop_index('ix_catalog_files_dates', table_name='catalog_files')
    op.drop_index('ix_catalog_files_platform_shop', table_name='catalog_files')
    op.drop_index('ix_catalog_files_status', table_name='catalog_files')
    op.drop_table('catalog_files')

    op.drop_index('ix_metrics_plat_shop_type', table_name='fact_product_metrics')
    op.drop_index('ix_metrics_plat_shop_date_gran', table_name='fact_product_metrics')
    op.drop_table('fact_product_metrics')

    op.drop_index('ix_fact_items_plat_shop_sku', table_name='fact_order_items')
    op.drop_index('ix_fact_items_plat_shop_order', table_name='fact_order_items')
    op.drop_table('fact_order_items')

    op.drop_index('ix_fact_orders_status', table_name='fact_orders')
    op.drop_index('ix_fact_orders_plat_shop_date', table_name='fact_orders')
    op.drop_table('fact_orders')

    op.drop_index('ix_currency_base_quote', table_name='dim_currency_rates')
    op.drop_table('dim_currency_rates')

    op.drop_index('ix_dim_products_platform_shop', table_name='dim_products')
    op.drop_table('dim_products')

    op.drop_index('ix_dim_shops_platform_slug', table_name='dim_shops')
    op.drop_index('ix_dim_shops_platform_shop', table_name='dim_shops')
    op.drop_table('dim_shops')

    op.drop_table('dim_platforms')

