from pathlib import Path


def test_claude_md_no_longer_recommends_runtime_metabase_usage():
    text = Path("CLAUDE.md").read_text(encoding="utf-8", errors="replace")

    assert "python run.py --with-metabase" not in text
    assert "legacy fallback/debug infrastructure" not in text
    assert "PostgreSQL Dashboard" in text


def test_historical_metabase_scripts_are_marked_historical_only():
    files = [
        "archive/metabase/scripts/init_metabase.py",
        "archive/metabase/scripts/verify_deploy_phase35_local.py",
        "archive/metabase/scripts/verify_deploy_full_local.py",
        "archive/metabase/scripts/create_metabase_model_tables.py",
        "archive/metabase/scripts/deep_check_metabase_issue.py",
        "archive/metabase/scripts/test_metabase_integration.py",
        "archive/metabase/scripts/test_metabase_performance.py",
        "archive/metabase/scripts/test_metabase_question_integration.py",
        "archive/metabase/scripts/verify_metabase_question_ids.py",
        "archive/metabase/scripts/run_4c8g_acceptance.py",
    ]

    for path_str in files:
        text = Path(path_str).read_text(encoding="utf-8", errors="replace")
        lowered = text.lower()
        assert "historical" in lowered
        assert "not part of the runtime path" in lowered
