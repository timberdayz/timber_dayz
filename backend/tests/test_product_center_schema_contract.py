from datetime import date

from sqlalchemy import inspect

from backend.schemas.product_center import ProductCenterBindingResponse
from modules.core.db import (
    BridgeErpSkuKey,
    BridgeSpuSku,
    DimErpSku,
    DimSpu,
)


def test_product_center_models_have_expected_tables_and_columns():
    expected = {
        DimSpu: {"spu", "spu_name", "category_l1", "category_l2", "main_image_url", "biz_status", "owner_user_id"},
        DimErpSku: {"sku_id", "sku_key", "erp_record_id", "weight_kg", "package_length_cm", "package_width_cm", "package_height_cm", "units_per_carton"},
        BridgeSpuSku: {"spu", "sku_id", "effective_from", "effective_to", "binding_status"},
        BridgeErpSkuKey: {"source_system", "source_platform", "source_shop_id", "source_key_type", "source_key", "sku_id"},
    }
    for model, columns in expected.items():
        actual = {column.name for column in inspect(model).columns}
        assert columns <= actual


def test_product_center_models_use_core_schema_and_business_keys():
    assert DimSpu.__table__.schema == "core"
    assert DimErpSku.__table__.schema == "core"
    assert BridgeSpuSku.__table__.schema == "core"
    assert BridgeErpSkuKey.__table__.schema == "core"
    assert any(const.name == "uq_dim_spu_spu" for const in DimSpu.__table__.constraints)
    assert any(const.name == "uq_dim_erp_sku_sku_key" for const in DimErpSku.__table__.constraints)
    assert any(index.name == "uq_bridge_spu_sku_current" for index in BridgeSpuSku.__table__.indexes)


def test_binding_response_accepts_sqlalchemy_orm_row():
    """Pydantic v2 needs from_attributes=True to validate SQLAlchemy ORM rows.

    Regression: the SKU 归属 history drawer returned HTTP 500 because the
    schema rejected raw BridgeSpuSku ORM objects.
    """
    row = BridgeSpuSku(
        id=1, spu="XH-TEST", sku_id=42,
        effective_from=date(2026, 1, 1), effective_to=None, binding_status="active",
    )
    payload = ProductCenterBindingResponse.model_validate(row)
    assert payload.spu == "XH-TEST"
    assert payload.sku_id == 42
    assert payload.effective_to is None
    assert payload.binding_status == "active"


def test_product_center_item_exposes_pricing_fields_as_optional():
    from backend.schemas.product_center import ProductCenterItem

    fields = ProductCenterItem.model_fields
    for name in (
        "creator_commission_rate",
        "creator_commission_rate_fallback",
        "current_discount_rate",
        "clearance_max_discount_rate",
        "min_selling_price",
        "min_selling_price_source",
        "min_selling_price_is_override",
        "min_selling_price_override",
        "min_selling_price_missing_reasons",
        "pricing_tier_label",
        "pricing_days_since_restock",
        "pricing_tier_source",
    ):
        assert name in fields, name
        assert fields[name].is_required() is False, name


def test_sku_write_models_accept_pricing_overrides():
    from backend.schemas.product_center import SkuBulkItem, SkuCreateRequest, SkuUpdateRequest

    for model in (SkuUpdateRequest, SkuBulkItem, SkuCreateRequest):
        assert "creator_commission_rate" in model.model_fields
        assert "min_selling_price_override" in model.model_fields


def test_pricing_policy_request_models_expose_single_discount_rate():
    from backend.schemas.product_center import (
        SkuPricingPolicyCreateRequest,
        SkuPricingPolicyUpdateRequest,
    )

    for model in (SkuPricingPolicyCreateRequest, SkuPricingPolicyUpdateRequest):
        assert "discount_rate" in model.model_fields
        assert "standard_discount_rate" not in model.model_fields
        assert "clearance_discount_rate" not in model.model_fields


