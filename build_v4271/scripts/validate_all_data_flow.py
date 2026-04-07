#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
综合数据流转验证脚本

整合所有验证工具：
1. API契约验证
2. 前端API方法验证
3. 数据库字段验证
4. 代码审查检查清单

使用方法：
    python scripts/validate_all_data_flow.py
"""

import sys
import subprocess
from pathlib import Path
from datetime import datetime

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def run_validation_script(script_name: str, description: str) -> tuple[bool, str]:
    """运行验证脚本"""
    print(f"\n{'=' * 60}")
    print(f"运行: {description}")
    print(f"{'=' * 60}")
    
    script_path = project_root / "scripts" / script_name
    
    if not script_path.exists():
        return False, f"脚本不存在: {script_name}"
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=300  # 5分钟超时
        )
        
        output = result.stdout + result.stderr
        
        if result.returncode == 0:
            return True, output
        else:
            return False, output
    
    except subprocess.TimeoutExpired:
        return False, f"脚本执行超时: {script_name}"
    except Exception as e:
        return False, f"执行失败: {str(e)}"


def safe_print(text):
    """安全打印函数，处理Windows终端编码问题"""
    try:
        print(text)
    except UnicodeEncodeError:
        # Windows GBK编码不支持的特殊字符替换为ASCII字符
        safe_text = text.replace('✓', '[OK]').replace('✗', '[ERROR]')
        print(safe_text)

def main():
    """主函数"""
    safe_print("=" * 60)
    safe_print("综合数据流转验证脚本")
    safe_print("=" * 60)
    safe_print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    safe_print(f"项目根目录: {project_root}")
    
    # 验证脚本列表
    validations = [
        ("validate_api_contracts.py", "API契约验证"),
        ("validate_frontend_api_methods.py", "前端API方法验证"),
        ("validate_database_fields.py", "数据库字段验证"),
        ("generate_code_review_checklist.py", "代码审查检查清单生成"),
    ]
    
    results = []
    
    # 运行所有验证
    for script_name, description in validations:
        success, output = run_validation_script(script_name, description)
        results.append({
            "script": script_name,
            "description": description,
            "success": success,
            "output": output
        })
        
        if success:
            safe_print(f"\n[OK] {description} - 通过")
        else:
            safe_print(f"\n[ERROR] {description} - 失败")
            safe_print(output[:500])  # 只显示前500字符
    
    # 生成总结报告
    safe_print("\n" + "=" * 60)
    safe_print("验证总结")
    safe_print("=" * 60)
    
    passed = sum(1 for r in results if r["success"])
    total = len(results)
    
    safe_print(f"\n通过: {passed}/{total}")
    
    for result in results:
        status = "[OK]" if result["success"] else "[ERROR]"
        safe_print(f"{status} {result['description']}")
    
    # 失败的验证
    failed = [r for r in results if not r["success"]]
    if failed:
        safe_print("\n失败的验证:")
        for result in failed:
            safe_print(f"  - {result['description']}")
            safe_print(f"    脚本: {result['script']}")
    
    # 保存详细报告
    report_file = project_root / "temp" / "data_flow_validation_report.txt"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("综合数据流转验证报告\n")
        f.write("=" * 60 + "\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        for result in results:
            f.write("=" * 60 + "\n")
            f.write(f"{result['description']}\n")
            f.write("=" * 60 + "\n")
            f.write(f"状态: {'通过' if result['success'] else '失败'}\n")
            f.write(f"脚本: {result['script']}\n\n")
            f.write(result['output'])
            f.write("\n\n")
    
    safe_print(f"\n详细报告已保存到: {report_file}")
    
    # 返回退出码
    if failed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

