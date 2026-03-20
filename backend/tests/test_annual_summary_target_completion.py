import asyncio
import json
from types import SimpleNamespace

from starlette.requests import Request

from backend.routers.dashboard_api import get_annual_summary_target_completion


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FallbackAwareDb:
    def __init__(self):
        self.execute_calls = []
        self.rollback_calls = 0

    async def execute(self, statement, params):
        sql = str(statement)
        self.execute_calls.append((sql, params))
        if len(self.execute_calls) == 1:
            raise RuntimeError("column target_sales_amount does not exist")
        return _Result((200, 5))

    async def rollback(self):
        self.rollback_calls += 1


class _MetabaseService:
    async def query_question(self, question_name, params):
        assert question_name == "annual_summary_kpi"
        assert params == {"granularity": "monthly", "period": "2026-03"}
        return {"gmv": 100}


def _make_request():
    app = SimpleNamespace(state=SimpleNamespace())
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/dashboard/annual-summary/target-completion",
            "headers": [],
            "client": ("127.0.0.1", 8001),
            "app": app,
        }
    )


def test_target_completion_rolls_back_and_uses_cn_fallback_columns(monkeypatch):
    db = _FallbackAwareDb()
    request = _make_request()

    monkeypatch.setattr(
        "backend.routers.dashboard_api.get_metabase_service",
        lambda: _MetabaseService(),
    )

    response = asyncio.run(
        get_annual_summary_target_completion(
            request=request,
            granularity="monthly",
            period="2026-03",
            db=db,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    fallback_sql, fallback_params = db.execute_calls[1]

    assert response.status_code == 200
    assert db.rollback_calls == 1
    assert fallback_params == {"period": "2026-03"}
    assert '"目标销售额"' in fallback_sql
    assert '"目标订单数"' in fallback_sql
    assert '"年月" = :period' in fallback_sql
    assert body["data"]["target_gmv"] == 200.0
    assert body["data"]["target_orders"] == 5
    assert body["data"]["achieved_gmv"] == 100.0
    assert body["data"]["achievement_rate_gmv"] == 50.0
