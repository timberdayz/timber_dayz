#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
角色限流配置测试脚本

测试内容：
1. 角色映射测试：验证各角色正确映射到限流等级
2. 配额验证测试：验证各角色使用正确的限流配额
3. 降级测试：验证未匹配到角色的用户使用 normal 配额
4. 匿名用户测试：验证未认证用户使用 anonymous 配额
5. 多角色优先级测试：验证多角色用户选择最高优先级
6. 降级机制测试：验证 is_superuser 和 username 降级机制

v4.19.3 新增：修复角色映射漏洞后的验证测试
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.middleware.rate_limiter import (
    get_user_rate_limit_tier,
    get_rate_limit_for_endpoint,
    RATE_LIMIT_TIERS
)


class MockRole:
    """模拟角色对象"""
    def __init__(self, role_code=None, role_name=None):
        self.role_code = role_code
        self.role_name = role_name


class MockUser:
    """模拟用户对象"""
    def __init__(self, username=None, is_superuser=False, roles=None):
        self.username = username
        self.is_superuser = is_superuser
        self.roles = roles or []


def test_role_mapping():
    """测试角色映射"""
    print("\n" + "="*60)
    print("测试 1: 角色映射测试")
    print("="*60)
    
    test_cases = [
        # (用户对象, 期望的限流等级, 描述)
        (MockUser(roles=[MockRole(role_code="admin", role_name="管理员")]), "admin", "admin 角色（role_code）"),
        (MockUser(roles=[MockRole(role_code="manager", role_name="主管")]), "manager", "manager 角色（role_code）"),
        (MockUser(roles=[MockRole(role_code="finance", role_name="财务")]), "finance", "finance 角色（role_code）"),
        (MockUser(roles=[MockRole(role_code="operator", role_name="操作员")]), "operator", "operator 角色（role_code）"),
        (MockUser(roles=[MockRole(role_name="管理员")]), "admin", "admin 角色（仅 role_name）"),
        (MockUser(roles=[MockRole(role_name="主管")]), "manager", "manager 角色（仅 role_name）"),
        (MockUser(roles=[MockRole(role_name="财务")]), "finance", "finance 角色（仅 role_name）"),
        (MockUser(roles=[MockRole(role_name="操作员")]), "operator", "operator 角色（仅 role_name）"),
        (MockUser(roles=[MockRole(role_name="Administrator")]), "admin", "Administrator 角色（英文）"),
        (MockUser(roles=[MockRole(role_name="Supervisor")]), "manager", "Supervisor 角色（英文）"),
    ]
    
    passed = 0
    failed = 0
    
    for user, expected, description in test_cases:
        result = get_user_rate_limit_tier(user)
        if result == expected:
            print(f"  [PASS] {description}: {result}")
            passed += 1
        else:
            print(f"  [FAIL] {description}: 期望 {expected}, 实际 {result}")
            failed += 1
    
    print(f"\n  结果: {passed} 通过, {failed} 失败")
    return failed == 0


def test_quota_verification():
    """测试配额验证"""
    print("\n" + "="*60)
    print("测试 2: 配额验证测试")
    print("="*60)
    
    test_cases = [
        # (用户对象, 端点类型, 期望的限流值)
        (MockUser(roles=[MockRole(role_code="admin")]), "default", "200/minute"),
        (MockUser(roles=[MockRole(role_code="admin")]), "data_sync", "100/minute"),
        (MockUser(roles=[MockRole(role_code="admin")]), "auth", "20/minute"),
        (MockUser(roles=[MockRole(role_code="manager")]), "default", "150/minute"),
        (MockUser(roles=[MockRole(role_code="manager")]), "data_sync", "80/minute"),
        (MockUser(roles=[MockRole(role_code="manager")]), "auth", "15/minute"),
        (MockUser(roles=[MockRole(role_code="finance")]), "default", "120/minute"),
        (MockUser(roles=[MockRole(role_code="finance")]), "data_sync", "30/minute"),
        (MockUser(roles=[MockRole(role_code="finance")]), "auth", "10/minute"),
        (MockUser(roles=[MockRole(role_code="operator")]), "default", "100/minute"),
        (MockUser(roles=[MockRole(role_code="operator")]), "data_sync", "50/minute"),
        (MockUser(roles=[MockRole(role_code="operator")]), "auth", "10/minute"),
    ]
    
    passed = 0
    failed = 0
    
    for user, endpoint_type, expected in test_cases:
        result = get_rate_limit_for_endpoint(user, endpoint_type)
        if result == expected:
            print(f"  [PASS] {get_user_rate_limit_tier(user)}/{endpoint_type}: {result}")
            passed += 1
        else:
            print(f"  [FAIL] {get_user_rate_limit_tier(user)}/{endpoint_type}: 期望 {expected}, 实际 {result}")
            failed += 1
    
    print(f"\n  结果: {passed} 通过, {failed} 失败")
    return failed == 0


