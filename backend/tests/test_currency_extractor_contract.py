from backend.services.currency_extractor import CurrencyExtractor


def test_currency_extractor_ignores_identifier_like_sku_fields():
    extractor = CurrencyExtractor()

    assert extractor.extract_currency_code("平台SKU") is None
    assert extractor.extract_currency_code("平台SKU(MYR)") is None
    assert extractor.extract_currency_code("订单编号(MMK)") is None


def test_currency_extractor_still_extracts_real_currency_fields():
    extractor = CurrencyExtractor()

    assert extractor.extract_currency_code("买家支付(MYR)") == "MYR"
