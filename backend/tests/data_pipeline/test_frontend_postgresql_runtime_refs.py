from pathlib import Path


def test_active_frontend_dashboard_files_no_longer_reference_metabase_runtime():
    files = [
        "frontend/src/api/dashboard.js",
        "frontend/src/api/index.js",
        # ⚠️ ``AnnualSummary.vue`` 已于 2026-05-25(commit 5d5101ec「feat:年度数据删除」)
        # 被删除 ⇒ 不再是「在役前端文件」, 从本清单移除。
        "frontend/src/domains/business/views/BusinessOverview.vue",
        "frontend/src/domains/business/views/hr/PerformanceDisplay.vue",
        "frontend/src/domains/business/views/hr/PerformanceManagement.vue",
        "frontend/src/config/menuGroups.js",
        "frontend/src/router/index.js",
        "frontend/src/stores/dashboard.js",
        "frontend/src/api/test.js",
    ]

    forbidden_terms = [
        "Metabase Question",
        "Metabase 服务",
        "METABASE_UNAVAILABLE",
        "Metabase 计算方案",
        "使用Metabase替代",
    ]

    for path_str in files:
        text = Path(path_str).read_text(encoding="utf-8", errors="replace")
        for term in forbidden_terms:
            assert term not in text, f"{path_str} still contains {term!r}"

    # 已删除的年度汇总页不允许被重新引入(否则它会绕过 PostgreSQL 看板)
    assert not Path("frontend/src/domains/business/views/AnnualSummary.vue").exists()


def test_frontend_metabase_embed_assets_are_archived():
    archived_files = [
        "archive/metabase/frontend/components/MetabaseChart.vue",
        "archive/metabase/frontend/services/metabase.js",
    ]
    for path_str in archived_files:
        text = Path(path_str).read_text(encoding="utf-8", errors="replace").lower()
        assert "historical only" in text
