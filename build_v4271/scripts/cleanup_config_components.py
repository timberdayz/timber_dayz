#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
清理数据库中错误注册的 config 组件

功能：
1. 查找所有 config 和 overlay_guard 组件
2. 显示将要删除的组件列表
3. 删除这些组件记录

使用方式：
    python scripts/cleanup_config_components.py --dry-run     # 预览模式
    python scripts/cleanup_config_components.py                # 执行删除
"""

import argparse
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from modules.core.db import ComponentVersion
from modules.core.logger import get_logger

logger = get_logger(__name__)


def cleanup_config_components(dry_run: bool = False) -> dict:
    """
    清理数据库中错误注册的 config 组件
    
    Args:
        dry_run: 预览模式，不实际删除
        
    Returns:
        dict: 清理统计
    """
    db = SessionLocal()
    result = {
        "found": [],
        "deleted": [],
        "errors": []
    }
    
    try:
        # 查找所有 config 和 overlay_guard 组件
        config_components = db.query(ComponentVersion).filter(
            (ComponentVersion.file_path.like('%_config.py'))
            | (ComponentVersion.file_path.like('%overlay_guard.py'))
            | (ComponentVersion.component_name.like('%_config'))
            | (ComponentVersion.component_name.like('%overlay_guard'))
        ).all()
        
        result["found"] = [
            {
                "id": comp.id,
                "component_name": comp.component_name,
                "file_path": comp.file_path,
                "version": comp.version,
                "is_stable": comp.is_stable
            }
            for comp in config_components
        ]
        
        logger.info(f"[INFO] 找到 {len(config_components)} 个需要删除的组件")
        
        if not config_components:
            logger.info("[DONE] 没有需要删除的组件")
            return result
        
        # 显示将要删除的组件
        logger.info("")
        logger.info("将要删除的组件列表：")
        logger.info("-" * 60)
        for comp in config_components:
            logger.info(
                f"  - {comp.component_name} v{comp.version} "
                f"({comp.file_path}) "
                f"{'[稳定版]' if comp.is_stable else ''}"
            )
        
        # 执行删除
        if not dry_run:
            logger.info("")
            logger.info("[ACTION] 开始删除...")
            
            for comp in config_components:
                try:
                    component_info = {
                        "id": comp.id,
                        "component_name": comp.component_name,
                        "file_path": comp.file_path,
                        "version": comp.version
                    }
                    
                    db.delete(comp)
                    result["deleted"].append(component_info)
                    
                    logger.info(f"[DELETE] {comp.component_name} v{comp.version}")
                    
                except Exception as e:
                    error_info = {
                        "component_name": comp.component_name,
                        "file_path": comp.file_path,
                        "error": str(e)
                    }
                    result["errors"].append(error_info)
                    logger.error(f"[ERROR] 删除失败 {comp.component_name}: {e}")
            
            db.commit()
            logger.info("")
            logger.info(f"[SUCCESS] 已删除 {len(result['deleted'])} 个组件")
        else:
            logger.info("")
            logger.info("[DRY-RUN] 预览模式，未实际删除")
        
    except Exception as e:
        logger.error(f"[ERROR] 清理过程出错: {e}", exc_info=True)
        db.rollback()
        result["errors"].append({"error": str(e)})
    finally:
        db.close()
    
    return result


def main():
    parser = argparse.ArgumentParser(description="清理数据库中错误注册的 config 组件")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览模式，不实际执行删除"
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("清理数据库中错误注册的 config 组件")
    logger.info("=" * 60)
    
    if args.dry_run:
        logger.info("[MODE] 预览模式 - 不会实际执行任何操作")
    
    logger.info("")
    
    # 执行清理
    result = cleanup_config_components(args.dry_run)
    
    # 输出统计
    logger.info("")
    logger.info("=" * 60)
    logger.info("清理统计")
    logger.info("=" * 60)
    logger.info(f"  找到: {len(result['found'])} 个组件")
    logger.info(f"  已删除: {len(result['deleted'])} 个组件")
    logger.info(f"  错误: {len(result['errors'])} 个")
    
    if result["errors"]:
        logger.info("")
        logger.info("错误详情：")
        for error in result["errors"]:
            logger.error(f"  - {error}")
    
    return 0 if len(result["errors"]) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

