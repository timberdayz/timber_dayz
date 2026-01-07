#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
YAML 组件清理脚本

功能：
1. 移动 YAML 文件到备份目录
2. 禁用 ComponentVersion 表中 .yaml 路径的记录
3. 添加废弃标记到 description

使用方式：
    python scripts/cleanup_yaml_components.py --dry-run  # 预览模式
    python scripts/cleanup_yaml_components.py            # 执行清理
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.models.database import SessionLocal
from modules.core.db import ComponentVersion
from modules.core.logger import get_logger

logger = get_logger(__name__)


def get_yaml_files(base_dir: Path) -> list:
    """获取所有 YAML 组件文件"""
    yaml_files = []
    yaml_dir = base_dir / "config" / "collection_components"
    
    if not yaml_dir.exists():
        logger.warning(f"[WARN] YAML 组件目录不存在: {yaml_dir}")
        return yaml_files
    
    for yaml_file in yaml_dir.rglob("*.yaml"):
        yaml_files.append(yaml_file)
    
    for yml_file in yaml_dir.rglob("*.yml"):
        yaml_files.append(yml_file)
    
    return yaml_files


def backup_yaml_files(yaml_files: list, backup_dir: Path, dry_run: bool = False) -> dict:
    """备份 YAML 文件到指定目录"""
    result = {
        "moved": [],
        "skipped": [],
        "errors": []
    }
    
    if not yaml_files:
        logger.info("[INFO] 没有 YAML 文件需要备份")
        return result
    
    if not dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)
    
    for yaml_file in yaml_files:
        try:
            # 保持相对路径结构
            relative_path = yaml_file.relative_to(project_root)
            target_path = backup_dir / relative_path
            
            if dry_run:
                logger.info(f"[DRY-RUN] 将移动: {yaml_file} -> {target_path}")
                result["moved"].append(str(yaml_file))
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(yaml_file), str(target_path))
                logger.info(f"[OK] 已移动: {yaml_file} -> {target_path}")
                result["moved"].append(str(yaml_file))
        except Exception as e:
            logger.error(f"[ERROR] 移动文件失败 {yaml_file}: {e}")
            result["errors"].append({"file": str(yaml_file), "error": str(e)})
    
    return result


def disable_yaml_versions(db: Session, dry_run: bool = False) -> dict:
    """禁用 ComponentVersion 表中 .yaml 路径的记录"""
    result = {
        "disabled": [],
        "skipped": [],
        "errors": []
    }
    
    # 查询所有 .yaml 路径的记录
    yaml_versions = db.query(ComponentVersion).filter(
        ComponentVersion.file_path.like("%.yaml")
    ).all()
    
    yaml_versions += db.query(ComponentVersion).filter(
        ComponentVersion.file_path.like("%.yml")
    ).all()
    
    if not yaml_versions:
        logger.info("[INFO] 没有 YAML 组件版本记录需要禁用")
        return result
    
    deprecation_note = "[DEPRECATED - YAML components migrated to Python]"
    
    for version in yaml_versions:
        try:
            if dry_run:
                logger.info(f"[DRY-RUN] 将禁用: {version.component_name} (v{version.version}) - {version.file_path}")
                result["disabled"].append({
                    "id": version.id,
                    "component_name": version.component_name,
                    "version": version.version,
                    "file_path": version.file_path
                })
            else:
                # 更新记录
                version.is_active = False
                
                # 添加废弃标记到 description
                if version.description:
                    if deprecation_note not in version.description:
                        version.description = f"{deprecation_note} {version.description}"
                else:
                    version.description = deprecation_note
                
                logger.info(f"[OK] 已禁用: {version.component_name} (v{version.version})")
                result["disabled"].append({
                    "id": version.id,
                    "component_name": version.component_name,
                    "version": version.version,
                    "file_path": version.file_path
                })
        except Exception as e:
            logger.error(f"[ERROR] 禁用版本失败 {version.component_name}: {e}")
            result["errors"].append({
                "id": version.id,
                "component_name": version.component_name,
                "error": str(e)
            })
    
    if not dry_run:
        db.commit()
    
    return result


def main():
    parser = argparse.ArgumentParser(description="YAML 组件清理脚本")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览模式，不实际执行清理"
    )
    parser.add_argument(
        "--skip-files",
        action="store_true",
        help="跳过文件备份，仅禁用数据库记录"
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="跳过数据库操作，仅备份文件"
    )
    
    args = parser.parse_args()
    
    # 生成备份目录名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = project_root / "backups" / f"yaml_components_{timestamp}"
    
    logger.info("=" * 60)
    logger.info("YAML 组件清理脚本")
    logger.info("=" * 60)
    
    if args.dry_run:
        logger.info("[MODE] 预览模式 - 不会实际执行任何操作")
    
    # 统计结果
    total_result = {
        "files_moved": 0,
        "files_errors": 0,
        "versions_disabled": 0,
        "versions_errors": 0
    }
    
    # 1. 备份 YAML 文件
    if not args.skip_files:
        logger.info("")
        logger.info("[STEP 1] 备份 YAML 文件")
        logger.info("-" * 40)
        
        yaml_files = get_yaml_files(project_root)
        logger.info(f"[INFO] 找到 {len(yaml_files)} 个 YAML 文件")
        
        if yaml_files:
            file_result = backup_yaml_files(yaml_files, backup_dir, args.dry_run)
            total_result["files_moved"] = len(file_result["moved"])
            total_result["files_errors"] = len(file_result["errors"])
    else:
        logger.info("[SKIP] 跳过文件备份")
    
    # 2. 禁用数据库记录
    if not args.skip_db:
        logger.info("")
        logger.info("[STEP 2] 禁用 ComponentVersion 记录")
        logger.info("-" * 40)
        
        db = SessionLocal()
        try:
            db_result = disable_yaml_versions(db, args.dry_run)
            total_result["versions_disabled"] = len(db_result["disabled"])
            total_result["versions_errors"] = len(db_result["errors"])
        finally:
            db.close()
    else:
        logger.info("[SKIP] 跳过数据库操作")
    
    # 3. 输出统计
    logger.info("")
    logger.info("=" * 60)
    logger.info("清理统计")
    logger.info("=" * 60)
    logger.info(f"  YAML 文件移动: {total_result['files_moved']}")
    logger.info(f"  文件移动错误: {total_result['files_errors']}")
    logger.info(f"  版本记录禁用: {total_result['versions_disabled']}")
    logger.info(f"  版本禁用错误: {total_result['versions_errors']}")
    
    if args.dry_run:
        logger.info("")
        logger.info("[NOTE] 这是预览模式，实际运行请移除 --dry-run 参数")
    else:
        logger.info("")
        logger.info(f"[DONE] 备份目录: {backup_dir}")
    
    # 返回退出码
    if total_result["files_errors"] > 0 or total_result["versions_errors"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

