"""
同步数据库调用检测脚本 - 西虹ERP系统

职责:
- 检测 async def 中的同步数据库调用
- 检测阻塞调用（time.sleep）
- 检测 BackgroundTasks/create_task 中的同步调用
- 生成详细报告

版本: v4.18.2
创建: 2026-01-01

使用方法:
    python scripts/detect_sync_db_calls.py
    python scripts/detect_sync_db_calls.py --path backend/routers
    python scripts/detect_sync_db_calls.py --verbose
"""

import os
import re
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass
from enum import Enum


class Severity(Enum):
    CRITICAL = "CRITICAL"  # 阻塞调用
    WARNING = "WARNING"    # 可能的问题
    INFO = "INFO"          # 建议检查


@dataclass
class Issue:
    file: str
    line: int
    severity: Severity
    pattern: str
    context: str
    suggestion: str


# 检测规则
DETECTION_RULES = [
    # 严重：async def 中的同步数据库调用
    {
        "pattern": r"\.query\(",
        "severity": Severity.CRITICAL,
        "description": "async def 中使用 db.query()",
        "suggestion": "使用 await db.execute(select(...))"
    },
    {
        "pattern": r"(?<!Async)SessionLocal\(\)",  # ⭐ v4.18.2修复：排除AsyncSessionLocal
        "severity": Severity.CRITICAL,
        "description": "async def 中直接创建 SessionLocal()",
        "suggestion": "使用 AsyncSessionLocal() 并手动管理生命周期"
    },
    {
        "pattern": r"time\.sleep\(",
        "severity": Severity.CRITICAL,
        "description": "async def 中使用 time.sleep()",
        "suggestion": "使用 await asyncio.sleep()"
    },
    {
        "pattern": r"db\.commit\(\)(?!\s*#.*async)",
        "severity": Severity.WARNING,
        "description": "可能的同步 db.commit()",
        "suggestion": "确保使用 await db.commit() 或检查是否在异步上下文中"
    },
    {
        "pattern": r"db\.rollback\(\)(?!\s*#.*async)",
        "severity": Severity.WARNING,
        "description": "可能的同步 db.rollback()",
        "suggestion": "确保使用 await db.rollback() 或检查是否在异步上下文中"
    },
    # psycopg2 相关
    {
        "pattern": r"from psycopg2",
        "severity": Severity.WARNING,
        "description": "导入 psycopg2（同步驱动）",
        "suggestion": "如果在异步上下文中使用，考虑迁移到 asyncpg"
    },
    {
        "pattern": r"execute_batch\(",
        "severity": Severity.WARNING,
        "description": "使用 psycopg2.extras.execute_batch()",
        "suggestion": "在异步上下文中使用 SQLAlchemy 异步批量插入"
    },
    {
        "pattern": r"connection\.connection",
        "severity": Severity.WARNING,
        "description": "获取原生 DBAPI 连接",
        "suggestion": "使用 await connection.get_raw_connection() 获取异步连接"
    },
    {
        "pattern": r"raw_conn\.cursor\(\)",
        "severity": Severity.WARNING,
        "description": "直接操作游标",
        "suggestion": "在异步上下文中使用 asyncpg 原生方法"
    },
    # BackgroundTasks 相关
    {
        "pattern": r"BackgroundTasks\.add_task\(",
        "severity": Severity.INFO,
        "description": "使用 BackgroundTasks.add_task()",
        "suggestion": "确保任务函数中的数据库操作是异步的"
    },
    {
        "pattern": r"asyncio\.create_task\(",
        "severity": Severity.INFO,
        "description": "使用 asyncio.create_task()",
        "suggestion": "确保任务函数中的数据库操作是异步的"
    },
    # 缺少 await
    {
        "pattern": r"db\.execute\([^)]+\)(?!\s*\)|\s*,)",
        "severity": Severity.INFO,
        "description": "db.execute() 调用",
        "suggestion": "确保在异步上下文中使用 await db.execute()"
    },
]


def find_async_functions(content: str) -> List[Tuple[int, int, str]]:
    """
    查找文件中的 async def 函数范围
    
    Returns:
        List of (start_line, end_line, function_name)
    """
    functions = []
    lines = content.split('\n')
    
    current_func = None
    current_start = None
    current_indent = None
    
    for i, line in enumerate(lines, 1):
        # 检测 async def 开始
        match = re.match(r'^(\s*)async\s+def\s+(\w+)', line)
        if match:
            # 保存上一个函数
            if current_func is not None:
                functions.append((current_start, i - 1, current_func))
            
            current_indent = len(match.group(1))
            current_func = match.group(2)
            current_start = i
            continue
        
        # 检测函数结束（新的函数定义或类定义，且缩进级别相同或更低）
        if current_func is not None:
            if line.strip() and not line.startswith(' ' * (current_indent + 1)):
                # 非缩进行，或缩进级别相同/更低
                if re.match(r'^\s*(async\s+)?def\s+|^\s*class\s+', line):
                    # 新的函数或类定义
                    indent = len(line) - len(line.lstrip())
                    if indent <= current_indent:
                        functions.append((current_start, i - 1, current_func))
                        current_func = None
    
    # 保存最后一个函数
    if current_func is not None:
        functions.append((current_start, len(lines), current_func))
    
    return functions


