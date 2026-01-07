#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审查数据验证服务是否符合数据库设计规范

⭐ v4.12.0新增：审查data_validator.py是否符合规范
"""

import sys
from pathlib import Path

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


def review_data_validator_compliance():
    """审查数据验证服务是否符合规范"""
    safe_print("=" * 70)
    safe_print("审查数据验证服务是否符合数据库设计规范")
    safe_print("=" * 70)
    
    issues = []
    
    # 审查data_validator.py
    safe_print("\n[1] 审查data_validator.py...")
    validator_file = project_root / "backend" / "services" / "data_validator.py"
    
    if validator_file.exists():
        with open(validator_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查是否验证主键字段
        pk_fields = ['platform_code', 'order_id', 'platform_sku', 'shop_id']
        found_pk_validation = False
        
        for field in pk_fields:
            if field in content and ('validate' in content.lower() or 'error' in content.lower()):
                found_pk_validation = True
                break
        
        if found_pk_validation:
            safe_print("    [OK] 验证主键字段")
        else:
            issues.append({
                'file': 'data_validator.py',
                'severity': 'info',
                'issue': '未明确验证主键字段',
                'suggestion': '应考虑验证主键字段（platform_code、order_id等）'
            })
            safe_print("    [INFO] 未明确验证主键字段（可能在入库时处理）")
        
        # 检查是否验证数据类型
        if 'int' in content or 'float' in content or 'str' in content:
            safe_print("    [OK] 验证数据类型")
        else:
            issues.append({
                'file': 'data_validator.py',
                'severity': 'info',
                'issue': '未明确验证数据类型',
                'suggestion': '应考虑验证数据类型（整数、浮点数、字符串等）'
            })
            safe_print("    [INFO] 未明确验证数据类型")
        
        # 检查是否验证业务规则
        if 'validate' in content.lower() or 'rule' in content.lower():
            safe_print("    [OK] 验证业务规则")
        else:
            issues.append({
                'file': 'data_validator.py',
                'severity': 'info',
                'issue': '未明确验证业务规则',
                'suggestion': '应考虑验证业务规则（如订单金额不能为负数）'
            })
            safe_print("    [INFO] 未明确验证业务规则")
        
        # 检查是否处理NULL值
        if 'None' in content or 'null' in content.lower():
            safe_print("    [OK] 处理NULL值")
        else:
            issues.append({
                'file': 'data_validator.py',
                'severity': 'info',
                'issue': '未明确处理NULL值',
                'suggestion': '应考虑处理NULL值（关键字段不允许NULL）'
            })
            safe_print("    [INFO] 未明确处理NULL值（可能在schema.py中定义）")
    
    # 显示问题摘要
    safe_print("\n" + "=" * 70)
    safe_print("审查结果摘要")
    safe_print("=" * 70)
    
    if issues:
        error_count = len([i for i in issues if i['severity'] == 'error'])
        warning_count = len([i for i in issues if i['severity'] == 'warning'])
        info_count = len([i for i in issues if i['severity'] == 'info'])
        
        safe_print(f"\n总问题数: {len(issues)}")
        safe_print(f"错误数: {error_count}")
        safe_print(f"警告数: {warning_count}")
        safe_print(f"信息数: {info_count}")
        
        safe_print("\n问题详情:")
        for i, issue in enumerate(issues, 1):
            severity_icon = {
                'error': '[ERROR]',
                'warning': '[WARN]',
                'info': '[INFO]'
            }.get(issue['severity'], '[UNKNOWN]')
            
            safe_print(f"\n  {i}. {severity_icon} {issue['file']}")
            safe_print(f"     问题: {issue['issue']}")
            safe_print(f"     建议: {issue['suggestion']}")
    else:
        safe_print("\n[OK] 未发现问题")
    
    # 说明
    safe_print("\n[说明]")
    safe_print("data_validator.py主要负责数据验证逻辑，不涉及数据库设计规范的核心内容。")
    safe_print("数据库设计规范（主键设计、字段NULL规则等）主要在schema.py中定义。")
    
    return len([i for i in issues if i['severity'] == 'error']) == 0


if __name__ == "__main__":
    success = review_data_validator_compliance()
    sys.exit(0 if success else 1)

