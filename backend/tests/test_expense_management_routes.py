import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.dependencies.auth import get_current_user
from backend.models.database import get_async_db


def _make_user(role_code: str = "finance", user_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=user_id,
        username="tester",
        is_superuser=False,
        roles=[SimpleNamespace(role_code=role_code, role_name=role_code)],
    )


@pytest.mark.asyncio
async def test_expense_create_accepts_missing_platform_code_when_lookup_succeeds(monkeypatch):
    from backend.domains.business.routers import expense_management as module

    executed = {}

    class _Result:
        def __init__(self, row):
            self._row = row

        def fetchone(self):
            return self._row

    class _DB:
        async def execute(self, query, params=None):
            sql = str(query)
            if 'SELECT COALESCE("是否锁定", false)' in sql:
                return _Result(None)
            if "INSERT INTO a_class.operating_costs" in sql:
                executed["params"] = params
                return _Result(
                    SimpleNamespace(
                        id=1,
                        shop_id=params["shop_id"],
                        platform_code=params["platform_code"],
                        year_month=params["year_month"],
                        rent=params["rent"],
                        marketing_fee=params["marketing_fee"],
                        utilities=params["utilities"],
                        ai_token_cost=params["ai_token_cost"],
                        labor_cost=params["labor_cost"],
                        other_costs=params["other_costs"],
                        total_cost=params["total_cost"],
                        note=params["note"],
                        attachments=[],
                        locked=False,
                        created_at="2026-05-25T00:00:00Z",
                        updated_at="2026-05-25T00:00:00Z",
                    )
                )
            raise AssertionError(sql)

        async def commit(self):
            return None

        async def rollback(self):
            return None

    async def _override_db():
        yield _DB()

    app = FastAPI()
    app.include_router(module.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: _make_user()
    app.dependency_overrides[get_async_db] = _override_db
    monkeypatch.setattr(
        module,
        "_resolve_shop_platform_code",
        lambda db, shop_id: __import__("asyncio").sleep(0, result="shopee"),
    )
    monkeypatch.setattr(module, "sync_monthly_cost_entry_task", lambda *args, **kwargs: __import__("asyncio").sleep(0))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/api/expenses",
            json={
                "shop_id": "shop-1",
                "platform_code": "",
                "year_month": "2026-05",
                "rent": 1,
                "marketing_fee": 2,
                "utilities": 3,
                "ai_token_cost": 4,
                "labor_cost": 6,
                "other_costs": 5,
            },
        )

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert body["success"] is True
    assert executed["params"]["platform_code"] == "shopee"
    assert executed["params"]["labor_cost"] == 6
    assert executed["params"]["total_cost"] == 21
    assert body["data"]["labor_cost"] == 6
    assert body["data"]["total_cost"] == 21


@pytest.mark.asyncio
async def test_expense_create_rejects_missing_platform_code_when_lookup_fails(monkeypatch):
    from backend.domains.business.routers import expense_management as module

    class _Result:
        def fetchone(self):
            return None

    class _DB:
        async def execute(self, query, params=None):
            sql = str(query)
            if 'SELECT COALESCE("是否锁定", false)' in sql:
                return _Result()
            raise AssertionError(sql)

        async def commit(self):
            return None

        async def rollback(self):
            return None

    async def _override_db():
        yield _DB()

    app = FastAPI()
    app.include_router(module.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: _make_user()
    app.dependency_overrides[get_async_db] = _override_db
    monkeypatch.setattr(
        module,
        "_resolve_shop_platform_code",
        lambda db, shop_id: __import__("asyncio").sleep(0, result=None),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/api/expenses",
            json={
                "shop_id": "shop-1",
                "platform_code": "",
                "year_month": "2026-05",
                "rent": 1,
                "marketing_fee": 2,
                "utilities": 3,
                "ai_token_cost": 4,
                "labor_cost": 6,
                "other_costs": 5,
            },
        )

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 400
    assert body["success"] is False
    assert body["message"] == "无法识别店铺所属平台"


@pytest.mark.asyncio
async def test_expense_delete_uses_soft_delete_and_restore_endpoint(monkeypatch):
    from backend.domains.business.routers import expense_management as module

    calls = []

    class _Result:
        def __init__(self, row):
            self._row = row

        def fetchone(self):
            return self._row

    class _DB:
        async def execute(self, query, params=None):
            sql = str(query)
            calls.append((sql, params))
            if 'SELECT id FROM a_class.operating_costs WHERE id = :expense_id AND "删除时间" IS NULL' in sql:
                return _Result(SimpleNamespace(id=5))
            if 'SET "删除时间" = NOW()' in sql:
                return _Result(None)
            if 'SELECT id\n            FROM a_class.operating_costs\n            WHERE id = :expense_id\n              AND "删除时间" IS NOT NULL' in sql:
                return _Result(SimpleNamespace(id=5))
            if 'SET "删除时间" = NULL' in sql:
                return _Result(None)
            raise AssertionError(sql)

        async def commit(self):
            return None

        async def rollback(self):
            return None

    async def _override_db():
        yield _DB()

    app = FastAPI()
    app.include_router(module.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: _make_user()
    app.dependency_overrides[get_async_db] = _override_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        delete_response = await client.delete("/api/expenses/5")
        restore_response = await client.post("/api/expenses/5/restore")

    delete_body = json.loads(delete_response.content.decode("utf-8"))
    restore_body = json.loads(restore_response.content.decode("utf-8"))

    assert delete_response.status_code == 200
    assert delete_body["success"] is True
    assert "软删除" in delete_body["message"]
    assert restore_response.status_code == 200
    assert restore_body["success"] is True
    assert "恢复" in restore_body["message"]
    assert any('SET "删除时间" = NOW()' in sql for sql, _ in calls)
    assert any('SET "删除时间" = NULL' in sql for sql, _ in calls)