def check_file(file_path: str, verbose: bool = False) -> List[Issue]:
    """检查单个文件"""
    issues = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"[!] 无法读取文件 {file_path}: {e}")
        return issues
    
    lines = content.split('\n')
    async_functions = find_async_functions(content)
    
    # 创建行号到函数的映射
    line_to_func = {}
    for start, end, func_name in async_functions:
        for line_num in range(start, end + 1):
            line_to_func[line_num] = func_name
    
    # 检查每个规则
    for rule in DETECTION_RULES:
        pattern = re.compile(rule["pattern"])
        
        for line_num, line in enumerate(lines, 1):
            match = pattern.search(line)
            if match:
                # 只在 async 函数中检查严重问题
                in_async = line_num in line_to_func
                
                # 对于 CRITICAL 和 WARNING，只在 async 上下文中报告
                if rule["severity"] in [Severity.CRITICAL, Severity.WARNING]:
                    if not in_async:
                        continue
                
                issues.append(Issue(
                    file=file_path,
                    line=line_num,
                    severity=rule["severity"],
                    pattern=rule["description"],
                    context=line.strip()[:80],
                    suggestion=rule["suggestion"]
                ))
    
    return issues


def scan_directory(path: str, verbose: bool = False) -> List[Issue]:
    """扫描目录中的所有 Python 文件"""
    all_issues = []
    
    path = Path(path)
    
    if path.is_file():
        return check_file(str(path), verbose)
    
    # 排除的目录
    exclude_dirs = {
        '__pycache__', '.git', '.venv', 'venv', 'node_modules',
        'backups', 'archive', 'temp', 'tests'
    }
    
    for py_file in path.rglob('*.py'):
        # 跳过排除的目录
        if any(excluded in py_file.parts for excluded in exclude_dirs):
            continue
        
        if verbose:
            print(f"[*] 检查: {py_file}")
        
        issues = check_file(str(py_file), verbose)
        all_issues.extend(issues)
    
    return all_issues


def print_report(issues: List[Issue], verbose: bool = False):
    """打印检测报告"""
    if not issues:
        print("\n[OK] 未检测到同步数据库调用问题")
        return
    
    # 按严重程度分组
    by_severity: Dict[Severity, List[Issue]] = {
        Severity.CRITICAL: [],
        Severity.WARNING: [],
        Severity.INFO: [],
    }
    
    for issue in issues:
        by_severity[issue.severity].append(issue)
    
    print("\n" + "=" * 80)
    print("同步数据库调用检测报告")
    print("=" * 80)
    
    # 统计
    print(f"\n总计发现 {len(issues)} 个问题:")
    print(f"  - CRITICAL (阻塞): {len(by_severity[Severity.CRITICAL])}")
    print(f"  - WARNING (警告): {len(by_severity[Severity.WARNING])}")
    print(f"  - INFO (建议): {len(by_severity[Severity.INFO])}")
    
    # 详细报告
    for severity in [Severity.CRITICAL, Severity.WARNING, Severity.INFO]:
        issues_list = by_severity[severity]
        if not issues_list:
            continue
        
        print(f"\n{'='*40}")
        print(f"{severity.value} ({len(issues_list)} 个)")
        print("=" * 40)
        
        # 按文件分组
        by_file: Dict[str, List[Issue]] = {}
        for issue in issues_list:
            if issue.file not in by_file:
                by_file[issue.file] = []
            by_file[issue.file].append(issue)
        
        for file_path, file_issues in sorted(by_file.items()):
            print(f"\n{file_path}:")
            for issue in sorted(file_issues, key=lambda x: x.line):
                print(f"  Line {issue.line}: {issue.pattern}")
                if verbose:
                    print(f"    Context: {issue.context}")
                    print(f"    Suggestion: {issue.suggestion}")
    
    print("\n" + "=" * 80)
    print("建议: 按 CRITICAL > WARNING > INFO 的优先级修复")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="检测 async def 中的同步数据库调用"
    )
    parser.add_argument(
        "--path",
        default="backend",
        help="要扫描的路径（默认: backend）"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细信息"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON 格式"
    )
    
    args = parser.parse_args()
    
    print(f"[*] 扫描路径: {args.path}")
    
    issues = scan_directory(args.path, args.verbose)
    
    if args.json:
        import json
        output = [
            {
                "file": issue.file,
                "line": issue.line,
                "severity": issue.severity.value,
                "pattern": issue.pattern,
                "context": issue.context,
                "suggestion": issue.suggestion,
            }
            for issue in issues
        ]
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print_report(issues, args.verbose)
    
    # 如果有 CRITICAL 问题，返回非零退出码
    has_critical = any(i.severity == Severity.CRITICAL for i in issues)
    sys.exit(1 if has_critical else 0)


if __name__ == "__main__":
    main()

