import importlib
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _load_module():
    return importlib.import_module("backend.domains.business.routers.hr_commission")


def test_performance_input_create_and_list_routes(monkeypatch):
    module = _load_module()

    class _FakeService:
        def __init__(self):
            self.created = []

        async def create(self, body, current_user, db):
            payload = {
                "id": 1,
                "employee_code": body.employee_code,
                "employee_name": "Alice",
                "year_month": body.year_month,
                "metric_code": body.metric_code,
                "metric_name": body.metric_name,
                "metric_direction": body.metric_direction,
                "target_value": body.target_value,
                "achieved_value": body.achieved_value,
                "max_score": body.max_score,
                "manual_score_enabled": body.manual_score_enabled,
                "manual_score_value": body.manual_score_value,
                "source": body.source,
                "reason": body.reason,
                "status": "active",
                "created_by": "tester",
                "created_at": "2026-05-29T00:00:00+00:00",
                "updated_at": "2026-05-29T00:00:00+00:00",
            }
            self.created.append(payload)
            return {"success": True, "data": payload}

        async def list(self, year_month, employee_code, status, page, page_size, db):
            return {
                "success": True,
                "data": {
                    "items": self.created,
                    "total": len(self.created),
                },
            }

    service = _FakeService()

    async def _fake_create(*, body, db, current_user):
        return await service.create(body, current_user, db)

    async def _fake_list(*, year_month, employee_code, status, page, page_size, db):
        return await service.list(year_month, employee_code, status, page, page_size, db)

    monkeypatch.setattr(module, "_create_employee_performance_input", _fake_create)
    monkeypatch.setattr(module, "_list_employee_performance_inputs", _fake_list)

    app = FastAPI()
    app.include_router(module.router)

    async def _fake_user():
        return SimpleNamespace(user_id=1, username="tester", is_superuser=True, roles=[])

    async def _fake_db():
        return SimpleNamespace()

    app.dependency_overrides[module.get_current_user] = _fake_user
    app.dependency_overrides[module.get_async_db] = _fake_db

    client = TestClient(app)

    create_resp = client.post(
        "/api/hr/performance-inputs",
        json={
            "year_month": "2026-03",
            "employee_code": "E001",
            "metric_code": "sales_target",
            "metric_name": "销售目标",
            "metric_direction": "up",
            "target_value": 100,
            "achieved_value": 85,
            "max_score": 50,
            "manual_score_enabled": False,
            "manual_score_value": None,
            "source": "manual_target",
            "reason": "March target",
        },
    )
    assert create_resp.status_code == 200
    body = create_resp.json()
    assert body["success"] is True
    assert body["data"]["employee_code"] == "E001"
    assert body["data"]["metric_code"] == "sales_target"

    list_resp = client.get(
        "/api/hr/performance-inputs",
        params={"year_month": "2026-03"},
    )
    assert list_resp.status_code == 200
    list_body = list_resp.json()
    assert list_body["success"] is True
    assert list_body["data"]["total"] == 1
    assert list_body["data"]["items"][0]["metric_name"] == "销售目标"
