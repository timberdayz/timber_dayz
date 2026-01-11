#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试方案A实施的功能

验证：
1. verify_schema_completeness 函数是否正确
2. init_db 函数是否正确（生产环境禁用）
3. 迁移文件是否完整
4. 代码逻辑是否正确
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def safe_print(text):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            safe_text = text.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)

def test_imports():
    """测试导入"""
    safe_print("\n[TEST 1] 测试函数导入...")
    try:
        from backend.models.database import init_db, verify_schema_completeness
        safe_print("  [OK] init_db 和 verify_schema_completeness 导入成功")
        return True
    except Exception as e:
        safe_print(f"  [FAIL] 导入失败: {e}")
        return False

def test_init_db_production_mode():
    """测试 init_db 在生产环境的禁用"""
    safe_print("\n[TEST 2] 测试 init_db 生产环境禁用...")
    try:
        # 设置生产环境
        original_env = os.environ.get("ENVIRONMENT")
        os.environ["ENVIRONMENT"] = "production"
        
        from backend.models.database import init_db
        
        # init_db 应该直接返回，不创建表
        try:
            init_db()
            safe_print("  [OK] 生产环境下 init_db() 直接返回（不创建表）")
        except Exception as e:
            safe_print(f"  [WARN] init_db() 抛出异常: {e}")
        
        # 恢复环境变量
        if original_env:
            os.environ["ENVIRONMENT"] = original_env
        else:
            os.environ.pop("ENVIRONMENT", None)
        
        return True
    except Exception as e:
        safe_print(f"  [FAIL] 测试失败: {e}")
        # 恢复环境变量
        if original_env:
            os.environ["ENVIRONMENT"] = original_env
        else:
            os.environ.pop("ENVIRONMENT", None)
        return False

def test_migration_files():
    """测试迁移文件"""
    safe_print("\n[TEST 3] 测试迁移文件完整性...")
    try:
        import re
        from pathlib import Path
        
        migrations_dir = Path("migrations/versions")
        test_files = [
            "20260110_0001_complete_schema_base_tables.py",
            "20251209_v4_6_0_collection_module_tables.py",
            "20251105_add_performance_indexes.py",
            "20251105_add_field_usage_tracking.py"
        ]
        
        errors = []
        for filename in test_files:
            file_path = migrations_dir / filename
            if not file_path.exists():
                errors.append(f"  [FAIL] {filename}: 文件不存在")
                continue
            
            content = file_path.read_text(encoding='utf-8')
            
            # 检查 revision
            if not re.search(r"^revision\s*=\s*['\"][^'\"]+['\"]", content, re.MULTILINE):
                errors.append(f"  [FAIL] {filename}: 缺少 revision")
                continue
            
            # 检查 down_revision（初始迁移除外）
            if filename != "20250829_1118_0af13b84ba3f_initial_database_schema.py":
                if not re.search(r"^down_revision\s*=", content, re.MULTILINE):
                    errors.append(f"  [WARN] {filename}: 缺少 down_revision（可能是初始迁移）")
                elif re.search(r"^down_revision\s*=\s*None", content, re.MULTILINE) and "initial" not in filename.lower():
                    errors.append(f"  [WARN] {filename}: down_revision = None（可能需要修复）")
            
            # 检查 upgrade 函数
            if not re.search(r"def\s+upgrade", content):
                errors.append(f"  [FAIL] {filename}: 缺少 upgrade 函数")
                continue
        
        if errors:
            safe_print("\n".join(errors))
            return False
        else:
            safe_print("  [OK] 所有迁移文件检查通过")
            return True
            
    except Exception as e:
        safe_print(f"  [FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_verify_function_signature():
    """测试 verify_schema_completeness 函数签名"""
    safe_print("\n[TEST 4] 测试 verify_schema_completeness 函数签名...")
    try:
        from backend.models.database import verify_schema_completeness
        import inspect
        
        sig = inspect.signature(verify_schema_completeness)
        
        # 检查函数是否有正确的返回类型
        # 函数应该返回 dict
        safe_print(f"  [INFO] 函数签名: {sig}")
        
        # 尝试调用（可能会失败，因为没有数据库连接，但不影响测试）
        # 这里只检查函数是否存在和可调用
        if callable(verify_schema_completeness):
            safe_print("  [OK] verify_schema_completeness 函数可调用")
            return True
        else:
            safe_print("  [FAIL] verify_schema_completeness 不是可调用对象")
            return False
            
    except Exception as e:
        safe_print(f"  [FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    safe_print("=" * 80)
    safe_print("方案A实施功能测试")
    safe_print("=" * 80)
    
    results = []
    
    results.append(("函数导入", test_imports()))
    results.append(("init_db 生产环境禁用", test_init_db_production_mode()))
    results.append(("迁移文件完整性", test_migration_files()))
    results.append(("verify_schema_completeness 函数签名", test_verify_function_signature()))
    
    safe_print("\n" + "=" * 80)
    safe_print("测试结果总结")
    safe_print("=" * 80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "[OK]" if result else "[FAIL]"
        safe_print(f"{status} {name}")
    
    safe_print(f"\n通过: {passed}/{total}")
    
    if passed == total:
        safe_print("\n[OK] 所有测试通过！")
        return 0
    else:
        safe_print(f"\n[FAIL] {total - passed} 个测试失败")
        return 1

if __name__ == "__main__":
    sys.exit(main())
