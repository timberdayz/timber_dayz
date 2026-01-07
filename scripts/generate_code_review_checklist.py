#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
代码审查检查清单工具

功能：
1. 自动生成代码审查检查清单
2. 检查代码是否符合标准
3. 生成检查报告
"""

import sys
import re
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class CodeReviewChecklistGenerator:
    """代码审查检查清单生成器"""
    
    def __init__(self):
        self.checks = {
            "api_response_format": [],
            "error_handling": [],
            "field_validation": [],
            "frontend_api_methods": []
        }
    
    def check_api_response_format(self, file_path: Path) -> List[Dict[str, Any]]:
        """检查API响应格式"""
        issues = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 检查是否使用raise HTTPException（除了410 Gone）
            http_exception_pattern = r'raise HTTPException\('
            matches = list(re.finditer(http_exception_pattern, content))
            
            for match in matches:
                line_start = content[:match.start()].rfind('\n') + 1
                line_end = content.find('\n', match.end())
                line_content = content[line_start:line_end] if line_end != -1 else content[line_start:]
                
                if '410' not in line_content and 'Gone' not in line_content:
                    line_num = content[:match.start()].count('\n') + 1
                    issues.append({
                        "type": "error",
                        "file": str(file_path),
                        "line": line_num,
                        "check": "API响应格式",
                        "message": "应使用error_response()而非raise HTTPException",
                        "suggestion": "使用error_response(code=..., message=..., recovery_suggestion=...)"
                    })
            
            # 检查error_response是否包含recovery_suggestion
            error_response_pattern = r'error_response\('
            matches = list(re.finditer(error_response_pattern, content))
            
            for match in matches:
                # 查找对应的闭合括号
                paren_count = 1
                pos = match.end()
                while pos < len(content) and paren_count > 0:
                    if content[pos] == '(':
                        paren_count += 1
                    elif content[pos] == ')':
                        paren_count -= 1
                    pos += 1
                
                error_response_content = content[match.start():pos]
                
                if 'recovery_suggestion' not in error_response_content:
                    line_num = content[:match.start()].count('\n') + 1
                    issues.append({
                        "type": "warning",
                        "file": str(file_path),
                        "line": line_num,
                        "check": "API响应格式",
                        "message": "error_response()缺少recovery_suggestion参数",
                        "suggestion": "添加recovery_suggestion='用户友好的恢复建议'"
                    })
        
        except Exception as e:
            issues.append({
                "type": "error",
                "file": str(file_path),
                "line": 0,
                "check": "API响应格式",
                "message": f"读取文件失败: {str(e)}",
                "suggestion": "检查文件权限和编码"
            })
        
        return issues
    
    def check_error_handling(self, file_path: Path) -> List[Dict[str, Any]]:
        """检查错误处理"""
        issues = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 检查except块中是否有错误日志
            except_pattern = r'except\s+.*?:'
            matches = list(re.finditer(except_pattern, content))
            
            for match in matches:
                except_start = match.end()
                # 查找下一个except或函数/类定义
                next_except = re.search(r'except\s+', content[except_start:])
                next_def = re.search(r'^\s*(?:def|class|async def)\s+', content[except_start:], re.MULTILINE)
                
                if next_except and next_def:
                    except_end = except_start + min(next_except.start(), next_def.start())
                elif next_except:
                    except_end = except_start + next_except.start()
                elif next_def:
                    except_end = except_start + next_def.start()
                else:
                    except_end = len(content)
                
                except_block = content[except_start:except_end]
                
                # 检查是否有logger.error或logger.exception
                if 'logger.error' not in except_block and 'logger.exception' not in except_block:
                    # 检查是否有error_response（如果有error_response，可能不需要logger）
                    if 'error_response(' not in except_block:
                        line_num = content[:match.start()].count('\n') + 1
                        issues.append({
                            "type": "warning",
                            "file": str(file_path),
                            "line": line_num,
                            "check": "错误处理",
                            "message": "except块中缺少错误日志记录",
                            "suggestion": "添加logger.error(..., exc_info=True)"
                        })
        
        except Exception as e:
            issues.append({
                "type": "error",
                "file": str(file_path),
                "line": 0,
                "check": "错误处理",
                "message": f"分析文件失败: {str(e)}",
                "suggestion": "检查文件格式"
            })
        
        return issues
    
    def check_frontend_response_format(self, file_path: Path) -> List[Dict[str, Any]]:
        """检查前端响应格式"""
        issues = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 检查是否使用response.success
            success_pattern = r'response\.success|res\.success|data\.success'
            matches = list(re.finditer(success_pattern, content))
            
            for match in matches:
                line_num = content[:match.start()].count('\n') + 1
                line_start = content[:match.start()].rfind('\n') + 1
                line_end = content.find('\n', match.end())
                line_content = content[line_start:line_end] if line_end != -1 else content[line_start:]
                
                issues.append({
                    "type": "error",
                    "file": str(file_path),
                    "line": line_num,
                    "check": "前端API调用",
                    "message": "不应检查response.success字段（拦截器已处理）",
                    "suggestion": "直接使用返回的data，拦截器已提取data字段"
                })
            
            # 检查是否使用response.pagination
            pagination_pattern = r'response\.pagination|res\.pagination'
            matches = list(re.finditer(pagination_pattern, content))
            
            for match in matches:
                line_num = content[:match.start()].count('\n') + 1
                issues.append({
                    "type": "warning",
                    "file": str(file_path),
                    "line": line_num,
                    "check": "前端API调用",
                    "message": "应使用扁平格式（response.total）而非嵌套格式（response.pagination.total）",
                    "suggestion": "使用response.total替代response.pagination.total"
                })
        
        except Exception as e:
            issues.append({
                "type": "error",
                "file": str(file_path),
                "line": 0,
                "check": "前端API调用",
                "message": f"读取文件失败: {str(e)}",
                "suggestion": "检查文件权限和编码"
            })
        
        return issues
    
    def scan_files(self) -> Dict[str, List[Path]]:
        """扫描所有需要检查的文件"""
        files = {
            "backend_routers": [],
            "frontend_views": []
        }
        
        # 后端路由文件
        router_dir = project_root / "backend" / "routers"
        if router_dir.exists():
            files["backend_routers"] = [f for f in router_dir.glob("*.py") if f.name != "__init__.py"]
        
        # 前端视图文件
        frontend_dir = project_root / "frontend" / "src" / "views"
        if frontend_dir.exists():
            files["frontend_views"] = list(frontend_dir.rglob("*.vue"))
        
        return files
    
    def generate_checklist(self) -> Dict[str, Any]:
        """生成检查清单"""
        files = self.scan_files()
        
        all_issues = {
            "api_response_format": [],
            "error_handling": [],
            "frontend_api_methods": []
        }
        
        # 检查后端路由文件
        for router_file in files["backend_routers"]:
            api_issues = self.check_api_response_format(router_file)
            all_issues["api_response_format"].extend(api_issues)
            
            error_issues = self.check_error_handling(router_file)
            all_issues["error_handling"].extend(error_issues)
        
        # 检查前端视图文件
        for vue_file in files["frontend_views"]:
            frontend_issues = self.check_frontend_response_format(vue_file)
            all_issues["frontend_api_methods"].extend(frontend_issues)
        
        return all_issues
    
    def generate_report(self, issues: Dict[str, Any]) -> str:
        """生成检查报告"""
        report = []
        report.append("=" * 60)
        report.append("代码审查检查清单报告")
        report.append("=" * 60)
        report.append("")
        
        # 统计信息
        total_errors = sum(len([i for i in issues[k] if i["type"] == "error"]) for k in issues)
        total_warnings = sum(len([i for i in issues[k] if i["type"] == "warning"]) for k in issues)
        
        report.append(f"总错误数: {total_errors}")
        report.append(f"总警告数: {total_warnings}")
        report.append("")
        
        # 按检查项分组
        for check_name, check_issues in issues.items():
            if not check_issues:
                continue
            
            errors = [i for i in check_issues if i["type"] == "error"]
            warnings = [i for i in check_issues if i["type"] == "warning"]
            
            if errors or warnings:
                report.append("=" * 60)
                report.append(f"{check_name.upper().replace('_', ' ')}")
                report.append("=" * 60)
                
                if errors:
                    report.append(f"\n错误 ({len(errors)}个):")
                    for error in errors[:10]:  # 只显示前10个
                        report.append(f"  [{error['file']}:{error['line']}] {error['message']}")
                        report.append(f"    建议: {error['suggestion']}")
                    if len(errors) > 10:
                        report.append(f"  ... 还有 {len(errors) - 10} 个错误")
                
                if warnings:
                    report.append(f"\n警告 ({len(warnings)}个):")
                    for warning in warnings[:10]:  # 只显示前10个
                        report.append(f"  [{warning['file']}:{warning['line']}] {warning['message']}")
                        report.append(f"    建议: {warning['suggestion']}")
                    if len(warnings) > 10:
                        report.append(f"  ... 还有 {len(warnings) - 10} 个警告")
                
                report.append("")
        
        # 总结
        report.append("=" * 60)
        report.append("总结")
        report.append("=" * 60)
        if total_errors == 0 and total_warnings == 0:
            report.append("[OK] 所有检查项通过！")
        else:
            report.append(f"[ERROR] 发现 {total_errors} 个错误，{total_warnings} 个警告")
            report.append("\n建议:")
            report.append("1. 修复所有错误项")
            report.append("2. 审查警告项，根据实际情况决定是否修复")
            report.append("3. 运行验证脚本确认修复效果")
        
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
    generator = CodeReviewChecklistGenerator()
    
    safe_print("生成代码审查检查清单...")
    issues = generator.generate_checklist()
    
    report = generator.generate_report(issues)
    safe_print(report)
    
    # 保存报告到文件
    report_file = project_root / "temp" / "code_review_checklist_report.txt"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    safe_print(f"\n报告已保存到: {report_file}")
    
    # 返回退出码
    total_errors = sum(len([i for i in issues[k] if i["type"] == "error"]) for k in issues)
    if total_errors > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

