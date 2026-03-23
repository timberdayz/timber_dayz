from pathlib import Path


def test_agent_start_here_no_longer_instructs_new_dashboard_work_via_metabase():
    text = Path("docs/AGENT_START_HERE.md").read_text(encoding="utf-8", errors="replace")

    forbidden_phrases = [
        "应该使用Metabase Question",
        "永远使用Metabase Question API查询数据",
        "Metabase直接查询原始表",
        "通过Metabase Question查询fact_raw_data_*表",
        "backend/routers/dashboard_api.py",
        "/api/metabase/health",
    ]

    for phrase in forbidden_phrases:
        assert phrase not in text

    required_phrases = [
        "PostgreSQL Dashboard",
        "USE_POSTGRESQL_DASHBOARD_ROUTER",
        "semantic",
        "mart",
        "api",
        "legacy",
    ]
    lowered = text.lower()
    for phrase in required_phrases:
        if phrase == "legacy":
            assert phrase in lowered
        else:
            assert phrase in text


def test_main_no_longer_documents_metabase_as_current_dashboard_architecture():
    text = Path("backend/main.py").read_text(encoding="utf-8", errors="replace")

    forbidden_phrases = [
        "dashboard_api已恢复,通过Metabase Question查询提供数据",
        "Metabase直接查询PostgreSQL原始表",
        "使用Metabase替代",
        "使用Metabase Dashboard替代",
        "使用Metabase Question API替代",
    ]

    for phrase in forbidden_phrases:
        assert phrase not in text

    assert "Dashboard router source: PostgreSQL" in text
    assert "Metabase proxy route disabled" in text
