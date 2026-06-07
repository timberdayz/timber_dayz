from backend.services.deduplication_service import DeduplicationService


def test_deduplication_hash_resolves_product_id_from_header_binding():
    row = {"商品 ID": "P-001", "商品名": "Test Product"}
    bindings = [
        {
            "raw_name": "商品 ID",
            "display_name": "商品 ID",
            "semantic_key": "product_id",
            "semantic_review_status": "confirmed_semantic",
            "aliases": ["商品 ID", "product_id"],
            "required": False,
            "hash_participates": True,
        },
        {
            "raw_name": "商品名",
            "display_name": "商品名",
            "semantic_key": None,
            "semantic_review_status": "confirmed_non_semantic",
            "aliases": [],
            "required": False,
            "hash_participates": False,
        },
    ]

    service = DeduplicationService(db=None)

    first_hash = service.calculate_data_hash(
        row,
        deduplication_fields=["product_id"],
        header_bindings=bindings,
    )
    second_hash = service.calculate_data_hash(
        {"商品 ID": "P-002", "商品名": "Test Product"},
        deduplication_fields=["product_id"],
        header_bindings=bindings,
    )

    assert first_hash != second_hash
