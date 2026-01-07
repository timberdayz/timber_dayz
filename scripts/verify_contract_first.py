#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Contract-First开发验证脚本 (v4.7.0)

检查：
1. Pydantic模型是否有重复定义
2. 所有API是否定义了response_model
3. Request/Response模型是否集中在schemas/目录
"""

import sys
import ast
import re
from pathlib import Path
from typing import List, Dict, Set, Tuple
from collections import defaultdict

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def safe_print(text):
    """安全打印（Windows兼容）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))


class PydanticModelFinder:
    """Pydantic模型查找器"""
    
    def __init__(self):
        self.models: Dict[str, List[Tuple[Path, int]]] = defaultdict(list)
        self.router_models: Set[str] = set()
        self.schema_models: Set[str] = set()
        
    def scan_project(self):
        """扫描整个项目"""
        exclude_dirs = {'node_modules', '__pycache__', '.git', 'backups', 'temp', 'venv', 'tests'}
        
        for py_file in project_root.rglob("*.py"):
            if any(exclude in py_file.parts for exclude in exclude_dirs):
                continue
                
            self._scan_file(py_file)
    
    def _scan_file(self, file_path: Path):
        """扫描单个文件"""
        try:
            content = file_path.read_text(encoding='utf-8')
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # 检查是否继承自BaseModel
                    for base in node.bases:
                        if isinstance(base, ast.Name) and base.id == 'BaseModel':
                            model_name = node.name
                            line_no = node.lineno
                            
                            # 记录模型位置
                            self.models[model_name].append((file_path, line_no))
                            
                            # 分类：router还是schema
                            if 'routers' in file_path.parts:
                                self.router_models.add(model_name)
                            elif 'schemas' in file_path.parts:
                                self.schema_models.add(model_name)
                            
        except Exception as e:
            pass
    
    def find_duplicates(self) -> List[Tuple[str, List[Tuple[Path, int]]]]:
        """查找重复的模型定义"""
        return [(name, locations) for name, locations in self.models.items() 
                if len(locations) > 1]
    
    def find_router_models(self) -> List[Tuple[str, List[Tuple[Path, int]]]]:
        """查找在router中定义的模型（应该在schemas/中）"""
        return [(name, locations) for name, locations in self.models.items() 
                if name in self.router_models]


class APIEndpointChecker:
    """API端点检查器"""
    
    def __init__(self):
        self.endpoints_without_response_model = []
        self.total_endpoints = 0
    
    def scan_routers(self):
        """扫描所有router文件"""
        routers_dir = project_root / 'backend' / 'routers'
        if not routers_dir.exists():
            return
        
        for py_file in routers_dir.glob('*.py'):
            if py_file.name != '__init__.py':
                self._scan_router(py_file)
    
    def _scan_router(self, file_path: Path):
        """扫描单个router文件"""
        try:
            content = file_path.read_text(encoding='utf-8')
            
            # 查找所有API定义
            pattern = r'@router\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']'
            matches = re.finditer(pattern, content)
            
            for match in matches:
                self.total_endpoints += 1
                method = match.group(1)
                path = match.group(2)
                line_no = content[:match.start()].count('\n') + 1
                
                # 检查接下来的几行是否有response_model
                lines = content.split('\n')
                decorator_line = line_no - 1
                
                # 检查装饰器行和函数定义行（通常在接下来的1-3行）
                has_response_model = False
                for i in range(decorator_line, min(decorator_line + 5, len(lines))):
                    if 'response_model=' in lines[i]:
                        has_response_model = True
                        break
                
                if not has_response_model:
                    self.endpoints_without_response_model.append({
                        'file': file_path,
                        'line': line_no,
                        'method': method.upper(),
                        'path': path
                    })
                    
        except Exception as e:
            pass


