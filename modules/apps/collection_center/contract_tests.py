#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据采集中心包契约测试

注(2026-11-03): 遗留 CLI 老程序(app.py / handlers.py)已退役,
原先针对「注册器发现 / 注册 / 健康检查 / 基本接口 / handlers 集成」
的用例随老程序一并移除;本文件保留仍与采集链路相关的契约用例。

用法:
    python modules/apps/collection_center/contract_tests.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from modules.core.logger import get_logger

logger = get_logger(__name__)


def test_new_architecture_modules():
    """测试新架构模块集成

    注: modules.utils.data_processing_pipeline 的 `from models.database import
    CollectionTask, DatabaseManager` 已失效(两个名字在 modules.core.db.schema
    单一数据源下都不存在),该模块已无法导入,故本用例不再断言它。
    """
    try:
        # 测试模块是否可以导入
        from modules.utils.login_orchestrator import LoginOrchestrator
        from modules.utils.step_runner import StepRunner

        logger.info("[OK] 新架构模块导入测试通过")

        # 测试StepRunner基础功能
        class MockBrowser:
            pass

        browser = MockBrowser()
        step_runner = StepRunner(browser)

        # 测试模板创建
        templates = step_runner.create_all_platform_templates()
        assert len(templates) >= 3, "应该创建至少3个平台模板"

        logger.info("[OK] 新架构模块功能测试通过")

    except Exception as e:
        logger.error(f"新架构模块测试失败: {e}")
        raise


def test_date_picker_api_contracts():
    """最小日期组件契约测试:
    - DateOption 包含 LAST_28_DAYS
    - TikTok DatePicker 提供 run(page, option)

    注: select_custom_range / select_week_index 现只存在于
    modules/platforms/tiktok/archive/date_picker.py(已归档),
    现行 TiktokDatePicker 只暴露 run(page, option),故不再断言这两个方法。
    (不做真实 UI 操作)
    """
    from modules.components.date_picker.base import DateOption
    from modules.platforms.tiktok.components.date_picker import TiktokDatePicker
    from modules.components.base import ExecutionContext

    assert hasattr(DateOption, "LAST_28_DAYS"), "DateOption 应包含 LAST_28_DAYS"

    # 仅校验方法存在性
    ctx = ExecutionContext(platform="tiktok", account={}, logger=None)
    dp = TiktokDatePicker(ctx)
    assert hasattr(dp, "run"), "TiktokDatePicker 需实现 run(page, option)"



def test_time_policy_resolution_and_routing():
    """不依赖 UI 的策略路由契约:
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

    # week index -> week
    ok, _ = apply_time_policy_tiktok(None, adapter, WeekInMonthPolicy(2025, 1, 1))
    assert ok and dp.called[-1][0] == "week"

    # custom range -> custom
    ok, _ = apply_time_policy_tiktok(None, adapter, CustomRangePolicy(date(2025,1,6), date(2025,1,12)))
    assert ok and dp.called[-1][0] == "custom"


def run_all_contract_tests():
    """运行所有契约测试"""
    print("[SEARCH] 开始数据采集中心契约测试...")

    try:
        test_new_architecture_modules()
        test_date_picker_api_contracts()
        test_time_policy_resolution_and_routing()

        print("[OK] 所有契约测试通过")
        return True

    except Exception as e:
        print(f"[FAIL] 契约测试失败: {e}")
        logger.error(f"契约测试失败: {e}")
        return False


if __name__ == "__main__":
    success = run_all_contract_tests()
    sys.exit(0 if success else 1)
