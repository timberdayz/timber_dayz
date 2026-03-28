from backend.utils.schema_cleanup_rehearsal import run_wave1_rehearsal


def test_wave1_rehearsal_upgrades_cleanly_and_archives_public_target_breakdown():
    result = run_wave1_rehearsal()

    assert result["current_revision"] == result["head_revision"]
    assert result["all_tables_exist"] is True
    assert result["public_target_breakdown_exists_before"] is True
    assert result["public_target_breakdown_exists_after"] is False
    assert result["archive_table_exists_after"] is True
    assert result["a_class_target_breakdown_exists_after"] is True
