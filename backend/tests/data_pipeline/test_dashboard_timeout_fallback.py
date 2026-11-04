"""看板「查询超时降级兜底」（B5）的行为契约。

背景
----
看板的查询有真实耗时（业务概览 / B 成本页在物化之前是 20 秒级）。
DB 有 ``statement_timeout``，超时会抛异常 ⇒ 端点返回 500，用户看到空白页。

B5 的要求：**超时时不要空白页** —— 返回「上一次成功的结果」，
并明确告诉用户「这份数据是截至什么时候的」。

不变量
------
1. **只在超时上降级** —— 其它异常（语法错、权限、连接断）照常 500，
   绝不能被伪装成「数据有点旧」（那会把真 bug 藏起来）。
2. **超时时没有快照 ⇒ 仍然 500** —— 不能凭空造数。
3. 降级响应必须带：``data_status="degraded"``、``data_as_of``、
   ``degraded_reason``、以及一条人话 warning。
4. 快照**按端点分桶** —— 不同端点的查询参数可能一样，不能互相串。
5. 客户端断开（``asyncio.CancelledError``）**不算超时**。
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import Request

from backend.domains.business.routers.dashboard_api_postgresql import (
    get_business_overview_kpi_postgresql,
    get_business_overview_operational_metrics_postgresql,
)
from backend.utils.query_timeout import is_query_timeout_error


class _FakeQueryTimeout(Exception):
    """模拟 PostgreSQL ``statement_timeout`` 触发时的驱动异常。"""


class _FakeCacheService:
    """最小可用的缓存替身：支持 get / set / get_or_set_singleflight。

    与真实 Redis 的差别：真实缓存有 TTL（看板普通缓存 180 秒、降级快照
    24 小时）。这里用 ``expire_regular_cache`` 显式模拟「普通缓存过期了，
    但快照还在」—— 那正是降级兜底要救的场景。
    """

    def __init__(self):
        self.store: dict[str, object] = {}

    @staticmethod
    def _key(cache_type: str, kwargs: dict) -> str:
        return "{type}|{kwargs}".format(
            type=cache_type, kwargs=sorted((k, str(v)) for k, v in kwargs.items())
        )

    async def get(self, cache_type: str, **kwargs):
        return self.store.get(self._key(cache_type, kwargs))

    async def set(self, cache_type: str, data, ttl=None, **kwargs):
        self.store[self._key(cache_type, kwargs)] = data
        return True

    async def get_or_set_singleflight(self, cache_type: str, producer, **kwargs):
        cached = await self.get(cache_type, **kwargs)
        if cached is not None:
            return cached
        produced = await producer()
        await self.set(cache_type, produced, **kwargs)
        return produced

    def expire_regular_cache(self, cache_type: str) -> None:
        """模拟普通缓存过期（降级快照不受影响）。"""
        prefix = "{type}|".format(type=cache_type)
        for key in [k for k in self.store if k.startswith(prefix)]:
            if ":last_success|" not in key:
                del self.store[key]


def _make_request(path: str, cache_service=None):
    state = SimpleNamespace(
        dashboard_assets_report={
            "ready": True,
            "modules": {
                "business_overview": {"status": "ready", "ready": True},
                "inventory_backlog": {"status": "ready", "ready": True},
                "b_cost": {"status": "ready", "ready": True},
            },
        }
    )
    if cache_service is not None:
        state.cache_service = cache_service
    app = SimpleNamespace(state=state)
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 8001),
            "app": app,
        }
    )


# ---------------------------------------------------------------------------
# 超时识别
# ---------------------------------------------------------------------------


def test_query_timeout_is_recognized_from_driver_message():
    assert is_query_timeout_error(
        Exception("canceling statement due to statement timeout")
    )


def test_query_timeout_is_recognized_from_sqlalchemy_timeout_error():
    from sqlalchemy.exc import TimeoutError as SATimeoutError

    assert is_query_timeout_error(SATimeoutError("pool timeout"))


def test_query_timeout_is_recognized_through_wrapped_dbapi_error():
    """SQLAlchemy 会把驱动异常包成 DBAPIError，原始异常挂在 orig 上。"""
    from sqlalchemy.exc import DBAPIError

    class _Orig(Exception):
        pass

    orig = _Orig("canceling statement due to statement timeout")
    wrapper = DBAPIError("SELECT 1", {}, orig)
    assert is_query_timeout_error(wrapper)


def test_non_timeout_errors_are_not_degraded():
    assert not is_query_timeout_error(ValueError("参数不合法"))
    assert not is_query_timeout_error(RuntimeError("relation does not exist"))
    assert not is_query_timeout_error(None)


def test_client_disconnect_is_not_a_timeout():
    """客户端断开 / 服务停机不是超时，不该拿旧数据糊弄过去。"""
    assert not is_query_timeout_error(asyncio.CancelledError())


# ---------------------------------------------------------------------------
# 端点行为
# ---------------------------------------------------------------------------


def _install_kpi_service(monkeypatch, error: Exception | None, payload=None):
    class _ServiceStub:
        async def get_business_overview_kpi(self, *args, **kwargs):
            if error is not None:
                raise error
            return payload or {"gmv": 123, "order_count": 10}

        async def get_business_overview_data_freshness(self, *args, **kwargs):
            return {"is_stale": False, "warnings": []}

    monkeypatch.setattr(
        "backend.domains.business.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )


def test_timeout_without_snapshot_still_returns_500(monkeypatch):
    """没有可用快照时不能凭空造数 —— 维持 500。"""
    _install_kpi_service(
        monkeypatch, _FakeQueryTimeout("canceling statement due to statement timeout")
    )
    cache_service = _FakeCacheService()

    response = asyncio.run(
        get_business_overview_kpi_postgresql(
            request=_make_request(
                "/api/dashboard/business-overview/kpi", cache_service
            ),
            period_key="2026-03-01",
            platform_code=None,
            shop_id=None,
        )
    )

    assert response.status_code == 500
    body = json.loads(response.body.decode("utf-8"))
    assert body.get("success") is not True


def test_non_timeout_error_is_not_degraded(monkeypatch):
    """非超时异常照常报错，不允许被伪装成「数据旧」。"""
    _install_kpi_service(monkeypatch, RuntimeError("relation does not exist"))
    cache_service = _FakeCacheService()

    response = asyncio.run(
        get_business_overview_kpi_postgresql(
            request=_make_request(
                "/api/dashboard/business-overview/kpi", cache_service
            ),
            period_key="2026-03-01",
            platform_code=None,
            shop_id=None,
        )
    )

    assert response.status_code == 500
    body = json.loads(response.body.decode("utf-8"))
    meta = body.get("meta") or {}
    assert meta.get("data_status") != "degraded"


def test_timeout_serves_last_success_snapshot_with_data_timestamp(monkeypatch):
    """超时 ⇒ 返回上一次成功的结果，并说清「数据截至什么时候」。"""
    cache_service = _FakeCacheService()

    # 第一次：成功 → 落快照
    _install_kpi_service(monkeypatch, None, payload={"gmv": 999, "order_count": 42})
    first = asyncio.run(
        get_business_overview_kpi_postgresql(
            request=_make_request(
                "/api/dashboard/business-overview/kpi", cache_service
            ),
            period_key="2026-03-01",
            platform_code=None,
            shop_id=None,
        )
    )
    assert first.status_code == 200
    assert json.loads(first.body.decode("utf-8"))["data"]["gmv"] == 999

    # 第二次：普通缓存已过期（180s），DB 超时 ⇒ 降级到 24 小时的快照
    cache_service.expire_regular_cache("dashboard_kpi")
    _install_kpi_service(
        monkeypatch, _FakeQueryTimeout("canceling statement due to statement timeout")
    )
    second = asyncio.run(
        get_business_overview_kpi_postgresql(
            request=_make_request(
                "/api/dashboard/business-overview/kpi", cache_service
            ),
            period_key="2026-03-01",
            platform_code=None,
            shop_id=None,
        )
    )

    assert second.status_code == 200
    assert second.headers.get("X-Cache") == "DEGRADED"
    body = json.loads(second.body.decode("utf-8"))
    assert body["data"]["gmv"] == 999, "应当返回上一次成功的数字"
    meta = body["meta"]
    assert meta["data_status"] == "degraded"
    assert meta["degraded_reason"] == "query_timeout"
    assert meta.get("data_as_of"), "必须告诉用户数据截至什么时候"
    assert any(
        "serving_stale_snapshot" in warning for warning in meta.get("warnings") or []
    )


def test_snapshot_is_isolated_per_endpoint(monkeypatch):
    """不同端点的查询参数可能一样 —— 快照不能互相串。"""
    cache_service = _FakeCacheService()

    _install_kpi_service(monkeypatch, None, payload={"gmv": 111})
    asyncio.run(
        get_business_overview_kpi_postgresql(
            request=_make_request(
                "/api/dashboard/business-overview/kpi", cache_service
            ),
            period_key="2026-03-01",
            platform_code=None,
            shop_id=None,
        )
    )

    class _MetricsServiceStub:
        async def get_business_overview_operational_metrics(self, *args, **kwargs):
            raise _FakeQueryTimeout("canceling statement due to statement timeout")

        async def get_business_overview_data_freshness(self, *args, **kwargs):
            return {"is_stale": False, "warnings": []}

    monkeypatch.setattr(
        "backend.domains.business.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _MetricsServiceStub(),
    )

    response = asyncio.run(
        get_business_overview_operational_metrics_postgresql(
            request=_make_request(
                "/api/dashboard/business-overview/operational-metrics", cache_service
            ),
            granularity=None,
            period_key="2026-03-01",
            platform_code=None,
            shop_id=None,
        )
    )

    # operational-metrics 自己没有快照 ⇒ 不能拿 kpi 的快照来充数
    assert response.status_code == 500


def test_snapshot_uses_its_own_cache_bucket():
    """快照键 = 端点 cache_type + ':last_success'。"""
    from backend.domains.business.routers.dashboard_api_postgresql import (
        _snapshot_cache_type,
    )

    assert _snapshot_cache_type("dashboard_kpi") == "dashboard_kpi:last_success"
    assert (
        _snapshot_cache_type("dashboard_operational_metrics")
        == "dashboard_operational_metrics:last_success"
    )
