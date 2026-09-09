from sqlalchemy import inspect

from modules.core.db import (
    DimErpSku,
    FeishuProjectionConfig,
    FeishuProjectionLog,
    FeishuProjectionTask,
    LogisticsBill,
    LogisticsBillLine,
    ProductCostAssumptionProfile,
    SkuProfitEstimate,
)


def test_sku_and_cost_models_support_manual_logistics_and_cost_sources():
    expected = {
        DimErpSku: {
            "default_purchase_cost",
            "purchase_cost_currency",
            "purchase_cost_source",
            "purchase_cost_confidence",
            "purchase_cost_confirmed_at",
        },
        LogisticsBill: {
            "notes",
            "confirmed_at",
            "confirmed_by",
            "voided_at",
            "voided_by",
            "void_reason",
        },
        LogisticsBillLine: {
            "sku_id",
            "shipped_qty",
            "calculated_total_weight_kg",
            "calculated_total_volume_cbm",
            "actual_total_weight_kg",
            "actual_total_volume_cbm",
            "headhaul_cost",
            "handling_cost",
            "last_mile_cost",
            "unit_headhaul_cost",
            "unit_handling_cost",
            "unit_last_mile_cost",
            "notes",
        },
        ProductCostAssumptionProfile: {"platform_fee_rate"},
        SkuProfitEstimate: {
            "purchase_cost_source",
            "logistics_cost_source",
            "storage_cost_source",
            "assumption_profile_id",
        },
    }
    for model, columns in expected.items():
        assert columns <= {column.name for column in inspect(model).columns}


def test_feishu_projection_models_are_isolated_in_ops_schema():
    expected = {
        FeishuProjectionConfig: {"provider_code", "spu_table_id", "sku_table_id", "initialized_at"},
        FeishuProjectionTask: {"entity_type", "business_key", "payload_hash", "status", "attempt_count"},
        FeishuProjectionLog: {"task_id", "status", "payload_hash", "error_message"},
    }
    for model, columns in expected.items():
        assert model.__table__.schema == "ops"
        assert columns <= {column.name for column in inspect(model).columns}
