from tools.test_component import ComponentTester


def test_component_tester_builds_export_runtime_config():
    tester = ComponentTester(
        platform="shopee",
        account_id="acc-1",
        output_dir="temp/test_results",
        runtime_config={
            "data_domain": "services",
            "sub_domain": "agent",
            "services_subtype": "agent",
            "granularity": "daily",
            "start_date": "2026-03-01",
            "end_date": "2026-03-07",
            "date_from": "2026-03-01",
            "date_to": "2026-03-07",
        },
    )

    cfg = tester._build_runtime_component_config()

    assert cfg["data_domain"] == "services"
    assert cfg["sub_domain"] == "agent"
    assert cfg["services_subtype"] == "agent"
    assert cfg["granularity"] == "daily"
    assert cfg["start_date"] == "2026-03-01"
    assert cfg["end_date"] == "2026-03-07"
    assert cfg["params"]["date_from"] == "2026-03-01"
    assert cfg["params"]["date_to"] == "2026-03-07"
    assert cfg["params"]["granularity"] == "daily"
    assert cfg["params"]["sub_domain"] == "agent"
