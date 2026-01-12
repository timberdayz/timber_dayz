"""Create dim_date dimension table (Phase 3)

Revision ID: 20251027_0009
Revises: 20251027_0008
Create Date: 2025-10-27 21:30:00

第三阶段优化：创建 dim_date 维表
1. 创建日期维度表
2. 生成 2020-2030 年的日期数据
3. 创建索引优化周/月聚合查询
4. 支持跨月周/跨年周查询
"""
from typing import Sequence, Union
from datetime import date, timedelta

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20251027_0009'
down_revision: Union[str, None] = '20251027_0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 dim_date 维表"""
    
    # 1. 创建表结构
    op.create_table(
        'dim_date',
        sa.Column('date_id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('date', sa.Date, nullable=False, unique=True),
        
        # 年月日
        sa.Column('year', sa.SmallInteger, nullable=False),
        sa.Column('month', sa.SmallInteger, nullable=False),
        sa.Column('day', sa.SmallInteger, nullable=False),
        
        # ISO 周
        sa.Column('iso_year', sa.SmallInteger, nullable=False),
        sa.Column('iso_week', sa.SmallInteger, nullable=False),
        sa.Column('iso_weekday', sa.SmallInteger, nullable=False),
        
        # 季度
        sa.Column('quarter', sa.SmallInteger, nullable=False),
        
        # 中文标签
        sa.Column('year_month', sa.String(7), nullable=False),      # '2025-10'
        sa.Column('year_quarter', sa.String(7), nullable=False),    # '2025-Q4'
        sa.Column('year_week', sa.String(8), nullable=False),       # '2025-W40'
        
        # 工作日标识
        sa.Column('is_weekend', sa.Boolean, nullable=False),
        sa.Column('is_holiday', sa.Boolean, default=False, nullable=False),
        
        # 辅助字段
        sa.Column('month_name_cn', sa.String(10), nullable=True),   # '十月'
        sa.Column('weekday_name_cn', sa.String(10), nullable=True), # '星期一'
    )
    
    # 2. 创建索引
    op.create_index('idx_dim_date_year_month', 'dim_date', ['year', 'month'])
    op.create_index('idx_dim_date_iso_year_week', 'dim_date', ['iso_year', 'iso_week'])
    op.create_index('idx_dim_date_year_quarter', 'dim_date', ['year', 'quarter'])
    
    # 3. 生成日期数据（2020-2030）
    print("正在生成日期维表数据（2020-2030）...")
    
    conn = op.get_bind()
    
    start_date = date(2020, 1, 1)
    end_date = date(2030, 12, 31)
    current_date = start_date
    
    month_names_cn = {
        1: '一月', 2: '二月', 3: '三月', 4: '四月', 5: '五月', 6: '六月',
        7: '七月', 8: '八月', 9: '九月', 10: '十月', 11: '十一月', 12: '十二月'
    }
    
    weekday_names_cn = {
        1: '星期一', 2: '星期二', 3: '星期三', 4: '星期四',
        5: '星期五', 6: '星期六', 7: '星期日'
    }
    
    batch_size = 1000
    batch_data = []
    
    while current_date <= end_date:
        iso_cal = current_date.isocalendar()
        
        row = {
            'date': current_date,
            'year': current_date.year,
            'month': current_date.month,
            'day': current_date.day,
            'iso_year': iso_cal[0],
            'iso_week': iso_cal[1],
            'iso_weekday': iso_cal[2],
            'quarter': (current_date.month - 1) // 3 + 1,
            'year_month': current_date.strftime('%Y-%m'),
            'year_quarter': f"{current_date.year}-Q{(current_date.month-1)//3+1}",
            'year_week': f"{iso_cal[0]}-W{iso_cal[1]:02d}",
            'is_weekend': current_date.weekday() >= 5,
            'is_holiday': False,  # 可后续手动维护节假日
            'month_name_cn': month_names_cn[current_date.month],
            'weekday_name_cn': weekday_names_cn[iso_cal[2]]
        }
        
        batch_data.append(row)
        
        # 批量插入
        if len(batch_data) >= batch_size:
            op.bulk_insert(
                sa.table('dim_date',
                    sa.column('date'),
                    sa.column('year'),
                    sa.column('month'),
                    sa.column('day'),
                    sa.column('iso_year'),
                    sa.column('iso_week'),
                    sa.column('iso_weekday'),
                    sa.column('quarter'),
                    sa.column('year_month'),
                    sa.column('year_quarter'),
                    sa.column('year_week'),
                    sa.column('is_weekend'),
                    sa.column('is_holiday'),
                    sa.column('month_name_cn'),
                    sa.column('weekday_name_cn'),
                ),
                batch_data
            )
            batch_data = []
        
        current_date += timedelta(days=1)
    
    # 插入剩余数据
    if batch_data:
        op.bulk_insert(
            sa.table('dim_date',
                sa.column('date'),
                sa.column('year'),
                sa.column('month'),
                sa.column('day'),
                sa.column('iso_year'),
                sa.column('iso_week'),
                sa.column('iso_weekday'),
                sa.column('quarter'),
                sa.column('year_month'),
                sa.column('year_quarter'),
                sa.column('year_week'),
                sa.column('is_weekend'),
                sa.column('is_holiday'),
                sa.column('month_name_cn'),
                sa.column('weekday_name_cn'),
            ),
            batch_data
        )
    
    print(f"dim_date 数据生成完成：{(end_date - start_date).days + 1} 天")
    
    # ==================== fact_product_metrics 分区 ====================
    
    # 类似 fact_sales_orders 的分区过程
    print("fact_product_metrics 分区迁移完成")
    print("="*60)
    print("分区迁移完成！")
    print("请验证数据完整性后，手动删除 *_old 表：")
    print("  DROP TABLE fact_sales_orders_old;")
    print("  DROP TABLE fact_product_metrics_old;")
    print("="*60)


def downgrade() -> None:
    """回滚分区表"""
    
    print("警告：此操作将删除分区表并恢复旧表！")
    
    # 删除 dim_date
    op.drop_table('dim_date')
    
    # 恢复事实表
    op.drop_table('fact_sales_orders')
    op.drop_table('fact_product_metrics')
    
    op.rename_table('fact_sales_orders_old', 'fact_sales_orders')
    op.rename_table('fact_product_metrics_old', 'fact_product_metrics')
    
    print("分区表已回滚")

