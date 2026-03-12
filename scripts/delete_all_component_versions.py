#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
清空所有组件版本记录

用于测试前重置组件版本库，或解决「删除失败，数据不存在」等状态不一致问题。
删除前会先处理 ComponentTestHistory 关联记录。

使用方式：
    python scripts/delete_all_component_versions.py --dry-run   # 预览
    python scripts/delete_all_component_versions.py             # 执行
"""

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from backend.models.database import SessionLocal
from modules.core.db import ComponentVersion, ComponentTestHistory
from modules.core.logger import get_logger

logger = get_logger(__name__)


def main(dry_run: bool = True):
    db: Session = SessionLocal()
    try:
        # 统计
        count_result = db.execute(select(ComponentVersion))
        all_versions = count_result.scalars().all()
        history_result = db.execute(select(ComponentTestHistory))
        all_history = history_result.scalars().all()

        total_versions = len(all_versions)
        total_history = len(all_history)

        if total_versions == 0 and total_history == 0:
            logger.info("无组件版本记录，无需删除")
            return 0

        logger.info(f"将删除: {total_versions} 条 ComponentVersion, {total_history} 条 ComponentTestHistory")
        for v in all_versions[:10]:
            logger.info(f"  - {v.component_name} v{v.version} (id={v.id})")
        if total_versions > 10:
            logger.info(f"  ... 及另外 {total_versions - 10} 条")

        if dry_run:
            logger.info("[DRY-RUN] 预览完成。执行实际删除请去掉 --dry-run")
            return 0

        # 1. 删除 ComponentTestHistory
        db.execute(delete(ComponentTestHistory))
        logger.info(f"已删除 {total_history} 条 ComponentTestHistory")

        # 2. 删除 ComponentVersion
        db.execute(delete(ComponentVersion))
        db.commit()
        logger.info(f"已删除 {total_versions} 条 ComponentVersion")

        logger.info("清空完成。建议刷新前端页面或清除 Redis 缓存以更新列表显示。")
        return 0
    except Exception as e:
        db.rollback()
        logger.error(f"清空失败: {e}", exc_info=True)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="清空所有组件版本记录")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不执行删除")
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run))
