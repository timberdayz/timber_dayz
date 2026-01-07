#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
修复mv_shop_health_summary物化视图

问题：物化视图可能缺少gmv字段或需要刷新
解决方案：检查并重新创建物化视图
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from sqlalchemy import text
from modules.core.logger import get_logger

logger = get_logger(__name__)


def check_mv_exists(db):
    """检查物化视图是否存在"""
    try:
        result = db.execute(text("""
            SELECT EXISTS (
                SELECT 1 
                FROM pg_matviews 
                WHERE matviewname = 'mv_shop_health_summary'
            )
        """))
        exists = result.scalar()
        return exists
    except Exception as e:
        logger.error(f"检查物化视图失败: {e}")
        return False


def check_mv_columns(db):
    """检查物化视图的列"""
    try:
        result = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'mv_shop_health_summary' 
            ORDER BY ordinal_position
        """))
        columns = [row[0] for row in result]
        return columns
    except Exception as e:
        logger.error(f"检查物化视图列失败: {e}")
        return []


def recreate_mv(db):
    """重新创建物化视图"""
    try:
        logger.info("删除旧物化视图...")
        db.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_shop_health_summary CASCADE"))
        db.commit()
        
        logger.info("创建新物化视图...")
        db.execute(text("""
            CREATE MATERIALIZED VIEW mv_shop_health_summary AS
            SELECT 
                -- 业务标识
                shs.platform_code,
                shs.shop_id,
                ds.shop_name,
                shs.metric_date,
                shs.granularity,
                
                -- 健康度评分
                shs.health_score,
                shs.gmv_score,
                shs.conversion_score,
                shs.inventory_score,
                shs.service_score,
                
                -- 基础指标
                shs.gmv,
                shs.conversion_rate,
                shs.inventory_turnover,
                shs.customer_satisfaction,
                
                -- 风险等级
                shs.risk_level,
                shs.risk_factors,
                
                -- 排名（基于健康度评分）
                ROW_NUMBER() OVER (
                    PARTITION BY shs.metric_date, shs.granularity 
                    ORDER BY shs.health_score DESC
                ) AS health_rank,
                
                -- 时间戳
                shs.created_at,
                shs.updated_at
                
            FROM shop_health_scores shs
            LEFT JOIN dim_shops ds ON shs.platform_code = ds.platform_code AND shs.shop_id = ds.shop_id
            
            WHERE shs.metric_date >= CURRENT_DATE - INTERVAL '90 days'
            
            WITH DATA
        """))
        
        logger.info("创建唯一索引...")
        db.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_shop_health_summary_pk 
            ON mv_shop_health_summary(platform_code, shop_id, metric_date, granularity)
        """))
        
        logger.info("创建查询索引...")
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_mv_shop_health_summary_date 
            ON mv_shop_health_summary(metric_date DESC, granularity)
        """))
        
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_mv_shop_health_summary_rank 
            ON mv_shop_health_summary(metric_date, granularity, health_rank)
        """))
        
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_mv_shop_health_summary_risk 
            ON mv_shop_health_summary(risk_level, metric_date DESC)
        """))
        
        db.commit()
        logger.info("物化视图创建成功")
        return True
        
    except Exception as e:
        logger.error(f"重新创建物化视图失败: {e}", exc_info=True)
        db.rollback()
        return False


def main():
    """主函数"""
    logger.info("开始修复mv_shop_health_summary物化视图...")
    
    db = next(get_db())
    
    try:
        # 1. 检查物化视图是否存在
        exists = check_mv_exists(db)
        logger.info(f"物化视图存在: {exists}")
        
        if exists:
            # 2. 检查列
            columns = check_mv_columns(db)
            logger.info(f"物化视图列: {', '.join(columns)}")
            
            # 3. 检查是否缺少gmv字段
            if 'gmv' not in columns:
                logger.warning("物化视图缺少gmv字段，需要重新创建")
                recreate_mv(db)
            else:
                logger.info("物化视图结构正确，尝试刷新...")
                try:
                    db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_shop_health_summary"))
                    db.commit()
                    logger.info("物化视图刷新成功")
                except Exception as e:
                    logger.warning(f"并发刷新失败，尝试普通刷新: {e}")
                    db.execute(text("REFRESH MATERIALIZED VIEW mv_shop_health_summary"))
                    db.commit()
                    logger.info("物化视图刷新成功")
        else:
            logger.warning("物化视图不存在，创建新物化视图...")
            recreate_mv(db)
        
        # 4. 验证修复结果
        columns = check_mv_columns(db)
        logger.info(f"修复后的物化视图列: {', '.join(columns)}")
        
        if 'gmv' in columns:
            logger.info("[OK] 修复成功：物化视图包含gmv字段")
        else:
            logger.error("[ERROR] 修复失败：物化视图仍然缺少gmv字段")
            return 1
        
    except Exception as e:
        logger.error(f"修复过程出错: {e}", exc_info=True)
        return 1
    finally:
        db.close()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

