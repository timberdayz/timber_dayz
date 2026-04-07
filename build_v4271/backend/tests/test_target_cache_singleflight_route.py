import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from starlette.requests import Request

from backend.routers.target_management import get_target_by_month


class _CacheServiceUsingSingleflightOnly:
    def __init__(self, payload):
        self.payload = payload
        self.get_calls = 0
        self.singleflight_calls = 0

    async def get(self, *args, **kwargs):
        self.get_calls += 1
        return None

    async def get_or_set_singleflight(self, *args, **kwargs):
        self.singleflight_calls += 1
        return self.payload


def _make_request(cache_service):
    app = SimpleNamespace(state=SimpleNamespace(cache_service=cache_service))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/targets/by-month",
            "headers": [],
            "client": ("127.0.0.1", 8001),
            "app": app,
        }
    )


def test_target_by_month_uses_singleflight_cache_on_miss():
    expected_payload = {
        "success": True,
        "data": {"target": None, "breakdowns": []},
        "message": "缓存结果",
    }
    cache_service = _CacheServiceUsingSingleflightOnly(expected_payload)
    request = _make_request(cache_service)
    db = AsyncMock()

    response = asyncio.run(
        get_target_by_month(
            request=request,
            month="2026-03",
            target_type="shop",
            db=db,
            current_user=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body == expected_payload
    assert cache_service.singleflight_calls == 1
