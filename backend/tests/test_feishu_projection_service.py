from backend.services.feishu_projection_service import _sku_table_fields, _spu_table_fields, projection_payload_hash


def test_projection_payload_hash_is_stable_for_same_payload_content():
    assert projection_payload_hash({"sku_id": 1, "name": "SKU-A"}) == projection_payload_hash({"name": "SKU-A", "sku_id": 1})


def test_projection_table_field_definitions_use_storage_keys():
    assert _spu_table_fields()[0] == {"name": "SPU", "type": "text"}
    assert _sku_table_fields()[0] == {"name": "ERP SKU", "type": "text"}
    assert all(field["type"] != "formula" for field in _spu_table_fields() + _sku_table_fields())
