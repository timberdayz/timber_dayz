import asyncio
import json
from types import SimpleNamespace

from starlette.requests import Request

from backend.routers.dashboard_api import get_business_overview_kpi


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
            "path": "/api/dashboard/business-overview/kpi",
            "headers": [],
            "client": ("127.0.0.1", 8001),
            "app": app,
        }
    )


def test_business_overview_kpi_uses_singleflight_cache_on_miss(monkeypatch):
    expected_payload = {
        "success": True,
        "data": {"gmv": 123},
        "message": "ok",
    }
    cache_service = _CacheServiceUsingSingleflightOnly(expected_payload)
    request = _make_request(cache_service)

    class _MetabaseServiceShouldNotBeCalled:
        async def query_question(self, *args, **kwargs):  # pragma: no cover
            raise AssertionError("Metabase should not be queried when cache service handles miss via singleflight")

    monkeypatch.setattr(
        "backend.routers.dashboard_api.get_metabase_service",
        lambda: _MetabaseServiceShouldNotBeCalled(),
    )

    response = asyncio.run(
        get_business_overview_kpi(
            request=request,
            month="2026-03-01",
            platform=None,
            start_date=None,
            end_date=None,
            platforms=None,
            shops=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body == expected_payload
    assert cache_service.singleflight_calls == 1
