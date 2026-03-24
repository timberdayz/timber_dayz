from backend.routers.component_versions import _build_component_test_runtime_config
from backend.schemas.component_version import ComponentTestRequest


def test_build_component_test_runtime_config_for_export_services_main_component():
    request = ComponentTestRequest(
        account_id="acc-1",
        granularity="daily",
        start_date="2026-03-01",
        end_date="2026-03-07",
        sub_domain="agent",
    )

    logical_type, runtime_config = _build_component_test_runtime_config(
        request, "shopee/services_export"
    )

    assert logical_type == "export"
    assert runtime_config == {
        "data_domain": "services",
        "sub_domain": "agent",
        "services_subtype": "agent",
        "granularity": "daily",
        "start_date": "2026-03-01",
        "end_date": "2026-03-07",
        "date_from": "2026-03-01",
        "date_to": "2026-03-07",
    }


def test_build_component_test_runtime_config_prefers_fixed_sub_domain_from_component_name():
    request = ComponentTestRequest(
        account_id="acc-1",
        granularity="weekly",
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


def test_build_component_test_runtime_config_for_login_ignores_export_fields():
    request = ComponentTestRequest(
        account_id="acc-1",
        granularity="daily",
        start_date="2026-03-01",
        end_date="2026-03-07",
        sub_domain="agent",
    )

    logical_type, runtime_config = _build_component_test_runtime_config(
        request, "miaoshou/login"
    )

    assert logical_type == "login"
    assert runtime_config == {}
