#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
快速测试迁移脚本中的外键定义是否正确

只检查关键表：bridge_product_keys 和 fact_product_metrics
"""

import sys
import re
from pathlib import Path

def safe_print(text: str):
    """安全打印"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            safe_text = text.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)

def check_table_foreign_keys(migration_file: Path, table_name: str):
    """检查表中的外键定义"""
    safe_print(f"\n[检查] 表 {table_name} 的外键定义...")
    
    with open(migration_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 查找表的定义部分
    table_pattern = rf"# =+\s+\d+\.\s+{table_name}\s+=+"
    match = re.search(table_pattern, content)
    if not match:
        safe_print(f"  [ERROR] 未找到表 {table_name} 的定义")
        return False
    
    # 提取表的 create_table 部分
    start_pos = match.end()
    # 查找下一个表的定义（或函数结束）
    next_table_match = re.search(r"# =+\s+\d+\.\s+\w+\s+=+", content[start_pos:])
    if next_table_match:
        table_section = content[start_pos:start_pos + next_table_match.start()]
    else:
        table_section = content[start_pos:start_pos + 5000]  # 限制范围
    
    # 查找外键约束
    fk_pattern = r"sa\.ForeignKeyConstraint\s*\(\s*\[([^\]]+)\]\s*,\s*\[([^\]]+)\](?:.*?ondelete=['\"]([^'\"]+)['\"])?"
    
    foreign_keys = []
    for match in re.finditer(fk_pattern, table_section, re.DOTALL):
        source_cols_str = match.group(1)
        target_cols_str = match.group(2)
        ondelete = match.group(3) if match.group(3) else None
        
        source_cols = [col.strip().strip("'\"") for col in source_cols_str.split(',')]
        target_cols = [col.strip().strip("'\"") for col in target_cols_str.split(',')]
        
        foreign_keys.append({
            'source_columns': source_cols,
            'target_columns': target_cols,
            'ondelete': ondelete
        })
    
    safe_print(f"  找到 {len(foreign_keys)} 个外键约束:")
    for i, fk in enumerate(foreign_keys, 1):
        source_cols_str = ', '.join(fk['source_columns'])
        target_cols_str = ', '.join(fk['target_columns'])
        ondelete_str = f", ondelete='{fk['ondelete']}'" if fk['ondelete'] else ""
        safe_print(f"    {i}. ({source_cols_str}) -> ({target_cols_str}){ondelete_str}")
    
    # 检查复合外键
    if table_name == 'bridge_product_keys':
        # 应该有1个复合外键引用 dim_products
        composite_fk_to_dim_products = [
            fk for fk in foreign_keys
            if len(fk['source_columns']) > 1
            and 'dim_products' in ' '.join(fk['target_columns'])
        ]
        if len(composite_fk_to_dim_products) == 1:
            fk = composite_fk_to_dim_products[0]
            if set(fk['source_columns']) == {'platform_code', 'shop_id', 'platform_sku'}:
                safe_print(f"  [OK] 复合外键定义正确: ({', '.join(fk['source_columns'])}) -> dim_products")
                return True
            else:
                safe_print(f"  [ERROR] 复合外键列不正确: 期望 (platform_code, shop_id, platform_sku), 实际 ({', '.join(fk['source_columns'])})")
                return False
        else:
            safe_print(f"  [ERROR] 应该有1个复合外键引用 dim_products，实际找到 {len(composite_fk_to_dim_products)} 个")
            return False
    
    elif table_name == 'fact_product_metrics':
        # 应该有1个复合外键引用 dim_products
        composite_fk_to_dim_products = [
            fk for fk in foreign_keys
            if len(fk['source_columns']) > 1
            and 'dim_products' in ' '.join(fk['target_columns'])
        ]
        if len(composite_fk_to_dim_products) == 1:
            fk = composite_fk_to_dim_products[0]
            if set(fk['source_columns']) == {'platform_code', 'shop_id', 'platform_sku'}:
                safe_print(f"  [OK] 复合外键定义正确: ({', '.join(fk['source_columns'])}) -> dim_products")
                return True
            else:
                safe_print(f"  [ERROR] 复合外键列不正确: 期望 (platform_code, shop_id, platform_sku), 实际 ({', '.join(fk['source_columns'])})")
                return False
        else:
            safe_print(f"  [ERROR] 应该有1个复合外键引用 dim_products，实际找到 {len(composite_fk_to_dim_products)} 个")
            return False
    
    return True

def main():
    project_root = Path(__file__).parent.parent
    migration_file = project_root / 'migrations' / 'versions' / '20260112_v5_0_0_schema_snapshot.py'
    
    if not migration_file.exists():
        safe_print(f"[ERROR] 迁移文件不存在: {migration_file}")
        sys.exit(1)
    
    safe_print("="*80)
    safe_print("迁移脚本外键定义检查（关键表）")
    safe_print("="*80)
    
    tables_to_check = ['bridge_product_keys', 'fact_product_metrics']
    all_passed = True
    
    for table_name in tables_to_check:
        if not check_table_foreign_keys(migration_file, table_name):
            all_passed = False
    
    safe_print("\n" + "="*80)
    if all_passed:
        safe_print("[OK] 关键表的外键定义正确！")
        sys.exit(0)
    else:
        safe_print("[FAIL] 关键表的外键定义有错误")
        sys.exit(1)

if __name__ == '__main__':
    main()
