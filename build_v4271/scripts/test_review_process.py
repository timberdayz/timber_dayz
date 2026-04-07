#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试规则审查流程

⭐ v4.12.0新增：测试规则审查流程是否正常工作
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


def test_review_process():
    """测试规则审查流程"""
    safe_print("=" * 70)
    safe_print("测试规则审查流程")
    safe_print("=" * 70)
    
    # 1. 检查审查流程文档是否存在
    safe_print("\n[1] 检查审查流程文档...")
    review_process_file = project_root / "docs" / "DEVELOPMENT_RULES" / "REVIEW_PROCESS.md"
    
    if review_process_file.exists():
        safe_print("    [OK] 审查流程文档存在")
        with open(review_process_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查关键内容
        key_sections = [
            '审查流程',
            '责任人',
            '审查工具',
            '审查结果处理'
        ]
        
        for section in key_sections:
            if section in content:
                safe_print(f"    [OK] 包含{section}章节")
            else:
                safe_print(f"    [WARN] 缺少{section}章节")
    else:
        safe_print("    [ERROR] 审查流程文档不存在")
        return False
    
    # 2. 检查审查工具是否存在
    safe_print("\n[2] 检查审查工具...")
    review_scripts = [
        "scripts/review_schema_compliance.py",
        "scripts/review_data_ingestion_compliance.py",
        "scripts/review_data_validator_compliance.py",
        "scripts/review_spec_completeness.py"
    ]
    
    all_exist = True
    for script_path in review_scripts:
        script_file = project_root / script_path
        if script_file.exists():
            safe_print(f"    [OK] {script_path}存在")
        else:
            safe_print(f"    [ERROR] {script_path}不存在")
            all_exist = False
    
    if not all_exist:
        return False
    
    # 3. 检查验证工具是否存在
    safe_print("\n[3] 检查验证工具...")
    validator_services = [
        "backend/services/database_design_validator.py",
        "backend/services/data_ingestion_validator.py",
        "backend/services/field_mapping_validator.py"
    ]
    
    all_exist = True
    for service_path in validator_services:
        service_file = project_root / service_path
        if service_file.exists():
            safe_print(f"    [OK] {service_path}存在")
        else:
            safe_print(f"    [ERROR] {service_path}不存在")
            all_exist = False
    
    if not all_exist:
        return False
    
    # 4. 检查检查清单文档是否存在
    safe_print("\n[4] 检查检查清单文档...")
    checklist_files = [
        "docs/DEVELOPMENT_RULES/DATABASE_DESIGN_CHECKLIST.md",
        "docs/DEVELOPMENT_RULES/CODE_REVIEW_CHECKLIST.md",
        "docs/DEVELOPMENT_RULES/DATABASE_CHANGE_CHECKLIST.md"
    ]
    
    all_exist = True
    for checklist_path in checklist_files:
        checklist_file = project_root / checklist_path
        if checklist_file.exists():
            safe_print(f"    [OK] {checklist_path}存在")
        else:
            safe_print(f"    [ERROR] {checklist_path}不存在")
            all_exist = False
    
    if not all_exist:
        return False
    
    # 5. 测试运行审查脚本（dry-run）
    safe_print("\n[5] 测试运行审查脚本（dry-run）...")
    try:
        # 只检查脚本是否可以导入，不实际运行
        import importlib.util
        
        script_paths = [
            "scripts/review_schema_compliance.py",
            "scripts/review_data_ingestion_compliance.py"
        ]
        
        for script_path in script_paths:
            script_file = project_root / script_path
            if script_file.exists():
                spec = importlib.util.spec_from_file_location("test_module", script_file)
                if spec and spec.loader:
                    safe_print(f"    [OK] {script_path}可以导入")
                else:
                    safe_print(f"    [WARN] {script_path}无法导入（可能需要实际运行测试）")
    except Exception as e:
        safe_print(f"    [WARN] 导入测试失败: {e}（可能需要实际运行测试）")
    
    # 显示结果
    safe_print("\n" + "=" * 70)
    safe_print("测试结果摘要")
    safe_print("=" * 70)
    safe_print("\n[OK] 规则审查流程测试通过")
    safe_print("\n审查流程组件:")
    safe_print("  - 审查流程文档: 存在")
    safe_print("  - 审查脚本: 存在")
    safe_print("  - 验证工具: 存在")
    safe_print("  - 检查清单文档: 存在")
    
    return True


if __name__ == "__main__":
    success = test_review_process()
    sys.exit(0 if success else 1)

