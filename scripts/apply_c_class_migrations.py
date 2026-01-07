#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接应用C类数据核心字段优化计划的数据库迁移

由于alembic配置问题，直接执行SQL迁移脚本

迁移顺序：
1. 添加currency_policy和source_priority字段
2. 优化C类数据物化视图
3. 添加物化视图性能优化索引
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db, engine
from modules.core.logger import get_logger
from sqlalchemy import text

logger = get_logger(__name__)


def apply_currency_policy_migration(db):
    """应用货币策略字段迁移"""
    logger.info("=" * 70)
    logger.info("步骤1: 添加currency_policy和source_priority字段")
    logger.info("=" * 70)
    
    try:
        # 检查字段是否已存在
        check_query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'field_mapping_dictionary' 
            AND column_name IN ('currency_policy', 'source_priority')
        """)
        existing_columns = db.execute(check_query).fetchall()
        existing_names = [row[0] for row in existing_columns]
        
        if 'currency_policy' in existing_names and 'source_priority' in existing_names:
            logger.info("[SKIP] currency_policy和source_priority字段已存在，跳过迁移")
            return True
        
        # 添加currency_policy字段
        if 'currency_policy' not in existing_names:
            logger.info("添加currency_policy字段...")
            db.execute(text("""
                ALTER TABLE field_mapping_dictionary 
                ADD COLUMN currency_policy VARCHAR(32) NULL;
            """))
            db.execute(text("""
                COMMENT ON COLUMN field_mapping_dictionary.currency_policy IS 
                '货币策略（CNY/无货币/多币种）- C类数据核心字段优化计划（Phase 3）';
            """))
            logger.info("[OK] currency_policy字段已添加")
        
        # 添加source_priority字段
        if 'source_priority' not in existing_names:
            logger.info("添加source_priority字段...")
            db.execute(text("""
                ALTER TABLE field_mapping_dictionary 
                ADD COLUMN source_priority JSONB NULL;
            """))
            db.execute(text("""
                COMMENT ON COLUMN field_mapping_dictionary.source_priority IS 
                '数据源优先级（JSON数组，如["miaoshou", "shopee"]）- C类数据核心字段优化计划（Phase 3）';
            """))
            logger.info("[OK] source_priority字段已添加")
        
        # 创建索引
        logger.info("创建currency_policy索引...")
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_dictionary_currency_policy 
            ON field_mapping_dictionary(currency_policy);
        """))
        logger.info("[OK] 索引已创建")
        
        db.commit()
        logger.info("[OK] 货币策略字段迁移完成")
        return True
        
    except Exception as e:
        logger.error(f"[FAIL] 迁移失败: {e}")
        db.rollback()
        return False


def apply_mv_optimization_migration(db):
    """应用物化视图优化迁移（可选，如果视图不存在则跳过）"""
    logger.info("\n" + "=" * 70)
    logger.info("步骤2: 优化C类数据物化视图（可选）")
    logger.info("=" * 70)
    
    try:
        # 检查mv_shop_daily_performance是否存在
        check_query = text("""
            SELECT COUNT(*) 
            FROM pg_matviews 
            WHERE matviewname = 'mv_shop_daily_performance' 
            AND schemaname = 'public'
        """)
        mv_exists = db.execute(check_query).scalar() > 0
        
        if not mv_exists:
            logger.info("[SKIP] mv_shop_daily_performance不存在，跳过物化视图优化")
            return True
        
        # 检查是否已有数据质量标识字段
        check_columns_query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'mv_shop_daily_performance' 
            AND column_name IN ('missing_gmv_flag', 'missing_uv_flag')
        """)
        existing_mv_columns = db.execute(check_columns_query).fetchall()
        existing_mv_names = [row[0] for row in existing_mv_columns]
        
        if 'missing_gmv_flag' in existing_mv_names:
            logger.info("[SKIP] 物化视图已包含数据质量标识字段，跳过优化")
            return True
        
        logger.info("[INFO] 物化视图优化需要重建视图，建议使用Alembic迁移")
        logger.info("[INFO] 或手动执行: migrations/versions/20250131_optimize_c_class_materialized_views.py")
        return True
        
    except Exception as e:
        logger.warning(f"[WARN] 物化视图优化检查失败: {e}")
        return True  # 不阻止后续步骤


def apply_mv_indexes_migration(db):
    """应用物化视图索引迁移（可选）"""
    logger.info("\n" + "=" * 70)
    logger.info("步骤3: 添加物化视图性能优化索引（可选）")
    logger.info("=" * 70)
    
    try:
        # 检查物化视图是否存在
        check_query = text("""
            SELECT matviewname 
            FROM pg_matviews 
            WHERE matviewname IN (
                'mv_shop_daily_performance',
                'mv_shop_health_summary',
                'mv_campaign_achievement',
                'mv_target_achievement'
            )
            AND schemaname = 'public'
        """)
        existing_mvs = [row[0] for row in db.execute(check_query).fetchall()]
        
        if not existing_mvs:
            logger.info("[SKIP] C类数据物化视图不存在，跳过索引创建")
            return True
        
        logger.info(f"[INFO] 发现 {len(existing_mvs)} 个C类数据物化视图")
        logger.info("[INFO] 索引创建建议使用Alembic迁移")
        logger.info("[INFO] 或手动执行: migrations/versions/20250131_add_c_class_mv_indexes.py")
        return True
        
    except Exception as e:
        logger.warning(f"[WARN] 索引迁移检查失败: {e}")
        return True  # 不阻止后续步骤


def main():
    """主函数"""
    logger.info("=" * 70)
    logger.info("C类数据核心字段优化计划 - 数据库迁移")
    logger.info("=" * 70)
    
    db = next(get_db())
    
    try:
        # 步骤1: 添加货币策略字段（必须）
        success1 = apply_currency_policy_migration(db)
        
        if not success1:
            logger.error("[FAIL] 货币策略字段迁移失败，停止后续步骤")
            return 1
        
        # 步骤2: 优化物化视图（可选）
        apply_mv_optimization_migration(db)
        
        # 步骤3: 添加索引（可选）
        apply_mv_indexes_migration(db)
        
        logger.info("\n" + "=" * 70)
        logger.info("[OK] 数据库迁移完成")
        logger.info("=" * 70)
        logger.info("\n下一步:")
        logger.info("1. 运行 scripts/add_c_class_missing_fields.py 补充缺失字段")
        logger.info("2. 运行 scripts/verify_c_class_core_fields.py 验证字段完整性")
        logger.info("3. 测试数据质量监控API端点")
        
        return 0
        
    except Exception as e:
        logger.error(f"[FAIL] 迁移失败: {e}", exc_info=True)
        db.rollback()
        return 1
    finally:
        db.close()


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
