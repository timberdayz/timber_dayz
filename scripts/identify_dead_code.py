#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
死代码识别脚本 (v4.7.0)

检查：
1. 未被main.py引用的router文件
2. ORM模型定义但未被使用
3. 废弃API是否还有调用
4. 前端是否调用了已删除的后端API
"""

import sys
import re
from pathlib import Path
from typing import List, Set, Dict

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def safe_print(text):
    """安全打印（Windows兼容）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))


def find_routers_in_main() -> Set[str]:
    """查找main.py中引用的所有router"""
    main_file = project_root / 'backend' / 'main.py'
    if not main_file.exists():
        return set()
    
    content = main_file.read_text(encoding='utf-8')
    
    # 提取import语句中的router名称
    import_pattern = r'from backend\.routers import \((.*?)\)'
    match = re.search(import_pattern, content, re.DOTALL)
    
    routers = set()
    if match:
        imports = match.group(1)
        for line in imports.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                # 提取router名称（逗号前的部分，去掉注释）
                router_name = line.split(',')[0].split('#')[0].strip()
                if router_name:
                    routers.add(router_name)
    
    # 也查找app.include_router语句
    include_pattern = r'app\.include_router\(\s*(\w+)\.router'
    for match in re.finditer(include_pattern, content):
        routers.add(match.group(1))
    
    return routers


def find_all_router_files() -> Set[str]:
    """查找所有router文件"""
    routers_dir = project_root / 'backend' / 'routers'
    if not routers_dir.exists():
        return set()
    
    router_files = set()
    
    for py_file in routers_dir.glob('*.py'):
        if py_file.name != '__init__.py':
            # 去掉.py扩展名
            router_name = py_file.stem
            router_files.add(router_name)
    
    return router_files


def find_orm_models_in_backend_models() -> List[Dict]:
    """查找backend/models/中独立定义的ORM模型"""
    models_dir = project_root / 'backend' / 'models'
    if not models_dir.exists():
        return []
    
    independent_models = []
    
    for py_file in models_dir.glob('*.py'):
        if py_file.name in ['__init__.py', 'database.py']:
            continue
        
        try:
            content = py_file.read_text(encoding='utf-8')
            
            # 查找class XXX(Base):模式
            pattern = r'class\s+(\w+)\s*\(\s*Base\s*\):'
            matches = re.findall(pattern, content)
            
            for model_name in matches:
                independent_models.append({
                    'file': py_file.relative_to(project_root),
                    'model': model_name
                })
        except Exception as e:
            safe_print(f"[WARNING] Failed to read {py_file}: {e}")
    
    return independent_models


def find_deprecated_api_calls() -> List[Dict]:
    """查找前端对已废弃API的调用"""
    deprecated_apis = {
        '/field-mapping/template/save': 'v4.5.1',
        '/field-mapping/template/apply': 'v4.5.1',
    }
    
    api_dir = project_root / 'frontend' / 'src' / 'api'
    if not api_dir.exists():
        return []
    
    calls = []
    
    for js_file in api_dir.glob('*.js'):
        try:
            content = js_file.read_text(encoding='utf-8')
            
            for api_path, version in deprecated_apis.items():
                if api_path in content:
                    # 找到行号
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        if api_path in line:
                            calls.append({
                                'file': js_file.relative_to(project_root),
                                'line': i,
                                'api': api_path,
                                'deprecated_since': version
                            })
                            break
        except Exception as e:
            safe_print(f"[WARNING] Failed to read {js_file}: {e}")
    
    return calls


def check_router_usage(router_name: str) -> Dict[str, any]:
    """检查router的使用情况"""
    router_file = project_root / 'backend' / 'routers' / f'{router_name}.py'
    if not router_file.exists():
        return {'exists': False}
    
    try:
        content = router_file.read_text(encoding='utf-8')
        
        # 统计API端点数量
        api_pattern = r'@router\.(get|post|put|delete|patch)\('
        api_count = len(re.findall(api_pattern, content))
        
        # 检查最后修改时间
        import os
        mtime = os.path.getmtime(router_file)
        from datetime import datetime
        last_modified = datetime.fromtimestamp(mtime)
        
        return {
            'exists': True,
            'api_count': api_count,
            'last_modified': last_modified.strftime('%Y-%m-%d'),
            'size': len(content)
        }
    except Exception as e:
        return {'exists': True, 'error': str(e)}


