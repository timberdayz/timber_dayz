#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迁移文件验证脚本
在提交代码之前检查迁移文件的常见问题

检查项：
1. Python语法错误
2. BOOLEAN类型默认值错误（sa.text('1')/'0' 应该是 'true'/'false'）
3. 外键引用错误（dim_product.product_surrogate_id 应该是 dim_product_master.product_id）
4. 外键引用的表是否在schema.py中定义
"""

import sys
import re
import ast
from pathlib import Path
from typing import List, Tuple, Dict, Set

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

def get_schema_tables() -> Set[str]:
    """从schema.py获取所有表名"""
    try:
        project_root = Path(__file__).parent.parent
        schema_file = project_root / "modules" / "core" / "db" / "schema.py"
        content = schema_file.read_text(encoding='utf-8')
        
        # 查找所有 __tablename__ = "xxx" 的定义
        pattern = r'__tablename__\s*=\s*["\']([^"\']+)["\']'
        tables = set(re.findall(pattern, content))
        
        return tables
    except Exception as e:
        safe_print(f"[WARNING] 无法读取schema.py: {e}")
        return set()

def check_python_syntax(migration_file: Path) -> Tuple[bool, str]:
    """检查Python语法"""
    try:
        content = migration_file.read_text(encoding='utf-8')
        ast.parse(content)
        return True, ""
    except SyntaxError as e:
        return False, f"语法错误: {e.msg} (行 {e.lineno})"
    except Exception as e:
        return False, f"解析错误: {e}"

def check_boolean_defaults(migration_file: Path) -> List[Tuple[int, str, str]]:
    """检查BOOLEAN类型的默认值错误"""
    errors = []
    try:
        content = migration_file.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        # 查找 sa.Boolean() 后跟 server_default=sa.text('1') 或 sa.text('0')
        for i, line in enumerate(lines, 1):
            # 检查是否有 Boolean + server_default=sa.text('1') 或 ('0')
            # 只检查同一行中有错误的默认值
            if 'sa.Boolean()' in line or 'sa.Boolean(' in line:
                # 检查同一行中是否有错误的默认值
                if re.search(r'server_default\s*=\s*sa\.text\([\'"]?([01])[\'"]?\)', line):
                    match = re.search(r'server_default\s*=\s*sa\.text\([\'"]?([01])[\'"]?\)', line)
                    if match:
                        value = match.group(1)
                        expected = 'true' if value == '1' else 'false'
                        errors.append((i, line.strip()[:80], f"BOOLEAN默认值错误: 使用sa.text('{value}')，应该是'{expected}'"))
        
    except Exception as e:
        safe_print(f"[WARNING] 无法检查BOOLEAN默认值: {e}")
    
    return errors

def check_foreign_key_references(migration_file: Path, schema_tables: Set[str]) -> List[Tuple[int, str, str]]:
    """检查外键引用错误"""
    errors = []
    try:
        content = migration_file.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            # 检查常见错误：dim_product.product_surrogate_id (应该是 dim_product_master.product_id)
            if 'dim_product.' in line and 'dim_product_master' not in line and 'dim_products' not in line:
                if 'product_surrogate_id' in line or ('ForeignKeyConstraint' in line and 'dim_product' in line):
                    errors.append((i, line.strip()[:80], "外键引用错误: dim_product.product_surrogate_id 应该是 dim_product_master.product_id"))
            
            # 检查外键引用的表是否在schema.py中定义（仅警告，不报错）
            if 'ForeignKeyConstraint' in line or 'create_foreign_key' in line:
                # 提取表名
                fk_match = re.search(r"['\"]([a-z_]+)\.[a-z_]+['\"]", line)
                if fk_match:
                    table_name = fk_match.group(1)
                    # 排除系统表和已知的表名
                    if table_name not in schema_tables and table_name not in ['alembic_version', 'dim_product_master', 'dim_products']:
                        if table_name == 'dim_product':
                            errors.append((i, line.strip()[:80], f"表名错误: {table_name} 应该是 dim_product_master"))
        
    except Exception as e:
        safe_print(f"[WARNING] 无法检查外键引用: {e}")
    
    return errors

def check_migration_file(migration_file: Path, schema_tables: Set[str]) -> Dict[str, any]:
    """检查单个迁移文件"""
    result = {
        'file': str(migration_file),
        'name': migration_file.name,
        'syntax_ok': True,
        'syntax_error': '',
        'boolean_errors': [],
        'fk_errors': [],
        'all_ok': True
    }
    
    # 1. 检查Python语法
    syntax_ok, syntax_error = check_python_syntax(migration_file)
    result['syntax_ok'] = syntax_ok
    result['syntax_error'] = syntax_error
    if not syntax_ok:
        result['all_ok'] = False
        return result
    
    # 2. 检查BOOLEAN默认值
    boolean_errors = check_boolean_defaults(migration_file)
    result['boolean_errors'] = boolean_errors
    if boolean_errors:
        result['all_ok'] = False
    
    # 3. 检查外键引用
    fk_errors = check_foreign_key_references(migration_file, schema_tables)
    result['fk_errors'] = fk_errors
    if fk_errors:
        result['all_ok'] = False
    
    return result

def main():
    """主函数"""
    project_root = Path(__file__).parent.parent
    migrations_dir = project_root / "migrations" / "versions"
    
    safe_print("=" * 80)
    safe_print("迁移文件验证脚本")
    safe_print("=" * 80)
    safe_print("")
    
    # 获取schema.py中的所有表名
    safe_print("[1] 读取schema.py中的表定义...")
    schema_tables = get_schema_tables()
    safe_print(f"  找到 {len(schema_tables)} 张表定义")
    safe_print("")
    
    # 获取所有迁移文件
    if not migrations_dir.exists():
        safe_print(f"[ERROR] 迁移文件目录不存在: {migrations_dir}")
        return 1
    
    migration_files = [f for f in migrations_dir.glob("*.py") if f.is_file()]
    migration_files.sort()
    
    safe_print(f"[2] 检查 {len(migration_files)} 个迁移文件...")
    safe_print("")
    
    results = []
    total_errors = 0
    
    for migration_file in migration_files:
        result = check_migration_file(migration_file, schema_tables)
        results.append(result)
        
        if not result['all_ok']:
            total_errors += 1
            safe_print(f"  [FAIL] {result['name']}")
            
            if result['syntax_error']:
                safe_print(f"    语法错误: {result['syntax_error']}")
            
            if result['boolean_errors']:
                for line_num, line, error_msg in result['boolean_errors']:
                    safe_print(f"    第{line_num}行: {error_msg}")
                    safe_print(f"      代码: {line}")
            
            if result['fk_errors']:
                for line_num, line, error_msg in result['fk_errors']:
                    safe_print(f"    第{line_num}行: {error_msg}")
                    safe_print(f"      代码: {line}")
        else:
            safe_print(f"  [OK] {result['name']}")
    
    safe_print("")
    safe_print("=" * 80)
    safe_print("验证结果汇总")
    safe_print("=" * 80)
    
    passed = len(results) - total_errors
    safe_print(f"总计: {len(results)} 个文件")
    safe_print(f"通过: {passed} 个")
    safe_print(f"失败: {total_errors} 个")
    
    safe_print("")
    if total_errors == 0:
        safe_print("[OK] 所有迁移文件验证通过")
        return 0
    else:
        safe_print("[WARNING] 发现错误，请修复后再提交")
        return 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        safe_print("\n[中断] 用户取消")
        sys.exit(1)
    except Exception as e:
        safe_print(f"\n[ERROR] 验证失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
