import pytest

from backend.routers.component_versions import _build_component_test_runtime_config
from backend.schemas.component_version import ComponentTestRequest
from backend.services.collection_contracts import build_date_range_from_time_selection


def test_build_component_test_runtime_config_for_export_services_main_component():
    request = ComponentTestRequest(
        account_id="acc-1",
        time_mode="preset",
        date_preset="last_7_days",
        sub_domain="agent",
    )

    logical_type, runtime_config = _build_component_test_runtime_config(
        request, "shopee/services_export"
    )

    normalized_range = build_date_range_from_time_selection(
        {"mode": "preset", "preset": "last_7_days"}
    )

    assert logical_type == "export"
    assert runtime_config == {
        "data_domain": "services",
        "sub_domain": "agent",
        "services_subtype": "agent",
        "granularity": "weekly",
        "time_selection": {
            "mode": "preset",
            "preset": "last_7_days",
        },
        "date_preset": "last_7_days",
        "start_date": normalized_range["start_date"],
        "end_date": normalized_range["end_date"],
        "date_from": normalized_range["date_from"],
        "date_to": normalized_range["date_to"],
    }


def test_build_component_test_runtime_config_prefers_fixed_sub_domain_from_component_name():
    request = ComponentTestRequest(
        account_id="acc-1",
        granularity="weekly",
        time_mode="custom",
        start_date="2026-03-01",
        end_date="2026-03-31",
        sub_domain=None,
    )

    logical_type, runtime_config = _build_component_test_runtime_config(
        request, "shopee/services_agent_export"
    )

    assert logical_type == "export"
    assert runtime_config["data_domain"] == "services"
    assert runtime_config["sub_domain"] == "agent"
    assert runtime_config["services_subtype"] == "agent"
    assert runtime_config["granularity"] == "weekly"
    assert runtime_config["time_selection"]["mode"] == "custom"


def test_build_component_test_runtime_config_for_login_ignores_export_fields():
    request = ComponentTestRequest(
        account_id="acc-1",
        time_mode="preset",
        date_preset="today",
        sub_domain="agent",
    )

    logical_type, runtime_config = _build_component_test_runtime_config(
        request, "miaoshou/login"
    )

    assert logical_type == "login"
    assert runtime_config == {}


def test_build_component_test_runtime_config_rejects_custom_without_granularity():
    request = ComponentTestRequest(
        account_id="acc-1",
        time_mode="custom",
        start_date="2026-03-01",
        end_date="2026-03-07",
    )

    with pytest.raises(ValueError, match="granularity is required for custom"):
        _build_component_test_runtime_config(request, "miaoshou/orders_shopee_export")
