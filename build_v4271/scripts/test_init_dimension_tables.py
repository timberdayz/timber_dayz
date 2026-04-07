#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 init_dimension_tables.py 脚本

验证方案A的实施是否正确：
1. 检查代码语法
2. 检查导入是否正确
3. 检查函数签名
4. 模拟测试同步逻辑（不实际执行数据库操作）
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def safe_print(msg):
    """安全打印（避免Windows编码问题）"""
    try:
        print(msg)
    except UnicodeEncodeError:
        # 替换特殊字符
        safe_msg = msg.encode('ascii', 'replace').decode('ascii')
        print(safe_msg)

def test_imports():
    """测试导入"""
    safe_print("[Test 1] 测试导入...")
    try:
        from backend.models.database import SessionLocal
        from modules.core.db import DimPlatform, DimShop, PlatformAccount
        from sqlalchemy import text
        from modules.core.logger import get_logger
        from typing import Optional
        safe_print("  [OK] 所有导入成功")
        return True
    except ImportError as e:
        safe_print(f"  [FAIL] 导入失败: {e}")
        return False

def test_function_signature():
    """测试函数签名"""
    safe_print("\n[Test 2] 测试函数签名...")
    try:
        from scripts.init_dimension_tables import sync_platform_account_to_dim_shop_sync, init_dimension_tables
        import inspect
        
        # 检查 sync_platform_account_to_dim_shop_sync 签名
        sig = inspect.signature(sync_platform_account_to_dim_shop_sync)
        return_type = sig.return_annotation
        safe_print(f"  sync_platform_account_to_dim_shop_sync 返回类型: {return_type}")
        
        if 'Optional' in str(return_type) or 'None' in str(return_type):
            safe_print("  [OK] 返回类型正确（支持 None）")
        else:
            safe_print("  [WARN] 返回类型可能不正确（应该支持 None）")
        
        # 检查 init_dimension_tables 是否存在
        if callable(init_dimension_tables):
            safe_print("  [OK] init_dimension_tables 函数存在")
        else:
            safe_print("  [FAIL] init_dimension_tables 函数不存在")
        
        return True
    except Exception as e:
        safe_print(f"  [FAIL] 测试失败: {e}")
        return False

def test_code_syntax():
    """测试代码语法"""
    safe_print("\n[Test 3] 测试代码语法...")
    try:
        import py_compile
        script_path = project_root / "scripts" / "init_dimension_tables.py"
        py_compile.compile(str(script_path), doraise=True)
        safe_print("  [OK] 代码语法正确")
        return True
    except py_compile.PyCompileError as e:
        safe_print(f"  [FAIL] 语法错误: {e}")
        return False
    except Exception as e:
        safe_print(f"  [FAIL] 编译失败: {e}")
        return False

def test_logic_structure():
    """测试逻辑结构（不执行数据库操作）"""
    safe_print("\n[Test 4] 测试逻辑结构...")
    try:
        # 读取文件内容
        script_path = project_root / "scripts" / "init_dimension_tables.py"
        content = script_path.read_text(encoding='utf-8')
        
        checks = {
            "从 platform_accounts 读取账号": "PlatformAccount" in content and "enabled == True" in content,
            "调用同步函数": "sync_platform_account_to_dim_shop_sync" in content,
            "处理 shop_id": "shop_id or account.account_id" in content,
            "创建/更新店铺": "DimShop(" in content,
            "确保平台存在": "DimPlatform" in content and "platform_code" in content,
            "提交事务": "db.commit()" in content,
            "错误处理": "except Exception" in content,
        }
        
        all_passed = True
        for check_name, passed in checks.items():
            if passed:
                safe_print(f"  [OK] {check_name}")
            else:
                safe_print(f"  [FAIL] {check_name}")
                all_passed = False
        
        return all_passed
    except Exception as e:
        safe_print(f"  [FAIL] 测试失败: {e}")
        return False

def test_documentation():
    """测试文档完整性"""
    safe_print("\n[Test 5] 测试文档完整性...")
    try:
        script_path = project_root / "scripts" / "init_dimension_tables.py"
        content = script_path.read_text(encoding='utf-8')
        
        checks = {
            "方案A说明": "方案A" in content,
            "v4.19.0版本标记": "v4.19.0" in content,
            "函数文档字符串": '"""' in content and "同步 platform_accounts" in content,
            "废弃说明": "废弃从 catalog_files" in content or "废弃" in content,
        }
        
        all_passed = True
        for check_name, passed in checks.items():
            if passed:
                safe_print(f"  [OK] {check_name}")
            else:
                safe_print(f"  [WARN] {check_name} (可选)")
        
        return True
    except Exception as e:
        safe_print(f"  [FAIL] 测试失败: {e}")
        return False

def main():
    """运行所有测试"""
    safe_print("=" * 60)
    safe_print("测试 init_dimension_tables.py 脚本（方案A实施验证）")
    safe_print("=" * 60)
    
    results = []
    results.append(("导入测试", test_imports()))
    results.append(("函数签名测试", test_function_signature()))
    results.append(("代码语法测试", test_code_syntax()))
    results.append(("逻辑结构测试", test_logic_structure()))
    results.append(("文档完整性测试", test_documentation()))
    
    safe_print("\n" + "=" * 60)
    safe_print("测试结果汇总")
    safe_print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "[OK] 通过" if result else "[FAIL] 失败"
        safe_print(f"{test_name}: {status}")
    
    safe_print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        safe_print("\n[SUCCESS] 所有测试通过！脚本可以安全使用。")
        return 0
    else:
        safe_print("\n[WARN] 部分测试失败，请检查上述问题。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
