#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
懒加载问题扫描脚本

扫描所有异步函数中可能存在的懒加载问题：
1. async def 函数中查询模型
2. 访问关系属性（.relationship）
3. 没有使用 selectinload/joinedload 预加载

版本: v1.0.0
创建: 2026-01-08
"""

import ast
import os
from pathlib import Path
from typing import List, Dict, Tuple
from collections import defaultdict

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 需要扫描的目录
SCAN_DIRS = [
    PROJECT_ROOT / "backend" / "routers",
    PROJECT_ROOT / "backend" / "services",
]

# 需要忽略的文件
IGNORE_PATTERNS = [
    "__pycache__",
    ".pyc",
    "__init__.py",
]

# 已知的关系属性（从 schema.py 提取）
KNOWN_RELATIONSHIPS = {
    "DimUser": ["roles", "audit_logs", "sessions", "notifications", "notification_preferences"],
    "DimRole": ["users"],
    "DimShop": ["platform"],
    "CollectionTask": ["config", "logs", "parent_task", "retry_tasks"],
    "CollectionConfig": ["tasks"],
    "CollectionTaskLog": ["task"],
    "FactAuditLog": ["user"],
    "UserSession": ["user"],
    "Notification": ["recipient"],
    "NotificationPreference": ["user"],
}

# 预加载函数名
PRELOAD_FUNCTIONS = ["selectinload", "joinedload", "subqueryload", "selectin_polymorphic"]


class LazyLoadingChecker(ast.NodeVisitor):
    """AST 访问者，检查懒加载问题"""
    
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.issues: List[Dict] = []
        self.current_function = None
        self.current_async = False
        self.select_statements: List[Tuple[int, str]] = []  # (line, model_name)
        self.relationship_accesses: List[Tuple[int, str]] = []  # (line, attr_name)
        self.preload_usage: List[Tuple[int, str]] = []  # (line, preload_func)
        self.imports = {}
        
    def visit_Import(self, node):
        """记录导入"""
        for alias in node.names:
            self.imports[alias.asname or alias.name] = alias.name
            
    def visit_ImportFrom(self, node):
        """记录 from ... import ..."""
        module = node.module or ""
        for alias in node.names:
            name = alias.asname or alias.name
            self.imports[name] = f"{module}.{alias.name}"
    
    def visit_AsyncFunctionDef(self, node):
        """检查异步函数"""
        old_function = self.current_function
        old_async = self.current_async
        old_selects = self.select_statements.copy()
        old_relationships = self.relationship_accesses.copy()
        old_preloads = self.preload_usage.copy()
        
        self.current_function = node.name
        self.current_async = True
        self.select_statements = []
        self.relationship_accesses = []
        self.preload_usage = []
        
        # 访问函数体
        self.generic_visit(node)
        
        # 分析问题
        self._analyze_issues(node.lineno, node.name)
        
        # 恢复状态
        self.current_function = old_function
        self.current_async = old_async
        self.select_statements = old_selects
        self.relationship_accesses = old_relationships
        self.preload_usage = old_preloads
    
    def visit_FunctionDef(self, node):
        """检查同步函数（可能包含异步调用）"""
        # 也检查同步函数，因为可能包含 await
        self.generic_visit(node)
    
    def visit_Call(self, node):
        """检查函数调用"""
        # 检查 select() 调用
        if isinstance(node.func, ast.Name):
            if node.func.id == "select":
                # 查找 select 的参数（模型类）
                for arg in node.args:
                    model_name = self._extract_model_name(arg)
                    if model_name:
                        self.select_statements.append((node.lineno, model_name))
        
        # 检查 selectinload/joinedload 使用
        if isinstance(node.func, ast.Attribute):
            if node.func.attr in PRELOAD_FUNCTIONS:
                self.preload_usage.append((node.lineno, node.func.attr))
        elif isinstance(node.func, ast.Name):
            if node.func.id in PRELOAD_FUNCTIONS:
                self.preload_usage.append((node.lineno, node.func.id))
        
        # 检查 .options() 调用（可能包含预加载）
        if isinstance(node.func, ast.Attribute):
            if node.func.attr == "options":
                # 检查 options 的参数
                for arg in node.args:
                    if isinstance(arg, ast.Call):
                        func_name = self._extract_function_name(arg)
                        if func_name in PRELOAD_FUNCTIONS:
                            self.preload_usage.append((node.lineno, func_name))
        
        self.generic_visit(node)
    
    def visit_Attribute(self, node):
        """检查属性访问（可能是关系属性）"""
        if self.current_async:
            # 检查是否是关系属性访问
            attr_name = node.attr
            obj_name = self._extract_object_name(node.value)
            
            # 检查是否是已知的关系属性
            if obj_name and self._is_relationship_access(obj_name, attr_name):
                self.relationship_accesses.append((node.lineno, f"{obj_name}.{attr_name}"))
        
        self.generic_visit(node)
    
    def _extract_model_name(self, node) -> str:
        """从 AST 节点提取模型名称"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            # 可能是 modules.core.db.DimUser
            return node.attr
        return None
    
    def _extract_object_name(self, node) -> str:
        """从 AST 节点提取对象名称"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        return None
    
    def _extract_function_name(self, node) -> str:
        """从 AST 节点提取函数名称"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        return None
    
    def _is_relationship_access(self, obj_name: str, attr_name: str) -> bool:
        """判断是否是关系属性访问"""
        # 检查所有已知模型的关系属性
        for model_name, relationships in KNOWN_RELATIONSHIPS.items():
            if attr_name in relationships:
                return True
        return False
    
    def _analyze_issues(self, func_line: int, func_name: str):
        """分析并记录问题"""
        if not self.current_async:
            return
        
        # 检查是否有 select 查询但没有预加载
        for select_line, model_name in self.select_statements:
            # 检查是否有对应的关系访问
            has_relationship_access = False
            relationship_attrs = []
            
            for rel_line, rel_attr in self.relationship_accesses:
                # 检查关系访问是否在 select 之后
                if rel_line > select_line:
                    has_relationship_access = True
                    relationship_attrs.append(rel_attr)
            
            if has_relationship_access:
                # 检查是否有预加载
                has_preload = False
                for preload_line, preload_func in self.preload_usage:
                    # 检查预加载是否在 select 和关系访问之间
                    if select_line <= preload_line <= max([r[0] for r in self.relationship_accesses], default=select_line):
                        has_preload = True
                        break
                
                if not has_preload:
                    # 检查是否是 db.refresh 调用（也是有效的预加载方式）
                    has_refresh = False
                    # 这个检查需要在完整的 AST 中查找，暂时跳过
                    
                    if not has_refresh:
                        self.issues.append({
                            "type": "missing_preload",
                            "severity": "error",
                            "line": select_line,
                            "function": func_name,
                            "model": model_name,
                            "relationships": relationship_attrs,
                            "message": f"在异步函数 {func_name} 中，查询 {model_name} 后访问了关系属性 {', '.join(relationship_attrs)}，但没有使用 selectinload/joinedload 预加载"
                        })
        
        # 检查是否有关系访问但没有对应的 select
        for rel_line, rel_attr in self.relationship_accesses:
            # 检查是否有对应的 select（在关系访问之前）
            has_select_before = False
            for select_line, model_name in self.select_statements:
                if select_line < rel_line:
                    has_select_before = True
                    break
            
            if not has_select_before:
                # 可能是从参数传入的对象（如 current_user）
                # 这种情况通常是安全的（因为来自 get_current_user，已经预加载）
                # 但我们也记录一下，作为信息
                self.issues.append({
                    "type": "relationship_access_without_select",
                    "severity": "info",
                    "line": rel_line,
                    "function": func_name,
                    "relationship": rel_attr,
                    "message": f"在异步函数 {func_name} 中访问了关系属性 {rel_attr}，但没有找到对应的 select 查询（可能是从参数传入的对象）"
                })


