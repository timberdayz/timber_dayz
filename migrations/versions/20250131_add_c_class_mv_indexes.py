"""添加C类数据物化视图性能优化索引

Revision ID: 20250131_add_c_class_mv_indexes
Revises: 20250131_optimize_c_class_mv
Create Date: 2025-01-31

C类数据核心字段优化计划（Phase 4）：
为C类数据物化视图添加性能优化索引

索引优化：
1. mv_shop_daily_performance - 时间范围查询索引、店铺维度聚合索引
2. mv_shop_health_summary - 排名查询索引、风险等级查询索引
3. mv_campaign_achievement - 日期范围查询索引
4. mv_target_achievement - 期间查询索引

注意事项：
- 使用IF NOT EXISTS避免冲突
- 索引设计遵循最左前缀原则
- 考虑查询模式和性能需求
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '20250131_add_c_class_mv_indexes'
down_revision = '20250131_optimize_c_class_mv'
branch_labels = None
depends_on = None


def upgrade():
    """添加C类数据物化视图性能优化索引"""
    
    # ========== mv_shop_daily_performance索引优化 ==========
    # 注意：基础索引已在物化视图创建时创建，这里只添加额外的性能优化索引
    
    # 数据质量标识字段查询索引（用于筛选数据质量问题）
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_mv_shop_daily_perf_quality 
        ON mv_shop_daily_performance(missing_gmv_flag, missing_uv_flag, missing_stock_flag, missing_rating_flag);
    """))
    
    # 平台+店铺+日期组合查询索引（优化常见查询模式）
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_mv_shop_daily_perf_platform_shop_date 
        ON mv_shop_daily_performance(platform_code, shop_id, metric_date DESC);
    """))
    
    # ========== mv_shop_health_summary索引优化 ==========
    # 注意：基础索引已在物化视图创建时创建，这里只添加额外的性能优化索引
    
    # 健康度评分范围查询索引（用于筛选健康/不健康店铺）
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_mv_shop_health_score_range 
        ON mv_shop_health_summary(health_score DESC, metric_date DESC);
    """))
    
    # 风险等级+日期查询索引（用于风险监控）
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_mv_shop_health_risk_date 
        ON mv_shop_health_summary(risk_level, metric_date DESC, granularity);
    """))
    
    # ========== mv_campaign_achievement索引优化 ==========
    
    # 达成率范围查询索引（用于筛选达成/未达成战役）
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_mv_campaign_achievement_rate 
        ON mv_campaign_achievement(gmv_achievement_rate DESC, order_achievement_rate DESC);
    """))
    
    # 平台+店铺+日期范围查询索引
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_mv_campaign_achievement_platform_shop 
        ON mv_campaign_achievement(platform_code, shop_id, start_date DESC, end_date DESC);
    """))
    
    # ========== mv_target_achievement索引优化 ==========
    
    # 达成率范围查询索引（用于筛选达成/未达成目标）
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_mv_target_achievement_rate 
        ON mv_target_achievement(achievement_rate DESC, target_period DESC);
    """))
    
    # 目标类型+期间查询索引
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_mv_target_achievement_type_period 
        ON mv_target_achievement(target_type, target_period DESC);
    """))
    
    # 平台+店铺+目标类型查询索引
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_mv_target_achievement_platform_shop_type 
        ON mv_target_achievement(platform_code, shop_id, target_type);
    """))


def downgrade():
    """删除C类数据物化视图性能优化索引"""
    
    # 删除mv_shop_daily_performance额外索引
    op.execute(text("DROP INDEX IF EXISTS idx_mv_shop_daily_perf_quality;"))
    op.execute(text("DROP INDEX IF EXISTS idx_mv_shop_daily_perf_platform_shop_date;"))
    
    # 删除mv_shop_health_summary额外索引
    op.execute(text("DROP INDEX IF EXISTS idx_mv_shop_health_score_range;"))
    op.execute(text("DROP INDEX IF EXISTS idx_mv_shop_health_risk_date;"))
    
    # 删除mv_campaign_achievement索引
    op.execute(text("DROP INDEX IF EXISTS idx_mv_campaign_achievement_rate;"))
    op.execute(text("DROP INDEX IF EXISTS idx_mv_campaign_achievement_platform_shop;"))
    
    # 删除mv_target_achievement索引
    op.execute(text("DROP INDEX IF EXISTS idx_mv_target_achievement_rate;"))
    op.execute(text("DROP INDEX IF EXISTS idx_mv_target_achievement_type_period;"))
    op.execute(text("DROP INDEX IF EXISTS idx_mv_target_achievement_platform_shop_type;"))

