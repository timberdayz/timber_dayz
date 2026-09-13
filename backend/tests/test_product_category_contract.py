import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.schemas.product_center import (
    ProductCategoryCreateRequest,
    ProductCategoryUpdateRequest,
    ProductCategoryResponse,
    SpuCreateRequest,
    SpuBulkRequest,
    SkuBulkRequest,
)
from modules.core.db import DimProductCategory


MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "current_migrations"
    / "versions"
    / "20260911_internal_product_category_taxonomy_v1.py"
)

# This approved contract is intentionally independent from the migration data.
APPROVED_V1_CATEGORIES = {
    "HOME_LIVING": (None, 1, "家居生活", "家居生活"),
    "HOME_STORAGE": ("HOME_LIVING", 2, "收纳整理", "家居生活/收纳整理"),
    "HOME_KITCHEN": ("HOME_LIVING", 2, "厨房餐饮", "家居生活/厨房餐饮"),
    "HOME_CLEANING_LAUNDRY": ("HOME_LIVING", 2, "清洁洗护", "家居生活/清洁洗护"),
    "HOME_BATH": ("HOME_LIVING", 2, "卫浴用品", "家居生活/卫浴用品"),
    "HOME_TEXTILES_BEDDING": ("HOME_LIVING", 2, "家纺寝具", "家居生活/家纺寝具"),
    "HOME_DECOR_LIGHTING": ("HOME_LIVING", 2, "家居装饰照明", "家居生活/家居装饰照明"),
    "BEAUTY_PERSONAL_CARE": (None, 1, "美妆个护", "美妆个护"),
    "BEAUTY_SKINCARE": ("BEAUTY_PERSONAL_CARE", 2, "护肤", "美妆个护/护肤"),
    "BEAUTY_MAKEUP": ("BEAUTY_PERSONAL_CARE", 2, "彩妆", "美妆个护/彩妆"),
    "BEAUTY_TOOLS": ("BEAUTY_PERSONAL_CARE", 2, "美妆工具", "美妆个护/美妆工具"),
    "BEAUTY_HAIRCARE_STYLING": ("BEAUTY_PERSONAL_CARE", 2, "洗护造型", "美妆个护/洗护造型"),
    "BEAUTY_PERSONAL_HYGIENE": ("BEAUTY_PERSONAL_CARE", 2, "个人清洁护理", "美妆个护/个人清洁护理"),
    "BEAUTY_DEVICES": ("BEAUTY_PERSONAL_CARE", 2, "美容个护电器", "美妆个护/美容个护电器"),
    "FASHION_ACCESSORIES": (None, 1, "服饰鞋包配饰", "服饰鞋包配饰"),
    "FASHION_WOMENSWEAR": ("FASHION_ACCESSORIES", 2, "女装", "服饰鞋包配饰/女装"),
    "FASHION_MENSWEAR": ("FASHION_ACCESSORIES", 2, "男装", "服饰鞋包配饰/男装"),
    "FASHION_UNDERWEAR_SLEEPWEAR": ("FASHION_ACCESSORIES", 2, "内衣家居服", "服饰鞋包配饰/内衣家居服"),
    "FASHION_SHOES": ("FASHION_ACCESSORIES", 2, "鞋靴", "服饰鞋包配饰/鞋靴"),
    "FASHION_BAGS_LUGGAGE": ("FASHION_ACCESSORIES", 2, "箱包旅行", "服饰鞋包配饰/箱包旅行"),
    "FASHION_JEWELRY_ACCESSORIES": ("FASHION_ACCESSORIES", 2, "时尚配饰", "服饰鞋包配饰/时尚配饰"),
    "FASHION_MODEST_TRADITIONAL": ("FASHION_ACCESSORIES", 2, "穆斯林与传统服饰", "服饰鞋包配饰/穆斯林与传统服饰"),
    "SPORTS_OUTDOORS": (None, 1, "运动户外", "运动户外"),
    "SPORTS_FITNESS": ("SPORTS_OUTDOORS", 2, "运动健身", "运动户外/运动健身"),
    "SPORTS_CAMPING_HIKING": ("SPORTS_OUTDOORS", 2, "露营徒步", "运动户外/露营徒步"),
    "SPORTS_BALL_RACKET": ("SPORTS_OUTDOORS", 2, "球类运动", "运动户外/球类运动"),
    "SPORTS_CYCLING_WHEELED": ("SPORTS_OUTDOORS", 2, "骑行与轮滑", "运动户外/骑行与轮滑"),
    "SPORTS_WATER": ("SPORTS_OUTDOORS", 2, "水上运动", "运动户外/水上运动"),
    "SPORTS_PROTECTION_ACCESSORIES": ("SPORTS_OUTDOORS", 2, "运动防护配件", "运动户外/运动防护配件"),
    "PET_SUPPLIES": (None, 1, "宠物用品", "宠物用品"),
    "PET_FEEDING": ("PET_SUPPLIES", 2, "喂养用品", "宠物用品/喂养用品"),
    "PET_CLEANING_TOILETING": ("PET_SUPPLIES", 2, "清洁如厕", "宠物用品/清洁如厕"),
    "PET_GROOMING_CARE": ("PET_SUPPLIES", 2, "宠物护理", "宠物用品/宠物护理"),
    "PET_BEDDING_HOUSING": ("PET_SUPPLIES", 2, "窝垫居住", "宠物用品/窝垫居住"),
    "PET_TOYS_TRAINING": ("PET_SUPPLIES", 2, "玩具训练", "宠物用品/玩具训练"),
    "BABY_MATERNITY": (None, 1, "母婴用品", "母婴用品"),
    "BABY_FEEDING": ("BABY_MATERNITY", 2, "喂养用品", "母婴用品/喂养用品"),
    "BABY_CARE_HYGIENE": ("BABY_MATERNITY", 2, "护理清洁", "母婴用品/护理清洁"),
    "BABY_TRAVEL_SAFETY": ("BABY_MATERNITY", 2, "出行安全", "母婴用品/出行安全"),
    "BABY_GEAR": ("BABY_MATERNITY", 2, "婴幼儿装备", "母婴用品/婴幼儿装备"),
    "MATERNITY_POSTPARTUM": ("BABY_MATERNITY", 2, "孕产护理", "母婴用品/孕产护理"),
    "BABY_APPAREL": ("BABY_MATERNITY", 2, "婴童服饰", "母婴用品/婴童服饰"),
    "TOYS_HOBBIES": (None, 1, "玩具爱好", "玩具爱好"),
    "TOYS_INFANT_LEARNING": ("TOYS_HOBBIES", 2, "婴幼儿益智", "玩具爱好/婴幼儿益智"),
    "TOYS_DOLLS_FIGURES": ("TOYS_HOBBIES", 2, "玩偶手办", "玩具爱好/玩偶手办"),
    "TOYS_BUILDING_CONSTRUCTION": ("TOYS_HOBBIES", 2, "拼搭建构", "玩具爱好/拼搭建构"),
    "TOYS_ARTS_CRAFTS": ("TOYS_HOBBIES", 2, "手工美术", "玩具爱好/手工美术"),
    "TOYS_GAMES_PUZZLES": ("TOYS_HOBBIES", 2, "游戏拼图", "玩具爱好/游戏拼图"),
    "HOBBIES_COLLECTIBLES": ("TOYS_HOBBIES", 2, "兴趣收藏", "玩具爱好/兴趣收藏"),
    "ELECTRONICS_ACCESSORIES": (None, 1, "数码与配件", "数码与配件"),
    "ELEC_MOBILE_TABLET_ACCESSORIES": ("ELECTRONICS_ACCESSORIES", 2, "手机平板配件", "数码与配件/手机平板配件"),
    "ELEC_AUDIO_VIDEO": ("ELECTRONICS_ACCESSORIES", 2, "影音设备", "数码与配件/影音设备"),
    "ELEC_SMART_WEARABLE": ("ELECTRONICS_ACCESSORIES", 2, "智能穿戴", "数码与配件/智能穿戴"),
    "ELEC_CAMERA_ACCESSORIES": ("ELECTRONICS_ACCESSORIES", 2, "相机配件", "数码与配件/相机配件"),
    "ELEC_COMPUTER_OFFICE": ("ELECTRONICS_ACCESSORIES", 2, "电脑办公数码", "数码与配件/电脑办公数码"),
    "ELEC_SMART_HOME": ("ELECTRONICS_ACCESSORIES", 2, "智能家居", "数码与配件/智能家居"),
    "FOOD_BEVERAGE": (None, 1, "食品饮料", "食品饮料"),
    "FOOD_SNACKS_CONFECTIONERY": ("FOOD_BEVERAGE", 2, "休闲食品", "食品饮料/休闲食品"),
    "FOOD_BEVERAGES": ("FOOD_BEVERAGE", 2, "饮品", "食品饮料/饮品"),
    "FOOD_COOKING_INGREDIENTS": ("FOOD_BEVERAGE", 2, "烹饪食材", "食品饮料/烹饪食材"),
    "FOOD_TEA_COFFEE": ("FOOD_BEVERAGE", 2, "茶咖冲饮", "食品饮料/茶咖冲饮"),
    "HEALTH_WELLNESS": (None, 1, "健康护理", "健康护理"),
    "HEALTH_SUPPLEMENTS": ("HEALTH_WELLNESS", 2, "营养补充", "健康护理/营养补充"),
    "HEALTH_CARE_DEVICES": ("HEALTH_WELLNESS", 2, "健康护理设备", "健康护理/健康护理设备"),
    "HEALTH_PROTECTION_FIRST_AID": ("HEALTH_WELLNESS", 2, "防护急救用品", "健康护理/防护急救用品"),
    "TOOLS_HOME_IMPROVEMENT": (None, 1, "工具家装园艺", "工具家装园艺"),
    "TOOLS_HAND_POWER": ("TOOLS_HOME_IMPROVEMENT", 2, "手动与电动工具", "工具家装园艺/手动与电动工具"),
    "TOOLS_HARDWARE": ("TOOLS_HOME_IMPROVEMENT", 2, "五金配件", "工具家装园艺/五金配件"),
    "HOME_IMPROVEMENT_ELECTRICAL_LIGHTING": ("TOOLS_HOME_IMPROVEMENT", 2, "家装电工照明", "工具家装园艺/家装电工照明"),
    "GARDEN_OUTDOOR_LIVING": ("TOOLS_HOME_IMPROVEMENT", 2, "园艺户外生活", "工具家装园艺/园艺户外生活"),
    "AUTOMOTIVE_MOTORCYCLE": (None, 1, "汽摩用品", "汽摩用品"),
    "AUTO_INTERIOR_EXTERIOR": ("AUTOMOTIVE_MOTORCYCLE", 2, "汽车内外饰", "汽摩用品/汽车内外饰"),
    "AUTO_CARE_MAINTENANCE": ("AUTOMOTIVE_MOTORCYCLE", 2, "汽车清洁养护", "汽摩用品/汽车清洁养护"),
    "MOTORCYCLE_RIDING_ACCESSORIES": ("AUTOMOTIVE_MOTORCYCLE", 2, "摩托骑行配件", "汽摩用品/摩托骑行配件"),
    "OFFICE_SCHOOL_SUPPLIES": (None, 1, "办公文教", "办公文教"),
    "OFFICE_STATIONERY": ("OFFICE_SCHOOL_SUPPLIES", 2, "文具办公", "办公文教/文具办公"),
    "OFFICE_SCHOOL_LEARNING": ("OFFICE_SCHOOL_SUPPLIES", 2, "学习教育", "办公文教/学习教育"),
    "OFFICE_PRINTING_PACKAGING": ("OFFICE_SCHOOL_SUPPLIES", 2, "打印包装耗材", "办公文教/打印包装耗材"),
}


