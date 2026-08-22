import asyncio
from types import SimpleNamespace

from fastapi.routing import APIRoute

from backend.domains.business.routers import hr_commission


def _route(path: str, method: str) -> APIRoute:
    return next(
        route
        for route in hr_commission.router.routes
        if isinstance(route, APIRoute)
        and route.path == path
        and method in (route.methods or set())
    )


def _requires_admin(route: APIRoute) -> bool:
    return any(
        getattr(dependency.call, "__name__", "") == "require_admin"
        for dependency in route.dependant.dependencies
    )


def test_legacy_personal_performance_write_routes_require_admin():
    for path, method in (
        ("/api/hr/performance-adjustments", "GET"),
        ("/api/hr/performance-adjustments", "POST"),
        ("/api/hr/performance-adjustments/{adjustment_id}", "PUT"),
        ("/api/hr/performance-adjustments/{adjustment_id}", "DELETE"),
        ("/api/hr/performance-inputs", "GET"),
        ("/api/hr/performance-inputs", "POST"),
        ("/api/hr/performance-inputs/{input_id}", "PUT"),
        ("/api/hr/performance-inputs/{input_id}", "DELETE"),
        ("/api/hr/performance-input-templates/apply", "POST"),
    ):
        assert _requires_admin(_route(path, method))


def test_employee_shop_assignment_write_routes_require_admin():
    for path, method in (
        ("/api/hr/employee-shop-assignments", "POST"),
        ("/api/hr/employee-shop-assignments/{id}", "PUT"),
        ("/api/hr/employee-shop-assignments/{id}", "DELETE"),
    ):
        assert _requires_admin(_route(path, method))


class _Result:
    def scalar_one_or_none(self):
        return SimpleNamespace(calculation_mode="controlled_targets_v1")


class _Db:
    def __init__(self, events):
        self.events = events

    async def execute(self, _statement):
        self.events.append("plan-read")
        return _Result()


class _Lock:
    def __init__(self, _db):
        self._db = _db

    async def acquire_month_transaction_lock(self, **_kwargs):
        self._db.events.append("month-lock")


def test_legacy_write_guard_locks_month_before_reading_controlled_plan(monkeypatch):
    events = []
    monkeypatch.setattr(hr_commission, "PayrollPeriodLockService", _Lock)

    response = asyncio.run(
        hr_commission._controlled_personal_target_write_conflict(
            db=_Db(events), year_month="2026-08"
        )
    )

    assert response.status_code == 409
    assert events == ["month-lock", "plan-read"]
