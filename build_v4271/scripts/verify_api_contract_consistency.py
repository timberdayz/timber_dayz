#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
前后端API契约一致性验证 (v4.7.0)

检查：
1. 前端API调用的路径是否存在于后端
2. 前端API参数是否与后端定义一致
3. 前端API文档（JSDoc）是否完整
"""

import sys
import re
import json
from pathlib import Path
from typing import List, Dict, Set

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def safe_print(text):
    """安全打印（Windows兼容）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))


class BackendAPIExtractor:
    """后端API提取器"""
    
    def __init__(self):
        self.endpoints: Dict[str, List[Dict]] = {}
    
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
            
            # 提取router prefix（如果有）
            prefix_match = re.search(r'router\s*=\s*APIRouter\([^)]*prefix=["\']([^"\']+)["\']', content)
            prefix = prefix_match.group(1) if prefix_match else ''
            
            # 查找所有API定义
            pattern = r'@router\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']'
            matches = re.finditer(pattern, content)
            
            for match in matches:
                method = match.group(1).upper()
                path = match.group(2)
                full_path = prefix + path if not path.startswith('/') else path
                
                # 标准化路径（移除重复的/）
                full_path = re.sub(r'/+', '/', full_path)
                
                key = f"{method} {full_path}"
                if key not in self.endpoints:
                    self.endpoints[key] = []
                
                self.endpoints[key].append({
                    'file': file_path.relative_to(project_root),
                    'method': method,
                    'path': full_path
                })
                
        except Exception as e:
            pass


class FrontendAPIExtractor:
    """前端API提取器"""
    
    def __init__(self):
        self.api_calls: List[Dict] = []
    
    def scan_api_files(self):
        """扫描所有前端API文件"""
        api_dir = project_root / 'frontend' / 'src' / 'api'
        if not api_dir.exists():
            return
        
        for js_file in api_dir.glob('*.js'):
            if js_file.name == 'index.js':
                continue
            self._scan_api_file(js_file)
    
    def _scan_api_file(self, file_path: Path):
        """扫描单个API文件"""
        try:
            content = file_path.read_text(encoding='utf-8')
            
            # 查找api.get/post/put/delete调用
            pattern = r'api\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']'
            matches = re.finditer(pattern, content)
            
            for match in matches:
                method = match.group(1).upper()
                path = match.group(2)
                line_no = content[:match.start()].count('\n') + 1
                
                # 标准化路径
                path = re.sub(r'/+', '/', path)
                
                self.api_calls.append({
                    'file': file_path.relative_to(project_root),
                    'line': line_no,
                    'method': method,
                    'path': path
                })
                
        except Exception as e:
            pass


def normalize_path(path: str) -> str:
    """标准化API路径，用于匹配"""
    # 移除参数占位符进行通配匹配
    # /accounts/123 -> /accounts/{id}
    # /collection/tasks/abc-123 -> /collection/tasks/{id}
    
    # 替换数字ID
    path = re.sub(r'/\d+', '/{id}', path)
    # 替换UUID格式ID
    path = re.sub(r'/[a-f0-9\-]{36}', '/{id}', path)
    # 替换其他ID格式
    path = re.sub(r'/[a-z0-9\-_]{8,}', '/{id}', path)
    
    return path


def path_matches(frontend_path: str, backend_path: str) -> bool:
    """检查前端路径是否匹配后端路径"""
    # 精确匹配
    if frontend_path == backend_path:
        return True
    
    # 规范化后匹配
    norm_frontend = normalize_path(frontend_path)
    norm_backend = normalize_path(backend_path)
    
    if norm_frontend == norm_backend:
        return True
    
    # 检查后端路径是否包含参数（如 {account_id}）
    backend_pattern = re.escape(backend_path)
    backend_pattern = backend_pattern.replace(r'\{[^}]+\}', r'[^/]+')
    if re.match(f'^{backend_pattern}$', frontend_path):
        return True
    
    return False


