import importlib
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _load_module():
    return importlib.import_module("backend.domains.business.routers.hr_employee")


def test_employee_income_audit_route_returns_audit_payload(monkeypatch):
    module = _load_module()

    async def _fake_build(*, employee_code, year_month, db):
        return {
            "success": True,
            "data": {
                "employee": {"employee_code": employee_code, "name": "李四"},
                "year_month": year_month,
                "settlement_status": "draft",
                "my_income_projection": {"net_salary": 5946.53, "is_locked": False},
                "shop_assignments": [],
                "performance_inputs": [],
                "performance_adjustments": [],
                "employee_performance": None,
                "employee_commission": None,
                "payroll_record": None,
            },
        }

    monkeypatch.setattr(module, "_build_employee_income_audit", _fake_build)
    monkeypatch.setattr(module, "is_admin_user", lambda user: True)

    app = FastAPI()
    app.include_router(module.router)

    async def _fake_user():
        return SimpleNamespace(user_id=1, username="tester", is_superuser=True, roles=[])

    async def _fake_db():
        return SimpleNamespace()

    app.dependency_overrides[module.get_current_user] = _fake_user
    app.dependency_overrides[module.get_async_db] = _fake_db

    client = TestClient(app)
    resp = client.get("/api/hr/income-audit/EMP001/2026-03")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["employee"]["employee_code"] == "EMP001"
    assert body["data"]["year_month"] == "2026-03"
