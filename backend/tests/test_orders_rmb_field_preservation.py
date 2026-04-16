import pytest


def test_orders_rmb_fields_preserve_distinct_internal_keys():
    from backend.services.data_ingestion_service import normalize_row_fields_for_domain

    normalized = normalize_row_fields_for_domain(
        domain="orders",
        row={
            "利润": "12.5",
            "利润(RMB)": "88.1",
            "买家支付": "9.1",
            "买家支付(RMB)": "64.2",
        },
    )

    assert normalized["profit"] == "12.5"
    assert normalized["profit_rmb"] == "88.1"
    assert normalized["buyer_payment"] == "9.1"
    assert normalized["buyer_payment_rmb"] == "64.2"


def test_orders_store_label_is_preserved_as_store_label_raw():
    from backend.services.data_ingestion_service import normalize_row_fields_for_domain

    normalized = normalize_row_fields_for_domain(
        domain="orders",
        row={
            "店铺": "Shopee新加坡1店",
            "站点": "新加坡",
        },
    )

    assert normalized["store_label_raw"] == "Shopee新加坡1店"
    assert normalized["site"] == "新加坡"


def test_orders_rmb_fields_do_not_silently_overwrite_legacy_fields():
    from backend.services.data_ingestion_service import normalize_row_fields_for_domain

    normalized = normalize_row_fields_for_domain(
        domain="orders",
        row={
            "订单原始金额": "10.0",
            "订单原始金额(RMB)": "70.0",
            "平台佣金": "1.2",
            "平台佣金(RMB)": "8.4",
            "预估回款金额": "6.5",
            "预估回款金额(RMB)": "45.5",
        },
    )

    assert normalized["original_amount"] == "10.0"
    assert normalized["original_amount_rmb"] == "70.0"
    assert normalized["platform_commission"] == "1.2"
    assert normalized["platform_commission_rmb"] == "8.4"
    assert normalized["estimated_settlement"] == "6.5"
    assert normalized["estimated_settlement_rmb"] == "45.5"


def test_orders_rmb_fields_avoid_collision_for_settlement_amount_pairs():
    from backend.services.data_ingestion_service import normalize_row_fields_for_domain

    normalized = normalize_row_fields_for_domain(
        domain="orders",
        row={
            "已结算金额": "100.0",
            "已结算金额(RMB)": "700.0",
        },
    )

    assert normalized["已结算金额"] == "100.0"
    assert normalized["已结算金额_rmb"] == "700.0"


def test_orders_rmb_fields_avoid_collision_for_real_tiktok_orders_amount_pairs():
    from backend.services.data_ingestion_service import normalize_row_fields_for_domain

    normalized = normalize_row_fields_for_domain(
        domain="orders",
        row={
            "利润": "12.5",
            "利润(RMB)": "88.1",
            "已结算金额": "100.0",
            "已结算金额(RMB)": "700.0",
            "买家实付金额": "90.0",
            "买家实付金额(RMB)": "630.0",
        },
    )

    assert normalized["profit"] == "12.5"
    assert normalized["profit_rmb"] == "88.1"
    assert normalized["已结算金额"] == "100.0"
    assert normalized["已结算金额_rmb"] == "700.0"
    assert normalized["买家实付金额"] == "90.0"
    assert normalized["买家实付金额_rmb"] == "630.0"


def test_orders_tax_abbreviation_fields_preserve_distinct_ascii_keys():
    from backend.services.data_ingestion_service import normalize_row_fields_for_domain

    normalized = normalize_row_fields_for_domain(
        domain="orders",
        row={
            "VAT": "1.0",
            "VAT(RMB)": "7.0",
            "SST": "2.0",
            "SST(RMB)": "14.0",
            "GST": "3.0",
            "GST(RMB)": "21.0",
        },
    )

    assert normalized["vat"] == "1.0"
    assert normalized["vat_rmb"] == "7.0"
    assert normalized["sst"] == "2.0"
    assert normalized["sst_rmb"] == "14.0"
    assert normalized["gst"] == "3.0"
    assert normalized["gst_rmb"] == "21.0"


def test_non_orders_domains_keep_existing_currency_suffix_stripping_behavior():
    from backend.services.data_ingestion_service import normalize_row_fields_for_domain

    normalized = normalize_row_fields_for_domain(
        domain="products",
        row={
            "利润(RMB)": "88.1",
        },
    )

    assert normalized["利润"] == "88.1"
    assert "profit_rmb" not in normalized


def test_orders_rmb_source_fields_have_explicit_alias_mappings():
    from backend.services.field_mapping.mapper import COMPREHENSIVE_ALIAS_DICTIONARY

    profit_rmb = "".join(chr(c) for c in [21033, 28070]) + "(rmb)"
    original_amount_rmb = "".join(chr(c) for c in [35746, 21333, 21407, 22987, 37329, 39069]) + "(rmb)"
    buyer_payment_rmb = "".join(chr(c) for c in [20080, 23478, 25903, 20184]) + "(rmb)"
    platform_commission_rmb = "".join(chr(c) for c in [24179, 21488, 20323, 37329]) + "(rmb)"
    estimated_settlement_rmb = "".join(chr(c) for c in [39044, 20272, 22238, 27454, 37329, 39069]) + "(rmb)"

    assert COMPREHENSIVE_ALIAS_DICTIONARY[profit_rmb] == "profit_rmb"
    assert COMPREHENSIVE_ALIAS_DICTIONARY[original_amount_rmb] == "original_amount_rmb"
    assert COMPREHENSIVE_ALIAS_DICTIONARY[buyer_payment_rmb] == "buyer_payment_rmb"
    assert COMPREHENSIVE_ALIAS_DICTIONARY[platform_commission_rmb] == "platform_commission_rmb"
    assert COMPREHENSIVE_ALIAS_DICTIONARY[estimated_settlement_rmb] == "estimated_settlement_rmb"


def test_inventory_domain_preserves_original_sku_header_names():
    from backend.services.data_ingestion_service import normalize_row_fields_for_domain

    row = {
        "*商品SKU": "SBF002-ZSHD-035",
        "*商品名称": "demo",
        "可用库存": 102,
    }

    normalized = normalize_row_fields_for_domain(
        domain="inventory",
        row=row,
    )

    assert normalized == row


def test_field_mapping_ingest_uses_orders_domain_specific_normalization():
    from pathlib import Path

    text = Path("backend/routers/field_mapping_ingest.py").read_text(encoding="utf-8")

    assert "normalize_row_fields_for_domain(" in text


def test_field_mapping_ingest_loads_template_field_parse_rules_for_b_class_import():
    from pathlib import Path

    text = Path("backend/routers/field_mapping_ingest.py").read_text(encoding="utf-8")

    assert "_load_field_parse_rules_for_file(" in text
    assert "raw_data_importer.field_parse_rules = field_parse_rules" in text


def test_field_mapping_ingest_blocks_legacy_fallback_when_template_parse_rules_fail():
    from pathlib import Path

    text = Path("backend/routers/field_mapping_ingest.py").read_text(encoding="utf-8")

    assert 'getattr(raw_data_importer, "field_parse_rules", None)' in text
    assert "and staged == 0" in text
    assert "\n                raise" in text
