from backend.services.sync_standardization_quality_service import SyncQualitySnapshot, build_sync_quality_warnings


def test_sync_quality_warns_when_hash_distinct_is_abnormally_low():
    snapshot = SyncQualitySnapshot(
        raw_rows=100,
        distinct_hashes=1,
        semantic_rows=100,
        semantic_non_null_rates={"product_id": 1.0},
        mart_rows=100,
    )

    warnings = build_sync_quality_warnings(snapshot)

    assert "Hash 风险: distinct data_hash 只有 1/100，可能存在身份字段缺失导致覆盖。" in warnings


def test_sync_quality_warns_when_semantic_key_fields_are_empty():
    snapshot = SyncQualitySnapshot(
        raw_rows=8,
        distinct_hashes=8,
        semantic_rows=8,
        semantic_non_null_rates={"product_id": 0.0, "product_name": 0.0},
        mart_rows=0,
    )

    warnings = build_sync_quality_warnings(snapshot)

    assert "标准化异常: product_id 非空率为 0，semantic 层可能缺少字段别名。" in warnings
    assert "标准化异常: product_name 非空率为 0，semantic 层可能缺少字段别名。" in warnings
    assert "标准化异常: mart 层未生成记录。" in warnings
