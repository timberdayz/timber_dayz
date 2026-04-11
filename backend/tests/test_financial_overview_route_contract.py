from pathlib import Path


def test_financial_overview_route_redirects_to_financial_management():
    text = Path("frontend/src/router/index.js").read_text(encoding="utf-8")

    assert "path: '/financial-overview'" in text
    assert "redirect: '/financial-management'" in text
    assert "component: () => import('../views/FinancialOverview.vue')" not in text
