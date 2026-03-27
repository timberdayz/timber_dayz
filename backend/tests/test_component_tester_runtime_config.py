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
            "granularity": "weekly",
            "time_selection": {
                "mode": "preset",
                "preset": "last_7_days",
            },
        },
    )

    cfg = tester._build_runtime_component_config()

    assert cfg["data_domain"] == "services"
    assert cfg["sub_domain"] == "agent"
    assert cfg["services_subtype"] == "agent"
    assert cfg["granularity"] == "weekly"
    assert cfg["time_selection"] == {
        "mode": "preset",
        "preset": "last_7_days",
    }
    assert cfg["params"]["granularity"] == "weekly"
    assert cfg["params"]["sub_domain"] == "agent"
