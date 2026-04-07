#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理临时文件脚本 - v4.11.4

清理规则：
- temp/outputs/：保留最近30天的文件，删除更早的文件
- temp/logs/：保留最近7天的日志文件
- temp/development/：保留最近7天的开发文件
- temp/cache/：清理所有.pkl缓存文件（可重新生成）
- temp/reports/：保留最近30天的报告
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
import shutil

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def safe_print(msg):
    """安全打印"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('utf-8', errors='ignore').decode('utf-8'))

def cleanup_directory(directory: Path, days_to_keep: int, dry_run: bool = False):
    """清理目录中的旧文件"""
    if not directory.exists():
        return 0, 0
    
    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    deleted_count = 0
    total_size = 0
    
    for file_path in directory.rglob('*'):
        if file_path.is_file():
            try:
                file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_mtime < cutoff_date:
                    file_size = file_path.stat().st_size
                    if not dry_run:
                        file_path.unlink()
                    deleted_count += 1
                    total_size += file_size
                    safe_print(f"  {'[DRY RUN] ' if dry_run else ''}删除: {file_path.relative_to(project_root)} ({file_size / 1024 / 1024:.2f} MB)")
            except Exception as e:
                safe_print(f"  错误: 无法删除 {file_path}: {e}")
    
    return deleted_count, total_size

def cleanup_cache(dry_run: bool = False):
    """清理缓存文件"""
    cache_dir = project_root / 'temp' / 'cache'
    if not cache_dir.exists():
        return 0, 0
    
    deleted_count = 0
    total_size = 0
    
    for pkl_file in cache_dir.rglob('*.pkl'):
        try:
            file_size = pkl_file.stat().st_size
            if not dry_run:
                pkl_file.unlink()
            deleted_count += 1
            total_size += file_size
        except Exception as e:
            safe_print(f"  错误: 无法删除 {pkl_file}: {e}")
    
    return deleted_count, total_size

def main():
    import argparse
    parser = argparse.ArgumentParser(description='清理临时文件')
    parser.add_argument('--dry-run', action='store_true', help='仅显示将要删除的文件，不实际删除')
    args = parser.parse_args()
    
    safe_print("=" * 60)
    safe_print("临时文件清理脚本 v4.11.4")
    safe_print("=" * 60)
    
    if args.dry_run:
        safe_print("\n[DRY RUN模式] 仅显示将要删除的文件\n")
    
    temp_dir = project_root / 'temp'
    if not temp_dir.exists():
        safe_print("temp目录不存在，无需清理")
        return
    
    total_deleted = 0
    total_size = 0
    
    # 清理outputs目录（保留30天）
    safe_print("\n[1/5] 清理outputs目录（保留30天）...")
    deleted, size = cleanup_directory(temp_dir / 'outputs', days_to_keep=30, dry_run=args.dry_run)
    total_deleted += deleted
    total_size += size
    safe_print(f"  删除 {deleted} 个文件，释放 {size / 1024 / 1024:.2f} MB")
    
    # 清理logs目录（保留7天）
    safe_print("\n[2/5] 清理logs目录（保留7天）...")
    deleted, size = cleanup_directory(temp_dir / 'logs', days_to_keep=7, dry_run=args.dry_run)
    total_deleted += deleted
    total_size += size
    safe_print(f"  删除 {deleted} 个文件，释放 {size / 1024 / 1024:.2f} MB")
    
    # 清理development目录（保留7天）
    safe_print("\n[3/5] 清理development目录（保留7天）...")
    deleted, size = cleanup_directory(temp_dir / 'development', days_to_keep=7, dry_run=args.dry_run)
    total_deleted += deleted
    total_size += size
    safe_print(f"  删除 {deleted} 个文件，释放 {size / 1024 / 1024:.2f} MB")
    
    # 清理reports目录（保留30天）
    safe_print("\n[4/5] 清理reports目录（保留30天）...")
    deleted, size = cleanup_directory(temp_dir / 'reports', days_to_keep=30, dry_run=args.dry_run)
    total_deleted += deleted
    total_size += size
    safe_print(f"  删除 {deleted} 个文件，释放 {size / 1024 / 1024:.2f} MB")
    
    # 清理cache目录（所有.pkl文件）
    safe_print("\n[5/5] 清理cache目录（所有.pkl文件）...")
    deleted, size = cleanup_cache(dry_run=args.dry_run)
    total_deleted += deleted
    total_size += size
    safe_print(f"  删除 {deleted} 个文件，释放 {size / 1024 / 1024:.2f} MB")
    
    safe_print("\n" + "=" * 60)
    safe_print("清理完成")
    safe_print("=" * 60)
    safe_print(f"总计删除: {total_deleted} 个文件")
    safe_print(f"总计释放: {total_size / 1024 / 1024:.2f} MB")
    
    if args.dry_run:
        safe_print("\n[DRY RUN模式] 未实际删除文件")
        safe_print("运行时不加--dry-run参数以实际删除文件")

if __name__ == '__main__':
    main()






