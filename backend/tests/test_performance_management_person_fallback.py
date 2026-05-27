import asyncio
import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from starlette.requests import Request

from backend.domains.business.routers.performance_management import list_performance_scores


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalars(self):
        return self


def test_list_performance_scores_person_reads_english_columns():
    db = AsyncMock()
    calls = {"n": 0}
    perf_row = SimpleNamespace(
        employee_code="E001",
        actual_sales=123.45,
        achievement_rate=0.88,
        performance_score=88.0,
    )

    async def _execute(stmt, params=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _ScalarResult(1)
        if calls["n"] == 2:
            return _RowsResult([perf_row])
        if calls["n"] == 3:
            return _RowsResult([perf_row])
        return _RowsResult([("E001", "Alice")])

    db.execute = AsyncMock(side_effect=_execute)
    db.rollback = AsyncMock()

    app = SimpleNamespace(state=SimpleNamespace())
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/performance/scores",
            "headers": [],
            "client": ("127.0.0.1", 8001),
            "app": app,
        }
    )

    resp = asyncio.run(
        list_performance_scores(
            request=request,
            period="2026-01",
            platform_code=None,
            shop_id=None,
            group_by="person",
            page=1,
            page_size=20,
            db=db,
        )
    )
    body = json.loads(resp.body.decode("utf-8"))

    assert body["success"] is True
    assert len(body["data"]) == 1
    row = body["data"][0]
    assert row["employee_code"] == "E001"
    assert row["employee_name"] == "Alice"
    assert row["rank"] == 1
    assert row["total_score"] == 88.0
    assert row["performance_coefficient"] is None
    assert isinstance(row["sales_achieved"], float)
    assert db.rollback.await_count == 0


def test_list_performance_scores_person_serializes_decimal_fields():
    db = AsyncMock()
    calls = {"n": 0}
    perf_row = SimpleNamespace(
        employee_code="E002",
        actual_sales=Decimal("123.45"),
        achievement_rate=Decimal("0.88"),
        performance_score=Decimal("88.0"),
    )

    async def _execute(stmt, params=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _ScalarResult(1)
        if calls["n"] == 2:
            return _RowsResult([perf_row])
        if calls["n"] == 3:
            return _RowsResult([perf_row])
        return _RowsResult([("E002", "Bob")])

    db.execute = AsyncMock(side_effect=_execute)
    db.rollback = AsyncMock()

    app = SimpleNamespace(state=SimpleNamespace())
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/performance/scores",
            "headers": [],
            "client": ("127.0.0.1", 8001),
            "app": app,
        }
    )

    resp = asyncio.run(
        list_performance_scores(
            request=request,
            period="2026-01",
            platform_code=None,
            shop_id=None,
            group_by="person",
            page=1,
            page_size=20,
            db=db,
        )
    )
    body = json.loads(resp.body.decode("utf-8"))

    assert body["success"] is True
    row = body["data"][0]
    assert row["sales_achieved"] == 123.45
    assert row["sales_rate"] == 88.0
    assert row["total_score"] == 88.0
