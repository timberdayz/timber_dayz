import asyncio

import pytest

from backend.services.cache_service import CacheService


class _FakeRedis:
    def __init__(self):
        self._data = {}
        self._lock = asyncio.Lock()

    async def get(self, key):
        async with self._lock:
            return self._data.get(key)

    async def setex(self, key, ttl, value):
        async with self._lock:
            self._data[key] = value
            return True

    async def set(self, key, value, ex=None, nx=False):
        async with self._lock:
            if nx and key in self._data:
                return False
            self._data[key] = value
            return True

    async def delete(self, *keys):
        async with self._lock:
            deleted = 0
            for key in keys:
                if key in self._data:
                    deleted += 1
                    del self._data[key]
            return deleted


@pytest.mark.asyncio
async def test_get_or_set_singleflight_only_runs_producer_once():
    redis_client = _FakeRedis()
    service = CacheService(redis_client=redis_client)
    calls = {"count": 0}

    async def producer():
        calls["count"] += 1
        await asyncio.sleep(0.05)
        return {"value": 42}

    results = await asyncio.gather(
        service.get_or_set_singleflight("dashboard_kpi", producer, month="2026-03-01"),
        service.get_or_set_singleflight("dashboard_kpi", producer, month="2026-03-01"),
        service.get_or_set_singleflight("dashboard_kpi", producer, month="2026-03-01"),
    )

    assert calls["count"] == 1
    assert results == [{"value": 42}, {"value": 42}, {"value": 42}]


@pytest.mark.asyncio
async def test_get_or_set_singleflight_reuses_cached_value_after_first_fill():
    redis_client = _FakeRedis()
    service = CacheService(redis_client=redis_client)
    calls = {"count": 0}

    async def producer():
        calls["count"] += 1
        return {"value": "cached"}

    first = await service.get_or_set_singleflight(
        "dashboard_kpi", producer, month="2026-03-01"
    )
    second = await service.get_or_set_singleflight(
        "dashboard_kpi", producer, month="2026-03-01"
    )

    assert calls["count"] == 1
    assert first == {"value": "cached"}
    assert second == {"value": "cached"}
