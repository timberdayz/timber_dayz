#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运行所有用户注册和审批流程测试

包括：
1. 安全测试
2. 单元测试
3. 集成测试
"""

import sys
import subprocess
from pathlib import Path

# 添加项目根目录到 Python 路径
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

def run_test(test_file: str, test_name: str) -> bool:
    """运行单个测试文件"""
    print("\n" + "=" * 70)
    print(f"  运行 {test_name}")
    print("=" * 70)
    
    try:
        result = subprocess.run(
            [sys.executable, test_file],
            cwd=str(root_dir),
            capture_output=False,
            timeout=300
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"[ERROR] {test_name} 执行超时")
        return False
    except Exception as e:
        print(f"[ERROR] {test_name} 执行失败: {e}")
        return False


def main():
    """主函数"""
    print("=" * 70)
    print("  用户注册和审批流程 - 完整测试套件")
    print("=" * 70)
    
    tests_dir = Path(__file__).parent
    
    # 测试文件列表
    test_files = [
        (tests_dir / "test_user_registration_security.py", "安全测试"),
        (tests_dir / "test_user_registration_unit.py", "单元测试"),
        (tests_dir / "test_user_registration_integration.py", "集成测试"),
    ]
    
    results = []
    
    for test_file, test_name in test_files:
        if test_file.exists():
            success = run_test(str(test_file), test_name)
            results.append((test_name, success))
        else:
            print(f"[WARN] 测试文件不存在: {test_file}")
            results.append((test_name, False))
    
    # 打印总结
    print("\n" + "=" * 70)
    print("  测试套件总结")
    print("=" * 70)
    
    for test_name, success in results:
        status = "[PASS]" if success else "[FAIL]"
        print(f"{status} {test_name}")
    
    total = len(results)
    passed = sum(1 for _, success in results if success)
    failed = total - passed
    
    print(f"\n总测试套件: {total}")
    print(f"通过: {passed}")
    print(f"失败: {failed}")
    print(f"通过率: {passed/total*100:.1f}%")
    print("=" * 70)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n[INFO] 测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] 测试执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

