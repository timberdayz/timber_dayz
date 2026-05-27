from pathlib import Path
import re


SOURCE = Path("backend/domains/business/routers/hr_commission.py").read_text(encoding="utf-8")


def test_put_shop_commission_config_requires_year_month_in_body() -> None:
    assert re.search(
        r"@router\.put\(\"/shop-commission-config/\{platform_code\}/\{shop_id\}\"\)\s+async def put_shop_commission_config\([\s\S]*?body: ShopCommissionConfigUpdate",
        SOURCE,
    )
    assert re.search(
        r"select\(ShopCommissionConfig\)\.where\([\s\S]*?ShopCommissionConfig\.year_month == body\.year_month[\s\S]*?ShopCommissionConfig\.platform_code == pc[\s\S]*?ShopCommissionConfig\.shop_id == sid",
        SOURCE,
    )
    assert re.search(
        r"ShopCommissionConfig\([\s\S]*?year_month=body\.year_month[\s\S]*?platform_code=pc[\s\S]*?shop_id=sid",
        SOURCE,
    )


def test_shop_profit_statistics_filters_shop_commission_config_by_month() -> None:
    assert re.search(
        r"config_query = select\(ShopCommissionConfig\)\.where\(\s*ShopCommissionConfig\.year_month == month\s*\)",
        SOURCE,
    )


def test_annual_profit_statistics_uses_month_specific_commission_config() -> None:
    assert re.search(
        r"select\(ShopCommissionConfig\)\.where\(\s*ShopCommissionConfig\.year_month == month_str\s*\)",
        SOURCE,
    )
