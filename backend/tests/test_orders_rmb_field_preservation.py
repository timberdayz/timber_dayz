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
