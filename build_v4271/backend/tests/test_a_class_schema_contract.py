import pytest

from modules.core.db import PerformanceConfig, SalesCampaign, SalesCampaignShop


@pytest.mark.parametrize(
    ("model", "table_name"),
    [
        (PerformanceConfig, "performance_config"),
        (SalesCampaign, "sales_campaigns"),
        (SalesCampaignShop, "sales_campaign_shops"),
    ],
)
def test_wave_a_tables_bind_explicitly_to_a_class_schema(model, table_name):
    table = model.__table__

    assert table.name == table_name
    assert table.schema == "a_class"
    assert table.fullname == f"a_class.{table_name}"
