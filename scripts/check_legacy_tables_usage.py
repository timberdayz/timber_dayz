#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查历史遗留表的使用情况

检查内容：
1. 表是否有数据（行数）
2. 代码中是否有引用（grep 搜索）
3. 表结构（列信息）
4. 表的最后修改时间（如果可获取）

用于确定哪些遗留表可以安全清理
"""

import sys
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import inspect, text
from backend.models.database import engine


def safe_print(text_str):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text_str, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text_str.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            safe_text = text_str.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)


def get_legacy_tables() -> Dict[str, List[str]]:
    """获取历史遗留表列表（按schema分类）"""
    return {
        'a_class': ['campaign_targets'],
        'core': ['dim_date', 'fact_sales_orders'],
        'public': [
            'collection_tasks_backup',
            'key_value',
            'keyvalue',
            'raw_ingestions',
            'report_execution_log',
            'report_recipient',
            'report_schedule',
            'report_schedule_user',
            'user_roles',
        ]
    }


def check_table_exists(conn, schema: str, table_name: str) -> bool:
    """检查表是否存在"""
    try:
        if schema == 'public':
            query = text("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                    AND table_name = :table_name
            """)
        else:
            query = text("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = :schema 
                    AND table_name = :table_name
            """)
            query = query.bindparams(schema=schema)
        
        query = query.bindparams(table_name=table_name)
        result = conn.execute(query).scalar()
        return result > 0
    except Exception as e:
        safe_print(f"  [ERROR] 检查表是否存在时出错: {e}")
        return False


def get_table_row_count(conn, schema: str, table_name: str) -> int:
    """获取表的行数"""
    try:
        if schema == 'public':
            query = text(f'SELECT COUNT(*) FROM "{table_name}"')
        else:
            query = text(f'SELECT COUNT(*) FROM "{schema}"."{table_name}"')
        
        result = conn.execute(query).scalar()
        return result or 0
    except Exception as e:
        safe_print(f"  [ERROR] 获取行数时出错: {e}")
        return -1


def get_table_size(conn, schema: str, table_name: str) -> str:
    """获取表的大小（人类可读格式）"""
    try:
        if schema == 'public':
            query = text(f"""
                SELECT pg_size_pretty(pg_total_relation_size('"{table_name}"'))
            """)
        else:
            query = text(f"""
                SELECT pg_size_pretty(pg_total_relation_size('"{schema}"."{table_name}"'))
            """)
        
        result = conn.execute(query).scalar()
        return result or "未知"
    except Exception as e:
        return f"错误: {e}"


def get_table_columns(conn, schema: str, table_name: str) -> List[str]:
    """获取表的列名列表"""
    try:
        if schema == 'public':
            query = text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                    AND table_name = :table_name
                ORDER BY ordinal_position
            """)
        else:
            query = text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = :schema
                    AND table_name = :table_name
                ORDER BY ordinal_position
            """)
            query = query.bindparams(schema=schema)
        
        query = query.bindparams(table_name=table_name)
        result = conn.execute(query)
        return [row[0] for row in result]
    except Exception as e:
        safe_print(f"  [ERROR] 获取列信息时出错: {e}")
        return []


def search_code_references(table_name: str) -> List[Dict[str, str]]:
    """在代码中搜索表的引用"""
    references = []
    
    # 搜索模式
    patterns = [
        rf'\b{table_name}\b',  # 表名
        rf'"{table_name}"',    # 双引号表名
        rf"'{table_name}'",    # 单引号表名
        rf'`{table_name}`',    # 反引号表名（MySQL风格）
    ]
    
    # 搜索目录
    search_dirs = [
        project_root / 'backend',
        project_root / 'modules',
        project_root / 'scripts',
        project_root / 'migrations',
    ]
    
    # 排除的文件模式
    exclude_patterns = [
        '__pycache__',
        '.pyc',
        '.pyo',
        'node_modules',
        '.git',
    ]
    
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        
        for file_path in search_dir.rglob('*.py'):
            # 排除某些目录
            if any(exclude in str(file_path) for exclude in exclude_patterns):
                continue
            
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                
                for pattern in patterns:
                    for match in re.finditer(pattern, content):
                        line_num = content[:match.start()].count('\n') + 1
                        line_content = content.split('\n')[line_num - 1].strip()
                        
                        # 避免重复（同一文件的同一行）
                        ref_key = f"{file_path}:{line_num}"
                        if not any(r['file'] == str(file_path) and r['line'] == line_num for r in references):
                            references.append({
                                'file': str(file_path.relative_to(project_root)),
                                'line': line_num,
                                'content': line_content[:100],  # 只取前100个字符
                            })
            except Exception as e:
                # 忽略无法读取的文件
                pass
    
    return references


def main():
    safe_print("=" * 80)
    safe_print("历史遗留表使用情况检查")
    safe_print("=" * 80)
    
    legacy_tables = get_legacy_tables()
    
    # 输出文件
    output_file = project_root / "temp" / "legacy_tables_usage_check.txt"
    output_file.parent.mkdir(exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f_out:
        with engine.connect() as conn:
            total_tables = sum(len(tables) for tables in legacy_tables.values())
            checked_count = 0
            
            for schema, tables in legacy_tables.items():
                safe_print(f"\n[{schema}] schema ({len(tables)} 张表)")
                f_out.write(f"\n[{schema}] schema ({len(tables)} 张表)\n")
                f_out.write("=" * 80 + "\n\n")
                
                for table_name in sorted(tables):
                    checked_count += 1
                    safe_print(f"\n[{checked_count}/{total_tables}] 检查表: {schema}.{table_name}")
                    f_out.write(f"\n表: {schema}.{table_name}\n")
                    f_out.write("-" * 80 + "\n")
                    
                    # 1. 检查表是否存在
                    exists = check_table_exists(conn, schema, table_name)
                    if not exists:
                        safe_print(f"  [INFO] 表不存在（可能已删除）")
                        f_out.write(f"状态: 表不存在（可能已删除）\n\n")
                        continue
                    
                    # 2. 获取表的行数
                    row_count = get_table_row_count(conn, schema, table_name)
                    if row_count >= 0:
                        safe_print(f"  行数: {row_count:,}")
                        f_out.write(f"行数: {row_count:,}\n")
                    else:
                        safe_print(f"  [ERROR] 无法获取行数")
                        f_out.write(f"行数: 无法获取\n")
                    
                    # 3. 获取表的大小
                    table_size = get_table_size(conn, schema, table_name)
                    safe_print(f"  大小: {table_size}")
                    f_out.write(f"大小: {table_size}\n")
                    
                    # 4. 获取表的列信息
                    columns = get_table_columns(conn, schema, table_name)
                    safe_print(f"  列数: {len(columns)}")
                    f_out.write(f"列数: {len(columns)}\n")
                    if columns:
                        safe_print(f"  列名: {', '.join(columns[:10])}{' ...' if len(columns) > 10 else ''}")
                        f_out.write(f"列名: {', '.join(columns)}\n")
                    
                    # 5. 搜索代码引用
                    safe_print(f"  搜索代码引用...")
                    references = search_code_references(table_name)
                    safe_print(f"  代码引用: {len(references)} 处")
                    f_out.write(f"代码引用: {len(references)} 处\n")
                    
                    if references:
                        safe_print(f"  引用位置:")
                        f_out.write(f"\n引用位置:\n")
                        for ref in references[:20]:  # 只显示前20个
                            ref_str = f"    {ref['file']}:{ref['line']} - {ref['content']}"
                            safe_print(ref_str)
                            f_out.write(f"  {ref['file']}:{ref['line']} - {ref['content']}\n")
                        if len(references) > 20:
                            safe_print(f"    ... 还有 {len(references) - 20} 处引用")
                            f_out.write(f"  ... 还有 {len(references) - 20} 处引用\n")
                    
                    # 6. 清理建议
                    f_out.write(f"\n清理建议:\n")
                    if row_count == 0:
                        safe_print(f"  [建议] 表为空，可以安全清理")
                        f_out.write(f"  - 表为空（0行），可以安全清理\n")
                    elif row_count > 0:
                        safe_print(f"  [警告] 表有数据（{row_count:,} 行），清理前需要确认")
                        f_out.write(f"  - 表有数据（{row_count:,} 行），清理前需要确认数据是否重要\n")
                    
                    if len(references) == 0:
                        safe_print(f"  [建议] 代码中无引用，可以安全清理")
                        f_out.write(f"  - 代码中无引用，可以安全清理\n")
                    elif len(references) > 0:
                        safe_print(f"  [警告] 代码中有引用（{len(references)} 处），需要检查引用位置")
                        f_out.write(f"  - 代码中有引用（{len(references)} 处），需要检查引用位置\n")
                    
                    f_out.write("\n")
            
            # 总结
            safe_print("\n" + "=" * 80)
            safe_print("检查总结")
            safe_print("=" * 80)
            
            f_out.write("\n" + "=" * 80 + "\n")
            f_out.write("检查总结\n")
            f_out.write("=" * 80 + "\n\n")
            
            safe_print(f"\n已检查 {checked_count} 张表")
            safe_print(f"详细报告已保存到: {output_file}")
            f_out.write(f"已检查 {checked_count} 张表\n")
            f_out.write(f"报告生成时间: {Path(__file__).stat().st_mtime}\n")
    
    safe_print("\n" + "=" * 80)
    safe_print("建议")
    safe_print("=" * 80)
    safe_print("1. 查看详细报告: temp/legacy_tables_usage_check.txt")
    safe_print("2. 对于有数据的表，确认数据是否重要")
    safe_print("3. 对于有代码引用的表，检查引用位置")
    safe_print("4. 确认可以安全清理的表后，再执行清理")
    safe_print("=" * 80)


if __name__ == "__main__":
    main()
