import asyncio
import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from starlette.requests import Request

from backend.routers.performance_management import list_performance_scores


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _MappingsResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


def test_list_performance_scores_person_fallback_cn_columns_serializable():
    db = AsyncMock()
    calls = {"n": 0}

    async def _execute(stmt, params=None):
        calls["n"] += 1
        sql = str(stmt)
        # 1) ORM 查询 employee_performance 失败，触发 fallback
        if calls["n"] == 1:
            raise Exception("column employee_performance.year_month does not exist")
        # 2) fallback total
        if "select count(1)" in sql and "employee_performance" in sql:
            return _ScalarResult(1)
        # 3) fallback page
        if 'from c_class.employee_performance' in sql and '"实际销售额"' in sql:
            return _MappingsResult(
                [
                    {
                        "employee_code": "E001",
                        "actual_sales": Decimal("123.45"),
                        "achievement_rate": Decimal("0.88"),
                        "performance_score": Decimal("88"),
                    }
                ]
            )
        # 4) fallback all rows for rank
        if 'from c_class.employee_performance' in sql and '"绩效得分" as performance_score' in sql:
            return _MappingsResult([{"employee_code": "E001", "performance_score": Decimal("88")}])
        # 5) 员工姓名查询
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
    assert isinstance(row["sales_achieved"], float)
    assert db.rollback.await_count >= 1
