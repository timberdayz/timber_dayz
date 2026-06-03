from modules.services.file_semantics import validate_file_semantics


def test_inventory_monthly_is_semantically_invalid():
    result = validate_file_semantics(
        source_platform="miaoshou",
        platform_code="miaoshou",
        data_domain="inventory",
        granularity="monthly",
        sub_domain=None,
        file_name="miaoshou_inventory_monthly_20260407_121357.xls",
    )

    assert result.is_valid is False
    assert result.reason == "inventory_granularity_invalid"


def test_inventory_snapshot_is_semantically_valid():
    result = validate_file_semantics(
        source_platform="miaoshou",
        platform_code="miaoshou",
        data_domain="inventory",
        granularity="snapshot",
        sub_domain=None,
        file_name="miaoshou_inventory_snapshot_20260407_121357.xls",
    )

    assert result.is_valid is True
    assert result.reason == ""
