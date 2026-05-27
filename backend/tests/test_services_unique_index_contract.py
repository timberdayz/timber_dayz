from pathlib import Path


def test_services_unique_index_contract_includes_platform_and_shop():
    source = Path("backend/services/platform_table_manager.py").read_text(encoding="utf-8")

    assert "platform_code, COALESCE(shop_id, ''), data_domain, granularity, data_hash" in source
    assert '(data_domain, sub_domain, granularity, data_hash)' not in source
