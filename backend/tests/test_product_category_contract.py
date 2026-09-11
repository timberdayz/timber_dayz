import pytest
from pydantic import ValidationError
from pathlib import Path

from backend.schemas.product_center import (
    ProductCategoryCreateRequest,
    SpuCreateRequest,
    SpuBulkRequest,
    SkuBulkRequest,
)
from modules.core.db import DimProductCategory


def test_company_category_model_has_stable_code_and_chinese_display_fields():
    columns = {column.name for column in DimProductCategory.__table__.columns}
    assert {
        "category_code",
        "parent_category_code",
        "level",
        "name_zh",
        "name_en",
        "category_path",
        "status",
        "version",
        "effective_from",
        "effective_to",
        "description",
    } <= columns


def test_category_request_requires_two_level_code_and_chinese_name():
    category = ProductCategoryCreateRequest(
        category_code="SPORTS_FITNESS",
        level=1,
        name_zh="运动健身",
        name_en="Sports & Fitness",
        version="v1",
    )
    assert category.level == 1
    with pytest.raises(ValidationError):
        ProductCategoryCreateRequest(
            category_code="sports fitness",
            level=1,
            name_zh="运动健身",
            version="v1",
        )


def test_spu_uses_stable_secondary_category_code_and_strict_identifier():
    request = SpuCreateRequest(
        spu="HOME-0001",
        spu_name="收纳盒",
        category_l2="STORAGE_ORGANIZATION",
    )
    assert request.category_l2 == "STORAGE_ORGANIZATION"
    with pytest.raises(ValidationError):
        SpuCreateRequest(spu="Home-1", spu_name="收纳盒", category_l2="X")


def test_spu_and_sku_master_data_include_cost_and_loss_drivers():
    from modules.core.db import DimErpSku, DimSpu

    assert {"logistics_damage_rate", "return_loss_rate"} <= {
        column.name for column in DimSpu.__table__.columns
    }
    assert {"expected_logistics_cost", "expected_storage_cost"} <= {
        column.name for column in DimErpSku.__table__.columns
    }


def test_bulk_requests_are_explicit_and_non_empty():
    assert len(SpuBulkRequest(items=[SpuCreateRequest(spu="HOME-0001", spu_name="收纳")]).items) == 1
    assert len(SkuBulkRequest(items=[]).items) == 0


def test_product_center_exposes_bulk_save_endpoints():
    source = Path("backend/domains/business/routers/product_center.py").read_text(
        encoding="utf-8"
    )
    assert '@router.post("/api/spus/bulk"' in source
    assert '@router.post("/api/skus/bulk"' in source


def test_company_category_migration_is_safe_for_existing_current_schema_databases():
    source = Path(
        "current_migrations/versions/20260911_company_product_categories.py"
    ).read_text(encoding="utf-8")

    assert "_has_table" in source
    assert "_has_column" in source
    assert "if_not_exists=True" in source
    assert "ON CONFLICT (category_code) DO NOTHING" in source


def test_purchase_order_lines_expose_the_canonical_sku_mapping_when_available():
    source = Path("backend/domains/business/routers/product_center.py").read_text(
        encoding="utf-8"
    )

    assert "BridgeErpSkuKey" in source
    assert '"sku_id": canonical_sku_ids.get(row.platform_sku)' in source


def test_baseline_profit_keeps_platform_fee_from_the_legacy_read_only_profile():
    source = Path("backend/services/product_finance_service.py").read_text(
        encoding="utf-8"
    )

    assert "platform_fee_rate=assumption.platform_fee_rate if assumption else None" in source


def test_profit_save_uses_the_preview_version_when_the_client_does_not_supply_one():
    source = Path("backend/services/product_finance_service.py").read_text(
        encoding="utf-8"
    )

    assert 'assumption_version=data.get("assumption_version") or preview["assumption_version"]' in source
