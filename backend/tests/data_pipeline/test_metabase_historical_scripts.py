from pathlib import Path


def test_claude_md_no_longer_recommends_runtime_metabase_usage():
    """CLAUDE.md 收敛成「薄适配器」: 规则入口是 AGENTS.md, 不再复述运行时架构。

    2026-05-22(commit ``f79b2593``「feat:规则大改」)起, CLAUDE.md 只保留
    「先读 AGENTS.md + 指向 docs/*」的指引 ⇒ 里面既不该出现 runtime metabase,
    也不该再复述 Dashboard 架构细节。
    """
    text = Path("CLAUDE.md").read_text(encoding="utf-8", errors="replace")

    assert "python run.py --with-metabase" not in text
    assert "legacy fallback/debug infrastructure" not in text
    assert "Metabase" not in text
    # 规则入口只有一个: AGENTS.md
    assert "AGENTS.md" in text
    assert "docs/DEVELOPMENT_RULES/README.md" in text
    assert "docs/architecture/README.md" in text


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
