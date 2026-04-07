from backend.utils.schema_cleanup_low_risk_proofs import collect_low_risk_candidate_proofs


def test_target_breakdown_has_authoritative_a_class_runtime_proof():
    report = collect_low_risk_candidate_proofs()

    candidate = report["target_breakdown"]

    assert candidate["expected_target_schema"] == "a_class"
    assert candidate["model_schema"] == "a_class"
    assert candidate["target_schema_sql_refs"] > 0
    assert candidate["public_schema_sql_refs"] == 0
    assert candidate["ready_for_wave1"] is True


def test_other_low_risk_candidates_are_ready_after_schema_alignment():
    report = collect_low_risk_candidate_proofs()

    for table_name in ("performance_config", "sales_campaigns", "sales_campaign_shops"):
        candidate = report[table_name]
        assert candidate["expected_target_schema"] == "a_class"
        assert candidate["model_schema"] == "a_class"
        assert candidate["ready_for_wave1"] is True
        assert candidate["blocker_reason"] == ""
