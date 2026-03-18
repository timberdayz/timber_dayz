import asyncio
import json
from unittest.mock import AsyncMock, patch

from backend.main import app
from backend.routers.mv import get_all_mv_status, refresh_all_materialized_views, router


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def fetchall(self):
        return self._rows


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value


def _response_json(response):
    return json.loads(response.body)


def test_refresh_all_materialized_views_awaits_execute_and_returns_row_count():
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _RowsResult([("mv_financial_overview",)]),
            _RowsResult([]),
            _ScalarResult(12),
        ]
    )
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    response = asyncio.run(refresh_all_materialized_views(db=db))
    payload = _response_json(response)

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["data"]["success_count"] == 1
    assert payload["data"]["results"][0]["view_name"] == "mv_financial_overview"
    assert payload["data"]["results"][0]["row_count"] == 12
    assert db.execute.await_count == 3
    assert db.commit.await_count == 1


def test_get_all_mv_status_awaits_execute_and_uses_refresh_log():
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _RowsResult([("mv_financial_overview", "16 kB")]),
            _ScalarResult(8),
            _ScalarResult(None),
        ]
    )

    fake_select = lambda *args, **kwargs: _FakeSelect()

    with patch("backend.routers.mv.select", fake_select), patch(
        "modules.core.db.MaterializedViewRefreshLog", _FakeRefreshLogModel
    ):
        response = asyncio.run(get_all_mv_status(db=db))

    payload = _response_json(response)

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["data"]["views"][0]["view_name"] == "mv_financial_overview"
    assert payload["data"]["views"][0]["row_count"] == 8
    assert db.execute.await_count == 3


class _FakeColumn:
    def __eq__(self, other):
        return ("eq", other)

    def desc(self):
        return "desc"


class _FakeRefreshLogModel:
    view_name = _FakeColumn()
    refresh_completed_at = _FakeColumn()


class _FakeSelect:
    def where(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self


def test_mv_routes_are_marked_deprecated():
    route_map = {route.path: route for route in router.routes}

    assert route_map["/mv/refresh-all"].deprecated is True
    assert route_map["/mv/status"].deprecated is True


def test_mv_routes_are_exposed_as_legacy_in_openapi():
    schema = app.openapi()
    refresh_op = schema["paths"]["/api/mv/refresh-all"]["post"]
    status_op = schema["paths"]["/api/mv/status"]["get"]

    assert refresh_op["deprecated"] is True
    assert status_op["deprecated"] is True
    assert "legacy-materialized-views" in refresh_op["tags"]
    assert "legacy-materialized-views" in status_op["tags"]
