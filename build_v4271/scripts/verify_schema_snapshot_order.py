#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
验证 Schema Snapshot 迁移文件的表创建顺序

检查所有外键依赖关系是否满足（被引用的表在引用表之前创建）
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple

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

def parse_table_positions(file_path: Path) -> Dict[str, int]:
    """解析迁移文件，获取每个表的创建位置"""
    content = file_path.read_text(encoding='utf-8')
    pattern = r'# ==================== (\d+)\. (\w+) ===================='
    matches = re.findall(pattern, content)
    return {name: int(pos) for pos, name in matches}

def get_foreign_key_dependencies(file_path: Path) -> Dict[str, List[str]]:
    """从迁移文件中提取外键依赖关系"""
    content = file_path.read_text(encoding='utf-8')
    dependencies = {}
    
    # 匹配表创建代码块
    table_pattern = r'# ==================== \d+\. (\w+) ====================(.*?)(?=# ====================|\Z)'
    for match in re.finditer(table_pattern, content, re.DOTALL):
        table_name = match.group(1)
        table_code = match.group(2)
        
        # 查找外键约束
        fk_pattern = r"sa\.ForeignKeyConstraint\(\[.*?\], \['(\w+)\.(\w+)'\]"
        fk_matches = re.findall(fk_pattern, table_code)
        
        ref_tables = set()
        for ref_table, ref_col in fk_matches:
            if ref_table != table_name:  # 排除自引用
                ref_tables.add(ref_table)
        
        if ref_tables:
            dependencies[table_name] = sorted(ref_tables)
    
    return dependencies

def verify_dependencies(table_positions: Dict[str, int], dependencies: Dict[str, List[str]]) -> Tuple[bool, List[str]]:
    """验证依赖关系是否满足"""
    errors = []
    
    for table_name, ref_tables in dependencies.items():
        table_pos = table_positions.get(table_name)
        if table_pos is None:
            errors.append(f"表 {table_name} 未找到")
            continue
        
        for ref_table in ref_tables:
            ref_pos = table_positions.get(ref_table)
            if ref_pos is None:
                errors.append(f"引用表 {ref_table} 未找到（被 {table_name} 引用）")
                continue
            
            if ref_pos >= table_pos:
                errors.append(
                    f"依赖顺序错误: {ref_table} (位置 {ref_pos}) 应该在 {table_name} (位置 {table_pos}) 之前创建"
                )
    
    return len(errors) == 0, errors

def main():
    """主函数"""
    project_root = Path(__file__).parent.parent
    snapshot_file = project_root / "migrations" / "versions" / "20260112_v5_0_0_schema_snapshot.py"
    
    if not snapshot_file.exists():
        safe_print(f"[ERROR] 迁移文件不存在: {snapshot_file}")
        return 1
    
    safe_print("[INFO] 解析迁移文件...")
    table_positions = parse_table_positions(snapshot_file)
    safe_print(f"[OK] 找到 {len(table_positions)} 张表")
    
    safe_print("[INFO] 提取外键依赖关系...")
    dependencies = get_foreign_key_dependencies(snapshot_file)
    safe_print(f"[OK] 找到 {len(dependencies)} 张表有外键依赖")
    
    safe_print("[INFO] 验证依赖顺序...")
    is_valid, errors = verify_dependencies(table_positions, dependencies)
    
    if is_valid:
        safe_print("[OK] 所有依赖关系验证通过！")
        
        # 显示一些关键依赖关系作为示例
        safe_print("\n[INFO] 关键依赖关系示例:")
        key_tables = ['dim_platforms', 'dim_users', 'dim_shops', 'alert_rules', 'backup_records', 'notification_templates']
        for table in key_tables:
            if table in table_positions:
                pos = table_positions[table]
                deps = dependencies.get(table, [])
                if deps:
                    deps_str = ', '.join(deps)
                    safe_print(f"  {table} (位置 {pos}) 依赖: {deps_str}")
                else:
                    safe_print(f"  {table} (位置 {pos}) 无依赖")
        
        return 0
    else:
        safe_print(f"[ERROR] 发现 {len(errors)} 个依赖顺序错误:")
        for error in errors[:20]:  # 只显示前20个错误
            safe_print(f"  - {error}")
        if len(errors) > 20:
            safe_print(f"  ... 还有 {len(errors) - 20} 个错误未显示")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
