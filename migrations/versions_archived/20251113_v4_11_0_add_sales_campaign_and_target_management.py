"""add_sales_campaign_and_target_management_tables_v4_11_0

Revision ID: v4_11_0_sales_campaign_target
Revises: v4_10_2_add_mv_display_field
Create Date: 2025-11-13 14:15:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'v4_11_0_sales_campaign_target'
down_revision = 'v4_10_2'  # 基于最新的迁移版本
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 销售战役管理表
    op.create_table(
        'sales_campaigns',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('campaign_name', sa.String(length=200), nullable=False, comment='战役名称'),
        sa.Column('campaign_type', sa.String(length=32), nullable=False, comment='战役类型：holiday/new_product/special_event'),
        sa.Column('start_date', sa.Date(), nullable=False, comment='开始日期'),
        sa.Column('end_date', sa.Date(), nullable=False, comment='结束日期'),
        sa.Column('target_amount', sa.Float(), nullable=False, server_default='0.0', comment='目标销售额（CNY）'),
        sa.Column('target_quantity', sa.Integer(), nullable=False, server_default='0', comment='目标订单数/销量'),
        sa.Column('actual_amount', sa.Float(), nullable=False, server_default='0.0', comment='实际销售额（CNY）'),
        sa.Column('actual_quantity', sa.Integer(), nullable=False, server_default='0', comment='实际订单数/销量'),
        sa.Column('achievement_rate', sa.Float(), nullable=False, server_default='0.0', comment='达成率（百分比）'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='pending', comment='状态：active/completed/pending/cancelled'),
        sa.Column('description', sa.Text(), nullable=True, comment='战役描述'),
        sa.Column('created_by', sa.String(length=64), nullable=True, comment='创建人'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('end_date >= start_date', name='chk_campaign_dates'),
        sa.CheckConstraint('target_amount >= 0', name='chk_campaign_amount'),
        sa.CheckConstraint('target_quantity >= 0', name='chk_campaign_quantity'),
    )
    op.create_index('ix_sales_campaigns_status', 'sales_campaigns', ['status'])
    op.create_index('ix_sales_campaigns_dates', 'sales_campaigns', ['start_date', 'end_date'])
    op.create_index('ix_sales_campaigns_type', 'sales_campaigns', ['campaign_type'])

    # 2. 销售战役参与店铺表
    op.create_table(
        'sales_campaign_shops',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('campaign_id', sa.Integer(), nullable=False),
        sa.Column('platform_code', sa.String(length=32), nullable=True),
        sa.Column('shop_id', sa.String(length=64), nullable=True),
        sa.Column('target_amount', sa.Float(), nullable=False, server_default='0.0', comment='目标销售额（CNY）'),
        sa.Column('target_quantity', sa.Integer(), nullable=False, server_default='0', comment='目标订单数/销量'),
        sa.Column('actual_amount', sa.Float(), nullable=False, server_default='0.0', comment='实际销售额（CNY）'),
        sa.Column('actual_quantity', sa.Integer(), nullable=False, server_default='0', comment='实际订单数/销量'),
        sa.Column('achievement_rate', sa.Float(), nullable=False, server_default='0.0', comment='达成率（百分比）'),
        sa.Column('rank', sa.Integer(), nullable=True, comment='排名'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['campaign_id'], ['sales_campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['platform_code', 'shop_id'], ['dim_shops.platform_code', 'dim_shops.shop_id'], name='fk_campaign_shop'),
        sa.UniqueConstraint('campaign_id', 'platform_code', 'shop_id', name='uq_campaign_shop'),
    )
    op.create_index('ix_campaign_shops_campaign', 'sales_campaign_shops', ['campaign_id'])
    op.create_index('ix_campaign_shops_shop', 'sales_campaign_shops', ['platform_code', 'shop_id'])

    # 3. 目标管理表
    op.create_table(
        'sales_targets',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('target_name', sa.String(length=200), nullable=False, comment='目标名称'),
        sa.Column('target_type', sa.String(length=32), nullable=False, comment='目标类型：shop/product/campaign'),
        sa.Column('period_start', sa.Date(), nullable=False, comment='开始时间'),
        sa.Column('period_end', sa.Date(), nullable=False, comment='结束时间'),
        sa.Column('target_amount', sa.Float(), nullable=False, server_default='0.0', comment='目标销售额（CNY）'),
        sa.Column('target_quantity', sa.Integer(), nullable=False, server_default='0', comment='目标订单数/销量'),
        sa.Column('achieved_amount', sa.Float(), nullable=False, server_default='0.0', comment='实际销售额（CNY）'),
        sa.Column('achieved_quantity', sa.Integer(), nullable=False, server_default='0', comment='实际订单数/销量'),
        sa.Column('achievement_rate', sa.Float(), nullable=False, server_default='0.0', comment='达成率（百分比）'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='active', comment='状态：active/completed/cancelled'),
        sa.Column('description', sa.Text(), nullable=True, comment='目标描述'),
        sa.Column('created_by', sa.String(length=64), nullable=True, comment='创建人'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('period_end >= period_start', name='chk_target_dates'),
        sa.CheckConstraint('target_amount >= 0', name='chk_target_amount'),
        sa.CheckConstraint('target_quantity >= 0', name='chk_target_quantity'),
    )
    op.create_index('ix_sales_targets_type', 'sales_targets', ['target_type'])
    op.create_index('ix_sales_targets_status', 'sales_targets', ['status'])
    op.create_index('ix_sales_targets_period', 'sales_targets', ['period_start', 'period_end'])

    # 4. 目标分解表
    op.create_table(
        'target_breakdown',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('target_id', sa.Integer(), nullable=False),
        sa.Column('breakdown_type', sa.String(length=32), nullable=False, comment='分解类型：shop/time'),
        sa.Column('platform_code', sa.String(length=32), nullable=True),
        sa.Column('shop_id', sa.String(length=64), nullable=True),
        sa.Column('period_start', sa.Date(), nullable=True, comment='周期开始'),
        sa.Column('period_end', sa.Date(), nullable=True, comment='周期结束'),
        sa.Column('period_label', sa.String(length=64), nullable=True, comment='周期标签，如\'第1周\'、\'2025-01\''),
        sa.Column('target_amount', sa.Float(), nullable=False, server_default='0.0', comment='目标销售额（CNY）'),
        sa.Column('target_quantity', sa.Integer(), nullable=False, server_default='0', comment='目标订单数/销量'),
        sa.Column('achieved_amount', sa.Float(), nullable=False, server_default='0.0', comment='实际销售额（CNY）'),
        sa.Column('achieved_quantity', sa.Integer(), nullable=False, server_default='0', comment='实际订单数/销量'),
        sa.Column('achievement_rate', sa.Float(), nullable=False, server_default='0.0', comment='达成率（百分比）'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['target_id'], ['sales_targets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['platform_code', 'shop_id'], ['dim_shops.platform_code', 'dim_shops.shop_id'], name='fk_breakdown_shop'),
        sa.CheckConstraint("breakdown_type IN ('shop', 'time')", name='chk_breakdown_type'),
    )
    op.create_index('ix_target_breakdown_target', 'target_breakdown', ['target_id'])
    op.create_index('ix_target_breakdown_shop', 'target_breakdown', ['platform_code', 'shop_id'])
    op.create_index('ix_target_breakdown_period', 'target_breakdown', ['period_start', 'period_end'])

    # 5. 店铺健康度评分表
    op.create_table(
        'shop_health_scores',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=64), nullable=False),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('granularity', sa.String(length=16), nullable=False, server_default='daily', comment='粒度：daily/weekly/monthly'),
        sa.Column('health_score', sa.Float(), nullable=False, server_default='0.0', comment='健康度总分（0-100）'),
        sa.Column('gmv_score', sa.Float(), nullable=False, server_default='0.0', comment='GMV得分'),
        sa.Column('conversion_score', sa.Float(), nullable=False, server_default='0.0', comment='转化得分'),
        sa.Column('inventory_score', sa.Float(), nullable=False, server_default='0.0', comment='库存得分'),
        sa.Column('service_score', sa.Float(), nullable=False, server_default='0.0', comment='服务得分'),
        sa.Column('gmv', sa.Float(), nullable=False, server_default='0.0', comment='GMV（CNY）'),
        sa.Column('conversion_rate', sa.Float(), nullable=False, server_default='0.0', comment='转化率（百分比）'),
        sa.Column('inventory_turnover', sa.Float(), nullable=False, server_default='0.0', comment='库存周转率'),
        sa.Column('customer_satisfaction', sa.Float(), nullable=False, server_default='0.0', comment='客户满意度（0-5分）'),
        sa.Column('risk_level', sa.String(length=16), nullable=False, server_default='low', comment='风险等级：low/medium/high'),
        sa.Column('risk_factors', postgresql.JSON(astext_type=sa.Text()), nullable=True, comment='风险因素列表'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['platform_code', 'shop_id'], ['dim_shops.platform_code', 'dim_shops.shop_id'], name='fk_shop_health'),
        sa.UniqueConstraint('platform_code', 'shop_id', 'metric_date', 'granularity', name='uq_shop_health'),
        sa.CheckConstraint('health_score >= 0 AND health_score <= 100', name='chk_health_score'),
        sa.CheckConstraint("risk_level IN ('low', 'medium', 'high')", name='chk_risk_level'),
    )
    op.create_index('ix_shop_health_shop', 'shop_health_scores', ['platform_code', 'shop_id'])
    op.create_index('ix_shop_health_date', 'shop_health_scores', ['metric_date'])
    op.create_index('ix_shop_health_score', 'shop_health_scores', ['health_score'])
    op.create_index('ix_shop_health_risk', 'shop_health_scores', ['risk_level'])

    # 6. 店铺预警提醒表
    op.create_table(
        'shop_alerts',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=64), nullable=False),
        sa.Column('alert_type', sa.String(length=64), nullable=False, comment='预警类型：inventory_turnover/conversion_rate/gmv_drop/...'),
        sa.Column('alert_level', sa.String(length=16), nullable=False, comment='预警级别：critical/warning/info'),
        sa.Column('title', sa.String(length=200), nullable=False, comment='预警标题'),
        sa.Column('message', sa.Text(), nullable=False, comment='预警内容'),
        sa.Column('metric_value', sa.Float(), nullable=True, comment='当前指标值'),
        sa.Column('threshold', sa.Float(), nullable=True, comment='阈值'),
        sa.Column('metric_unit', sa.String(length=32), nullable=True, comment='指标单位'),
        sa.Column('is_resolved', sa.Boolean(), nullable=False, server_default='false', comment='是否已解决'),
        sa.Column('resolved_at', sa.DateTime(), nullable=True, comment='解决时间'),
        sa.Column('resolved_by', sa.String(length=64), nullable=True, comment='解决人'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['platform_code', 'shop_id'], ['dim_shops.platform_code', 'dim_shops.shop_id'], name='fk_shop_alert'),
        sa.CheckConstraint("alert_level IN ('critical', 'warning', 'info')", name='chk_alert_level'),
    )
    op.create_index('ix_shop_alerts_shop', 'shop_alerts', ['platform_code', 'shop_id'])
    op.create_index('ix_shop_alerts_level', 'shop_alerts', ['alert_level'])
    op.create_index('ix_shop_alerts_resolved', 'shop_alerts', ['is_resolved'])
    op.create_index('ix_shop_alerts_created', 'shop_alerts', ['created_at'])

    # 7. 绩效评分表
    op.create_table(
        'performance_scores',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=64), nullable=False),
        sa.Column('period', sa.String(length=16), nullable=False, comment='考核周期，如\'2025-01\''),
        sa.Column('total_score', sa.Float(), nullable=False, server_default='0.0', comment='总分（0-100）'),
        sa.Column('sales_score', sa.Float(), nullable=False, server_default='0.0', comment='销售额得分（权重30%）'),
        sa.Column('profit_score', sa.Float(), nullable=False, server_default='0.0', comment='毛利得分（权重25%）'),
        sa.Column('key_product_score', sa.Float(), nullable=False, server_default='0.0', comment='重点产品得分（权重25%）'),
        sa.Column('operation_score', sa.Float(), nullable=False, server_default='0.0', comment='运营得分（权重20%）'),
        sa.Column('score_details', postgresql.JSON(astext_type=sa.Text()), nullable=True, comment='得分明细（JSON格式）'),
        sa.Column('rank', sa.Integer(), nullable=True, comment='排名'),
        sa.Column('performance_coefficient', sa.Float(), nullable=False, server_default='1.0', comment='绩效系数'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['platform_code', 'shop_id'], ['dim_shops.platform_code', 'dim_shops.shop_id'], name='fk_performance_shop'),
        sa.UniqueConstraint('platform_code', 'shop_id', 'period', name='uq_performance_shop_period'),
        sa.CheckConstraint('total_score >= 0 AND total_score <= 100', name='chk_total_score'),
    )
    op.create_index('ix_performance_shop', 'performance_scores', ['platform_code', 'shop_id'])
    op.create_index('ix_performance_period', 'performance_scores', ['period'])
    op.create_index('ix_performance_score', 'performance_scores', ['total_score'])
    op.create_index('ix_performance_rank', 'performance_scores', ['rank'])

    # 8. 绩效权重配置表
    op.create_table(
        'performance_config',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('config_name', sa.String(length=64), nullable=False, server_default='default', comment='配置名称'),
        sa.Column('sales_weight', sa.Integer(), nullable=False, server_default='30', comment='销售额权重（%）'),
        sa.Column('profit_weight', sa.Integer(), nullable=False, server_default='25', comment='毛利权重（%）'),
        sa.Column('key_product_weight', sa.Integer(), nullable=False, server_default='25', comment='重点产品权重（%）'),
        sa.Column('operation_weight', sa.Integer(), nullable=False, server_default='20', comment='运营权重（%）'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true', comment='是否启用'),
        sa.Column('effective_from', sa.Date(), nullable=False, comment='生效开始日期'),
        sa.Column('effective_to', sa.Date(), nullable=True, comment='生效结束日期（NULL表示永久有效）'),
        sa.Column('created_by', sa.String(length=64), nullable=True, comment='创建人'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('sales_weight + profit_weight + key_product_weight + operation_weight = 100', name='chk_weights_sum'),
        sa.CheckConstraint(
            'sales_weight >= 0 AND sales_weight <= 100 AND '
            'profit_weight >= 0 AND profit_weight <= 100 AND '
            'key_product_weight >= 0 AND key_product_weight <= 100 AND '
            'operation_weight >= 0 AND operation_weight <= 100',
            name='chk_weights_range'
        ),
    )
    op.create_index('ix_performance_config_active', 'performance_config', ['is_active', 'effective_from'])

    # 9. 滞销清理排名表
    op.create_table(
        'clearance_rankings',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('platform_code', sa.String(length=32), nullable=False),
        sa.Column('shop_id', sa.String(length=64), nullable=False),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('granularity', sa.String(length=16), nullable=False, comment='粒度：monthly/weekly'),
        sa.Column('clearance_amount', sa.Float(), nullable=False, server_default='0.0', comment='清理金额（CNY）'),
        sa.Column('clearance_quantity', sa.Integer(), nullable=False, server_default='0', comment='清理数量'),
        sa.Column('incentive_amount', sa.Float(), nullable=False, server_default='0.0', comment='激励金额（CNY）'),
        sa.Column('total_incentive', sa.Float(), nullable=False, server_default='0.0', comment='总计激励（CNY）'),
        sa.Column('rank', sa.Integer(), nullable=True, comment='排名'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['platform_code', 'shop_id'], ['dim_shops.platform_code', 'dim_shops.shop_id'], name='fk_clearance_ranking'),
        sa.UniqueConstraint('platform_code', 'shop_id', 'metric_date', 'granularity', name='uq_clearance_ranking'),
    )
    op.create_index('ix_clearance_ranking_date', 'clearance_rankings', ['metric_date', 'granularity'])
    op.create_index('ix_clearance_ranking_rank', 'clearance_rankings', ['rank'])
    op.create_index('ix_clearance_ranking_amount', 'clearance_rankings', ['clearance_amount'])


def downgrade() -> None:
    # 删除表（按相反顺序）
    op.drop_table('clearance_rankings')
    op.drop_table('performance_config')
    op.drop_table('performance_scores')
    op.drop_table('shop_alerts')
    op.drop_table('shop_health_scores')
    op.drop_table('target_breakdown')
    op.drop_table('sales_targets')
    op.drop_table('sales_campaign_shops')
    op.drop_table('sales_campaigns')

