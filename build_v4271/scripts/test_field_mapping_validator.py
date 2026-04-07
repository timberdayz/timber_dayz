#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试字段映射验证工具

⭐ v4.12.0新增：测试字段映射验证功能
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from backend.services.field_mapping_validator import validate_field_mapping
from modules.core.logger import get_logger

logger = get_logger(__name__)


def safe_print(text_str):
    """安全打印（Windows兼容）"""
    try:
        print(text_str)
    except UnicodeEncodeError:
        print(text_str.encode('gbk', errors='ignore').decode('gbk'))


def test_field_mapping_validator():
    """测试字段映射验证工具"""
    safe_print("=" * 70)
    safe_print("测试字段映射验证工具")
    safe_print("=" * 70)
    
    db = next(get_db())
    
    try:
        # 运行验证
        safe_print("\n[1] 运行字段映射验证...")
        result = validate_field_mapping(db)
        
        # 显示结果
        safe_print("\n[2] 验证结果:")
        safe_print(f"  有效性: {'[OK]' if result.is_valid else '[FAIL]'}")
        safe_print(f"  总问题数: {len(result.issues)}")
        safe_print(f"  错误数: {result.summary.get('error_count', 0)}")
        safe_print(f"  警告数: {result.summary.get('warning_count', 0)}")
        safe_print(f"  信息数: {result.summary.get('info_count', 0)}")
        
        # 显示分类统计
        safe_print("\n[3] 分类统计:")
        category_counts = result.summary.get('category_counts', {})
        for category, count in category_counts.items():
            safe_print(f"  {category}: {count}")
        
        # 显示问题详情
        if result.issues:
            safe_print("\n[4] 问题详情:")
            for i, issue in enumerate(result.issues, 1):
                severity_icon = {
                    'error': '[ERROR]',
                    'warning': '[WARN]',
                    'info': '[INFO]'
                }.get(issue.severity, '[UNKNOWN]')
                
                safe_print(f"\n  {i}. {severity_icon} {issue.category}")
                if issue.field_name:
                    safe_print(f"     字段: {issue.field_name}")
                safe_print(f"     问题: {issue.issue}")
                if issue.suggestion:
                    safe_print(f"     建议: {issue.suggestion}")
                if issue.code_location:
                    safe_print(f"     位置: {issue.code_location}")
        else:
            safe_print("\n[4] 未发现问题")
        
        return result.is_valid
        
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        safe_print(f"\n[ERROR] 测试失败: {e}")
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = test_field_mapping_validator()
    sys.exit(0 if success else 1)

