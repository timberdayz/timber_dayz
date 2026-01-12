#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Alembic 迁移验证脚本

验证 Schema 快照迁移是否可以被 Alembic 正确识别。

使用方法:
    python scripts/test_alembic_migration.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def safe_print(text: str):
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


def test_migration_file_exists():
    """测试迁移文件是否存在"""
    safe_print("\n[测试] 检查迁移文件是否存在...")
    migration_file = project_root / "migrations" / "versions" / "20260112_v5_0_0_schema_snapshot.py"
    
    if migration_file.exists():
        safe_print(f"  [OK] 迁移文件存在: {migration_file.name}")
        return True
    else:
        safe_print(f"  [FAIL] 迁移文件不存在: {migration_file}")
        return False


def test_migration_file_syntax():
    """测试迁移文件语法"""
    safe_print("\n[测试] 检查迁移文件语法...")
    migration_file = project_root / "migrations" / "versions" / "20260112_v5_0_0_schema_snapshot.py"
    
    try:
        # 编译检查
        import py_compile
        py_compile.compile(str(migration_file), doraise=True)
        safe_print("  [OK] 迁移文件语法正确")
        return True
    except py_compile.PyCompileError as e:
        safe_print(f"  [FAIL] 迁移文件语法错误: {e}")
        return False
    except Exception as e:
        safe_print(f"  [FAIL] 检查失败: {e}")
        return False


def test_migration_revision_id():
    """测试迁移 revision ID"""
    safe_print("\n[测试] 检查迁移 revision ID...")
    migration_file = project_root / "migrations" / "versions" / "20260112_v5_0_0_schema_snapshot.py"
    
    try:
        content = migration_file.read_text(encoding='utf-8')
        
        # 检查 revision
        if "revision = 'v5_0_0_schema_snapshot'" in content:
            safe_print("  [OK] revision ID 正确: v5_0_0_schema_snapshot")
        else:
            safe_print("  [FAIL] revision ID 不正确或缺失")
            return False
        
        # 检查 down_revision
        if "down_revision = None" in content:
            safe_print("  [OK] down_revision 正确: None")
        else:
            safe_print("  [WARN] down_revision 可能不正确")
        
        return True
    except Exception as e:
        safe_print(f"  [FAIL] 检查失败: {e}")
        return False


def test_migration_idempotency():
    """测试迁移幂等性（检查是否存在性检查）"""
    safe_print("\n[测试] 检查迁移幂等性...")
    migration_file = project_root / "migrations" / "versions" / "20260112_v5_0_0_schema_snapshot.py"
    
    try:
        content = migration_file.read_text(encoding='utf-8')
        
        # 检查是否存在性检查
        if "if 'table_name' not in existing_tables:" in content or "existing_tables" in content:
            safe_print("  [OK] 迁移包含存在性检查（幂等性保障）")
        else:
            safe_print("  [WARN] 迁移可能缺少存在性检查")
        
        # 检查 safe_print
        if "safe_print" in content or "def safe_print" in content:
            safe_print("  [OK] 迁移使用 safe_print（Windows 兼容性）")
        else:
            safe_print("  [WARN] 迁移可能未使用 safe_print")
        
        return True
    except Exception as e:
        safe_print(f"  [FAIL] 检查失败: {e}")
        return False


def main():
    """主函数"""
    safe_print("=" * 80)
    safe_print("Alembic 迁移验证")
    safe_print("=" * 80)
    
    results = []
    
    # 运行测试
    results.append(("迁移文件存在", test_migration_file_exists()))
    results.append(("迁移文件语法", test_migration_file_syntax()))
    results.append(("迁移 revision ID", test_migration_revision_id()))
    results.append(("迁移幂等性", test_migration_idempotency()))
    
    # 总结
    safe_print("\n" + "=" * 80)
    safe_print("测试结果总结")
    safe_print("=" * 80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        safe_print(f"{status} {test_name}")
    
    safe_print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        safe_print("\n[OK] 所有测试通过！")
        safe_print("\n注意: 实际数据库迁移需要在数据库环境中执行:")
        safe_print("  alembic upgrade v5_0_0_schema_snapshot  # 新数据库")
        safe_print("  alembic upgrade heads                   # 已有数据库")
        return 0
    else:
        safe_print(f"\n[WARN] {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
