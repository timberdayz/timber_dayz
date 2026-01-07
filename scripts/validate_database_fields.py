#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库字段验证工具

功能：
1. 检查查询中使用的字段是否存在于schema
2. 检查物化视图字段定义
3. 生成验证报告
"""

import sys
import re
from pathlib import Path
from typing import List, Dict, Any, Set
from collections import defaultdict

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class DatabaseFieldValidator:
    """数据库字段验证器"""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.schema_fields = {}  # {table_name: set(field_names)}
        self.mv_fields = {}  # {mv_name: set(field_names)}
    
    def extract_schema_fields(self) -> Dict[str, Set[str]]:
        """从schema.py中提取表字段"""
        schema_file = project_root / "modules" / "core" / "db" / "schema.py"
        
        if not schema_file.exists():
            self.errors.append({
                "file": str(schema_file),
                "message": "schema.py文件不存在"
            })
            return {}
        
        fields = {}
        
        try:
            with open(schema_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 匹配表定义：class TableName(Base):
            table_pattern = r'class\s+(\w+)\s*\([^)]*Base[^)]*\):'
            table_matches = list(re.finditer(table_pattern, content))
            
            for table_match in table_matches:
                table_name = table_match.group(1)
                table_start = table_match.end()
                
                # 查找下一个类定义或文件结束
                next_match = re.search(r'class\s+\w+\s*\(', content[table_start:])
                if next_match:
                    table_end = table_start + next_match.start()
                else:
                    table_end = len(content)
                
                table_content = content[table_start:table_end]
                
                # 提取字段定义：Column(...) 或 field_name = Column(...)
                column_pattern = r'(?:(\w+)\s*=\s*)?Column\('
                column_matches = re.finditer(column_pattern, table_content)
                
                table_fields = set()
                for col_match in column_matches:
                    if col_match.group(1):
                        table_fields.add(col_match.group(1))
                    else:
                        # 查找前一个标识符（字段名）
                        before_col = table_content[:col_match.start()]
                        field_match = re.search(r'(\w+)\s*=\s*$', before_col, re.MULTILINE)
                        if field_match:
                            table_fields.add(field_match.group(1))
                
                if table_fields:
                    fields[table_name] = table_fields
        
        except Exception as e:
            self.errors.append({
                "file": str(schema_file),
                "message": f"解析schema.py失败: {str(e)}"
            })
        
        return fields
    
    def extract_mv_fields(self) -> Dict[str, Set[str]]:
        """从物化视图服务中提取视图字段"""
        mv_service_file = project_root / "backend" / "services" / "materialized_view_service.py"
        
        if not mv_service_file.exists():
            return {}
        
        mv_fields = {}
        
        try:
            with open(mv_service_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 匹配SELECT语句中的字段
            select_pattern = r'SELECT\s+(.*?)\s+FROM\s+(\w+)'
            matches = re.finditer(select_pattern, content, re.IGNORECASE | re.DOTALL)
            
            for match in matches:
                fields_str = match.group(1)
                table_name = match.group(2)
                
                # 提取字段名（简单处理，不考虑复杂表达式）
                field_names = re.findall(r'\b(\w+)\b', fields_str)
                # 过滤掉SQL关键字
                sql_keywords = {'SELECT', 'FROM', 'WHERE', 'GROUP', 'BY', 'ORDER', 'AS', 'COUNT', 'SUM', 'AVG', 'MAX', 'MIN'}
                field_names = [f for f in field_names if f.upper() not in sql_keywords]
                
                if field_names:
                    mv_fields[table_name] = set(field_names)
        
        except Exception as e:
            self.warnings.append({
                "file": str(mv_service_file),
                "message": f"解析物化视图服务失败: {str(e)}"
            })
        
        return mv_fields
    
    def validate_query_fields(self, file_path: Path) -> List[Dict[str, Any]]:
        """验证查询文件中的字段"""
        issues = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 匹配SELECT语句
            select_pattern = r'SELECT\s+(.*?)\s+FROM\s+(\w+)'
            matches = re.finditer(select_pattern, content, re.IGNORECASE | re.DOTALL)
            
            for match in matches:
                fields_str = match.group(1)
                table_name = match.group(2)
                
                # 提取字段名
                field_names = re.findall(r'\b(\w+)\b', fields_str)
                sql_keywords = {'SELECT', 'FROM', 'WHERE', 'GROUP', 'BY', 'ORDER', 'AS', 'COUNT', 'SUM', 'AVG', 'MAX', 'MIN'}
                field_names = [f for f in field_names if f.upper() not in sql_keywords]
                
                # 检查字段是否存在
                if table_name in self.schema_fields:
                    table_fields = self.schema_fields[table_name]
                    for field_name in field_names:
                        if field_name not in table_fields and field_name not in {'*', '1'}:
                            line_num = content[:match.start()].count('\n') + 1
                            issues.append({
                                "type": "warning",
                                "file": str(file_path),
                                "line": line_num,
                                "message": f"字段 '{field_name}' 可能不存在于表 '{table_name}'"
                            })
        
        except Exception as e:
            issues.append({
                "type": "error",
                "file": str(file_path),
                "line": 0,
                "message": f"读取文件失败: {str(e)}"
            })
        
        return issues
    
    def validate_all(self) -> Dict[str, Any]:
        """验证所有数据库字段"""
        # 1. 提取schema字段
        self.schema_fields = self.extract_schema_fields()
        
        # 2. 提取物化视图字段
        self.mv_fields = self.extract_mv_fields()
        
        # 3. 验证查询文件
        all_issues = {
            "errors": self.errors.copy(),
            "warnings": self.warnings.copy()
        }
        
        # 扫描服务文件中的查询
        services_dir = project_root / "backend" / "services"
        if services_dir.exists():
            for service_file in services_dir.rglob("*.py"):
                if service_file.name == "__init__.py":
                    continue
                
                query_issues = self.validate_query_fields(service_file)
                all_issues["errors"].extend([i for i in query_issues if i.get("type") == "error"])
                all_issues["warnings"].extend([i for i in query_issues if i.get("type") == "warning"])
        
        return all_issues
    
    def generate_report(self, issues: Dict[str, Any]) -> str:
        """生成验证报告"""
        report = []
        report.append("=" * 60)
        report.append("数据库字段验证报告")
        report.append("=" * 60)
        report.append("")
        
        # 统计信息
        error_count = len(issues["errors"])
        warning_count = len(issues["warnings"])
        
        report.append(f"错误数量: {error_count}")
        report.append(f"警告数量: {warning_count}")
        report.append(f"已扫描表数: {len(self.schema_fields)}")
        report.append(f"已扫描物化视图数: {len(self.mv_fields)}")
        report.append("")
        
        # 错误列表
        if issues["errors"]:
            report.append("=" * 60)
            report.append("错误列表")
            report.append("=" * 60)
            for error in issues["errors"]:
                line_num = error.get('line', 0) or 0
                file_path = error.get('file', 'unknown')
                message = error.get('message', '未知错误')
                report.append(f"[错误] {file_path}:{line_num}")
                report.append(f"  {message}")
                report.append("")
        
        # 警告列表（只显示前10个）
        if issues["warnings"]:
            report.append("=" * 60)
            report.append("警告列表（前10个）")
            report.append("=" * 60)
            for warning in issues["warnings"][:10]:
                line_num = warning.get('line', 0) or 0
                file_path = warning.get('file', 'unknown')
                message = warning.get('message', '未知警告')
                report.append(f"[警告] {file_path}:{line_num}")
                report.append(f"  {message}")
                report.append("")
            if len(issues["warnings"]) > 10:
                report.append(f"... 还有 {len(issues['warnings']) - 10} 个警告")
        
        # 总结
        report.append("=" * 60)
        report.append("总结")
        report.append("=" * 60)
        if error_count == 0 and warning_count == 0:
            report.append("✓ 所有数据库字段验证通过！")
        else:
            report.append(f"✗ 发现 {error_count} 个错误，{warning_count} 个警告")
        
        return "\n".join(report)


def main():
    """主函数"""
    validator = DatabaseFieldValidator()
    
    print("开始验证数据库字段...")
    issues = validator.validate_all()
    
    report = validator.generate_report(issues)
    # Windows编码兼容处理
    try:
        sys.stdout.buffer.write(report.encode('utf-8'))
    except (UnicodeEncodeError, AttributeError):
        print(report.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore'))
    
    # 返回退出码
    if issues["errors"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

