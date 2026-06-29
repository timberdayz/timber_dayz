from backend.services.data_sync_service import DataSyncService


def test_alias_only_header_change_does_not_block_sync():
    assert (
        DataSyncService._is_blocking_header_change(
            {
                "detected": True,
                "is_exact_match": False,
                "is_semantic_match": True,
                "added_fields": ["TikTok 平台佣金"],
                "removed_fields": ["TikTok Shop平台佣金"],
            }
        )
        is False
    )


def test_non_breaking_semantic_contract_header_change_does_not_block_sync():
    assert (
        DataSyncService._is_blocking_header_change(
            {
                "detected": True,
                "is_exact_match": False,
                "is_semantic_match": False,
                "semantic_contract_status": "non_breaking_drift",
                "blocking_changes": [],
                "missing_required_keys": [],
                "added_fields": ["profit"],
                "removed_fields": ["estimated_settlement_amount"],
            }
        )
        is False
    )


def test_true_structural_header_change_blocks_sync():
    assert (
        DataSyncService._is_blocking_header_change(
            {
                "detected": True,
                "is_exact_match": False,
                "is_semantic_match": False,
                "added_fields": ["新字段"],
                "removed_fields": ["旧字段"],
            }
        )
        is True
    )


def test_match_rate_is_formatted_as_percentage_value_not_ratio():
    assert DataSyncService._format_header_match_rate(91.7) == "91.7%"
