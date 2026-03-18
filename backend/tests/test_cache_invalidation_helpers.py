import pytest

from backend.routers.performance_management import invalidate_performance_related_caches
from backend.routers.target_management import invalidate_target_related_caches


class _FakeCacheService:
    def __init__(self):
        self.calls = []

    async def invalidate_dashboard_business_overview(self):
        self.calls.append(("dashboard", None))
        return 1

    async def invalidate(self, cache_type: str):
        self.calls.append(("invalidate", cache_type))
        return 1


@pytest.mark.asyncio
async def test_invalidate_target_related_caches_clears_target_and_dashboard_keys():
    cache_service = _FakeCacheService()

    await invalidate_target_related_caches(cache_service)

    assert cache_service.calls == [
        ("dashboard", None),
        ("invalidate", "target_by_month"),
        ("invalidate", "target_breakdown"),
    ]


@pytest.mark.asyncio
async def test_invalidate_performance_related_caches_clears_score_keys():
    cache_service = _FakeCacheService()

    await invalidate_performance_related_caches(cache_service)

    assert cache_service.calls == [
        ("invalidate", "performance_scores"),
        ("invalidate", "performance_scores_shop"),
    ]
