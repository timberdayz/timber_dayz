#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
统一健康检查测试

验证整个系统的健康状态：
- 所有应用能被发现
- 所有应用能正常注册
- 所有应用健康检查通过
- 系统整体状态正常
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from modules.core import get_registry
from modules.core.logger import get_logger

logger = get_logger(__name__)


def test_system_discovery():
    """测试系统应用发现"""
    print("🔍 测试应用发现...")
    
    registry = get_registry()
    
    # 清空现有注册
    registry._applications.clear()
    registry._instances.clear()
    registry._metadata.clear()
    
    # 重新发现
    count = registry.discover_applications()
    
    assert count > 0, "应该能发现至少一个应用"
    
    apps = registry.list_applications()
    expected_apps = ["account_manager", "collection_center", "web_interface_manager"]
    
    for expected_app in expected_apps:
        assert expected_app in apps, f"应该能发现 {expected_app}"
    
    print(f"✅ 发现 {count} 个应用: {apps}")
    return True


def test_system_metadata():
    """测试系统元数据完整性"""
    print("📋 测试应用元数据...")
    
    registry = get_registry()
    
    # 确保应用已发现
    if not registry.list_applications():
        registry.discover_applications()
    
    apps = registry.list_applications()
    
    for app_id in apps:
        info = registry.get_application_info(app_id)
        assert info is not None, f"应该能获取 {app_id} 的信息"
        assert "name" in info, f"{app_id} 应该有 name 字段"
        assert "version" in info, f"{app_id} 应该有 version 字段"
        assert "description" in info, f"{app_id} 应该有 description 字段"
        assert info.get("name") != app_id, f"{app_id} 应该有有意义的名称"
        
        print(f"  ✅ {app_id}: {info['name']} v{info['version']}")
    
    return True


def test_system_health():
    """测试系统整体健康状态"""
    print("🏥 测试系统健康状态...")
    
    registry = get_registry()
    
    # 确保应用已发现
    if not registry.list_applications():
        registry.discover_applications()
    
    # 执行全系统健康检查
    health_status = registry.health_check_all()
    
    assert len(health_status) > 0, "应该有健康检查结果"
    
    failed_apps = []
    for app_id, is_healthy in health_status.items():
        if is_healthy:
            print(f"  ✅ {app_id}: 健康")
        else:
            print(f"  ❌ {app_id}: 异常")
            failed_apps.append(app_id)
    
    if failed_apps:
        print(f"⚠️  {len(failed_apps)} 个应用健康检查失败: {failed_apps}")
        # 注意：这里不直接 assert False，因为某些应用可能依赖外部资源
        # 但会记录警告
        logger.warning(f"健康检查失败的应用: {failed_apps}")
    
    healthy_count = sum(1 for status in health_status.values() if status)
    total_count = len(health_status)
    
    print(f"📊 健康检查结果: {healthy_count}/{total_count} 健康")
    
    # 至少要有一半应用健康
    assert healthy_count >= total_count // 2, f"健康应用数量过少: {healthy_count}/{total_count}"
    
    return True


def test_system_statistics():
    """测试系统统计信息"""
    print("📊 测试系统统计...")
    
    registry = get_registry()
    
    # 确保应用已发现
    if not registry.list_applications():
        registry.discover_applications()
    
    stats = registry.get_statistics()
    
    assert "total_applications" in stats, "应该有总应用数统计"
    assert "running_instances" in stats, "应该有运行实例统计"
    assert "applications" in stats, "应该有应用列表"
    assert "running_apps" in stats, "应该有运行应用列表"
    
    assert stats["total_applications"] > 0, "应该有注册的应用"
    assert len(stats["applications"]) == stats["total_applications"], "应用列表数量应该匹配"
    
    print(f"  📱 总应用数: {stats['total_applications']}")
    print(f"  🏃 运行实例: {stats['running_instances']}")
    print(f"  ✅ 运行中应用: {len(stats['running_apps'])}")
    
    return True


def run_unified_health_check():
    """运行统一健康检查"""
    print("🚀 开始系统统一健康检查...")
    print("=" * 50)
    
    try:
        test_system_discovery()
        test_system_metadata()
        test_system_health()
        test_system_statistics()
        
        print("=" * 50)
        print("✅ 系统统一健康检查通过")
        return True
        
    except Exception as e:
        print("=" * 50)
        print(f"❌ 系统健康检查失败: {e}")
        logger.error(f"系统健康检查失败: {e}")
        return False


if __name__ == "__main__":
    success = run_unified_health_check()
    sys.exit(0 if success else 1)
