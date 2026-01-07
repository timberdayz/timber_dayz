"""
测试账号能力过滤功能（Phase 2.5.1）

验证TaskService.filter_domains_by_account_capability方法
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.task_service import TaskService


def test_filter_with_all_capabilities():
    """测试：账号支持所有数据域"""
    account = {
        "account_id": "test_001",
        "capabilities": {
            "orders": True,
            "products": True,
            "services": True,
            "analytics": True,
            "finance": True,
            "inventory": True
        }
    }
    
    requested = ["orders", "products", "services"]
    service = TaskService(None)  # 不需要db
    
    supported, unsupported = service.filter_domains_by_account_capability(account, requested)
    
    assert supported == ["orders", "products", "services"]
    assert unsupported == []
    print("[OK] test_filter_with_all_capabilities")


def test_filter_with_partial_capabilities():
    """测试：账号部分支持数据域"""
    account = {
        "account_id": "global_001",
        "capabilities": {
            "orders": True,
            "products": True,
            "services": False,  # 全球账号不支持services
            "analytics": True,
            "finance": True,
            "inventory": True
        }
    }
    
    requested = ["orders", "services", "products"]
    service = TaskService(None)
    
    supported, unsupported = service.filter_domains_by_account_capability(account, requested)
    
    assert supported == ["orders", "products"]
    assert unsupported == ["services"]
    print("[OK] test_filter_with_partial_capabilities")


def test_filter_with_no_capabilities():
    """测试：账号没有配置capabilities（默认全部支持）"""
    account = {
        "account_id": "legacy_001",
        # 没有capabilities字段
    }
    
    requested = ["orders", "products", "services"]
    service = TaskService(None)
    
    supported, unsupported = service.filter_domains_by_account_capability(account, requested)
    
    assert supported == ["orders", "products", "services"]
    assert unsupported == []
    print("[OK] test_filter_with_no_capabilities")


def test_filter_with_empty_capabilities():
    """测试：账号capabilities为空字典（默认全部支持）"""
    account = {
        "account_id": "empty_001",
        "capabilities": {}
    }
    
    requested = ["orders", "products"]
    service = TaskService(None)
    
    supported, unsupported = service.filter_domains_by_account_capability(account, requested)
    
    assert supported == ["orders", "products"]
    assert unsupported == []
    print("[OK] test_filter_with_empty_capabilities")


def test_filter_with_unknown_domain():
    """测试：请求未知数据域（默认支持）"""
    account = {
        "account_id": "test_002",
        "capabilities": {
            "orders": True,
            "products": False
        }
    }
    
    requested = ["orders", "products", "unknown_domain"]
    service = TaskService(None)
    
    supported, unsupported = service.filter_domains_by_account_capability(account, requested)
    
    # unknown_domain不在capabilities中，默认为True
    assert supported == ["orders", "unknown_domain"]
    assert unsupported == ["products"]
    print("[OK] test_filter_with_unknown_domain")


def test_filter_all_unsupported():
    """测试：所有请求的数据域都不支持"""
    account = {
        "account_id": "limited_001",
        "capabilities": {
            "orders": False,
            "products": False,
            "services": False
        }
    }
    
    requested = ["orders", "products", "services"]
    service = TaskService(None)
    
    supported, unsupported = service.filter_domains_by_account_capability(account, requested)
    
    assert supported == []
    assert unsupported == ["orders", "products", "services"]
    print("[OK] test_filter_all_unsupported")


if __name__ == "__main__":
    print("=" * 60)
    print("Testing Account Capability Filter (Phase 2.5.1)")
    print("=" * 60)
    print()
    
    try:
        test_filter_with_all_capabilities()
        test_filter_with_partial_capabilities()
        test_filter_with_no_capabilities()
        test_filter_with_empty_capabilities()
        test_filter_with_unknown_domain()
        test_filter_all_unsupported()
        
        print()
        print("=" * 60)
        print("[SUCCESS] All 6 tests passed!")
        print("=" * 60)
        
    except AssertionError as e:
        print()
        print("=" * 60)
        print(f"[FAILED] Test failed: {e}")
        print("=" * 60)
        sys.exit(1)
    except Exception as e:
        print()
        print("=" * 60)
        print(f"[ERROR] Unexpected error: {e}")
        print("=" * 60)
        sys.exit(1)

