#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析当前迁移状态：找出需要迁移到 Alembic 的表
"""

import re
from pathlib import Path
from collections import defaultdict

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

def analyze_migrations():
    """分析所有迁移文件"""
    migrations_dir = Path("migrations/versions")
    
    migrations = {}
    revision_to_file = {}
    
    for file in sorted(migrations_dir.glob("*.py")):
        if file.name.startswith("__"):
            continue
            
        content = file.read_text(encoding='utf-8')
        
        # 提取 revision
        rev_match = re.search(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", content, re.MULTILINE)
        if not rev_match:
            safe_print(f"[WARN] {file.name}: 缺少 revision 变量")
            continue
            
        revision = rev_match.group(1)
        
        # 提取 down_revision
        down_match = re.search(r"^down_revision\s*=\s*(?:['\"]([^'\"]+)['\"]|None)", content, re.MULTILINE)
        down_revision = None
        if down_match:
            down_val = down_match.group(1)
            if down_val and down_val != "None":
                down_revision = down_val
        
        # 提取创建的表
        created_tables = set()
        for match in re.finditer(r"op\.create_table\(['\"](\w+)['\"]", content):
            created_tables.add(match.group(1))
        
        migrations[revision] = {
            "file": file.name,
            "revision": revision,
            "down_revision": down_revision,
            "created_tables": created_tables
        }
        revision_to_file[revision] = file.name
    
    return migrations, revision_to_file

def find_tables_in_schema():
    """找出 schema.py 中定义的所有表"""
    schema_file = Path("modules/core/db/schema.py")
    content = schema_file.read_text(encoding='utf-8')
    
    tables = set()
    for match in re.finditer(r"__tablename__\s*=\s*['\"](\w+)['\"]", content):
        tables.add(match.group(1))
    
    return tables

def find_latest_revision(migrations):
    """找出最新的 revision（没有其他迁移指向它的）"""
    # 找出所有作为 down_revision 的 revision
    used_as_down = set()
    for mig in migrations.values():
        if mig["down_revision"]:
            used_as_down.add(mig["down_revision"])
    
    # 找出所有不是任何迁移的 down_revision 的 revision（可能是多个分支的head）
    heads = []
    for revision, mig in migrations.items():
        if revision not in used_as_down:
            heads.append(revision)
    
    # 如果有多个head，选择日期最新的
    if len(heads) > 1:
        # 按日期排序，选择最新的
        heads.sort(reverse=True)
        safe_print(f"[INFO] 发现多个迁移分支，选择最新的: {heads[0]}")
    
    return heads[0] if heads else None

def main():
    safe_print("=" * 80)
    safe_print("分析当前迁移状态")
    safe_print("=" * 80)
    
    # 1. 分析所有迁移文件
    safe_print("\n[1] 分析迁移文件...")
    migrations, revision_to_file = analyze_migrations()
    safe_print(f"  找到 {len(migrations)} 个迁移文件")
    
    # 2. 找出 schema.py 中定义的所有表
    safe_print("\n[2] 分析 schema.py 中定义的表...")
    schema_tables = find_tables_in_schema()
    safe_print(f"  schema.py 中定义了 {len(schema_tables)} 张表")
    
    # 3. 找出所有迁移中创建的表
    safe_print("\n[3] 分析迁移中已创建的表...")
    migration_tables = set()
    for mig in migrations.values():
        migration_tables.update(mig["created_tables"])
    safe_print(f"  迁移中已创建 {len(migration_tables)} 张表")
    
    # 4. 找出需要迁移的表（在 schema.py 中但不在迁移中）
    safe_print("\n[4] 找出需要迁移到 Alembic 的表...")
    missing_tables = schema_tables - migration_tables
    safe_print(f"  需要迁移的表数量: {len(missing_tables)}")
    
    if missing_tables:
        safe_print("\n  需要迁移的表列表:")
        for table in sorted(missing_tables):
            safe_print(f"    - {table}")
    
    # 5. 找出最新的 revision
    safe_print("\n[5] 找出最新的 revision...")
    latest_revision = find_latest_revision(migrations)
    if latest_revision:
        safe_print(f"  最新 revision: {latest_revision} ({revision_to_file.get(latest_revision, 'N/A')})")
    else:
        safe_print("  [ERROR] 无法确定最新 revision")
    
    # 6. 检查迁移链问题
    safe_print("\n[6] 检查迁移链问题...")
    missing_down_revisions = []
    for revision, mig in migrations.items():
        if mig["down_revision"] is None and revision != latest_revision:
            missing_down_revisions.append((revision, mig["file"]))
    
    if missing_down_revisions:
        safe_print(f"  发现 {len(missing_down_revisions)} 个迁移缺少 down_revision:")
        for rev, file in missing_down_revisions:
            safe_print(f"    - {file}: revision={rev}")
    
    # 输出总结
    safe_print("\n" + "=" * 80)
    safe_print("总结")
    safe_print("=" * 80)
    safe_print(f"迁移文件数: {len(migrations)}")
    safe_print(f"schema.py 表数: {len(schema_tables)}")
    safe_print(f"迁移中表数: {len(migration_tables)}")
    safe_print(f"需要迁移的表数: {len(missing_tables)}")
    safe_print(f"最新 revision: {latest_revision}")
    safe_print(f"迁移链问题: {len(missing_down_revisions)} 个")
    
    return {
        "missing_tables": sorted(missing_tables),
        "latest_revision": latest_revision,
        "migration_count": len(migrations),
        "schema_table_count": len(schema_tables),
        "migration_table_count": len(migration_tables)
    }

if __name__ == "__main__":
    main()
