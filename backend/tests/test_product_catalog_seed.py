from openpyxl import Workbook

from scripts.seed_product_catalog import load_lookup, validate_rows


def test_product_catalog_seed_deduplicates_skus_and_validates_categories(tmp_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["SKU code", "SPU code", "一级 code", "一级中文", "二级 code", "二级中文", "中文商品名"])
    sheet.append(["SKU-1", "XH-TOYS-YSC", "TOYS_HOBBIES", "玩具爱好", "HOBBIES_COLLECTIBLES", "兴趣收藏", "钥匙扣"])
    sheet.append(["SKU-1", "XH-TOYS-YSC", "TOYS_HOBBIES", "玩具爱好", "HOBBIES_COLLECTIBLES", "兴趣收藏", "钥匙扣"])
    path = tmp_path / "lookup.xlsx"
    workbook.save(path)

    rows, duplicates = load_lookup(path)

    assert len(rows) == 1
    assert duplicates == ["SKU-1"]
    assert validate_rows(rows) == []


def test_product_catalog_seed_rejects_unclassified_sku(tmp_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["SKU code", "SPU code", "一级 code", "一级中文", "二级 code", "二级中文", "中文商品名"])
    sheet.append(["SKU-1", "XH-TOYS-YSC", "TOYS_HOBBIES", "玩具爱好", "", "", "待评估"])
    path = tmp_path / "lookup.xlsx"
    workbook.save(path)

    rows, _ = load_lookup(path)

    assert any("missing secondary category" in error for error in validate_rows(rows))


def test_product_catalog_seed_excludes_tbd_rows_from_apply_set():
    from scripts.seed_product_catalog import rows_ready_for_apply

    rows = [
        {"sku_key": "SKU-1", "spu": "XH-TOYS-YSC", "category_l1_code": "TOYS_HOBBIES", "category_l2_code": "HOBBIES_COLLECTIBLES", "spu_name": "收藏品"},
        {"sku_key": "SKU-TBD", "spu": "XH-TBD-CTS", "category_l1_code": "待评估", "category_l2_code": "待评估", "spu_name": "待评估"},
    ]

    ready, deferred = rows_ready_for_apply(rows)

    assert [row["sku_key"] for row in ready] == ["SKU-1"]
    assert deferred == ["SKU-TBD"]


def test_product_catalog_seed_contains_confirmed_warehouse_seed():
    from scripts.seed_product_catalog import WAREHOUSE_SEED

    assert {row["warehouse_code"] for row in WAREHOUSE_SEED} == {
        "SG-01",
        "MY-01",
        "PH-01-CHILD",
        "PH-03-FASHION",
        "PH-REPAIR",
    }
    assert all(row["country_code"] in {"SG", "MY", "PH"} for row in WAREHOUSE_SEED)
