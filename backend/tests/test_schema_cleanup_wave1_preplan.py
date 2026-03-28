from backend.utils.schema_cleanup_wave1_preplan import build_wave1_preplan


def test_wave1_preplan_allows_only_target_breakdown():
    preplan = build_wave1_preplan()

    approved = preplan["approved_targets"]

    assert len(approved) == 1
    assert approved[0]["table_name"] == "target_breakdown"
    assert approved[0]["source_schema"] == "public"
    assert approved[0]["target_schema"] == "a_class"
    assert approved[0]["operation"] == "archive_rename"


def test_wave1_preplan_blocks_schema_misaligned_tables():
    preplan = build_wave1_preplan()

    blocked = {item["table_name"]: item for item in preplan["blocked_targets"]}

    for table_name in ("performance_config", "sales_campaigns", "sales_campaign_shops"):
        assert table_name in blocked
        assert blocked[table_name]["expected_target_schema"] == "a_class"
        assert "model schema" in blocked[table_name]["blocker_reason"]
