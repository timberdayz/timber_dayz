"""add_backup_records_table

Revision ID: v4_20_0_backup_records
Revises: v4_20_0_security_config
Create Date: 2026-01-08

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'v4_20_0_backup_records'
down_revision = 'v4_20_0_security_config'
branch_labels = None
depends_on = None


def upgrade():
    # 创建备份记录表
    op.create_table(
        'backup_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('backup_type', sa.String(length=32), nullable=False),
        sa.Column('backup_path', sa.String(length=512), nullable=False),
        sa.Column('backup_size', sa.BIGINT(), nullable=False),
        sa.Column('checksum', sa.String(length=64), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['dim_users.user_id'], name='fk_backup_records_created_by'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 创建索引
    op.create_index('ix_backup_records_status', 'backup_records', ['status'])
    op.create_index('ix_backup_records_created_at', 'backup_records', ['created_at'])


def downgrade():
    # 删除索引
    op.drop_index('ix_backup_records_created_at', table_name='backup_records')
    op.drop_index('ix_backup_records_status', table_name='backup_records')
    
    # 删除表
    op.drop_table('backup_records')