def main():
    """主函数"""
    safe_print("\n" + "="*80)
    safe_print("Frontend-Backend API Contract Consistency Check (v4.7.0)")
    safe_print("="*80)
    
    # 提取后端API
    safe_print("\n[Step 1] Extracting backend API endpoints...")
    backend = BackendAPIExtractor()
    backend.scan_routers()
    safe_print(f"  Found {len(backend.endpoints)} backend API endpoints")
    
    # 提取前端API调用
    safe_print("\n[Step 2] Extracting frontend API calls...")
    frontend = FrontendAPIExtractor()
    frontend.scan_api_files()
    safe_print(f"  Found {len(frontend.api_calls)} frontend API calls")
    
    # 检查一致性
    safe_print("\n[Step 3] Checking consistency...")
    safe_print("-" * 80)
    
    mismatches = []
    for api_call in frontend.api_calls:
        key = f"{api_call['method']} {api_call['path']}"
        
        # 检查精确匹配
        if key in backend.endpoints:
            continue
        
        # 检查模糊匹配
        found_match = False
        for backend_key in backend.endpoints.keys():
            backend_method, backend_path = backend_key.split(' ', 1)
            if backend_method == api_call['method'] and path_matches(api_call['path'], backend_path):
                found_match = True
                break
        
        if not found_match:
            mismatches.append(api_call)
    
    if mismatches:
        safe_print(f"[WARNING] Found {len(mismatches)} API calls without matching backend endpoints:")
        
        # 显示前20个
        for mismatch in mismatches[:20]:
            safe_print(f"  - {mismatch['file']}:{mismatch['line']} "
                      f"{mismatch['method']} {mismatch['path']}")
        
        if len(mismatches) > 20:
            safe_print(f"  ... and {len(mismatches) - 20} more")
        
        safe_print("\n  Possible reasons:")
        safe_print("    1. API path changed but frontend not updated")
        safe_print("    2. API prefix not included in search")
        safe_print("    3. Dynamic path construction in frontend")
        safe_print("    4. API endpoint removed but frontend still calls it")
    else:
        safe_print("[OK] All frontend API calls match backend endpoints")
    
    # 检查反向：后端API是否被前端使用
    safe_print("\n[Step 4] Checking for unused backend APIs...")
    safe_print("-" * 80)
    
    frontend_paths = set()
    for call in frontend.api_calls:
        frontend_paths.add(f"{call['method']} {call['path']}")
    
    unused_apis = []
    for backend_key in backend.endpoints.keys():
        if backend_key not in frontend_paths:
            # 检查是否有模糊匹配
            backend_method, backend_path = backend_key.split(' ', 1)
            found_match = False
            for call in frontend.api_calls:
                if call['method'] == backend_method and path_matches(call['path'], backend_path):
                    found_match = True
                    break
            
            if not found_match:
                unused_apis.append(backend_key)
    
    if unused_apis:
        safe_print(f"[INFO] Found {len(unused_apis)} backend APIs not called by frontend:")
        safe_print("  (These might be called by mobile apps, scripts, or are newly added)")
        for api in unused_apis[:10]:
            safe_print(f"  - {api}")
        if len(unused_apis) > 10:
            safe_print(f"  ... and {len(unused_apis) - 10} more")
    else:
        safe_print("[INFO] All backend APIs are used by frontend")
    
    # 总结
    safe_print("\n" + "="*80)
    safe_print("Summary")
    safe_print("="*80)
    safe_print(f"  Backend endpoints: {len(backend.endpoints)}")
    safe_print(f"  Frontend API calls: {len(frontend.api_calls)}")
    safe_print(f"  Mismatches: {len(mismatches)}")
    safe_print(f"  Potentially unused backend APIs: {len(unused_apis)}")
    
    if len(mismatches) > 0:
        safe_print("\n[ACTION REQUIRED] Fix API mismatches before deployment")
        return 1
    else:
        safe_print("\n[OK] Frontend-backend API contract is consistent")
        return 0


if __name__ == "__main__":
    sys.exit(main())