def test_fallback_mechanism():
    """测试降级机制"""
    print("\n" + "="*60)
    print("测试 3: 降级机制测试")
    print("="*60)
    
    test_cases = [
        # (用户对象, 期望的限流等级, 描述)
        (None, "anonymous", "匿名用户"),
        (MockUser(), "normal", "无角色用户"),
        (MockUser(username="admin"), "admin", "admin 用户名（无角色）"),
        (MockUser(is_superuser=True), "admin", "is_superuser=True（无角色）"),
        (MockUser(username="test", roles=[MockRole(role_code="unknown")]), "normal", "未知角色"),
    ]
    
    passed = 0
    failed = 0
    
    for user, expected, description in test_cases:
        result = get_user_rate_limit_tier(user)
        if result == expected:
            print(f"  [PASS] {description}: {result}")
            passed += 1
        else:
            print(f"  [FAIL] {description}: 期望 {expected}, 实际 {result}")
            failed += 1
    
    print(f"\n  结果: {passed} 通过, {failed} 失败")
    return failed == 0


def test_multiple_roles_priority():
    """测试多角色优先级"""
    print("\n" + "="*60)
    print("测试 4: 多角色优先级测试")
    print("="*60)
    
    test_cases = [
        # (用户对象, 期望的限流等级, 描述)
        (MockUser(roles=[
            MockRole(role_code="operator"),
            MockRole(role_code="admin")
        ]), "admin", "admin + operator（应选择 admin）"),
        (MockUser(roles=[
            MockRole(role_code="operator"),
            MockRole(role_code="manager")
        ]), "manager", "manager + operator（应选择 manager）"),
        (MockUser(roles=[
            MockRole(role_code="finance"),
            MockRole(role_code="operator")
        ]), "finance", "finance + operator（应选择 finance）"),
    ]
    
    passed = 0
    failed = 0
    
    for user, expected, description in test_cases:
        result = get_user_rate_limit_tier(user)
        if result == expected:
            print(f"  [PASS] {description}: {result}")
            passed += 1
        else:
            print(f"  [FAIL] {description}: 期望 {expected}, 实际 {result}")
            failed += 1
    
    print(f"\n  结果: {passed} 通过, {failed} 失败")
    return failed == 0


def test_configuration_completeness():
    """测试配置完整性"""
    print("\n" + "="*60)
    print("测试 5: 配置完整性测试")
    print("="*60)
    
    required_roles = ["admin", "manager", "finance", "operator", "normal", "anonymous"]
    required_endpoints = ["default", "data_sync", "auth"]
    
    passed = 0
    failed = 0
    
    # 检查所有必需角色是否存在
    for role in required_roles:
        if role in RATE_LIMIT_TIERS:
            print(f"  [PASS] 角色 {role} 存在于配置中")
            passed += 1
        else:
            print(f"  [FAIL] 角色 {role} 不存在于配置中")
            failed += 1
    
    # 检查所有角色的端点配置是否完整
    for role in required_roles:
        if role in RATE_LIMIT_TIERS:
            for endpoint in required_endpoints:
                if endpoint in RATE_LIMIT_TIERS[role]:
                    print(f"  [PASS] {role}/{endpoint} 配置存在")
                    passed += 1
                else:
                    print(f"  [FAIL] {role}/{endpoint} 配置不存在")
                    failed += 1
    
    # 检查 premium 角色是否已移除
    if "premium" not in RATE_LIMIT_TIERS:
        print(f"  [PASS] premium 角色已移除（正确）")
        passed += 1
    else:
        print(f"  [FAIL] premium 角色仍然存在（应移除）")
        failed += 1
    
    print(f"\n  结果: {passed} 通过, {failed} 失败")
    return failed == 0


def main():
    """主测试函数"""
    print("\n" + "="*60)
    print("角色限流配置测试")
    print("="*60)
    print("v4.19.3 修复验证测试")
    
    results = []
    
    # 运行所有测试
    results.append(("角色映射测试", test_role_mapping()))
    results.append(("配额验证测试", test_quota_verification()))
    results.append(("降级机制测试", test_fallback_mechanism()))
    results.append(("多角色优先级测试", test_multiple_roles_priority()))
    results.append(("配置完整性测试", test_configuration_completeness()))
    
    # 汇总结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    
    total_passed = sum(1 for _, result in results if result)
    total_failed = sum(1 for _, result in results if not result)
    
    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {test_name}")
    
    print(f"\n总计: {total_passed} 通过, {total_failed} 失败")
    
    if total_failed == 0:
        print("\n[OK] 所有测试通过！")
        return 0
    else:
        print("\n[ERROR] 部分测试失败，请检查修复")
        return 1


if __name__ == "__main__":
    sys.exit(main())

