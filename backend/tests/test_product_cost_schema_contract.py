from sqlalchemy import inspect

from modules.core.db import (
    LogisticsBill,
    LogisticsBillLine,
    LogisticsBillLineAllocation,
    ProductCostAssumptionProfile,
    SkuProfitEstimate,
)


def test_product_cost_models_expose_versioned_estimate_and_bill_fields():
    expected = {
        LogisticsBill: {"bill_id", "bill_no", "logistics_provider", "total_amount", "status", "source_file_id"},
        LogisticsBillLine: {"bill_id", "line_no", "item_code", "volume_cbm", "gross_weight_kg", "line_total_amount"},
        LogisticsBillLineAllocation: {"bill_line_id", "sku_id", "allocated_amount", "allocation_basis"},
        ProductCostAssumptionProfile: {"profile_id", "destination", "transport_type", "billing_basis", "freight_unit_rate", "return_rate", "damage_rate"},
        SkuProfitEstimate: {"estimate_id", "sku_id", "estimate_as_of", "assumption_version", "scenario", "estimated_contribution_profit", "estimated_margin_rate"},
    }
    for model, columns in expected.items():
        assert columns <= {column.name for column in inspect(model).columns}
        assert model.__table__.schema == "finance"
