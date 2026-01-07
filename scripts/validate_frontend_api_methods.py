#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
前端API方法存在性检查工具

功能：
1. 扫描前端代码中的API调用
2. 验证调用的方法是否存在
3. 生成检查报告
"""

import sys
import re
from pathlib import Path
from typing import List, Dict, Any, Set
from collections import defaultdict

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class FrontendAPIMethodValidator:
    """前端API方法验证器"""
    
    def __init__(self):
        self.api_methods = set()  # 已定义的API方法
        self.api_calls = []  # API调用列表
        self.errors = []
        self.warnings = []
    
    def extract_api_methods(self, api_file: Path) -> Set[str]:
        """从API文件中提取已定义的方法"""
        methods = set()
        
        try:
            with open(api_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 匹配方法定义：async methodName( 或 methodName(
            method_pattern = r'(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{'
            matches = re.finditer(method_pattern, content)
            
            for match in matches:
                method_name = match.group(1)
                # 排除私有方法（以下划线开头）
                if not method_name.startswith('_'):
                    methods.add(method_name)
        
        except Exception as e:
            self.errors.append({
                "file": str(api_file),
                "message": f"读取API文件失败: {str(e)}"
            })
        
        return methods
    
    def extract_api_calls(self, vue_file: Path) -> List[Dict[str, Any]]:
        """从Vue文件中提取API调用"""
        calls = []
        
        try:
            with open(vue_file, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
            
            # 匹配API调用：api.methodName( 或 this.api.methodName(
            api_call_pattern = r'(?:this\.)?api\.(\w+)\s*\('
            matches = re.finditer(api_call_pattern, content)
            
            for match in matches:
                method_name = match.group(1)
                line_num = content[:match.start()].count('\n') + 1
                line_content = lines[line_num - 1].strip()
                
                calls.append({
                    "method": method_name,
                    "file": str(vue_file),
                    "line": line_num,
                    "line_content": line_content
                })
        
        except Exception as e:
            self.errors.append({
                "file": str(vue_file),
                "message": f"读取Vue文件失败: {str(e)}"
            })
        
        return calls
    
    def scan_frontend_files(self) -> List[Path]:
        """扫描所有前端文件"""
        frontend_dir = project_root / "frontend" / "src"
        vue_files = list(frontend_dir.rglob("*.vue"))
        js_files = list(frontend_dir.rglob("*.js"))
        ts_files = list(frontend_dir.rglob("*.ts"))
        
        return vue_files + js_files + ts_files
    
    def validate_all(self) -> Dict[str, Any]:
        """验证所有API方法调用"""
        # 1. 提取API文件中定义的方法
        api_file = project_root / "frontend" / "src" / "api" / "index.js"
        if api_file.exists():
            self.api_methods = self.extract_api_methods(api_file)
        else:
            self.errors.append({
                "file": str(api_file),
                "message": "API文件不存在"
            })
            return {
                "errors": self.errors,
                "warnings": self.warnings,
                "missing_methods": [],
                "stats": {
                    "total_methods": 0,
                    "total_calls": 0,
                    "missing_calls": 0
                }
            }
        
        # 2. 扫描所有前端文件，提取API调用
        frontend_files = self.scan_frontend_files()
        for frontend_file in frontend_files:
            calls = self.extract_api_calls(frontend_file)
            self.api_calls.extend(calls)
        
        # 3. 验证API调用是否存在
        missing_methods = []
        for call in self.api_calls:
            if call["method"] not in self.api_methods:
                missing_methods.append(call)
        
        return {
            "errors": self.errors,
            "warnings": self.warnings,
            "missing_methods": missing_methods,
            "stats": {
                "total_methods": len(self.api_methods),
                "total_calls": len(self.api_calls),
                "missing_calls": len(missing_methods)
            }
        }
    
    def generate_report(self, results: Dict[str, Any]) -> str:
        """生成验证报告"""
        report = []
        report.append("=" * 60)
        report.append("前端API方法存在性检查报告")
        report.append("=" * 60)
        report.append("")
        
        # 统计信息
        stats = results["stats"]
        report.append(f"已定义API方法数: {stats['total_methods']}")
        report.append(f"API调用总数: {stats['total_calls']}")
        report.append(f"缺失方法调用数: {stats['missing_calls']}")
        report.append("")
        
        # 缺失方法列表
        if results["missing_methods"]:
            report.append("=" * 60)
            report.append("缺失的API方法调用")
            report.append("=" * 60)
            
            # 按方法名分组
            missing_by_method = defaultdict(list)
            for call in results["missing_methods"]:
                missing_by_method[call["method"]].append(call)
            
            for method_name, calls in sorted(missing_by_method.items()):
                report.append(f"\n方法: {method_name} (在 {len(calls)} 处调用)")
                for call in calls[:5]:  # 只显示前5处
                    report.append(f"  - {call['file']}:{call['line']}")
                    report.append(f"    {call['line_content']}")
                if len(calls) > 5:
                    report.append(f"  ... 还有 {len(calls) - 5} 处调用")
        
        # 错误列表
        if results["errors"]:
            report.append("\n" + "=" * 60)
            report.append("错误列表")
            report.append("=" * 60)
            for error in results["errors"]:
                report.append(f"[错误] {error['file']}")
                report.append(f"  {error['message']}")
        
        # 总结
        report.append("\n" + "=" * 60)
        report.append("总结")
        report.append("=" * 60)
        if stats['missing_calls'] == 0 and not results["errors"]:
            report.append("[OK] 所有API方法调用都存在！")
        else:
            report.append(f"[ERROR] 发现 {stats['missing_calls']} 个缺失的方法调用")
            if results["errors"]:
                report.append(f"[ERROR] 发现 {len(results['errors'])} 个错误")
        
        return "\n".join(report)


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
    validator = FrontendAPIMethodValidator()
    
    safe_print("开始检查前端API方法...")
    results = validator.validate_all()
    
    report = validator.generate_report(results)
    safe_print(report)
    
    # 返回退出码
    if results["stats"]["missing_calls"] > 0 or results["errors"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

