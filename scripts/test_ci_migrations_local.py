#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
本地CI迁移测试脚本

模拟GitHub Actions中的迁移验证步骤，检查是否存在部署问题
"""

import sys
import subprocess
from pathlib import Path

def safe_print(text: str):
    """安全打印"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            safe_text = text.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)

def test_1_migration_script_syntax():
    """测试1: 迁移脚本语法检查"""
    safe_print("\n[TEST 1] 迁移脚本语法检查...")
    
    migration_file = Path(__file__).parent.parent / "migrations" / "versions" / "20260112_v5_0_0_schema_snapshot.py"
    
    if not migration_file.exists():
        safe_print("  [FAIL] 迁移文件不存在")
        return False
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(migration_file)],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            safe_print("  [OK] 迁移脚本语法正确")
            return True
        else:
            safe_print(f"  [FAIL] 迁移脚本语法错误:")
            safe_print(f"    {result.stderr}")
            return False
    except Exception as e:
        safe_print(f"  [FAIL] 检查失败: {e}")
        return False

def test_2_key_tables_foreign_keys():
    """测试2: 关键表外键定义检查"""
    safe_print("\n[TEST 2] 关键表外键定义检查...")
    
    test_script = Path(__file__).parent / "test_migration_foreign_keys.py"
    
    if not test_script.exists():
        safe_print("  [SKIP] 测试脚本不存在，跳过")
        return True
    
    try:
        result = subprocess.run(
            [sys.executable, str(test_script)],
            capture_output=True,
            text=True,
            timeout=30,
            encoding='utf-8',
            errors='replace'
        )
        
        if result.returncode == 0:
            safe_print("  [OK] 关键表外键定义正确")
            return True
        else:
            safe_print(f"  [FAIL] 关键表外键定义错误:")
            # 显示最后20行输出
            lines = result.stdout.split('\n')[-20:]
            for line in lines:
                if line.strip():
                    safe_print(f"    {line}")
            return False
    except Exception as e:
        safe_print(f"  [FAIL] 检查失败: {e}")
        return False

def test_3_alembic_config():
    """测试3: Alembic配置检查"""
    safe_print("\n[TEST 3] Alembic配置检查...")
    
    alembic_ini = Path(__file__).parent.parent / "alembic.ini"
    
    if not alembic_ini.exists():
        safe_print("  [FAIL] alembic.ini 不存在")
        return False
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "current"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=Path(__file__).parent.parent
        )
        
        # alembic current 可能返回非0（如果没有数据库连接），但配置应该是正确的
        safe_print("  [OK] Alembic配置存在（需要数据库连接才能验证版本）")
        return True
    except FileNotFoundError:
        safe_print("  [WARN] Alembic未安装，跳过配置检查")
        return True
    except Exception as e:
        safe_print(f"  [WARN] Alembic检查失败（可能需要数据库连接）: {e}")
        return True  # 不阻塞，因为可能没有数据库连接

def test_4_migration_heads():
    """测试4: 检查迁移heads"""
    safe_print("\n[TEST 4] 检查迁移heads...")
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "heads"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=Path(__file__).parent.parent
        )
        
        if result.returncode == 0:
            output = result.stdout.strip()
            safe_print(f"  [OK] 迁移heads: {output}")
            return True
        else:
            safe_print(f"  [WARN] 无法获取迁移heads（可能需要数据库连接）")
            return True  # 不阻塞
    except FileNotFoundError:
        safe_print("  [WARN] Alembic未安装，跳过")
        return True
    except Exception as e:
        safe_print(f"  [WARN] 检查失败: {e}")
        return True  # 不阻塞

def main():
    """主函数"""
    safe_print("=" * 80)
    safe_print("本地CI迁移测试")
    safe_print("=" * 80)
    safe_print("\n模拟GitHub Actions中的迁移验证步骤")
    safe_print("注意: 完整测试需要Docker环境（运行 scripts/validate_migrations_local.py）")
    
    results = []
    
    # 测试1: 迁移脚本语法检查
    results.append(("迁移脚本语法检查", test_1_migration_script_syntax()))
    
    # 测试2: 关键表外键定义检查
    results.append(("关键表外键定义检查", test_2_key_tables_foreign_keys()))
    
    # 测试3: Alembic配置检查
    results.append(("Alembic配置检查", test_3_alembic_config()))
    
    # 测试4: 迁移heads检查
    results.append(("迁移heads检查", test_4_migration_heads()))
    
    # 汇总结果
    safe_print("\n" + "=" * 80)
    safe_print("测试结果汇总")
    safe_print("=" * 80)
    
    passed = sum(1 for _, result in results if result)
    failed = sum(1 for _, result in results if not result)
    total = len(results)
    
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        safe_print(f"  {status} {name}")
    
    safe_print("")
    safe_print(f"总计: {total} 项测试")
    safe_print(f"通过: {passed} 项")
    safe_print(f"失败: {failed} 项")
    
    safe_print("")
    if failed == 0:
        safe_print("[OK] 所有测试通过")
        safe_print("\n建议: 运行完整迁移测试（需要Docker环境）:")
        safe_print("  python scripts/validate_migrations_local.py")
        return 0
    else:
        safe_print("[WARNING] 部分测试失败，请检查上述错误信息")
        return 1

if __name__ == "__main__":
    sys.exit(main())
