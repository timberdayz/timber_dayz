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
    """
    升级到分区表（已禁用）
    
    注意：此迁移已禁用，分区表作为性能优化功能，不影响核心业务。
    如需启用分区表，请手动执行此迁移或在低峰期执行。
    
    分区表迁移需要在低峰期（凌晨2-4点）执行，会锁表。
    建议在确认系统稳定后，由DBA手动执行。
    """
    # [DISABLED] 分区表迁移已禁用，作为性能优化功能，后续可手动执行
    # 如需启用，请取消下面的 pass 并恢复原始实现
    pass


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

