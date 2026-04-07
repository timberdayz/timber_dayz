#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
迁移脚本：删除不符合标准化 component_name 的 ComponentVersion 记录

执行时机：在 0.2 录制保存逻辑与 component_name 校验上线后执行。

行为：
- 删除 ComponentVersion 表中不符合标准化 component_name 规则的记录
- 删除前先处理 ComponentTestHistory（删除 version_id 指向待删记录）
- 保留标准化主文件（login.py 等），仅删除/归档非标准化旧 .py 文件（如 miaoshou_login.py）

使用方式：
    python scripts/migrate_component_versions_standardized.py --dry-run   # 预览
    python scripts/migrate_component_versions_standardized.py             # 执行
"""

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from backend.models.database import SessionLocal
from backend.services.component_name_utils import is_standard_component_name
from modules.core.db import ComponentVersion, ComponentTestHistory
from modules.core.logger import get_logger

logger = get_logger(__name__)


def main(dry_run: bool = True):
    db: Session = SessionLocal()
    try:
        result = db.execute(select(ComponentVersion))
        all_versions = result.scalars().all()

        to_delete = []
        for v in all_versions:
            if not is_standard_component_name(v.component_name):
                to_delete.append(v)

        if not to_delete:
            logger.info("No non-standard component versions to migrate")
            return 0

        logger.info(f"Found {len(to_delete)} non-standard ComponentVersion records")
        for v in to_delete:
            logger.info(f"  - {v.component_name} v{v.version} (id={v.id})")

        if dry_run:
            logger.info("[DRY-RUN] Would delete above records. Run without --dry-run to execute.")
            return 0

        for v in to_delete:
            db.execute(delete(ComponentTestHistory).where(ComponentTestHistory.version_id == v.id))
        db.execute(delete(ComponentVersion).where(ComponentVersion.id.in_([x.id for x in to_delete])))
        db.commit()
        logger.info(f"Deleted {len(to_delete)} ComponentVersion records and related ComponentTestHistory")
        return 0
    except Exception as e:
        db.rollback()
        logger.error(f"Migration failed: {e}", exc_info=True)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run))
