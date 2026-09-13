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
