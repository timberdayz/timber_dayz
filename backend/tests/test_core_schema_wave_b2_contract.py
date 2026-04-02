import pytest

from modules.core.db import (
    BridgeProductKeys,
    CollectionSyncPoint,
    ComponentTestHistory,
    ComponentVersion,
    DimCurrency,
    DimCurrencyRate,
    DimExchangeRate,
    DimFiscalCalendar,
    DimMetricFormula,
    DimPlatform,
    DimProduct,
    DimProductMaster,
    DimShop,
    DimVendor,
    FieldMappingAudit,
    FieldMappingDictionary,
    FieldMappingTemplate,
    FieldMappingTemplateItem,
    FieldUsageTracking,
    POHeader,
    StagingInventory,
    StagingOrders,
    StagingProductMetrics,
    TaxReport,
    TaxVoucher,
    JournalEntry,
)


@pytest.mark.parametrize(
    ("model", "table_name"),
    [
        (DimPlatform, "dim_platforms"),
        (DimProduct, "dim_products"),
        (DimProductMaster, "dim_product_master"),
        (BridgeProductKeys, "bridge_product_keys"),
        (DimExchangeRate, "dim_exchange_rates"),
        (DimCurrencyRate, "dim_currency_rates"),
        (CollectionSyncPoint, "collection_sync_points"),
        (ComponentVersion, "component_versions"),
        (ComponentTestHistory, "component_test_history"),
        (FieldMappingDictionary, "field_mapping_dictionary"),
        (FieldMappingTemplate, "field_mapping_templates"),
        (FieldMappingTemplateItem, "field_mapping_template_items"),
        (FieldMappingAudit, "field_mapping_audit"),
        (FieldUsageTracking, "field_usage_tracking"),
        (DimMetricFormula, "dim_metric_formulas"),
        (DimCurrency, "dim_currencies"),
        (DimFiscalCalendar, "dim_fiscal_calendar"),
        (DimVendor, "dim_vendors"),
        (StagingOrders, "staging_orders"),
        (StagingProductMetrics, "staging_product_metrics"),
        (StagingInventory, "staging_inventory"),
    ],
)
def test_wave_b2_tables_bind_explicitly_to_core_schema(model, table_name):
    table = model.__table__

    assert table.name == table_name
    assert table.schema == "core"
    assert table.fullname == f"core.{table_name}"


def test_dim_shop_platform_fk_targets_core_dim_platforms():
    fk_targets = {fk.target_fullname for fk in DimShop.__table__.foreign_keys}

    assert "core.dim_platforms.platform_code" in fk_targets


def test_bridge_product_keys_fk_targets_core_product_tables():
    fk_targets = {fk.target_fullname for fk in BridgeProductKeys.__table__.foreign_keys}

    assert "core.dim_product_master.product_id" in fk_targets
    assert "core.dim_products.platform_code" in fk_targets
    assert "core.dim_products.shop_id" in fk_targets
    assert "core.dim_products.platform_sku" in fk_targets


def test_finance_foreign_keys_target_core_vendor_and_fiscal_tables():
    po_fk_targets = {fk.target_fullname for fk in POHeader.__table__.foreign_keys}
    tax_voucher_fk_targets = {fk.target_fullname for fk in TaxVoucher.__table__.foreign_keys}
    tax_report_fk_targets = {fk.target_fullname for fk in TaxReport.__table__.foreign_keys}
    journal_entry_fk_targets = {fk.target_fullname for fk in JournalEntry.__table__.foreign_keys}

    assert "core.dim_vendors.vendor_code" in po_fk_targets
    assert "core.dim_fiscal_calendar.period_code" in tax_voucher_fk_targets
    assert "core.dim_fiscal_calendar.period_code" in tax_report_fk_targets
    assert "core.dim_fiscal_calendar.period_code" in journal_entry_fk_targets
