#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路径迁移脚本 - 将数据库中的绝对路径转换为相对路径

功能：
1. 扫描 catalog_files 表中的所有 file_path 和 meta_file_path
2. 识别绝对路径并转换为相对路径
3. 统一使用正斜杠（/）存储
4. 生成迁移报告

使用方法：
    # 预览模式（不修改数据库）
    python scripts/migrate_paths.py --dry-run
    
    # 执行迁移
    python scripts/migrate_paths.py --execute
    
    # 指定项目根目录
    python scripts/migrate_paths.py --execute --project-root /app

v4.18.0 新增
"""

import argparse
import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime

# 添加项目根目录到路径
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))


@dataclass
class MigrationReport:
    """迁移报告"""
    total_records: int = 0
    absolute_paths: int = 0
    relative_paths: int = 0
    mixed_slashes: int = 0  # 混合斜杠的路径
    converted: int = 0
    skipped: int = 0
    failed: int = 0
    not_found: int = 0
    errors: List[Dict] = field(default_factory=list)
    warnings: List[Dict] = field(default_factory=list)
    conversions: List[Dict] = field(default_factory=list)


def normalize_path(path_str: str) -> str:
    """
    标准化路径：统一使用正斜杠
    """
    return path_str.replace("\\", "/")


def is_absolute_path(path_str: str) -> bool:
    """
    检查是否为绝对路径
    
    支持检测：
    - Windows: C:\..., D:\..., F:\...
    - Linux/Mac: /home/..., /app/...
    """
    normalized = normalize_path(path_str)
    
    # Windows 绝对路径（包括大小写）
    if len(normalized) >= 2 and normalized[1] == ':':
        return True
    
    # Linux/Mac 绝对路径
    if normalized.startswith('/') and not normalized.startswith('//'):
        # 排除相对路径如 data/raw/...
        return True
    
    return False


def extract_relative_path(absolute_path: str, project_root_path: Path) -> Tuple[Optional[str], str]:
    """
    从绝对路径中提取相对路径
    
    Args:
        absolute_path: 绝对路径字符串
        project_root_path: 项目根目录
        
    Returns:
        (相对路径, 状态消息) 或 (None, 错误消息)
    """
    normalized = normalize_path(absolute_path)
    
    # 关键路径标识
    key_paths = [
        "data/raw/",
        "data/input/",
        "data/processed/",
        "downloads/",
        "temp/outputs/",
        "temp/"
    ]
    
    # 尝试从路径中提取相对部分
    for key_path in key_paths:
        if key_path in normalized:
            idx = normalized.find(key_path)
            relative_path = normalized[idx:]
            return relative_path, f"extracted from {key_path}"
    
    # 尝试使用项目根目录匹配
    project_root_str = normalize_path(str(project_root_path))
    if project_root_str in normalized:
        idx = normalized.find(project_root_str)
        relative_path = normalized[idx + len(project_root_str):]
        if relative_path.startswith('/'):
            relative_path = relative_path[1:]
        return relative_path, "matched project root"
    
    return None, "cannot extract relative path"


def validate_path(relative_path: str, project_root_path: Path) -> bool:
    """
    验证相对路径是否有效（文件是否存在）
    """
    full_path = project_root_path / relative_path
    return full_path.exists()


def run_migration(dry_run: bool = True, project_root_override: str = None, verbose: bool = False) -> MigrationReport:
    """
    执行路径迁移
    
    Args:
        dry_run: 是否为预览模式（不修改数据库）
        project_root_override: 覆盖项目根目录
        verbose: 详细输出
        
    Returns:
        MigrationReport: 迁移报告
    """
    from modules.core.logger import get_logger
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    
    logger = get_logger(__name__)
    report = MigrationReport()
    
    # 确定项目根目录
    if project_root_override:
        root_path = Path(project_root_override).resolve()
    else:
        from modules.core.path_manager import get_project_root
        root_path = get_project_root()
    
    logger.info(f"[PathMigration] 项目根目录: {root_path}")
    logger.info(f"[PathMigration] 模式: {'预览(dry-run)' if dry_run else '执行'}")
    
    # 获取数据库连接
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        try:
            from backend.utils.config import get_settings
            settings = get_settings()
            database_url = settings.DATABASE_URL
        except Exception as e:
            logger.error(f"[PathMigration] 无法获取数据库连接: {e}")
            report.errors.append({"type": "database", "message": str(e)})
            return report
    
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # 使用原生 SQL 查询，只获取存在的字段（避免字段不匹配问题）
        # 直接查询不包含 meta_file_path，因为该列可能不存在
        result = session.execute(text("""
            SELECT id, file_path, file_name
            FROM catalog_files
        """))
        has_meta_file_path = False  # 当前数据库表没有 meta_file_path 列
        
        records = result.fetchall()
        report.total_records = len(records)
        logger.info(f"[PathMigration] 找到 {report.total_records} 条记录")
        if not has_meta_file_path:
            logger.info(f"[PathMigration] 注意：数据库表没有 meta_file_path 列，将跳过该字段的迁移")
        
        for row in records:
            file_id = row[0]
            file_path = row[1]
            file_name = row[2]
            meta_file_path = None  # 当前数据库表没有此列
            
            # 处理 file_path
            if file_path:
                normalized_file_path = normalize_path(file_path)
                
                # 检查是否需要转换
                needs_conversion = False
                conversion_reason = []
                
                # 检查是否为绝对路径
                if is_absolute_path(file_path):
                    report.absolute_paths += 1
                    needs_conversion = True
                    conversion_reason.append("absolute_path")
                else:
                    report.relative_paths += 1
                
                # 检查是否有反斜杠
                if "\\" in file_path:
                    report.mixed_slashes += 1
                    needs_conversion = True
                    conversion_reason.append("backslash")
                
                if needs_conversion:
                    # 提取相对路径
                    if is_absolute_path(file_path):
                        new_path, status = extract_relative_path(file_path, root_path)
                        if new_path is None:
                            report.failed += 1
                            report.errors.append({
                                "id": file_id,
                                "file_name": file_name,
                                "original_path": file_path,
                                "error": status
                            })
                            continue
                    else:
                        new_path = normalized_file_path
                        status = "normalized slashes"
                    
                    # 验证路径
                    path_exists = validate_path(new_path, root_path)
                    if not path_exists:
                        report.not_found += 1
                        report.warnings.append({
                            "id": file_id,
                            "file_name": file_name,
                            "original_path": file_path,
                            "new_path": new_path,
                            "warning": "file not found after conversion"
                        })
                    
                    # 记录转换
                    report.conversions.append({
                        "id": file_id,
                        "file_name": file_name,
                        "original_path": file_path,
                        "new_path": new_path,
                        "status": status,
                        "exists": path_exists,
                        "reason": conversion_reason
                    })
                    
                    # 执行更新
                    if not dry_run:
                        session.execute(
                            text("UPDATE catalog_files SET file_path = :new_path WHERE id = :file_id"),
                            {"new_path": new_path, "file_id": file_id}
                        )
                        if verbose:
                            logger.info(f"[PathMigration] 更新 {file_id}: {file_path} -> {new_path}")
                    
                    report.converted += 1
                else:
                    report.skipped += 1
            
            # 处理 meta_file_path（如果存在且列存在）
            if has_meta_file_path and meta_file_path and (is_absolute_path(meta_file_path) or "\\" in meta_file_path):
                if is_absolute_path(meta_file_path):
                    new_meta_path, _ = extract_relative_path(meta_file_path, root_path)
                else:
                    new_meta_path = normalize_path(meta_file_path)
                
                if new_meta_path and not dry_run:
                    session.execute(
                        text("UPDATE catalog_files SET meta_file_path = :new_path WHERE id = :file_id"),
                        {"new_path": new_meta_path, "file_id": file_id}
                    )
        
        # 提交更改
        if not dry_run:
            session.commit()
            logger.info(f"[PathMigration] 已提交 {report.converted} 条更新")
        
    except Exception as e:
        logger.error(f"[PathMigration] 迁移失败: {e}", exc_info=True)
        report.errors.append({"type": "migration", "message": str(e)})
        if not dry_run:
            session.rollback()
    finally:
        session.close()
    
    return report


def print_report(report: MigrationReport, verbose: bool = False):
    """打印迁移报告"""
    print("\n" + "=" * 60)
    print("               路径迁移报告")
    print("=" * 60)
    
    print(f"\n[统计]")
    print(f"  总记录数:        {report.total_records}")
    print(f"  绝对路径:        {report.absolute_paths}")
    print(f"  相对路径:        {report.relative_paths}")
    print(f"  混合斜杠:        {report.mixed_slashes}")
    
    print(f"\n[结果]")
    print(f"  已转换:          {report.converted}")
    print(f"  跳过:            {report.skipped}")
    print(f"  失败:            {report.failed}")
    print(f"  文件不存在:      {report.not_found}")
    
    if report.errors:
        print(f"\n[错误] ({len(report.errors)} 条)")
        for i, err in enumerate(report.errors[:10], 1):
            print(f"  {i}. ID={err.get('id', 'N/A')}: {err.get('error', err.get('message', 'unknown'))}")
        if len(report.errors) > 10:
            print(f"  ... 还有 {len(report.errors) - 10} 条错误")
    
    if report.warnings:
        print(f"\n[警告] ({len(report.warnings)} 条)")
        for i, warn in enumerate(report.warnings[:10], 1):
            print(f"  {i}. ID={warn.get('id')}: {warn.get('warning')}")
        if len(report.warnings) > 10:
            print(f"  ... 还有 {len(report.warnings) - 10} 条警告")
    
    if verbose and report.conversions:
        print(f"\n[转换详情] ({len(report.conversions)} 条)")
        for i, conv in enumerate(report.conversions[:20], 1):
            status = "[OK]" if conv.get('exists') else "[MISSING]"
            print(f"  {i}. {status} ID={conv['id']}")
            print(f"      原: {conv['original_path']}")
            print(f"      新: {conv['new_path']}")
        if len(report.conversions) > 20:
            print(f"  ... 还有 {len(report.conversions) - 20} 条转换")
    
    print("\n" + "=" * 60)
    
    # 总结建议
    if report.converted > 0 and report.failed == 0:
        print("[OK] 所有路径转换成功")
    elif report.failed > 0:
        print(f"[WARN] 有 {report.failed} 条记录转换失败，请检查错误详情")
    if report.not_found > 0:
        print(f"[WARN] 有 {report.not_found} 个文件不存在，可能需要手动处理")


def main():
    parser = argparse.ArgumentParser(
        description="路径迁移脚本 - 将数据库中的绝对路径转换为相对路径"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="预览模式，不修改数据库（默认）"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="执行迁移，修改数据库"
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=None,
        help="指定项目根目录（默认自动检测）"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="详细输出"
    )
    
    args = parser.parse_args()
    
    # 如果指定了 --execute，则不是 dry-run
    dry_run = not args.execute
    
    if not dry_run:
        print("[WARN] 即将执行迁移，这将修改数据库！")
        confirm = input("确认执行？(yes/no): ")
        if confirm.lower() != "yes":
            print("已取消")
            return
    
    print(f"\n开始{'预览' if dry_run else '执行'}迁移...")
    report = run_migration(
        dry_run=dry_run,
        project_root_override=args.project_root,
        verbose=args.verbose
    )
    
    print_report(report, verbose=args.verbose)
    
    if dry_run and report.converted > 0:
        print(f"\n[TIP] 使用 --execute 参数执行实际迁移")


if __name__ == "__main__":
    main()