def scan_file(file_path: Path) -> List[Dict]:
    """扫描单个文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content, filename=str(file_path))
        checker = LazyLoadingChecker(file_path)
        checker.visit(tree)
        
        return checker.issues
    except SyntaxError as e:
        print(f"[WARNING] 无法解析 {file_path}: {e}")
        return []
    except Exception as e:
        print(f"[ERROR] 扫描 {file_path} 时出错: {e}")
        return []


def scan_directory(directory: Path) -> List[Dict]:
    """扫描目录中的所有 Python 文件"""
    all_issues = []
    
    for py_file in directory.rglob("*.py"):
        # 跳过忽略的文件
        if any(pattern in str(py_file) for pattern in IGNORE_PATTERNS):
            continue
        
        issues = scan_file(py_file)
        for issue in issues:
            issue["file"] = str(py_file.relative_to(PROJECT_ROOT))
        all_issues.extend(issues)
    
    return all_issues


def generate_report(issues: List[Dict]) -> str:
    """生成报告"""
    if not issues:
        return "[OK] 未发现懒加载问题"
    
    # 按严重程度分类
    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    infos = [i for i in issues if i["severity"] == "info"]
    
    report = []
    report.append("=" * 80)
    report.append("懒加载问题扫描报告")
    report.append("=" * 80)
    report.append(f"\n总计: {len(issues)} 个问题")
    report.append(f"  - 错误 (Error): {len(errors)} 个")
    report.append(f"  - 警告 (Warning): {len(warnings)} 个")
    report.append(f"  - 信息 (Info): {len(infos)} 个")
    report.append("")
    
    # 按文件分组
    issues_by_file = defaultdict(list)
    for issue in issues:
        issues_by_file[issue["file"]].append(issue)
    
    # 详细报告
    if errors:
        report.append("=" * 80)
        report.append("错误 (Error) - 必须修复")
        report.append("=" * 80)
        report.append("")
        
        for file_path, file_issues in sorted(issues_by_file.items()):
            file_errors = [i for i in file_issues if i["severity"] == "error"]
            if file_errors:
                report.append(f"\n文件: {file_path}")
                for issue in file_errors:
                    report.append(f"  行 {issue['line']}: {issue['function']}()")
                    report.append(f"    {issue['message']}")
                    if 'relationships' in issue:
                        report.append(f"    关系属性: {', '.join(issue['relationships'])}")
                    report.append("")
    
    if warnings:
        report.append("=" * 80)
        report.append("警告 (Warning) - 建议修复")
        report.append("=" * 80)
        report.append("")
        
        for file_path, file_issues in sorted(issues_by_file.items()):
            file_warnings = [i for i in file_issues if i["severity"] == "warning"]
            if file_warnings:
                report.append(f"\n文件: {file_path}")
                for issue in file_warnings:
                    report.append(f"  行 {issue['line']}: {issue['function']}()")
                    report.append(f"    {issue['message']}")
                    report.append("")
    
    if infos:
        report.append("=" * 80)
        report.append("信息 (Info) - 仅供参考")
        report.append("=" * 80)
        report.append("")
        report.append(f"共 {len(infos)} 个信息项（通常是安全的，如从参数传入的对象）")
        report.append("")
    
    # 修复建议
    report.append("=" * 80)
    report.append("修复建议")
    report.append("=" * 80)
    report.append("")
    report.append("对于错误级别的问题，请使用以下方式修复：")
    report.append("")
    report.append("1. 在查询时使用 selectinload 预加载关系：")
    report.append("   from sqlalchemy.orm import selectinload")
    report.append("   result = await db.execute(")
    report.append("       select(Model)")
    report.append("       .options(selectinload(Model.relationship))")
    report.append("   )")
    report.append("")
    report.append("2. 或者在修改关系后使用 db.refresh：")
    report.append("   await db.refresh(model, ['relationship'])")
    report.append("")
    report.append("=" * 80)
    
    return "\n".join(report)


def main():
    """主函数"""
    print("=" * 80)
    print("懒加载问题扫描脚本")
    print("=" * 80)
    print(f"\n扫描目录:")
    for scan_dir in SCAN_DIRS:
        print(f"  - {scan_dir.relative_to(PROJECT_ROOT)}")
    print("")
    
    all_issues = []
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            print(f"[WARNING] 目录不存在: {scan_dir}")
            continue
        
        print(f"[扫描] {scan_dir.relative_to(PROJECT_ROOT)}...")
        issues = scan_directory(scan_dir)
        all_issues.extend(issues)
        print(f"  发现 {len(issues)} 个问题")
    
    print("")
    print("=" * 80)
    print("生成报告...")
    print("=" * 80)
    print("")
    
    report = generate_report(all_issues)
    print(report)
    
    # 保存报告到文件
    report_file = PROJECT_ROOT / "reports" / "lazy_loading_scan_report.txt"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n报告已保存到: {report_file.relative_to(PROJECT_ROOT)}")
    
    # 返回退出码
    errors = [i for i in all_issues if i["severity"] == "error"]
    return 1 if errors else 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