def main():
    """主函数"""
    safe_print("\n" + "="*80)
    safe_print("Contract-First Development Verification (v4.7.0)")
    safe_print("="*80)
    
    passed_tests = 0
    failed_tests = 0
    warnings = 0
    
    # Test 1: 检查Pydantic模型重复定义
    safe_print("\n[Test 1] Checking for duplicate Pydantic model definitions...")
    safe_print("-" * 80)
    
    finder = PydanticModelFinder()
    finder.scan_project()
    duplicates = finder.find_duplicates()
    
    if duplicates:
        safe_print(f"[FAILED] Found {len(duplicates)} duplicate model definitions:")
        for model_name, locations in duplicates:
            safe_print(f"\n  {model_name} is defined in {len(locations)} places:")
            for file_path, line_no in locations:
                try:
                    rel_path = file_path.relative_to(project_root)
                except:
                    rel_path = file_path
                safe_print(f"    - {rel_path}:{line_no}")
        failed_tests += 1
    else:
        safe_print("[OK] No duplicate Pydantic model definitions found")
        passed_tests += 1
    
    # Test 2: 检查模型定义位置（应该在schemas/目录）
    safe_print("\n[Test 2] Checking model definition locations...")
    safe_print("-" * 80)
    
    router_models = finder.find_router_models()
    schemas_count = len(finder.schema_models)
    routers_count = len(finder.router_models)
    total_count = len(finder.models)
    
    safe_print(f"  Total Pydantic models: {total_count}")
    safe_print(f"  Models in schemas/ directory: {schemas_count}")
    safe_print(f"  Models in routers/ directory: {routers_count}")
    
    if routers_count > schemas_count * 2:  # 如果router中的模型是schema的2倍以上
        safe_print(f"[WARNING] Most models ({routers_count}) are defined in routers/")
        safe_print("  Recommendation: Move models to backend/schemas/ for better organization")
        warnings += 1
    else:
        safe_print("[OK] Model organization is acceptable")
        passed_tests += 1
    
    # Test 3: 检查API端点是否定义response_model
    safe_print("\n[Test 3] Checking API endpoints for response_model...")
    safe_print("-" * 80)
    
    checker = APIEndpointChecker()
    checker.scan_routers()
    
    safe_print(f"  Total API endpoints scanned: {checker.total_endpoints}")
    safe_print(f"  Endpoints without response_model: {len(checker.endpoints_without_response_model)}")
    
    if checker.endpoints_without_response_model:
        coverage = (checker.total_endpoints - len(checker.endpoints_without_response_model)) * 100 // max(checker.total_endpoints, 1)
        safe_print(f"  response_model coverage: {coverage}%")
        
        if len(checker.endpoints_without_response_model) > 20:
            safe_print(f"[WARNING] Found {len(checker.endpoints_without_response_model)} "
                      "endpoints without response_model (showing first 10):")
            for endpoint in checker.endpoints_without_response_model[:10]:
                try:
                    rel_path = endpoint['file'].relative_to(project_root)
                except:
                    rel_path = endpoint['file']
                safe_print(f"  - {rel_path}:{endpoint['line']} "
                          f"{endpoint['method']} {endpoint['path']}")
            safe_print(f"  ... and {len(checker.endpoints_without_response_model) - 10} more")
        else:
            safe_print(f"[WARNING] Found {len(checker.endpoints_without_response_model)} "
                      "endpoints without response_model:")
            for endpoint in checker.endpoints_without_response_model:
                try:
                    rel_path = endpoint['file'].relative_to(project_root)
                except:
                    rel_path = endpoint['file']
                safe_print(f"  - {rel_path}:{endpoint['line']} "
                          f"{endpoint['method']} {endpoint['path']}")
        warnings += 1
    else:
        safe_print("[OK] All API endpoints have response_model defined")
        passed_tests += 1
    
    # Test 4: 统计信息
    safe_print("\n[Test 4] Project statistics...")
    safe_print("-" * 80)
    
    total_models = len(finder.models)
    if total_models > 0:
        safe_print(f"  Total Pydantic models: {total_models}")
        safe_print(f"  Models in schemas/:     {schemas_count} ({schemas_count*100//total_models}%)")
        safe_print(f"  Models in routers/:     {routers_count} ({routers_count*100//total_models}%)")
        
        coverage = schemas_count * 100 // total_models
        if coverage < 30:
            safe_print(f"[WARNING] Low schemas/ coverage: {coverage}%")
            safe_print("  Recommendation: Gradually move models to schemas/ directory")
            warnings += 1
        else:
            safe_print(f"[OK] Schemas coverage: {coverage}%")
            passed_tests += 1
    else:
        safe_print("[WARNING] No Pydantic models found in project")
        warnings += 1
    
    # 总结
    safe_print("\n" + "="*80)
    safe_print("Summary")
    safe_print("="*80)
    safe_print(f"  Tests Passed:  {passed_tests}")
    safe_print(f"  Tests Failed:  {failed_tests}")
    safe_print(f"  Warnings:      {warnings}")
    
    total_issues = failed_tests + warnings
    if total_issues == 0:
        safe_print("\n[OK] All contract-first checks passed!")
        return 0
    else:
        safe_print(f"\n[ATTENTION] Found {total_issues} issues that need attention")
        safe_print("\nRecommendations:")
        safe_print("  1. Fix duplicate model definitions (highest priority)")
        safe_print("  2. Add response_model to all API endpoints")
        safe_print("  3. Move models from routers/ to backend/schemas/")
        return 1


if __name__ == "__main__":
    sys.exit(main())

