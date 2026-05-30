import importlib
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _load_module():
    return importlib.import_module("backend.domains.business.routers.hr_commission")


def test_performance_input_template_list_and_apply_routes(monkeypatch):
    module = _load_module()

    async def _fake_list(*, db, employee_code):
        return {
            "success": True,
            "data": {
                "recommended_template_code": "general_operator",
                "items": [
                    {
                        "template_code": "general_operator",
                        "template_name": "通用运营模板",
                        "position_name": None,
                        "recommended": True,
                        "metrics": [
                            {
                                "metric_code": "sales_execution",
                                "metric_name": "销售执行",
                                "metric_direction": "up",
                                "target_value": 100.0,
                                "achieved_value": 0.0,
                                "max_score": 40.0,
                                "manual_score_enabled": False,
                                "manual_score_value": None,
                            }
                        ],
                    }
                ],
            },
        }

    async def _fake_apply(*, body, db, current_user):
        return {
            "success": True,
            "data": {
                "employee_code": body.employee_code,
                "year_month": body.year_month,
                "template_code": body.template_code or "general_operator",
                "created_count": 4,
                "updated_count": 0,
                "skipped_count": 0,
            },
        }

    monkeypatch.setattr(module, "_build_employee_performance_templates", _fake_list)
    monkeypatch.setattr(module, "_apply_employee_performance_template", _fake_apply)

    app = FastAPI()
    app.include_router(module.router)

    async def _fake_user():
        return SimpleNamespace(user_id=1, username="tester", is_superuser=True, roles=[])

    async def _fake_db():
        return SimpleNamespace()

    app.dependency_overrides[module.get_current_user] = _fake_user
    app.dependency_overrides[module.get_async_db] = _fake_db

    client = TestClient(app)

    list_resp = client.get("/api/hr/performance-input-templates", params={"employee_code": "EMP001"})
    assert list_resp.status_code == 200
    list_body = list_resp.json()
    assert list_body["success"] is True
    assert list_body["data"]["recommended_template_code"] == "general_operator"

    apply_resp = client.post(
        "/api/hr/performance-input-templates/apply",
        json={
            "employee_code": "EMP001",
            "year_month": "2026-03",
            "template_code": "general_operator",
            "overwrite": False,
        },
    )
    assert apply_resp.status_code == 200
    apply_body = apply_resp.json()
    assert apply_body["success"] is True
    assert apply_body["data"]["created_count"] == 4
