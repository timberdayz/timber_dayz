#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审查数据入库服务是否符合数据库设计规范

⭐ v4.12.0新增：审查data_ingestion_service.py和data_importer.py是否符合规范
"""

import sys
from pathlib import Path
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


def review_data_ingestion_compliance():
    """审查数据入库服务是否符合规范"""
    safe_print("=" * 70)
    safe_print("审查数据入库服务是否符合数据库设计规范")
    safe_print("=" * 70)
    
    issues = []
    
    # 1. 审查data_ingestion_service.py
    safe_print("\n[1] 审查data_ingestion_service.py...")
    ingestion_file = project_root / "backend" / "services" / "data_ingestion_service.py"
    
    if ingestion_file.exists():
        with open(ingestion_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查shop_id获取规则
        if 'shop_id' in content:
            # 检查是否从file_record获取shop_id
            if 'file_record.shop_id' in content or 'file_record and file_record.shop_id' in content:
                safe_print("    [OK] shop_id获取规则：从file_record获取")
            else:
                issues.append({
                    'file': 'data_ingestion_service.py',
                    'severity': 'warning',
                    'issue': 'shop_id获取可能不符合规范（未从file_record获取）',
                    'suggestion': '应优先从file_record获取shop_id'
                })
                safe_print("    [WARN] shop_id获取规则：未明确从file_record获取")
        
        # 检查platform_code获取规则
        if 'platform_code' in content:
            if 'file_record.platform_code' in content or 'file_record and file_record.platform_code' in content:
                safe_print("    [OK] platform_code获取规则：从file_record获取")
            else:
                issues.append({
                    'file': 'data_ingestion_service.py',
                    'severity': 'info',
                    'issue': 'platform_code获取可能不符合规范（未从file_record获取）',
                    'suggestion': '应优先从file_record获取platform_code'
                })
                safe_print("    [INFO] platform_code获取规则：未明确从file_record获取")
        
        # 检查AccountAlias映射
        if 'AccountAlignmentService' in content or 'account_alignment' in content:
            safe_print("    [OK] 使用AccountAlias映射服务")
        else:
            issues.append({
                'file': 'data_ingestion_service.py',
                'severity': 'info',
                'issue': '未使用AccountAlias映射服务',
                'suggestion': '应考虑使用AccountAlias映射非标准店铺名称'
            })
            safe_print("    [INFO] 未使用AccountAlias映射服务（可能在其他服务中使用）")
    
    # 2. 审查data_importer.py
    safe_print("\n[2] 审查data_importer.py...")
    importer_file = project_root / "backend" / "services" / "data_importer.py"
    
    if importer_file.exists():
        with open(importer_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查shop_id获取规则
        shop_id_patterns = [
            r'file_record\.shop_id',
            r'file_record\s+and\s+file_record\.shop_id',
            r'AccountAlignmentService',
            r'align_account|align_order'
        ]
        
        found_patterns = []
        for pattern in shop_id_patterns:
            if re.search(pattern, content):
                found_patterns.append(pattern)
        
        if found_patterns:
            safe_print(f"    [OK] shop_id获取规则：找到{len(found_patterns)}个符合规范的实现")
            if 'AccountAlignmentService' in content or 'align_account' in content or 'align_order' in content:
                safe_print("    [OK] 使用AccountAlias映射服务")
        else:
            issues.append({
                'file': 'data_importer.py',
                'severity': 'warning',
                'issue': 'shop_id获取可能不符合规范',
                'suggestion': '应遵循shop_id获取优先级：源数据 → AccountAlias映射 → 文件元数据 → 默认值'
            })
            safe_print("    [WARN] shop_id获取规则：未找到符合规范的实现")
        
        # 检查platform_code获取规则
        platform_code_patterns = [
            r'file_record\.platform_code',
            r'file_record\s+and\s+file_record\.platform_code'
        ]
        
        found_platform_patterns = []
        for pattern in platform_code_patterns:
            if re.search(pattern, content):
                found_platform_patterns.append(pattern)
        
        if found_platform_patterns:
            safe_print(f"    [OK] platform_code获取规则：找到{len(found_platform_patterns)}个符合规范的实现")
        else:
            issues.append({
                'file': 'data_importer.py',
                'severity': 'info',
                'issue': 'platform_code获取可能不符合规范',
                'suggestion': '应优先从file_record获取platform_code'
            })
            safe_print("    [INFO] platform_code获取规则：未找到符合规范的实现")
        
        # 检查关键字段NULL处理
        nullable_checks = [
            r'nullable=False',
            r'default=\d+\.?\d*',
            r'default=0\.0',
            r'default=1'
        ]
        
        found_nullable_checks = []
        for pattern in nullable_checks:
            if re.search(pattern, content):
                found_nullable_checks.append(pattern)
        
        if found_nullable_checks:
            safe_print(f"    [OK] 关键字段NULL处理：找到{len(found_nullable_checks)}个符合规范的实现")
        else:
            issues.append({
                'file': 'data_importer.py',
                'severity': 'info',
                'issue': '关键字段NULL处理可能不符合规范',
                'suggestion': '关键业务字段应不允许NULL，使用默认值'
            })
            safe_print("    [INFO] 关键字段NULL处理：未找到符合规范的实现")
    
    # 3. 使用数据入库流程验证工具
    safe_print("\n[3] 使用数据入库流程验证工具...")
    try:
        from backend.models.database import get_db
        from backend.services.data_ingestion_validator import validate_data_ingestion_process
        
        db = next(get_db())
        result = validate_data_ingestion_process(db)
        
        if result.issues:
            safe_print(f"    发现 {len(result.issues)} 个问题")
            for issue in result.issues[:5]:  # 只显示前5个
                severity_icon = {
                    'error': '[ERROR]',
                    'warning': '[WARN]',
                    'info': '[INFO]'
                }.get(issue.severity, '[UNKNOWN]')
                
                safe_print(f"    {severity_icon} {issue.category}: {issue.issue}")
        else:
            safe_print("    [OK] 数据入库流程验证通过")
        
        db.close()
    except Exception as e:
        safe_print(f"    [ERROR] 验证工具运行失败: {e}")
    
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
    
    return len([i for i in issues if i['severity'] == 'error']) == 0


if __name__ == "__main__":
    success = review_data_ingestion_compliance()
    sys.exit(0 if success else 1)

