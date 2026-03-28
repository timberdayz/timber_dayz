from backend.utils.schema_cleanup_rehearsal import run_dim_shops_public_retirement_rehearsal


def test_dim_shops_public_retirement_rehearsal_archives_public_copy_cleanly():
    result = run_dim_shops_public_retirement_rehearsal()

    assert result["current_revision"] == result["head_revision"]
    assert result["all_tables_exist"] is True
    assert result["public_dim_shops_exists_before"] is True
    assert result["core_dim_shops_exists_before"] is True
    assert result["public_dim_shops_exists_after"] is False
    assert result["archive_dim_shops_exists_after"] is True
    assert result["core_dim_shops_exists_after"] is True
