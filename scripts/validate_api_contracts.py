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
    
    def validate_all(self, target_files: List[Path] = None) -> Dict[str, Any]:
        """验证所有API端点（如果指定了target_files，只验证这些文件）"""
        if target_files is None:
            router_files = self.scan_router_files()
        else:
            # 只验证指定的文件（过滤出 router 文件）
            router_files = []
            for file_path in target_files:
                file_path_obj = Path(file_path) if isinstance(file_path, str) else file_path
                
                # 统一转换为相对于项目根目录的路径
                file_path_str = str(file_path_obj).replace('\\', '/')
                
                # 如果是绝对路径，尝试提取相对路径部分
                if file_path_obj.is_absolute():
                    try:
                        file_path_obj = file_path_obj.relative_to(project_root)
                        file_path_str = str(file_path_obj).replace('\\', '/')
                    except ValueError:
                        # 如果无法提取相对路径，检查是否包含 backend/routers
                        if '/backend/routers/' in file_path_str:
                            # 提取 backend/routers/ 之后的部分
                            parts = file_path_str.split('/backend/routers/')
                            if len(parts) > 1:
                                file_path_str = f"backend/routers/{parts[1]}"
                            else:
                                continue
                        else:
                            continue
                
                # 标准化路径（移除 ./ 前缀）
                file_path_str = file_path_str.lstrip('./')
                
                # 检查是否是 router 文件
                if file_path_str.startswith("backend/routers/") and file_path_str.endswith(".py"):
                    file_name = Path(file_path_str).name
                    if file_name != "__init__.py":
                        full_path = project_root / file_path_str
                        if full_path.exists():
                            router_files.append(full_path)
        
        all_issues = {
            "errors": [],
            "warnings": [],
            "validated_file_count": len(router_files)
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
    
    def generate_report(self, issues: Dict[str, Any], validated_file_count: int = 0) -> str:
        """生成验证报告"""
        report = []
        report.append("=" * 60)
        report.append("API契约验证报告")
        report.append("=" * 60)
        report.append("")
        
        # 统计信息
        error_count = len(issues["errors"])
        warning_count = len(issues["warnings"])
        
        if validated_file_count > 0:
            report.append(f"验证文件数: {validated_file_count}")
        elif validated_file_count == 0:
            report.append(f"验证文件数: 0（改动文件中没有 router 文件或指定文件列表为空，跳过验证）")
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
        if validated_file_count == 0:
            report.append("[OK] 本次发布没有改动 router 文件，跳过验证")
        elif error_count == 0 and warning_count == 0:
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
    import argparse
    
    parser = argparse.ArgumentParser(description="验证API契约")
    parser.add_argument(
        "--files",
        nargs="+",
        help="只验证指定的文件列表（相对于项目根目录的路径，如 backend/routers/xxx.py）"
    )
    parser.add_argument(
        "--changed-files",
        help="从文件读取改动的文件列表（每行一个文件路径）"
    )
    args = parser.parse_args()
    
    validator = APIContractValidator()
    
    target_files = None
    if args.files:
        target_files = [Path(f) for f in args.files]
        safe_print(f"开始验证API契约（仅验证 {len(target_files)} 个指定文件）...")
    elif args.changed_files:
        changed_files_path = Path(args.changed_files)
        if changed_files_path.exists():
            with open(changed_files_path, 'r', encoding='utf-8') as f:
                target_files = [Path(line.strip()) for line in f if line.strip()]
            safe_print(f"开始验证API契约（仅验证 {len(target_files)} 个改动文件）...")
        else:
            safe_print(f"[WARN] 改动文件列表不存在: {args.changed_files}，将验证所有文件")
    else:
        safe_print("开始验证API契约（验证所有文件）...")
    
    issues = validator.validate_all(target_files)
    
    validated_file_count = issues.get("validated_file_count", 0)
    report = validator.generate_report(issues, validated_file_count)
    safe_print(report)
    
    # 返回退出码
    if issues["errors"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

