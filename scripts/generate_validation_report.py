#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成数据库设计规范验证报告

⭐ v4.12.0新增：生成详细的验证报告
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from backend.services.database_design_validator import validate_database_design
from modules.core.logger import get_logger

logger = get_logger(__name__)


def generate_report(output_file: str = None):
    """生成验证报告"""
    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"temp/outputs/database_design_validation_report_{timestamp}.json"
    
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("生成数据库设计规范验证报告")
    print("=" * 70)
    
    try:
        # 获取数据库会话
        db = next(get_db())
        
        # 运行验证
        print("\n[1] 运行数据库设计验证...")
        result = validate_database_design(db)
        
        # 准备报告数据
        report = {
            "timestamp": datetime.now().isoformat(),
            "version": "v4.12.0",
            "summary": result.summary,
            "is_valid": result.is_valid,
            "issues": []
        }
        
        # 转换问题为字典
        for issue in result.issues:
            issue_dict = {
                "severity": issue.severity,
                "category": issue.category,
                "table_name": issue.table_name,
                "field_name": issue.field_name,
                "issue": issue.issue,
                "suggestion": issue.suggestion
            }
            report["issues"].append(issue_dict)
        
        # 按严重程度分组
        report["issues_by_severity"] = {
            "error": [i for i in report["issues"] if i["severity"] == "error"],
            "warning": [i for i in report["issues"] if i["severity"] == "warning"],
            "info": [i for i in report["issues"] if i["severity"] == "info"]
        }
        
        # 按分类分组
        report["issues_by_category"] = {}
        for issue in report["issues"]:
            category = issue["category"]
            if category not in report["issues_by_category"]:
                report["issues_by_category"][category] = []
            report["issues_by_category"][category].append(issue)
        
        # 保存报告
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"\n[2] 报告已保存到: {output_path}")
        print(f"\n[3] 报告摘要:")
        print(f"   - 总问题数: {report['summary']['total_issues']}")
        print(f"   - 错误数: {report['summary']['error_count']}")
        print(f"   - 警告数: {report['summary']['warning_count']}")
        print(f"   - 信息数: {report['summary']['info_count']}")
        print(f"   - 验证状态: {'通过' if report['is_valid'] else '未通过'}")
        
        # 显示分类统计
        print(f"\n[4] 问题分类统计:")
        for category, issues in report["issues_by_category"].items():
            print(f"   - {category}: {len(issues)}")
        
        db.close()
        
        print(f"\n[SUCCESS] 验证报告生成成功！")
        return str(output_path)
        
    except Exception as e:
        logger.error(f"生成验证报告失败: {e}", exc_info=True)
        print(f"\n[ERROR] 生成报告失败: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    output_file = sys.argv[1] if len(sys.argv) > 1 else None
    generate_report(output_file)

