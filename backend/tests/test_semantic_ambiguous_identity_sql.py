from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SQL_ASSETS = (
    "sql/semantic/orders_atomic.sql",
    "sql/semantic/analytics_atomic.sql",
    "sql/semantic/orders_monthly_atomic_mv.sql",
    "sql/semantic/analytics_monthly_atomic_mv.sql",
)

LEGACY_WARNING_CODES = (
    "missing_identity",
    "unresolved_shop_account",
    "missing_required_platform_shop_id",
)


def _text(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def test_no_sql_asset_uses_bare_limit_1_on_identity():
    """四条语义路径都不允许再对身份候选直接 LIMIT 1。"""
    for rel in SQL_ASSETS:
        text = _text(rel)
        assert "ambiguous_shop_label" in text, f"{rel} 缺少 ambiguous_shop_label 告警码"
        assert "unmatched_shop_label" in text, f"{rel} 缺少 unmatched_shop_label 告警码"
        assert "identity_candidate_count" in text, f"{rel} 缺少 identity_candidate_count"


def test_monthly_assets_keep_legacy_warning_codes():
    """既有的三个告警码不能被新词表覆盖掉（spec A7 的「并存关系」）。

    live 上 `missing_identity` / `unresolved_shop_account` / `missing_required_platform_shop_id`
    已经在用（88 行 `unresolved_shop_account`），新词表只能**加**不能**盖**。
    """
    for rel in (
        "sql/semantic/orders_monthly_atomic_mv.sql",
        "sql/semantic/analytics_monthly_atomic_mv.sql",
    ):
        text = _text(rel)
        for code in LEGACY_WARNING_CODES:
            assert code in text, f"{rel} 丢了既有告警码 {code}"


def test_candidate_view_carries_region_dimension():
    """第二批：候选视图必须带出区域维度，供同名品牌店按站点消歧。

    视图的 identity_rows 是 4 路 UNION ALL；加列必须同时改 4 个分支
    **和** 视图末尾的 SELECT 列表，否则 PostgreSQL 报
    `each UNION query must have the same number of columns`（已实测）。
    """
    text = _text("sql/semantic/shop_identity_resolution_candidates.sql")
    assert text.count("UNION ALL") == 3, "候选视图的 UNION 分支数变了（应为 4 路 UNION ALL）"
    assert "identity_shop_region" in text, "候选视图没有带出区域维度"
    assert "candidate_shop_region" in text, "候选视图的 CTE 没有店铺区域列"
