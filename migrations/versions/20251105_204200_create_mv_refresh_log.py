"""create materialized view refresh log table

Revision ID: 20251105_204200
Revises: 20251105_204106
Create Date: 2025-11-05 20:42:00

物化视图刷新日志表 - 审计和监控

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = '20251105_204200'
down_revision = '20251105_204106'
branch_labels = None
depends_on = None


def upgrade():
    """
    创建物化视图刷新日志表（mv_refresh_log）
    
    用途：
    1. 记录每次刷新的时间和耗时
    2. 监控刷新性能
    3. 告警检测（连续失败）
    4. 审计追踪
    """
    
    op.execute(text("""
        CREATE TABLE IF NOT EXISTS mv_refresh_log (
            id SERIAL PRIMARY KEY,
            view_name VARCHAR(128) NOT NULL,
            refresh_started_at TIMESTAMP NOT NULL DEFAULT NOW(),
            refresh_completed_at TIMESTAMP,
            duration_seconds FLOAT,
            row_count INTEGER,
            status VARCHAR(20) DEFAULT 'running',
            error_message TEXT,
            triggered_by VARCHAR(64) DEFAULT 'scheduler',
            
            -- 索引
            CONSTRAINT chk_status CHECK (status IN ('running', 'success', 'failed'))
        );
    """))
    
    # 创建索引
    op.execute(text("""
        CREATE INDEX idx_mv_refresh_log_view 
        ON mv_refresh_log(view_name, refresh_started_at DESC);
    """))
    
    op.execute(text("""
        CREATE INDEX idx_mv_refresh_log_status 
        ON mv_refresh_log(status, refresh_started_at DESC);
    """))
    
    print("[MV] 刷新日志表创建成功")
    
    # 创建监控函数（获取最近刷新状态）
    op.execute(text("""
        CREATE OR REPLACE FUNCTION get_mv_refresh_status(p_view_name VARCHAR)
        RETURNS TABLE(
            last_refresh TIMESTAMP,
            duration_seconds FLOAT,
            row_count INTEGER,
            status VARCHAR,
            age_minutes INTEGER
        ) AS $$
        BEGIN
            RETURN QUERY
            SELECT 
                refresh_completed_at,
                mv_refresh_log.duration_seconds,
                mv_refresh_log.row_count,
                mv_refresh_log.status,
                EXTRACT(EPOCH FROM (NOW() - refresh_completed_at))::INTEGER / 60 as age_minutes
            FROM mv_refresh_log
            WHERE view_name = p_view_name
              AND status = 'success'
            ORDER BY refresh_completed_at DESC
            LIMIT 1;
        END;
        $$ LANGUAGE plpgsql;
    """))
    
    print("[MV] 监控函数创建成功")


def downgrade():
    """
    回滚：删除刷新日志表和监控函数
    """
    op.execute(text("DROP FUNCTION IF EXISTS get_mv_refresh_status(VARCHAR);"))
    op.execute(text("DROP TABLE IF EXISTS mv_refresh_log CASCADE;"))
    
    print("[MV] 刷新日志表已删除")

