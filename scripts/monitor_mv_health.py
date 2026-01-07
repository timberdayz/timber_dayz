"""
物化视图健康监控脚本
执行：python scripts/monitor_mv_health.py

功能：
1. 检查刷新状态（是否有失败）
2. 检查数据新鲜度（是否过期）
3. 检查行数异常（突增/突减）
4. 检查刷新性能（耗时趋势）

v4.9.2新增
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from sqlalchemy import text
from datetime import datetime, timedelta
from modules.core.logger import get_logger

logger = get_logger(__name__)

def check_mv_health():
    """物化视图健康检查"""
    db = SessionLocal()
    issues = []
    warnings = []
    
    try:
        logger.info("=" * 60)
        logger.info("[健康检查] 物化视图健康度检查")
        logger.info("=" * 60)
        
        # 1. 检查所有视图的最后刷新状态
        logger.info("\n[检查1/4] 刷新状态检查...")
        
        result = db.execute(text("""
            WITH latest_refresh AS (
                SELECT 
                    view_name,
                    refresh_completed_at,
                    duration_seconds,
                    row_count,
                    status,
                    EXTRACT(EPOCH FROM (NOW() - refresh_completed_at))/60 as age_minutes,
                    ROW_NUMBER() OVER (PARTITION BY view_name ORDER BY refresh_completed_at DESC) as rn
                FROM mv_refresh_log
                WHERE refresh_completed_at IS NOT NULL
            )
            SELECT 
                view_name,
                refresh_completed_at,
                duration_seconds,
                row_count,
                status,
                age_minutes
            FROM latest_refresh
            WHERE rn = 1
            ORDER BY view_name
        """))
        
        for row in result:
            view_name, completed_at, duration, row_count, status, age_minutes = row
            
            # 检查1: 刷新失败
            if status == 'failed':
                issues.append(f"[ERROR] {view_name}: 刷新失败")
            
            # 检查2: 数据过期（>30分钟）
            if age_minutes and age_minutes > 30:
                warnings.append(f"[WARN] {view_name}: 数据过期（{age_minutes:.0f}分钟）")
            
            # 检查3: 刷新过慢（>60秒）
            if duration and duration > 60:
                warnings.append(f"[WARN] {view_name}: 刷新慢（{duration:.1f}秒）")
            
            # 检查4: 数据为空
            if row_count == 0:
                warnings.append(f"[WARN] {view_name}: 无数据（0行）")
            
            logger.info(f"  {view_name}: {status} | {row_count}行 | {duration:.2f}秒 | {age_minutes:.0f}分钟前")
        
        # 2. 检查是否有未刷新的视图
        logger.info("\n[检查2/4] 未刷新视图检查...")
        
        result = db.execute(text("""
            SELECT matviewname 
            FROM pg_matviews 
            WHERE schemaname = 'public'
              AND matviewname NOT IN (
                  SELECT DISTINCT view_name FROM mv_refresh_log
              )
        """))
        
        unrefreshed = [row[0] for row in result]
        if unrefreshed:
            for view in unrefreshed:
                warnings.append(f"[WARN] {view}: 从未刷新过")
                logger.info(f"  {view}: 从未刷新")
        else:
            logger.info("  [OK] 所有视图都有刷新记录")
        
        # 3. 检查刷新频率
        logger.info("\n[检查3/4] 刷新频率检查...")
        
        result = db.execute(text("""
            SELECT 
                view_name,
                COUNT(*) as refresh_count,
                AVG(duration_seconds) as avg_duration,
                MAX(duration_seconds) as max_duration
            FROM mv_refresh_log
            WHERE refresh_completed_at >= NOW() - INTERVAL '24 hours'
            GROUP BY view_name
            ORDER BY view_name
        """))
        
        for row in result:
            view_name, count, avg_dur, max_dur = row
            logger.info(f"  {view_name}: 24h刷新{count}次 | 平均{avg_dur:.2f}秒 | 最慢{max_dur:.2f}秒")
        
        # 4. 数据质量检查
        logger.info("\n[检查4/4] 数据质量检查...")
        
        # 检查核心视图是否有数据
        core_views = ['mv_product_management', 'mv_daily_sales', 'mv_financial_overview']
        for view in core_views:
            try:
                result = db.execute(text(f"SELECT COUNT(*) FROM {view}"))
                count = result.scalar()
                if count == 0:
                    issues.append(f"[ERROR] {view}: 核心视图无数据")
                    logger.info(f"  {view}: [ERROR] 无数据")
                else:
                    logger.info(f"  {view}: [OK] {count}行")
            except Exception as e:
                issues.append(f"[ERROR] {view}: 查询失败 - {e}")
        
        # 汇总
        logger.info("\n" + "=" * 60)
        logger.info("[汇总] 健康检查结果")
        logger.info("=" * 60)
        
        if issues:
            logger.error(f"\n[ERROR] 发现{len(issues)}个严重问题:")
            for issue in issues:
                logger.error(f"  {issue}")
        
        if warnings:
            logger.warning(f"\n[WARN] 发现{len(warnings)}个警告:")
            for warning in warnings:
                logger.warning(f"  {warning}")
        
        if not issues and not warnings:
            logger.info("\n✅ 所有检查通过！物化视图健康状态良好！")
            return True
        else:
            logger.warning(f"\n⚠️ 发现{len(issues)}个错误、{len(warnings)}个警告")
            return False
        
    except Exception as e:
        logger.error(f"[ERROR] 健康检查失败: {e}", exc_info=True)
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = check_mv_health()
    sys.exit(0 if success else 1)

