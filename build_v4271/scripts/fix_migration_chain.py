#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复 Alembic 迁移链问题

自动检测并修复 down_revision = None 的迁移文件，建立正确的迁移链。
"""

import re
from pathlib import Path
from collections import defaultdict, OrderedDict
from typing import Dict, Optional, Set

def safe_print(text):
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

def parse_migration_file(file_path: Path) -> Optional[Dict]:
    """解析迁移文件，提取 revision 和 down_revision"""
    try:
        content = file_path.read_text(encoding='utf-8')
        
        # 提取 revision
        rev_match = re.search(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", content, re.MULTILINE)
        if not rev_match:
            return None
        
        revision = rev_match.group(1)
        
        # 提取 down_revision
        down_match = re.search(r"^down_revision\s*=\s*(?:['\"]([^'\"]+)['\"]|None)", content, re.MULTILINE)
        down_revision = None
        if down_match and down_match.group(1):
            down_revision = down_match.group(1)
        
        # 提取日期（用于排序）
        date_match = re.search(r"(\d{8})", file_path.name)
        date = date_match.group(1) if date_match else "00000000"
        
        return {
            "file": file_path.name,
            "revision": revision,
            "down_revision": down_revision,
            "date": date,
            "content": content,
            "path": file_path
        }
    except Exception as e:
        safe_print(f"[ERROR] 解析文件 {file_path.name} 失败: {e}")
        return None

def build_migration_graph(migrations_dir: Path) -> Dict:
    """构建迁移图"""
    migrations = {}
    revision_to_file = {}
    
    for file in sorted(migrations_dir.glob("*.py")):
        if file.name.startswith("__"):
            continue
        
        mig = parse_migration_file(file)
        if mig:
            migrations[mig["revision"]] = mig
            revision_to_file[mig["revision"]] = file.name
    
    return migrations, revision_to_file

def find_latest_revision(migrations: Dict) -> str:
    """找出最新的 revision（没有其他迁移指向它的）"""
    used_as_down = set()
    for mig in migrations.values():
        if mig["down_revision"]:
            used_as_down.add(mig["down_revision"])
    
    heads = [rev for rev in migrations.keys() if rev not in used_as_down]
    
    if not heads:
        return None
    
    if len(heads) > 1:
        # 如果有多个 head，选择日期最新的
        heads.sort(key=lambda rev: migrations[rev]["date"], reverse=True)
        safe_print(f"[WARN] 发现多个迁移分支，选择最新的: {heads[0]}")
    
    return heads[0]

def build_chain(migrations: Dict, start_revision: str) -> list:
    """从指定 revision 开始，向前构建迁移链"""
    chain = []
    current = start_revision
    
    while current:
        if current not in migrations:
            break
        mig = migrations[current]
        chain.append(mig)
        current = mig["down_revision"]
    
    return chain

def fix_migration_chain(migrations_dir: Path, dry_run: bool = True):
    """修复迁移链问题"""
    safe_print("=" * 80)
    safe_print("修复 Alembic 迁移链")
    safe_print("=" * 80)
    
    # 1. 构建迁移图
    migrations, revision_to_file = build_migration_graph(migrations_dir)
    safe_print(f"\n[INFO] 找到 {len(migrations)} 个迁移文件")
    
    # 2. 找出最新的 revision
    latest_revision = find_latest_revision(migrations)
    if not latest_revision:
        safe_print("[ERROR] 无法确定最新 revision")
        return
    
    safe_print(f"[INFO] 最新 revision: {latest_revision}")
    
    # 3. 找出所有 down_revision = None 的迁移（除了最新的）
    missing_down_revisions = []
    for revision, mig in migrations.items():
        if mig["down_revision"] is None and revision != latest_revision:
            missing_down_revisions.append(mig)
    
    if not missing_down_revisions:
        safe_print("\n[OK] 所有迁移都有正确的 down_revision")
        return
    
    safe_print(f"\n[INFO] 发现 {len(missing_down_revisions)} 个迁移缺少 down_revision:")
    for mig in missing_down_revisions:
        safe_print(f"  - {mig['file']}: revision={mig['revision']}")
    
    # 4. 尝试为每个迁移找到正确的 down_revision
    safe_print("\n[INFO] 尝试修复迁移链...")
    
    # 按日期排序，找到每个迁移的正确前一个迁移
    sorted_migrations = sorted(migrations.values(), key=lambda m: m["date"])
    
    fixes = []
    for mig in missing_down_revisions:
        # 找到日期最接近但更早的迁移
        mig_date = mig["date"]
        candidates = [m for m in sorted_migrations if m["date"] < mig_date and m["revision"] != mig["revision"]]
        
        if candidates:
            # 选择日期最接近的迁移
            candidates.sort(key=lambda m: m["date"], reverse=True)
            suggested_down = candidates[0]["revision"]
            
            fixes.append({
                "file": mig["file"],
                "revision": mig["revision"],
                "suggested_down_revision": suggested_down,
                "path": mig["path"]
            })
            safe_print(f"  [FIX] {mig['file']}: 建议设置 down_revision = '{suggested_down}'")
        else:
            safe_print(f"  [WARN] {mig['file']}: 无法确定前一个迁移，需要手动修复")
    
    # 5. 执行修复
    if fixes and not dry_run:
        safe_print("\n[INFO] 开始修复...")
        for fix in fixes:
            content = fix["path"].read_text(encoding='utf-8')
            
            # 替换 down_revision = None
            new_content = re.sub(
                r"^down_revision\s*=\s*None.*$",
                f"down_revision = '{fix['suggested_down_revision']}'",
                content,
                flags=re.MULTILINE
            )
            
            fix["path"].write_text(new_content, encoding='utf-8')
            safe_print(f"  [OK] 修复: {fix['file']}")
        
        safe_print(f"\n[OK] 修复完成: {len(fixes)} 个迁移文件")
    elif fixes:
        safe_print("\n[INFO] 这是 dry-run 模式，未实际修改文件")
        safe_print("[INFO] 使用 --execute 参数来实际执行修复")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="修复 Alembic 迁移链问题")
    parser.add_argument("--execute", action="store_true", help="实际执行修复（默认是 dry-run）")
    args = parser.parse_args()
    
    migrations_dir = Path("migrations/versions")
    
    if not migrations_dir.exists():
        safe_print(f"[ERROR] 迁移目录不存在: {migrations_dir}")
        return 1
    
    fix_migration_chain(migrations_dir, dry_run=not args.execute)
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
