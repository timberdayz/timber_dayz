from pathlib import Path


def test_services_upsert_conflict_contract_uses_platform_and_shop():
    source = Path("backend/services/raw_data_importer.py").read_text(encoding="utf-8")

    assert "(platform_code, COALESCE(shop_id, ''), data_domain, granularity, data_hash)" in source
    assert "(platform_code, shop_id, data_domain, granularity, data_hash)" in source
    assert "(data_domain, sub_domain, granularity, data_hash)" not in source
