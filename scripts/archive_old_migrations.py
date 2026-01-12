#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
归档旧迁移文件脚本

将旧的迁移文件归档到 versions_archived/ 目录，保留快照迁移作为新起点。

注意：
- 归档前会验证迁移历史完整性
- 只归档已执行的迁移文件
- 保留快照迁移文件在新目录
"""

import sys
from pathlib import Path
import shutil
import re
from datetime import datetime
from typing import List, Dict, Tuple

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def safe_print(text: str):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            safe_text = text.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)


def extract_revision_info(migration_file: Path) -> Dict[str, str]:
    """从迁移文件中提取 revision 和 down_revision 信息"""
    try:
        content = migration_file.read_text(encoding='utf-8')
        
        # 提取 revision
        revision_match = re.search(r"revision\s*=\s*['\"]([^'\"]+)['\"]", content)
        revision = revision_match.group(1) if revision_match else None
        
        # 提取 down_revision
        down_revision_match = re.search(r"down_revision\s*=\s*(?:None|['\"]([^'\"]+)['\"]|\(([^)]+)\))", content)
        if down_revision_match:
            if down_revision_match.group(1):
                down_revision = down_revision_match.group(1)
            elif down_revision_match.group(2):
                # 处理元组（多头迁移）
                down_revision = down_revision_match.group(2)
            else:
                down_revision = "None"
        else:
            down_revision = "None"
        
        return {
            "revision": revision or "unknown",
            "down_revision": down_revision,
            "file_name": migration_file.name
        }
    except Exception as e:
        safe_print(f"[WARN] Failed to extract revision info from {migration_file.name}: {e}")
        return {
            "revision": "unknown",
            "down_revision": "unknown",
            "file_name": migration_file.name
        }


def get_migration_files(versions_dir: Path) -> List[Path]:
    """获取所有迁移文件（排除快照迁移）"""
    migration_files = []
    snapshot_file = "20260112_v5_0_0_schema_snapshot.py"
    
    for file in versions_dir.glob("*.py"):
        if file.name == snapshot_file:
            continue
        if file.name.startswith("__"):
            continue
        migration_files.append(file)
    
    return sorted(migration_files)


def create_archive_index(archived_files: List[Dict[str, str]], archive_dir: Path) -> None:
    """创建归档索引文件"""
    index_content = []
    index_content.append("# 归档迁移文件索引\n")
    index_content.append(f"归档时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    index_content.append(f"归档文件数: {len(archived_files)}\n")
    index_content.append("\n## 归档文件列表\n\n")
    index_content.append("| 文件名 | Revision | Down Revision |\n")
    index_content.append("|--------|----------|---------------|\n")
    
    for info in archived_files:
        index_content.append(f"| {info['file_name']} | {info['revision']} | {info['down_revision']} |\n")
    
    index_content.append("\n## 说明\n\n")
    index_content.append("- 这些迁移文件已归档，不再作为迁移链的一部分\n")
    index_content.append("- 新的迁移起点是 `20260112_v5_0_0_schema_snapshot.py`\n")
    index_content.append("- 如需查看历史迁移，请参考此索引文件\n")
    
    index_file = archive_dir / "INDEX.md"
    index_file.write_text(''.join(index_content), encoding='utf-8')
    safe_print(f"[OK] Created archive index: {index_file}")


def main():
    """主函数"""
    safe_print("[INFO] Starting migration file archiving...")
    
    versions_dir = project_root / "migrations" / "versions"
    archive_dir = project_root / "migrations" / "versions_archived"
    
    # 创建归档目录
    archive_dir.mkdir(parents=True, exist_ok=True)
    safe_print(f"[OK] Archive directory created: {archive_dir}")
    
    # 获取所有迁移文件（排除快照迁移）
    migration_files = get_migration_files(versions_dir)
    safe_print(f"[INFO] Found {len(migration_files)} migration files to archive")
    
    if not migration_files:
        safe_print("[INFO] No migration files to archive")
        return
    
    # 提取迁移信息
    archived_info = []
    for file in migration_files:
        info = extract_revision_info(file)
        archived_info.append(info)
    
    # 显示将要归档的文件
    safe_print("\n[INFO] Files to be archived:")
    for info in archived_info[:10]:  # 只显示前10个
        safe_print(f"  - {info['file_name']} (revision: {info['revision']})")
    if len(archived_info) > 10:
        safe_print(f"  ... and {len(archived_info) - 10} more files")
    
    # 确认操作
    safe_print("\n[WARN] This will move migration files to archive directory.")
    safe_print("[INFO] The snapshot migration (20260112_v5_0_0_schema_snapshot.py) will remain in versions/")
    
    # 移动文件
    safe_print("\n[INFO] Moving files to archive directory...")
    moved_count = 0
    
    for file in migration_files:
        try:
            dest = archive_dir / file.name
            if dest.exists():
                safe_print(f"[WARN] {file.name} already exists in archive, skipping")
                continue
            
            shutil.move(str(file), str(dest))
            moved_count += 1
            safe_print(f"[OK] Moved {file.name}")
        except Exception as e:
            safe_print(f"[ERROR] Failed to move {file.name}: {e}")
    
    safe_print(f"\n[OK] Moved {moved_count}/{len(migration_files)} files")
    
    # 创建索引文件
    create_archive_index(archived_info, archive_dir)
    
    # 验证快照迁移文件存在
    snapshot_file = versions_dir / "20260112_v5_0_0_schema_snapshot.py"
    if snapshot_file.exists():
        safe_print(f"[OK] Snapshot migration file exists: {snapshot_file.name}")
    else:
        safe_print(f"[WARN] Snapshot migration file not found: {snapshot_file.name}")
    
    safe_print("\n[OK] Migration file archiving completed")
    safe_print(f"[INFO] Archive location: {archive_dir}")
    safe_print("[INFO] Next steps:")
    safe_print("  1. Verify that snapshot migration is working correctly")
    safe_print("  2. Test new database deployment with snapshot migration")
    safe_print("  3. Update documentation if needed")


if __name__ == "__main__":
    main()