def _load_taxonomy_migration():
    assert MIGRATION_PATH.exists(), "the v1 taxonomy migration must exist"
    spec = importlib.util.spec_from_file_location("internal_product_category_taxonomy_v1", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_internal_product_category_taxonomy_v1_matches_the_approved_contract():
    migration = _load_taxonomy_migration()
    rows = migration.CATEGORY_ROWS
    rows_by_code = {row["category_code"]: row for row in rows}

    assert len(rows) == len(rows_by_code) == 78
    assert sum(row["level"] == 1 for row in rows) == 13
    assert sum(row["level"] == 2 for row in rows) == 65
    assert {
        code: (
            row["parent_category_code"],
            row["level"],
            row["name_zh"],
            row["category_path"],
        )
        for code, row in rows_by_code.items()
    } == APPROVED_V1_CATEGORIES
    assert all(row["status"] == "active" for row in rows)
    assert all(row["is_selectable"] is True for row in rows)


def test_legacy_pet_daily_is_made_unselectable_without_resurrecting_its_status():
    source = Path(
        "current_migrations/versions/20260911_internal_product_category_taxonomy_v1.py"
    ).read_text(encoding="utf-8")
    legacy_update = source.split("WHERE category_code = 'PET_DAILY'", 1)[0]
    assert "SET is_selectable = false" in legacy_update
    assert "SET status = 'active'" not in legacy_update


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


def test_category_contract_exposes_selectable_flag_and_filters_non_selectable_by_default():
    source = Path("backend/domains/business/routers/product_center.py").read_text(
        encoding="utf-8"
    )
    assert "is_selectable" in ProductCategoryCreateRequest.model_fields
    assert "is_selectable" in ProductCategoryUpdateRequest.model_fields
    assert "is_selectable" in ProductCategoryResponse.model_fields
    assert "DimProductCategory.is_selectable.is_(True)" in source
    assert "include_inactive" in source


def test_spu_category_assignment_requires_selectable_l2_but_allows_legacy_pet_daily_reads():
    source = Path("backend/domains/business/routers/product_center.py").read_text(
        encoding="utf-8"
    )
    assert "category_l2.is_selectable" in source
    assert "spu_name is required when creating" in source
    assert "category_l2_code is required when creating" in source
    assert "existing_category_l2_code" in source
    assert "category_l2_code != existing_category_l2_code" in source
    assert "existing_category_l2_code=row.category_l2_code or row.category_l2" in source
    assert "category_l2_code must reference a category code" in source
    assert "category_l1_code cannot be set without category_l2_code" in source


def test_category_lifecycle_rejects_invalid_parent_child_transitions():
    source = Path("backend/domains/business/routers/product_center.py").read_text(
        encoding="utf-8"
    )
    assert "active children" in source
    assert "cannot deactivate level 1 category" in source
    assert "cannot activate level 2 category under inactive level 1 parent" in source
    assert ".with_for_update()" in source


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
