"""Merge all migration heads into single head

Revision ID: 20260111_merge_all_heads
Revises: 20260110_complete_schema_base, 20251105_204200, 20251105_add_image_url, 20250131_mv_attach_rate, 20250131_add_c_class_mv_indexes
Create Date: 2026-01-11

合并所有迁移分支为单一头，解决 "Multiple head revisions" 错误。

合并的分支：
1. 20260110_complete_schema_base - 完整表结构基础迁移
2. 20251105_204200 - 物化视图刷新日志表
3. 20251105_add_image_url - 产品指标图片URL字段
4. 20250131_mv_attach_rate - 店铺连带率物化视图
5. 20250131_add_c_class_mv_indexes - C类数据物化视图索引

注意：此迁移不执行任何数据库操作，仅用于合并分支。
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260111_merge_all_heads'
down_revision = (
    '20260110_complete_schema_base',
    '20251105_204200',
    '20251105_add_image_url',
    '20250131_mv_attach_rate',
    '20250131_add_c_class_mv_indexes'
)
branch_labels = None
depends_on = None


def upgrade():
    """合并迁移 - 无需执行任何操作"""
    print("[INFO] Merging all migration heads into single head")
    print("[INFO] This migration is a merge point and performs no database operations")
    pass


def downgrade():
    """回滚合并 - 无需执行任何操作"""
    print("[INFO] Unmerging migration heads")
    print("[INFO] This migration is a merge point and performs no database operations")
    pass
