#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据采集中心应用契约测试

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
    assert "collection_center" in registry.list_applications(), "应该能发现 collection_center"

    logger.info("✅ 应用发现测试通过")


def test_contract_registration():
    """测试应用能正常注册"""
    registry = get_registry()

    # 确保应用已注册
    if "collection_center" not in registry.list_applications():
        registry.discover_applications()

    # 检查元数据
    info = registry.get_application_info("collection_center")
    assert info is not None, "应该能获取应用信息"
    assert info.get("name") == "数据采集中心", "应用名称应该正确"
    assert info.get("version") == "1.0.0", "应用版本应该正确"
    assert "description" in info, "应该有描述信息"

    logger.info("✅ 应用注册测试通过")


def test_contract_health_check():
    """测试健康检查通过"""
    registry = get_registry()

    # 获取应用实例
    app = registry.get_application("collection_center")
    assert app is not None, "应该能获取应用实例"

    # 执行健康检查
    is_healthy = app.health_check()
    assert is_healthy, "健康检查应该通过"

    logger.info("✅ 健康检查测试通过")


def test_contract_basic_interface():
    """测试基本接口可用"""
    registry = get_registry()

    # 获取应用实例
    app = registry.get_application("collection_center")
    assert app is not None, "应该能获取应用实例"

    # 测试基本接口
    info = app.get_info()
    assert isinstance(info, dict), "get_info() 应该返回字典"
    assert "name" in info, "应该包含 name 字段"
    assert "version" in info, "应该包含 version 字段"

    # 测试运行状态
    assert not app.is_running(), "初始状态应该是未运行"

    logger.info("✅ 基本接口测试通过")


def test_new_architecture_modules():
    """测试新架构三模块集成"""
    try:
        # 测试三大模块是否可以导入
        from modules.utils.login_orchestrator import LoginOrchestrator
        from modules.utils.step_runner import StepRunner
        from modules.utils.data_processing_pipeline import DataProcessingPipeline

        logger.info("✅ 新架构模块导入测试通过")

        # 测试StepRunner基础功能
        class MockBrowser:
            pass

        browser = MockBrowser()
        step_runner = StepRunner(browser)

        # 测试模板创建
        templates = step_runner.create_all_platform_templates()
        assert len(templates) >= 3, "应该创建至少3个平台模板"

        logger.info("✅ 新架构模块功能测试通过")

    except Exception as e:
        logger.error(f"新架构模块测试失败: {e}")
        raise


def test_handlers_integration():
    """测试处理器集成"""
    try:
        from modules.apps.collection_center.handlers import DataCollectionHandler

        handler = DataCollectionHandler()

        # 测试账号加载
        accounts, source = handler._load_accounts_for_run()
        assert isinstance(accounts, list), "账号应该是列表"
        assert isinstance(source, str), "数据源应该是字符串"

        # 检查login_url配置
        accounts_with_login_url = sum(1 for acc in accounts if acc.get('login_url'))
        logger.info(f"配置login_url的账号: {accounts_with_login_url}/{len(accounts)}")

        logger.info("✅ 处理器集成测试通过")

    except Exception as e:
        logger.error(f"处理器集成测试失败: {e}")
        raise


def test_date_picker_api_contracts():
    """最小日期组件契约测试：
    - DateOption 包含 LAST_28_DAYS
    - TikTok DatePicker 提供选择快捷范围与自定义/周索引的方法
    （不做真实 UI 操作）
    """
    from modules.components.date_picker.base import DateOption
    from modules.platforms.tiktok.components.date_picker import TiktokDatePicker
    from modules.components.base import ExecutionContext

    assert hasattr(DateOption, "LAST_28_DAYS"), "DateOption 应包含 LAST_28_DAYS"

    # 仅校验方法存在性
    ctx = ExecutionContext(platform="tiktok", account={}, logger=None)
    dp = TiktokDatePicker(ctx)
    assert hasattr(dp, "run"), "TiktokDatePicker 需实现 run(page, option)"
    assert hasattr(dp, "select_custom_range"), "需提供 select_custom_range(page, start, end)"
    assert hasattr(dp, "select_week_index"), "需提供 select_week_index(page, y, m, idx)"




def test_time_policy_resolution_and_routing():
    """不依赖 UI 的策略路由契约：
    - rolling_days=7/28 解析为 quick 且能调用 dp.run
    - week_index、自定义区间分流至对应方法
    """
    from datetime import date
    from modules.services.time_policy import (
        RollingDaysPolicy, CustomRangePolicy, WeekInMonthPolicy,
        resolve_for_tiktok, apply_time_policy_tiktok,
    )

    class _MockDP:
        def __init__(self):
            self.called = []
        def run(self, page, option):
            self.called.append(("run", option.value))
            class R:
                success = True
                message = "ok"
            return R()
        def select_custom_range(self, page, s, e):
            self.called.append(("custom", (s, e)))
            return True
        def select_week_index(self, page, y, m, i):
            self.called.append(("week", (y, m, i)))
            return True

    class _MockAdapter:
        def __init__(self, dp): self._dp = dp
        def date_picker(self): return self._dp

    dp = _MockDP(); adapter = _MockAdapter(dp)

    # rolling 7
    mode, payload = resolve_for_tiktok(RollingDaysPolicy(7))
    assert mode == "quick" and payload["option"].value == "last_7_days"
    ok, _ = apply_time_policy_tiktok(None, adapter, RollingDaysPolicy(7))
    assert ok and dp.called[-1][0] == "run"

    # rolling 28
    ok, _ = apply_time_policy_tiktok(None, adapter, RollingDaysPolicy(28))
    assert ok and dp.called[-1][0] == "run"

    # week index → week
    ok, _ = apply_time_policy_tiktok(None, adapter, WeekInMonthPolicy(2025, 1, 1))
    assert ok and dp.called[-1][0] == "week"

    # custom range → custom
    ok, _ = apply_time_policy_tiktok(None, adapter, CustomRangePolicy(date(2025,1,6), date(2025,1,12)))
    assert ok and dp.called[-1][0] == "custom"


def run_all_contract_tests():
    """运行所有契约测试"""
    print("🔍 开始数据采集中心应用契约测试...")

    try:
        test_contract_discovery()
        test_contract_registration()
        test_contract_health_check()
        test_contract_basic_interface()
        test_new_architecture_modules()
        test_handlers_integration()

        print("✅ 所有契约测试通过")
        return True

    except Exception as e:
        print(f"❌ 契约测试失败: {e}")
        logger.error(f"契约测试失败: {e}")
        return False


if __name__ == "__main__":
    success = run_all_contract_tests()
    sys.exit(0 if success else 1)
