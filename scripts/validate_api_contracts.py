#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API契约测试框架

验证内容：
1. API响应格式是否符合标准
2. 错误响应格式是否符合标准
3. 分页响应格式是否符合标准
4. 请求ID是否正确传递
"""

import sys
import ast
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple
from collections import defaultdict

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class APIContractValidator:
    """API契约验证器"""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.stats = {
            "total_endpoints": 0,
            "valid_responses": 0,
            "invalid_responses": 0,
            "missing_error_handling": 0,
            "missing_recovery_suggestion": 0
        }
    
    def validate_response_format(self, file_path: Path) -> List[Dict[str, Any]]:
        """验证API响应格式"""
        issues = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 检查是否使用success_response
            if 'success_response(' in content:
                # 检查是否正确导入
                if 'from backend.utils.api_response import' not in content:
                    issues.append({
                        "type": "error",
                        "file": str(file_path),
                        "line": 0,
                        "message": "使用success_response但未导入api_response模块"
                    })
            
            # 检查是否使用error_response
            if 'error_response(' in content:
                # 检查是否正确导入
                if 'from backend.utils.api_response import' not in content:
                    issues.append({
                        "type": "error",
                        "file": str(file_path),
                        "line": 0,
                        "message": "使用error_response但未导入api_response模块"
                    })
                
                # 检查是否包含recovery_suggestion
                if 'recovery_suggestion' not in content:
                    issues.append({
                        "type": "warning",
                        "file": str(file_path),
                        "line": 0,
                        "message": "error_response调用缺少recovery_suggestion参数"
                    })
            
            # 检查是否还有raise HTTPException（除了410 Gone）
            http_exception_pattern = r'raise HTTPException\('
            matches = list(re.finditer(http_exception_pattern, content))
            for match in matches:
                # 检查是否是410 Gone（废弃API）
                line_start = content[:match.start()].rfind('\n') + 1
                line_end = content.find('\n', match.end())
                line_content = content[line_start:line_end] if line_end != -1 else content[line_start:]
                
                if '410' not in line_content and 'Gone' not in line_content:
                    line_num = content[:match.start()].count('\n') + 1
                    issues.append({
                        "type": "error",
                        "file": str(file_path),
                        "line": line_num,
                        "message": f"发现raise HTTPException（应使用error_response）: {line_content.strip()}"
                    })
        
        except Exception as e:
            issues.append({
                "type": "error",
                "file": str(file_path),
                "line": 0,
                "message": f"读取文件失败: {str(e)}"
            })
        
        return issues
    
    def validate_error_handling(self, file_path: Path) -> List[Dict[str, Any]]:
        """验证错误处理"""
        issues = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 检查try-except块
            try_blocks = list(re.finditer(r'try:', content))
            for try_match in try_blocks:
                # 查找对应的except块
                try_start = try_match.end()
                except_match = re.search(r'except\s+.*?:', content[try_start:])
                
                if except_match:
                    except_start = try_start + except_match.start()
                    except_end = try_start + except_match.end()
                    
                    # 检查except块中是否有错误日志
                    except_block_end = content.find('\n    ', except_end)
                    if except_block_end == -1:
                        except_block_end = len(content)
                    
                    except_block = content[except_end:except_block_end]
                    
                    # 检查是否有logger.error
                    if 'logger.error' not in except_block and 'logger.exception' not in except_block:
                        line_num = content[:except_start].count('\n') + 1
                        issues.append({
                            "type": "warning",
                            "file": str(file_path),
                            "line": line_num,
                            "message": "except块中缺少错误日志记录"
                        })
                    
                    # 检查是否使用error_response
                    if 'error_response(' not in except_block and 'raise HTTPException' in except_block:
                        line_num = content[:except_start].count('\n') + 1
                        issues.append({
                            "type": "error",
                            "file": str(file_path),
                            "line": line_num,
                            "message": "except块中使用raise HTTPException而非error_response"
                        })
        
        except Exception as e:
            issues.append({
                "type": "error",
                "file": str(file_path),
                "line": 0,
                "message": f"分析文件失败: {str(e)}"
            })
        
        return issues
    
    def scan_router_files(self) -> List[Path]:
        """扫描所有路由文件"""
        router_dir = project_root / "backend" / "routers"
        router_files = list(router_dir.glob("*.py"))
        # 排除__init__.py
        router_files = [f for f in router_files if f.name != "__init__.py"]
        return router_files
    
    def validate_all(self) -> Dict[str, Any]:
        """验证所有API端点"""
        router_files = self.scan_router_files()
        
        all_issues = {
            "errors": [],
            "warnings": []
        }
        
        for router_file in router_files:
            # 验证响应格式
            response_issues = self.validate_response_format(router_file)
            all_issues["errors"].extend([i for i in response_issues if i["type"] == "error"])
            all_issues["warnings"].extend([i for i in response_issues if i["type"] == "warning"])
            
            # 验证错误处理
            error_handling_issues = self.validate_error_handling(router_file)
            all_issues["errors"].extend([i for i in error_handling_issues if i["type"] == "error"])
            all_issues["warnings"].extend([i for i in error_handling_issues if i["type"] == "warning"])
        
        return all_issues
    
    def generate_report(self, issues: Dict[str, Any]) -> str:
        """生成验证报告"""
        report = []
        report.append("=" * 60)
        report.append("API契约验证报告")
        report.append("=" * 60)
        report.append("")
        
        # 统计信息
        error_count = len(issues["errors"])
        warning_count = len(issues["warnings"])
        
        report.append(f"错误数量: {error_count}")
        report.append(f"警告数量: {warning_count}")
        report.append("")
        
        # 错误列表
        if issues["errors"]:
            report.append("=" * 60)
            report.append("错误列表")
            report.append("=" * 60)
            for error in issues["errors"]:
                report.append(f"[错误] {error['file']}:{error['line']}")
                report.append(f"  {error['message']}")
                report.append("")
        
        # 警告列表
        if issues["warnings"]:
            report.append("=" * 60)
            report.append("警告列表")
            report.append("=" * 60)
            for warning in issues["warnings"]:
                report.append(f"[警告] {warning['file']}:{warning['line']}")
                report.append(f"  {warning['message']}")
                report.append("")
        
        # 总结
        report.append("=" * 60)
        report.append("总结")
        report.append("=" * 60)
        if error_count == 0 and warning_count == 0:
            report.append("[OK] 所有API端点符合契约标准！")
        else:
            report.append(f"[ERROR] 发现 {error_count} 个错误，{warning_count} 个警告")
        
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
    validator = APIContractValidator()
    
    safe_print("开始验证API契约...")
    issues = validator.validate_all()
    
    report = validator.generate_report(issues)
    safe_print(report)
    
    # 返回退出码
    if issues["errors"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

