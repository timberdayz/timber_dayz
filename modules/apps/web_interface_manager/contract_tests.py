#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Web界面管理应用契约测试

验证应用的基本契约：
- 能被注册器发现
- 能正常注册
- 健康检查通过
- 基本接口可用
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from modules.core import get_registry
from modules.core.logger import get_logger

logger = get_logger(__name__)


def test_contract_discovery():
    """测试应用能被发现"""
    registry = get_registry()
    
    # 清空现有注册
    registry._applications.clear()
    registry._instances.clear()
    registry._metadata.clear()
    
    # 重新发现
    count = registry.discover_applications()
    
    assert count > 0, "应该能发现至少一个应用"
    assert "web_interface_manager" in registry.list_applications(), "应该能发现 web_interface_manager"
    
    logger.info("[OK] 应用发现测试通过")


def test_contract_registration():
    """测试应用能正常注册"""
    registry = get_registry()
    
    # 确保应用已注册
    if "web_interface_manager" not in registry.list_applications():
        registry.discover_applications()
    
    # 检查元数据
    info = registry.get_application_info("web_interface_manager")
    assert info is not None, "应该能获取应用信息"
    assert info.get("name") == "Web界面管理", "应用名称应该正确"
    assert info.get("version") == "1.0.0", "应用版本应该正确"
    assert "description" in info, "应该有描述信息"
    
    logger.info("[OK] 应用注册测试通过")


def test_contract_health_check():
    """测试健康检查通过"""
    registry = get_registry()
    
    # 获取应用实例
    app = registry.get_application("web_interface_manager")
    assert app is not None, "应该能获取应用实例"
    
    # 执行健康检查
    is_healthy = app.health_check()
    assert is_healthy, "健康检查应该通过"
    
    logger.info("[OK] 健康检查测试通过")


def test_contract_basic_interface():
    """测试基本接口可用"""
    registry = get_registry()
    
    # 获取应用实例
    app = registry.get_application("web_interface_manager")
    assert app is not None, "应该能获取应用实例"
    
    # 测试基本接口
    info = app.get_info()
    assert isinstance(info, dict), "get_info() 应该返回字典"
    assert "name" in info, "应该包含 name 字段"
    assert "version" in info, "应该包含 version 字段"
    
    # 测试运行状态
    assert not app.is_running(), "初始状态应该是未运行"
    
    logger.info("[OK] 基本接口测试通过")


def run_all_contract_tests():
    """运行所有契约测试"""
    print("[SEARCH] 开始Web界面管理应用契约测试...")
    
    try:
        test_contract_discovery()
        test_contract_registration()
        test_contract_health_check()
        test_contract_basic_interface()
        
        print("[OK] 所有契约测试通过")
        return True
        
    except Exception as e:
        print(f"[FAIL] 契约测试失败: {e}")
        logger.error(f"契约测试失败: {e}")
        return False


if __name__ == "__main__":
    success = run_all_contract_tests()
    sys.exit(0 if success else 1)
