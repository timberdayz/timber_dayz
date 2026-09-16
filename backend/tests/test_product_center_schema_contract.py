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
