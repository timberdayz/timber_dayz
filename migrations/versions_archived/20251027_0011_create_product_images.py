"""create product_images table for v3.0

Revision ID: 20251027_0011
Revises: 20251027_0010
Create Date: 2025-10-27

产品图片表：存储产品图片URL和元数据
支持SKU级别的图片管理
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251027_0011'
down_revision = '20251027_0010'
branch_labels = None
depends_on = None


def upgrade():
    """创建product_images表"""
    
    # 创建product_images表
    op.create_table(
        'product_images',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        
        # 产品标识（三元组：平台+店铺+SKU）
        sa.Column('platform_code', sa.String(32), nullable=False, comment='平台编码'),
        sa.Column('shop_id', sa.String(64), nullable=False, comment='店铺ID'),
        sa.Column('platform_sku', sa.String(128), nullable=False, comment='平台SKU'),
        
        # 图片URL
        sa.Column('image_url', sa.String(1024), nullable=False, comment='原图URL'),
        sa.Column('thumbnail_url', sa.String(1024), nullable=False, comment='缩略图URL'),
        
        # 图片类型和顺序
        sa.Column('image_type', sa.String(20), nullable=False, default='main', comment='图片类型: main/detail/spec'),
        sa.Column('image_order', sa.Integer(), nullable=False, default=0, comment='显示顺序'),
        
        # 图片元数据
        sa.Column('file_size', sa.Integer(), nullable=True, comment='文件大小(bytes)'),
        sa.Column('width', sa.Integer(), nullable=True, comment='图片宽度(px)'),
        sa.Column('height', sa.Integer(), nullable=True, comment='图片高度(px)'),
        sa.Column('format', sa.String(10), nullable=True, comment='图片格式: JPEG/PNG/GIF'),
        
        # 质量评分（预留，v4.0 AI识别）
        sa.Column('quality_score', sa.Float(), nullable=True, comment='图片质量评分(0-100)'),
        sa.Column('is_main_image', sa.Boolean(), nullable=False, default=False, comment='是否主图'),
        
        # 时间戳
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.func.now(), comment='创建时间'),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now(), comment='更新时间'),
        
        # 外键约束（注释掉，因为dim_products暂不存在）
        # sa.ForeignKeyConstraint(
        #     ['platform_code', 'shop_id', 'platform_sku'],
        #     ['dim_products.platform_code', 'dim_products.shop_id', 'dim_products.platform_sku'],
        #     name='fk_product_images_product'
        # ),
        
        comment='产品图片表：存储产品图片URL和元数据'
    )
    
    # 索引：按SKU查询
    op.create_index(
        'idx_product_images_sku',
        'product_images',
        ['platform_sku'],
        comment='按SKU查询'
    )
    
    # 索引：按平台+店铺+SKU查询
    op.create_index(
        'idx_product_images_product',
        'product_images',
        ['platform_code', 'shop_id', 'platform_sku'],
        comment='按产品三元组查询'
    )
    
    # 索引：查询主图
    op.create_index(
        'idx_product_images_main',
        'product_images',
        ['platform_sku', 'is_main_image'],
        postgresql_where=sa.text('is_main_image = TRUE'),
        comment='快速查询主图'
    )
    
    # 索引：按顺序排序
    op.create_index(
        'idx_product_images_order',
        'product_images',
        ['platform_sku', 'image_order'],
        comment='按顺序查询图片'
    )
    
    print("[V3.0] product_images表创建成功")


def downgrade():
    """删除product_images表"""
    
    # 删除索引
    op.drop_index('idx_product_images_order', table_name='product_images')
    op.drop_index('idx_product_images_main', table_name='product_images')
    op.drop_index('idx_product_images_product', table_name='product_images')
    op.drop_index('idx_product_images_sku', table_name='product_images')
    
    # 删除表
    op.drop_table('product_images')
    
    print("[V3.0] product_images表已删除")

