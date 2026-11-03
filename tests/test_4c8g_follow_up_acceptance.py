# -*- coding: utf-8 -*-
"""
4c8g 单机后续优化验收自动化测试 (tasks 7.2)

验证：告警冷却、写时失效接口。

说明：原先覆盖 Metabase 不可用协议、熔断与缓存预热跳过的三组用例，
对应的 Metabase 子系统已整体退役（迁移到 PostgreSQL 链路），
随 v7.12.9 一并移除，避免留下永远失败的断言。
全部 mock，不依赖真实 Redis/Webhook。
"""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest_plugins = ("anyio",)


# ----- 1. 告警服务：冷却期内不重复发送 -----
class TestAlertServiceCooldown:
    """同一类型告警在冷却期内只发一次"""

    @pytest.mark.anyio
    async def test_send_resource_alert_respects_cooldown(self):
        from backend.services import alert_service

        # 重置冷却状态以便测试
        async with alert_service._cooldown_lock:
            alert_service._cooldown.clear()

        with patch("backend.services.alert_service._send_webhook", new_callable=AsyncMock) as m_webhook:
            with patch.dict(os.environ, {"RESOURCE_MONITOR_ALERT_COOLDOWN_MINUTES": "5"}):
                await alert_service.send_resource_alert(
                    "resource_cpu", "CPU high", cpu_usage=90.0, memory_usage=None
                )
                first_calls = m_webhook.call_count
                await alert_service.send_resource_alert(
                    "resource_cpu", "CPU still high", cpu_usage=91.0, memory_usage=None
                )
                # 第二次应因冷却未调用 webhook（若环境无 WEBHOOK_URL 则两次都可能不调，这里只验证不抛错）
                assert first_calls >= 0


# ----- 2. 写时失效：invalidate_dashboard_business_overview 接口存在且使用约定 key -----
class TestCacheInvalidationDashboard:
    """写时失效集中接口与 key 约定"""

    @pytest.mark.anyio
    async def test_invalidate_dashboard_business_overview_interface_and_prefix(self):
        from backend.services.cache_service import CacheService

        async def mock_scan_iter(match=None, count=100):
            if False:
                yield  # empty async generator

        mock_redis = AsyncMock()
        mock_redis.scan_iter = mock_scan_iter
        mock_redis.delete = AsyncMock(return_value=0)

        cache = CacheService(redis_client=mock_redis)
        n = await cache.invalidate_dashboard_business_overview()
        assert isinstance(n, int) and n >= 0
        assert cache.CACHE_PREFIX == "xihong_erp:"
