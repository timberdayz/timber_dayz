"""v4.7.0: 添加平台账号管理表

Revision ID: 20251213_platform_accounts
Revises: 20251211_v4_7_0_collection_task_granularity_optimization
Create Date: 2025-12-13

产品化升级：前端GUI账号管理，替代手动编辑local_accounts.py
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = '20251213_platform_accounts'
down_revision = 'collection_task_granularity_v470'
branch_labels = None
depends_on = None


def upgrade():
    """创建platform_accounts表"""
    op.create_table(
        'platform_accounts',
        # 主键和唯一标识
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('account_id', sa.String(length=100), nullable=False, comment='账号唯一标识'),
        
        # 账号基本信息
        sa.Column('parent_account', sa.String(length=100), nullable=True, comment='主账号（多店铺共用时填写）'),
        sa.Column('platform', sa.String(length=50), nullable=False, comment='平台代码'),
        sa.Column('store_name', sa.String(length=200), nullable=False, comment='店铺名称'),
        
        # 店铺信息
        sa.Column('shop_type', sa.String(length=50), nullable=True, comment='店铺类型: local/global'),
        sa.Column('shop_region', sa.String(length=50), nullable=True, comment='店铺区域: SG/MY/GLOBAL等'),
        
        # 登录信息（敏感）
        sa.Column('username', sa.String(length=200), nullable=False, comment='登录用户名'),
        sa.Column('password_encrypted', sa.Text(), nullable=False, comment='加密后的密码'),
        sa.Column('login_url', sa.Text(), nullable=True, comment='登录URL'),
        
        # 联系信息
        sa.Column('email', sa.String(length=200), nullable=True, comment='邮箱'),
        sa.Column('phone', sa.String(length=50), nullable=True, comment='手机号'),
        sa.Column('region', sa.String(length=50), nullable=True, server_default='CN', comment='账号注册地区'),
        sa.Column('currency', sa.String(length=10), nullable=True, server_default='CNY', comment='主货币'),
        
        # 能力配置（JSONB）
        sa.Column(
            'capabilities',
            JSONB,
            nullable=False,
            server_default=sa.text("'{\"orders\": true, \"products\": true, \"services\": true, \"analytics\": true, \"finance\": true, \"inventory\": true}'::jsonb"),
            comment='账号支持的数据域能力'
        ),
        
        # 状态和设置
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true', comment='是否启用'),
        sa.Column('proxy_required', sa.Boolean(), nullable=False, server_default='false', comment='是否需要代理'),
        sa.Column('notes', sa.Text(), nullable=True, comment='备注'),
        
        # 审计字段
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()'), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()'), comment='更新时间'),
        sa.Column('created_by', sa.String(length=100), nullable=True, comment='创建人'),
        sa.Column('updated_by', sa.String(length=100), nullable=True, comment='更新人'),
        
        # 扩展字段
        sa.Column('extra_config', JSONB, nullable=True, server_default='{}', comment='扩展配置'),
        
        # 约束
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_id', name='uq_platform_accounts_account_id')
    )
    
    # 创建索引
    op.create_index('ix_platform_accounts_platform', 'platform_accounts', ['platform'])
    op.create_index('ix_platform_accounts_parent', 'platform_accounts', ['parent_account'])
    op.create_index('ix_platform_accounts_enabled', 'platform_accounts', ['enabled'])
    op.create_index('ix_platform_accounts_shop_type', 'platform_accounts', ['shop_type'])
    
    print("[OK] platform_accounts表创建成功")
    print("[INFO] 提示：")
    print("   1. 使用前端界面管理账号：/account-management")
    print("   2. 从local_accounts.py导入：POST /api/accounts/import-from-local")
    print("   3. 密码将被加密存储，需配置ACCOUNT_ENCRYPTION_KEY环境变量")


def downgrade():
    """删除platform_accounts表"""
    op.drop_index('ix_platform_accounts_shop_type', table_name='platform_accounts')
    op.drop_index('ix_platform_accounts_enabled', table_name='platform_accounts')
    op.drop_index('ix_platform_accounts_parent', table_name='platform_accounts')
    op.drop_index('ix_platform_accounts_platform', table_name='platform_accounts')
    op.drop_table('platform_accounts')
    print("[OK] platform_accounts表已删除")