def test_pricing_policy_update_request_cannot_deactivate_current_tier():
    """更新请求不得能改 status —— 否则当前行会从「当前生效规则」里消失，静默丢掉一档。"""
    from backend.schemas.product_center import (
        SkuPricingPolicyCreateRequest,
        SkuPricingPolicyUpdateRequest,
    )

    assert "status" not in SkuPricingPolicyUpdateRequest.model_fields
    # create 仍然可以指定初始状态（建出来的行若为 inactive，不进入当前规则集合）
    assert "status" in SkuPricingPolicyCreateRequest.model_fields


def test_profit_candidate_response_exposes_pricing_fields():
    """候选接口的 response_model 必须同步扩展，否则字段被 Pydantic 丢弃、前端护栏空转。"""
    from backend.schemas.product_center import PlatformSkuProfitCandidateResponse

    fields = PlatformSkuProfitCandidateResponse.model_fields
    for name in (
        "creator_commission_rate",
        "creator_commission_rate_fallback",
        "current_discount_rate",
        "clearance_max_discount_rate",
        "min_selling_price",
        "min_selling_price_source",
        "min_selling_price_is_override",
        "min_selling_price_override",
        "min_selling_price_missing_reasons",
        "pricing_tier_label",
        "pricing_days_since_restock",
        "pricing_tier_source",
        "min_selling_price_below",
    ):
        assert name in fields, name


def test_platform_option_and_fee_rate_request_expose_cost_rates():
    from backend.schemas.product_center import (
        PlatformFeeRateUpdateRequest,
        SkuOperatingPlatformOption,
    )

    for model in (PlatformFeeRateUpdateRequest, SkuOperatingPlatformOption):
        assert "default_creator_commission_rate" in model.model_fields
        assert "other_cost_rate" in model.model_fields


def test_orm_models_expose_pricing_columns_and_policy_table():
    """ORM 层断言：能提前抓住 import 期崩溃（例如 Index 误传 schema=）。"""
    from modules.core.db import DimErpSku, DimPlatform, SkuPricingPolicy

    sku_columns = {c.name for c in DimErpSku.__table__.columns}
    assert {"creator_commission_rate", "min_selling_price_override"} <= sku_columns

    platform_columns = {c.name for c in DimPlatform.__table__.columns}
    assert {"default_creator_commission_rate", "other_cost_rate"} <= platform_columns

    policy_columns = {c.name for c in SkuPricingPolicy.__table__.columns}
    assert {
        "policy_id", "min_restock_days", "tier_label", "discount_rate",
        "target_margin_rate", "platform_basis", "effective_from", "effective_to",
        "status", "source", "version", "notes",
    } <= policy_columns

    constraint_names = {c.name for c in SkuPricingPolicy.__table__.constraints}
    assert {
        "uq_sku_pricing_policy_tier_start",
        "ck_sku_pricing_policy_age_start",
        "ck_sku_pricing_policy_discount_rate",
        "ck_sku_pricing_policy_target_margin",
        "ck_sku_pricing_policy_window",
        "ck_sku_pricing_policy_status",
    } <= constraint_names

    index_names = {i.name for i in SkuPricingPolicy.__table__.indexes}
    assert {
        "uq_sku_pricing_policies_current",
        "ix_sku_pricing_policy_scope",
    } <= index_names

    # Index 不接受 schema= 关键字，索引 schema 由表继承
    assert SkuPricingPolicy.__table__.schema == "finance"
    for index in SkuPricingPolicy.__table__.indexes:
        assert index.table.schema == "finance"


def test_product_center_item_validates_bare_orm_row():
    """回归护栏：ProductCenterItem 被用于校验裸 ORM 行，新增字段必填会直接打断既有流程。"""
    from backend.schemas.product_center import ProductCenterItem
    from modules.core.db import DimErpSku

    row = DimErpSku(sku_id=9001, sku_key="TEST-SKU-1", sku_name="测试SKU")
    item = ProductCenterItem.model_validate(row)
    assert item.min_selling_price is None
    assert item.pricing_tier_source is None
    assert item.min_selling_price_missing_reasons == []
