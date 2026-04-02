from backend.utils.schema_cleanup_wave2_proofs import collect_wave2_candidate_proofs


def test_wave2_candidates_expose_model_schema_and_expected_target():
    report = collect_wave2_candidate_proofs()

    assert report["entity_aliases"]["expected_target_schema"] == "b_class"
    assert report["entity_aliases"]["model_schema"] == "b_class"

    assert report["staging_raw_data"]["expected_target_schema"] == "b_class"
    assert report["staging_raw_data"]["model_schema"] == "b_class"

    assert report["dim_shops"]["expected_target_schema"] == "core"
    assert report["dim_shops"]["model_schema"] == "core"


def test_dim_shops_is_flagged_as_high_risk_with_live_read_and_write_paths():
    report = collect_wave2_candidate_proofs()

    candidate = report["dim_shops"]

    assert candidate["risk_level"] == "high"
    assert candidate["runtime_read_file_count"] > 0
    assert candidate["runtime_write_file_count"] > 0
    assert candidate["search_path_public_before_target"] is True
    assert candidate["ready_for_wave2_migration"] is False


def test_entity_aliases_and_staging_raw_data_remain_proof_only():
    report = collect_wave2_candidate_proofs()

    for table_name in ("entity_aliases", "staging_raw_data"):
        candidate = report[table_name]
        assert candidate["risk_level"] == "medium"
        assert candidate["ready_for_wave2_migration"] is False
        assert candidate["historical_target_ref_count"] > 0
        assert "runtime proof" in candidate["blocker_reason"]
