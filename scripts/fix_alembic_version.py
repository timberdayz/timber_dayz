#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复 Alembic 迁移版本记录

用于修复数据库中的迁移版本记录，当版本指向不存在的迁移文件时使用。

使用方法：
    python scripts/fix_alembic_version.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from backend.utils.config import get_settings
from modules.core.logger import get_logger

logger = get_logger(__name__)


def check_current_version(engine):
    """检查当前数据库中的迁移版本"""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version_num FROM alembic_version"))
        row = result.fetchone()
        if row:
            return row[0]
        return None


def update_version(engine, new_version):
    """更新数据库中的迁移版本"""
    with engine.connect() as conn:
        # 检查表是否存在
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'alembic_version'
            )
        """))
        table_exists = result.scalar()
        
        if not table_exists:
            logger.warning("[FixAlembic] alembic_version 表不存在，创建表...")
            conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            conn.execute(text("INSERT INTO alembic_version (version_num) VALUES (:version)"), {"version": new_version})
            conn.commit()
            logger.info(f"[FixAlembic] 已创建 alembic_version 表并设置版本为: {new_version}")
        else:
            current_version = check_current_version(engine)
            logger.info(f"[FixAlembic] 当前版本: {current_version}")
            
            if current_version == new_version:
                logger.info(f"[FixAlembic] 版本已经是目标版本，无需更新")
                return
            
            # 更新版本
            conn.execute(text("UPDATE alembic_version SET version_num = :new_version"), {"new_version": new_version})
            conn.commit()
            logger.info(f"[FixAlembic] 已更新版本: {current_version} -> {new_version}")


def main():
    """主函数"""
    try:
        settings = get_settings()
        database_url = settings.DATABASE_URL
        
        logger.info(f"[FixAlembic] 连接到数据库: {database_url.split('@')[-1] if '@' in database_url else 'SQLite'}")
        
        # 创建数据库引擎
        engine = create_engine(database_url)
        
        # 检查当前版本
        current_version = check_current_version(engine)
        logger.info(f"[FixAlembic] 当前数据库版本: {current_version}")
        
        # 定义有效的迁移版本链
        valid_versions = [
            'v5_0_0_schema_snapshot',  # 基础快照
            '20260125_fix_st',         # 修复 sales_targets
            '20260126_tb_cols',       # 修复 target_breakdown
            '20260127_rm_fact_orders' # 删除 fact_orders（最新）
        ]
        
        # 如果当前版本无效或不存在，更新为最新有效版本
        if current_version is None:
            logger.warning("[FixAlembic] 未找到版本记录，设置为最新版本")
            target_version = valid_versions[-1]
        elif current_version not in valid_versions:
            logger.warning(f"[FixAlembic] 当前版本 '{current_version}' 不在有效版本列表中")
            logger.info("[FixAlembic] 将更新为最新有效版本")
            target_version = valid_versions[-1]
        elif current_version == '20260111_complete_missing':
            logger.warning("[FixAlembic] 检测到无效版本 '20260111_complete_missing'")
            logger.info("[FixAlembic] 将更新为最新有效版本")
            target_version = valid_versions[-1]
        else:
            logger.info(f"[FixAlembic] 当前版本 '{current_version}' 有效，无需更新")
            return
        
        # 更新版本
        update_version(engine, target_version)
        
        # 验证更新
        new_version = check_current_version(engine)
        logger.info(f"[FixAlembic] 更新后版本: {new_version}")
        
        logger.info("[FixAlembic] 修复完成！现在可以在外部终端执行: python -m alembic upgrade head")
        
    except Exception as e:
        logger.error(f"[FixAlembic] 修复失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
