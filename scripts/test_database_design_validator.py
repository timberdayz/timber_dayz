#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库设计规范验证工具测试脚本

⭐ v4.12.0新增：测试数据库设计规范验证工具
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from backend.services.database_design_validator import validate_database_design, DatabaseDesignValidator
from modules.core.logger import get_logger

logger = get_logger(__name__)


def test_validation_tool():
    """测试验证工具"""
    print("=" * 70)
    print("数据库设计规范验证工具测试")
    print("=" * 70)
    
    try:
        # 获取数据库会话
        db = next(get_db())
        
        # 运行验证
        print("\n[1] 运行数据库设计验证...")
        result = validate_database_design(db)
        
        # 显示验证结果
        print("\n[2] 验证结果摘要:")
        print(f"   - 是否通过: {'[OK]' if result.is_valid else '[FAIL]'}")
        print(f"   - 总问题数: {len(result.issues)}")
        print(f"   - 错误数: {result.summary.get('error_count', 0)}")
        print(f"   - 警告数: {result.summary.get('warning_count', 0)}")
        print(f"   - 信息数: {result.summary.get('info_count', 0)}")
        
        # 显示分类统计
        category_counts = result.summary.get('category_counts', {})
        if category_counts:
            print("\n[3] 问题分类统计:")
            for category, count in category_counts.items():
                print(f"   - {category}: {count}")
        
        # 显示前10个问题
        if result.issues:
            print("\n[4] 前10个问题详情:")
            for i, issue in enumerate(result.issues[:10], 1):
                severity_icon = {
                    'error': '[ERROR]',
                    'warning': '[WARN]',
                    'info': '[INFO]'
                }.get(issue.severity, '[UNKNOWN]')
                
                print(f"\n   {i}. {severity_icon} {issue.category} - {issue.table_name}")
                if issue.field_name:
                    print(f"      字段: {issue.field_name}")
                print(f"      问题: {issue.issue}")
                if issue.suggestion:
                    print(f"      建议: {issue.suggestion}")
        
        # 显示所有错误
        errors = [i for i in result.issues if i.severity == 'error']
        if errors:
            print("\n[5] 所有错误（必须修复）:")
            for i, error in enumerate(errors, 1):
                print(f"\n   {i}. [ERROR] {error.table_name}")
                if error.field_name:
                    print(f"      字段: {error.field_name}")
                print(f"      问题: {error.issue}")
                if error.suggestion:
                    print(f"      建议: {error.suggestion}")
        
        # 显示警告
        warnings = [i for i in result.issues if i.severity == 'warning']
        if warnings:
            print(f"\n[6] 警告数量: {len(warnings)}（建议修复）")
            if len(warnings) <= 5:
                for i, warning in enumerate(warnings, 1):
                    print(f"\n   {i}. [WARN] {warning.table_name}")
                    if warning.field_name:
                        print(f"      字段: {warning.field_name}")
                    print(f"      问题: {warning.issue}")
                    if warning.suggestion:
                        print(f"      建议: {warning.suggestion}")
            else:
                print(f"   （显示前5个警告）")
                for i, warning in enumerate(warnings[:5], 1):
                    print(f"\n   {i}. [WARN] {warning.table_name}")
                    if warning.field_name:
                        print(f"      字段: {warning.field_name}")
                    print(f"      问题: {warning.issue}")
        
        # 测试验证器方法
        print("\n[7] 测试验证器方法...")
        validator = DatabaseDesignValidator(db)
        
        # 测试表验证
        print("   - 测试表结构验证...")
        table_issues = validator.validate_tables()
        print(f"     发现 {len(table_issues)} 个表结构问题")
        
        # 测试物化视图验证
        print("   - 测试物化视图验证...")
        mv_issues = validator.validate_materialized_views()
        print(f"     发现 {len(mv_issues)} 个物化视图问题")
        
        # 总结
        print("\n" + "=" * 70)
        print("测试总结")
        print("=" * 70)
        
        if result.is_valid:
            print("[SUCCESS] 数据库设计验证通过！")
            print("   - 没有发现错误级别的问题")
            if warnings:
                print(f"   - 有 {len(warnings)} 个警告建议修复")
        else:
            print("[FAILURE] 数据库设计验证未通过！")
            print(f"   - 发现 {len(errors)} 个错误必须修复")
            if warnings:
                print(f"   - 有 {len(warnings)} 个警告建议修复")
        
        print("\n验证工具功能正常！")
        
        db.close()
        return result.is_valid
        
    except Exception as e:
        logger.error(f"测试验证工具失败: {e}", exc_info=True)
        print(f"\n[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_validation_tool()
    sys.exit(0 if success else 1)

