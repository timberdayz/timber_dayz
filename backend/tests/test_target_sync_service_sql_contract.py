from pathlib import Path


def test_target_sync_service_avoids_asyncpg_named_param_cast_syntax():
    source = Path("backend/services/target_sync_service.py").read_text(encoding="utf-8")

    assert ":period_start::date" not in source
    assert "CAST(:period_start AS date)" in source
