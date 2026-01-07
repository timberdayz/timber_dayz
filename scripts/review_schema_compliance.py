#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审查schema.py是否符合数据库设计规范

⭐ v4.12.0新增：审查数据库模型定义是否符合规范
"""

import sys
from pathlib import Path
import ast
import re

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from modules.core.logger import get_logger

logger = get_logger(__name__)


def safe_print(text_str):
    """安全打印（Windows兼容）"""
    try:
        print(text_str)
    except UnicodeEncodeError:
        print(text_str.encode('gbk', errors='ignore').decode('gbk'))


def review_schema_compliance():
    """审查schema.py是否符合规范"""
    safe_print("=" * 70)
    safe_print("审查schema.py是否符合数据库设计规范")
    safe_print("=" * 70)
    
    # 使用数据库设计验证工具进行验证
    safe_print("\n[INFO] 使用数据库设计验证工具进行验证...")
    
    try:
        from backend.models.database import get_db
        from backend.services.database_design_validator import validate_database_design
        
        db = next(get_db())
        result = validate_database_design(db)
        
        # 筛选主键设计相关问题
        pk_issues = [i for i in result.issues if i.category == 'primary_key']
        
        safe_print(f"\n主键设计问题数: {len(pk_issues)}")
        
        if pk_issues:
            safe_print("\n主键设计问题详情:")
            for i, issue in enumerate(pk_issues[:10], 1):  # 只显示前10个
                severity_icon = {
                    'error': '[ERROR]',
                    'warning': '[WARN]',
                    'info': '[INFO]'
                }.get(issue.severity, '[UNKNOWN]')
                
                safe_print(f"  {i}. {severity_icon} {issue.table_name}: {issue.issue}")
                if issue.suggestion:
                    safe_print(f"     建议: {issue.suggestion}")
        else:
            safe_print("\n[OK] 未发现主键设计问题")
        
        db.close()
        
        return len([i for i in pk_issues if i.severity == 'error']) == 0
        
    except Exception as e:
        safe_print(f"\n[ERROR] 验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 以下代码已废弃，使用数据库设计验证工具替代
    return True
    
    schema_file = project_root / "modules" / "core" / "db" / "schema.py"
    
    if not schema_file.exists():
        safe_print(f"[ERROR] schema.py文件不存在: {schema_file}")
        return False
    
    with open(schema_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    issues = []
    
    # 1. 检查运营数据表的主键设计
    safe_print("\n[1] 检查运营数据表的主键设计...")
    
    # 运营数据表（应该使用业务标识作为主键或自增ID+唯一索引）
    operational_tables = {
        'FactOrder': {
            'expected_pk': ['platform_code', 'shop_id', 'order_id'],
            'is_operational': True
        },
        'FactOrderItem': {
            'expected_pk': ['platform_code', 'shop_id', 'order_id', 'platform_sku'],
            'is_operational': True
        },
        'FactProductMetric': {
            'expected_pk': ['id'],  # 使用自增ID，业务唯一性通过唯一索引保证
            'expected_unique': ['platform_code', 'shop_id', 'platform_sku', 'metric_date', 'granularity', 'data_domain'],
            'is_operational': True
        },
        'FactOrderAmount': {
            'expected_pk': ['id'],  # 使用自增ID，业务唯一性通过唯一索引保证
            'is_operational': True
        }
    }
    
    # 解析Python文件，查找类定义
    tree = ast.parse(content)
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_name = node.name
            if class_name in operational_tables:
                table_info = operational_tables[class_name]
                safe_print(f"\n  审查表: {class_name}")
                
                # 检查主键字段
                pk_fields = []
                has_auto_increment_id = False
                unique_constraints = []
                
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name) and target.id == '__tablename__':
                                # 跳过表名定义
                                continue
                    
                    # 检查Column定义
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name):
                                var_name = target.id
                                
                                # 检查是否是Column定义
                                if isinstance(item.value, ast.Call):
                                    if isinstance(item.value.func, ast.Name) and item.value.func.id == 'Column':
                                        # 检查是否有primary_key=True
                                        for keyword in item.value.keywords:
                                            if keyword.arg == 'primary_key' and isinstance(keyword.value, ast.Constant) and keyword.value.value:
                                                pk_fields.append(var_name)
                                                
                                                # 检查是否是自增ID
                                                if var_name == 'id':
                                                    # 检查是否有autoincrement=True
                                                    for kw in item.value.keywords:
                                                        if kw.arg == 'autoincrement' and isinstance(kw.value, ast.Constant) and kw.value.value:
                                                            has_auto_increment_id = True
                
                # 检查唯一索引
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name) and target.id == '__table_args__':
                                if isinstance(item.value, ast.Tuple):
                                    for elem in item.value.elts:
                                        if isinstance(elem, ast.Call):
                                            # 检查UniqueConstraint或Index(unique=True)
                                            if isinstance(elem.func, ast.Name):
                                                if elem.func.id == 'UniqueConstraint':
                                                    # 提取字段名
                                                    constraint_fields = []
                                                    for arg in elem.args:
                                                        if isinstance(arg, ast.Constant):
                                                            constraint_fields.append(arg.value)
                                                        elif isinstance(arg, ast.List):
                                                            for el in arg.elts:
                                                                if isinstance(el, ast.Constant):
                                                                    constraint_fields.append(el.value)
                                                    if constraint_fields:
                                                        unique_constraints.append(constraint_fields)
                                
                                elif isinstance(item.value, ast.Tuple):
                                    for elem in item.value.elts:
                                        if isinstance(elem, ast.Call) and isinstance(elem.func, ast.Name) and elem.func.id == 'Index':
                                            # 检查是否有unique=True
                                            has_unique = False
                                            index_fields = []
                                            for kw in elem.keywords:
                                                if kw.arg == 'unique' and isinstance(kw.value, ast.Constant) and kw.value.value:
                                                    has_unique = True
                                            
                                            if has_unique:
                                                # 提取字段名
                                                for arg in elem.args[1:]:  # 跳过第一个参数（索引名）
                                                    if isinstance(arg, ast.Constant):
                                                        index_fields.append(arg.value)
                                                    elif isinstance(arg, ast.List):
                                                        for el in arg.elts:
                                                            if isinstance(el, ast.Constant):
                                                                index_fields.append(el.value)
                                                if index_fields:
                                                    unique_constraints.append(index_fields)
                
                # 验证主键设计
                expected_pk = table_info.get('expected_pk', [])
                expected_unique = table_info.get('expected_unique', [])
                
                if expected_pk:
                    if set(pk_fields) != set(expected_pk):
                        issues.append({
                            'severity': 'warning',
                            'table': class_name,
                            'issue': f'主键字段不匹配: 期望{expected_pk}, 实际{pk_fields}',
                            'suggestion': f'应使用{expected_pk}作为主键'
                        })
                        safe_print(f"    [WARN] 主键字段不匹配: 期望{expected_pk}, 实际{pk_fields}")
                    else:
                        safe_print(f"    [OK] 主键设计符合规范: {pk_fields}")
                
                # 验证唯一索引（如果使用自增ID）
                if has_auto_increment_id and expected_unique:
                    found_unique = False
                    matching_constraint = None
                    
                    for constraint in unique_constraints:
                        # 检查是否包含所有期望的字段（允许额外字段）
                        if set(expected_unique).issubset(set(constraint)):
                            found_unique = True
                            matching_constraint = constraint
                            break
                    
                    if not found_unique:
                        issues.append({
                            'severity': 'error',
                            'table': class_name,
                            'issue': f'缺少业务唯一索引: 期望包含{expected_unique}',
                            'suggestion': f'应创建唯一索引包含{expected_unique}字段'
                        })
                        safe_print(f"    [ERROR] 缺少业务唯一索引: 期望包含{expected_unique}, 实际找到{unique_constraints}")
                    else:
                        safe_print(f"    [OK] 业务唯一索引符合规范: {matching_constraint} (包含{expected_unique})")
    
    # 2. 检查关键字段的NULL规则
    safe_print("\n[2] 检查关键字段的NULL规则...")
    
    # 关键字段列表（应该NOT NULL）
    critical_fields = {
        'FactOrder': ['subtotal', 'subtotal_rmb', 'total_amount', 'total_amount_rmb'],
        'FactOrderItem': ['quantity', 'unit_price', 'unit_price_rmb'],
        'FactProductMetric': ['price', 'price_rmb', 'sales_amount', 'sales_amount_rmb']  # 注意：这些字段允许NULL（inventory域）
    }
    
    # 这里需要更复杂的AST解析，暂时跳过
    safe_print("    [INFO] 关键字段NULL规则检查需要更深入的AST解析，建议使用数据库设计验证工具")
    
    # 显示问题摘要
    safe_print("\n" + "=" * 70)
    safe_print("审查结果摘要")
    safe_print("=" * 70)
    
    if issues:
        error_count = len([i for i in issues if i['severity'] == 'error'])
        warning_count = len([i for i in issues if i['severity'] == 'warning'])
        
        safe_print(f"\n总问题数: {len(issues)}")
        safe_print(f"错误数: {error_count}")
        safe_print(f"警告数: {warning_count}")
        
        safe_print("\n问题详情:")
        for i, issue in enumerate(issues, 1):
            severity_icon = {
                'error': '[ERROR]',
                'warning': '[WARN]'
            }.get(issue['severity'], '[UNKNOWN]')
            
            safe_print(f"\n  {i}. {severity_icon} {issue['table']}")
            safe_print(f"     问题: {issue['issue']}")
            safe_print(f"     建议: {issue['suggestion']}")
    else:
        safe_print("\n[OK] 未发现问题")
    
    return len([i for i in issues if i['severity'] == 'error']) == 0


if __name__ == "__main__":
    success = review_schema_compliance()
    sys.exit(0 if success else 1)

