# -*- coding: utf-8 -*-
"""
业务概览 Dashboard 缓存 singleflight 契约测试。

覆盖线上 PostgreSQL 路由实际使用的缓存解析器
`backend.domains.business.routers.dashboard_api_postgresql._resolve_cached_payload`：

- 缓存未命中 → 走 singleflight（并发去重），路由自身不直接回源
- 缓存命中   → 直接返回缓存值，不触发 singleflight
- 没有缓存服务 → 旁路回源（BYPASS）

注：旧的 Metabase 时代 `backend/routers/dashboard_api.py` 桩模块已随 v7.12.9 退役删除，
这里改为直接验证 PostgreSQL 链路上的同一份契约。
"""

import asyncio
from types import SimpleNamespace

from starlette.requests import Request

from backend.domains.business.routers.dashboard_api_postgresql import (
    _resolve_cached_payload,
)


class _CacheServiceStub:
    """记录 get / get_or_set_singleflight 调用情况的缓存服务替身。"""

    def __init__(self, cached_value=None, singleflight_payload=None):
        self.cached_value = cached_value
        self.singleflight_payload = singleflight_payload
        self.get_calls = 0
        self.singleflight_calls = 0
        self.singleflight_cache_type = None
        self.singleflight_kwargs = None

    async def get(self, *args, **kwargs):
        self.get_calls += 1
        return self.cached_value

    async def get_or_set_singleflight(self, cache_type, producer, **kwargs):
        self.singleflight_calls += 1
        self.singleflight_cache_type = cache_type
        self.singleflight_kwargs = kwargs
        return self.singleflight_payload


def _make_request(cache_service=None):
    state = SimpleNamespace()
    if cache_service is not None:
        state.cache_service = cache_service
    app = SimpleNamespace(state=state)
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/dashboard/business-overview/kpi",
            "headers": [],
            "client": ("127.0.0.1", 8001),
            "app": app,
        }
    )


def test_resolve_cached_payload_uses_singleflight_on_cache_miss():
    expected_payload = {
        "success": True,
        "data": {"gmv": 123},
        "message": "ok",
    }
    cache_service = _CacheServiceStub(cached_value=None, singleflight_payload=expected_payload)
    request = _make_request(cache_service)

    async def _producer():  # pragma: no cover - 未命中时由缓存服务负责调用
        raise AssertionError("producer must not run directly when a cache miss is handled by singleflight")

    payload, cache_status = asyncio.run(
        _resolve_cached_payload(
            request,
            "dashboard_kpi",
            {"month": "2026-03-01"},
            _producer,
        )
    )

    assert payload == expected_payload
    assert cache_status == "MISS"
    assert cache_service.get_calls == 1
    assert cache_service.singleflight_calls == 1
    assert cache_service.singleflight_cache_type == "dashboard_kpi"
    assert cache_service.singleflight_kwargs["month"] == "2026-03-01"
    assert cache_service.singleflight_kwargs["lock_ttl"] >= 1
    assert cache_service.singleflight_kwargs["wait_timeout"] >= 1


def test_resolve_cached_payload_returns_cached_value_without_singleflight():
    cached_payload = {
        "success": True,
        "data": {"gmv": 999},
        "message": "cached",
    }
    cache_service = _CacheServiceStub(cached_value=cached_payload, singleflight_payload=None)
    request = _make_request(cache_service)

    async def _producer():  # pragma: no cover - 命中时不应回源
        raise AssertionError("producer must not run when the cache already holds a value")

    payload, cache_status = asyncio.run(
        _resolve_cached_payload(
            request,
            "dashboard_kpi",
            {"month": "2026-03-01"},
            _producer,
        )
    )

    assert payload == cached_payload
    assert cache_status == "HIT"
    assert cache_service.get_calls == 1
    assert cache_service.singleflight_calls == 0


def test_resolve_cached_payload_bypasses_cache_when_service_absent():
    produced_payload = {
        "success": True,
        "data": {"gmv": 7},
        "message": "ok",
    }
    request = _make_request(None)

    async def _producer():
        return produced_payload

    payload, cache_status = asyncio.run(
        _resolve_cached_payload(
            request,
            "dashboard_kpi",
            {"month": "2026-03-01"},
            _producer,
        )
    )

    assert payload == produced_payload
    assert cache_status == "BYPASS"