def main():
    """主函数"""
    safe_print("\n" + "="*80)
    safe_print("Dead Code Identification (v4.7.0)")
    safe_print("="*80)
    
    issues_found = 0
    
    # Test 1: 未使用的router文件
    safe_print("\n[Test 1] Checking for unused router files...")
    safe_print("-" * 80)
    
    routers_in_main = find_routers_in_main()
    all_routers = find_all_router_files()
    unused_routers = all_routers - routers_in_main
    
    safe_print(f"  Total router files: {len(all_routers)}")
    safe_print(f"  Registered in main.py: {len(routers_in_main)}")
    
    if unused_routers:
        safe_print(f"\n[FOUND] {len(unused_routers)} unused router files:")
        for router in sorted(unused_routers):
            usage_info = check_router_usage(router)
            if usage_info.get('exists'):
                safe_print(f"  - backend/routers/{router}.py")
                safe_print(f"    API endpoints: {usage_info.get('api_count', 'unknown')}")
                safe_print(f"    Last modified: {usage_info.get('last_modified', 'unknown')}")
        issues_found += len(unused_routers)
    else:
        safe_print("[OK] All router files are referenced in main.py")
    
    # Test 2: backend/models/中的独立ORM定义
    safe_print("\n[Test 2] Checking for independent ORM models in backend/models/...")
    safe_print("-" * 80)
    
    independent_models = find_orm_models_in_backend_models()
    
    if independent_models:
        safe_print(f"[WARNING] Found {len(independent_models)} ORM models "
                  "defined outside modules/core/db/schema.py:")
        for model_info in independent_models:
            safe_print(f"  - {model_info['file']}: {model_info['model']}")
        safe_print("  Recommendation: Move to modules/core/db/schema.py (SSOT)")
        issues_found += len(independent_models)
    else:
        safe_print("[OK] No independent ORM models found in backend/models/")
    
    # Test 3: 前端调用已废弃API
    safe_print("\n[Test 3] Checking for frontend calls to deprecated APIs...")
    safe_print("-" * 80)
    
    deprecated_calls = find_deprecated_api_calls()
    
    if deprecated_calls:
        safe_print(f"[FOUND] {len(deprecated_calls)} calls to deprecated APIs:")
        for call in deprecated_calls:
            safe_print(f"  - {call['file']}:{call['line']}: {call['api']} "
                      f"(deprecated since {call['deprecated_since']})")
        issues_found += len(deprecated_calls)
    else:
        safe_print("[OK] No calls to deprecated APIs found")
    
    # Test 4: 重复功能的router
    safe_print("\n[Test 4] Checking for potentially duplicate routers...")
    safe_print("-" * 80)
    
    potential_duplicates = {
        'accounts': 'account_management',
        'inventory': 'inventory_management',
        'performance': 'performance_management',
    }
    
    duplicates_found = []
    for old_name, new_name in potential_duplicates.items():
        if old_name in all_routers and new_name in all_routers:
            duplicates_found.append((old_name, new_name))
    
    if duplicates_found:
        safe_print(f"[WARNING] Found {len(duplicates_found)} potential duplicate router pairs:")
        for old_name, new_name in duplicates_found:
            safe_print(f"  - {old_name}.py vs {new_name}.py")
            safe_print(f"    Recommendation: Review if {old_name}.py can be removed")
        issues_found += len(duplicates_found)
    else:
        safe_print("[OK] No obvious duplicate routers found")
    
    # 总结
    safe_print("\n" + "="*80)
    safe_print("Summary")
    safe_print("="*80)
    safe_print(f"  Total issues found: {issues_found}")
    
    if issues_found > 0:
        safe_print(f"\n[ACTION REQUIRED] Please review and clean up {issues_found} issues")
        safe_print("\nNext steps:")
        safe_print("  1. Review unused routers and decide if they should be deleted")
        safe_print("  2. Move independent ORM models to modules/core/db/schema.py")
        safe_print("  3. Update frontend code to use new APIs")
        safe_print("  4. Consolidate duplicate functionality")
        return 1
    else:
        safe_print("\n[OK] No dead code detected!")
        return 0


if __name__ == "__main__":
    sys.exit(main())

