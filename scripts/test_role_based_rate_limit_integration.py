#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于角色的限流集成测试脚本

⭐ v4.19.4 新增：验证 API 端点实际使用角色限流

测试内容：
1. 验证不同角色获得不同的限流配额
2. 验证匿名用户使用 anonymous 配额
3. 验证多角色用户使用最高优先级角色的配额
"""

import sys
import os
import asyncio
import time
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.middleware.rate_limiter import (
    get_user_rate_limit_tier,
    get_rate_limit_for_endpoint,
    RATE_LIMIT_TIERS,
    role_based_rate_limit
)
from modules.core.db import DimUser, DimRole


def print_header(text: str):
    """打印测试标题"""
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}")


def print_result(test_name: str, passed: bool, message: str = ""):
    """打印测试结果"""
    status = "[PASS]" if passed else "[FAIL]"
    print(f"{status} {test_name}")
    if message:
        print(f"      {message}")


def create_mock_user(username: str, roles: list = None, is_superuser: bool = False):
    """创建模拟用户对象"""
    user = type('MockUser', (), {
        'username': username,
        'is_superuser': is_superuser,
        'roles': roles or []
    })()
    return user


def create_mock_role(role_code: str, role_name: str = None):
    """创建模拟角色对象"""
    role = type('MockRole', (), {
        'role_code': role_code,
        'role_name': role_name or role_code
    })()
    return role


def test_role_mapping():
    """测试角色映射"""
    print_header("1. 角色映射测试")
    
    test_cases = [
        # (用户对象, 期望的限流等级, 描述)
        (create_mock_user("admin", [create_mock_role("admin")]), "admin", "admin 角色"),
        (create_mock_user("manager", [create_mock_role("manager")]), "manager", "manager 角色"),
        (create_mock_user("finance", [create_mock_role("finance")]), "finance", "finance 角色"),
        (create_mock_user("operator", [create_mock_role("operator")]), "operator", "operator 角色"),
        (create_mock_user("normal"), "normal", "无角色用户"),
        (None, "anonymous", "匿名用户"),
        (create_mock_user("superuser", is_superuser=True), "admin", "is_superuser 标志"),
        (create_mock_user("admin_user"), "normal", "用户名包含 admin 但无角色"),
        (create_mock_user("admin", [create_mock_role("admin", "管理员")]), "admin", "中文角色名"),
    ]
    
    passed = 0
    failed = 0
    
    for user, expected, description in test_cases:
        try:
            result = get_user_rate_limit_tier(user)
            if result == expected:
                print_result(f"角色映射: {description}", True, f"期望: {expected}, 实际: {result}")
                passed += 1
            else:
                print_result(f"角色映射: {description}", False, f"期望: {expected}, 实际: {result}")
                failed += 1
        except Exception as e:
            print_result(f"角色映射: {description}", False, f"异常: {e}")
            failed += 1
    
    print(f"\n总计: {passed} 通过, {failed} 失败")
    return failed == 0


def test_rate_limit_quota():
    """测试限流配额"""
    print_header("2. 限流配额测试")
    
    test_cases = [
        # (用户对象, 端点类型, 期望的限流值)
        (create_mock_user("admin", [create_mock_role("admin")]), "default", "200/minute"),
        (create_mock_user("admin", [create_mock_role("admin")]), "data_sync", "100/minute"),
        (create_mock_user("admin", [create_mock_role("admin")]), "auth", "20/minute"),
        (create_mock_user("manager", [create_mock_role("manager")]), "default", "150/minute"),
        (create_mock_user("finance", [create_mock_role("finance")]), "default", "120/minute"),
        (create_mock_user("operator", [create_mock_role("operator")]), "default", "100/minute"),
        (create_mock_user("normal"), "default", "60/minute"),
        (None, "default", "30/minute"),  # anonymous
        (None, "auth", "3/minute"),  # anonymous auth
    ]
    
    passed = 0
    failed = 0
    
    for user, endpoint_type, expected in test_cases:
        try:
            result = get_rate_limit_for_endpoint(user, endpoint_type)
            if result == expected:
                print_result(
                    f"配额验证: {get_user_rate_limit_tier(user)}/{endpoint_type}",
                    True,
                    f"期望: {expected}, 实际: {result}"
                )
                passed += 1
            else:
                print_result(
                    f"配额验证: {get_user_rate_limit_tier(user)}/{endpoint_type}",
                    False,
                    f"期望: {expected}, 实际: {result}"
                )
                failed += 1
        except Exception as e:
            print_result(
                f"配额验证: {get_user_rate_limit_tier(user)}/{endpoint_type}",
                False,
                f"异常: {e}"
            )
            failed += 1
    
    print(f"\n总计: {passed} 通过, {failed} 失败")
    return failed == 0


def test_multi_role_priority():
    """测试多角色优先级"""
    print_header("3. 多角色优先级测试")
    
    test_cases = [
        # (用户对象, 期望的限流等级, 描述)
        (
            create_mock_user("user1", [
                create_mock_role("admin"),
                create_mock_role("operator")
            ]),
            "admin",
            "admin + operator (应使用 admin)"
        ),
        (
            create_mock_user("user2", [
                create_mock_role("manager"),
                create_mock_role("operator")
            ]),
            "manager",
            "manager + operator (应使用 manager)"
        ),
        (
            create_mock_user("user3", [
                create_mock_role("finance"),
                create_mock_role("operator")
            ]),
            "finance",
            "finance + operator (应使用 finance)"
        ),
    ]
    
    passed = 0
    failed = 0
    
    for user, expected, description in test_cases:
        try:
            result = get_user_rate_limit_tier(user)
            if result == expected:
                print_result(f"多角色优先级: {description}", True, f"期望: {expected}, 实际: {result}")
                passed += 1
            else:
                print_result(f"多角色优先级: {description}", False, f"期望: {expected}, 实际: {result}")
                failed += 1
        except Exception as e:
            print_result(f"多角色优先级: {description}", False, f"异常: {e}")
            failed += 1
    
    print(f"\n总计: {passed} 通过, {failed} 失败")
    return failed == 0


def test_edge_cases():
    """测试边界情况"""
    print_header("4. 边界情况测试")
    
    test_cases = [
        # (用户对象, 期望的限流等级, 描述)
        (create_mock_user("user1", [create_mock_role("", "")]), "normal", "空字符串 role_code"),
        (create_mock_user("user2", [{"role_code": "admin", "role_name": "管理员"}]), "admin", "字典格式角色"),
        (create_mock_user("user3", [create_mock_role("ADMIN")]), "admin", "大写 role_code"),
        (create_mock_user("user4", [create_mock_role("manager", "主管")]), "manager", "中文 role_name"),
    ]
    
    passed = 0
    failed = 0
    
    for user, expected, description in test_cases:
        try:
            result = get_user_rate_limit_tier(user)
            if result == expected:
                print_result(f"边界情况: {description}", True, f"期望: {expected}, 实际: {result}")
                passed += 1
            else:
                print_result(f"边界情况: {description}", False, f"期望: {expected}, 实际: {result}")
                failed += 1
        except Exception as e:
            print_result(f"边界情况: {description}", False, f"异常: {e}")
            failed += 1
    
    print(f"\n总计: {passed} 通过, {failed} 失败")
    return failed == 0


def test_config_completeness():
    """测试配置完整性"""
    print_header("5. 配置完整性测试")
    
    roles = ["admin", "manager", "finance", "operator", "normal", "anonymous"]
    endpoint_types = ["default", "data_sync", "auth"]
    
    passed = 0
    failed = 0
    
    for role in roles:
        if role not in RATE_LIMIT_TIERS:
            print_result(f"配置完整性: {role} 角色缺失", False)
            failed += 1
            continue
        
        for endpoint_type in endpoint_types:
            if endpoint_type not in RATE_LIMIT_TIERS[role]:
                print_result(
                    f"配置完整性: {role}/{endpoint_type} 配置缺失",
                    False
                )
                failed += 1
            else:
                limit_value = RATE_LIMIT_TIERS[role][endpoint_type]
                print_result(
                    f"配置完整性: {role}/{endpoint_type}",
                    True,
                    f"限流值: {limit_value}"
                )
                passed += 1
    
    print(f"\n总计: {passed} 通过, {failed} 失败")
    return failed == 0


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("  基于角色的限流集成测试")
    print("=" * 60)
    
    results = []
    
    # 运行所有测试
    results.append(("角色映射测试", test_role_mapping()))
    results.append(("限流配额测试", test_rate_limit_quota()))
    results.append(("多角色优先级测试", test_multi_role_priority()))
    results.append(("边界情况测试", test_edge_cases()))
    results.append(("配置完整性测试", test_config_completeness()))
    
    # 汇总结果
    print_header("测试结果汇总")
    total_passed = sum(1 for _, passed in results if passed)
    total_failed = sum(1 for _, passed in results if not passed)
    
    for test_name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {test_name}")
    
    print(f"\n总计: {total_passed} 通过, {total_failed} 失败")
    
    if total_failed == 0:
        print("\n[OK] 所有测试通过！")
        return 0
    else:
        print("\n[FAIL] 部分测试失败，请检查实现")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

