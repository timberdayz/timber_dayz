from pathlib import Path

SEMANTIC_PATHS = (
    "sql/semantic/orders_atomic.sql",
    "sql/semantic/analytics_atomic.sql",
    "sql/semantic/orders_monthly_atomic_mv.sql",
    "sql/semantic/analytics_monthly_atomic_mv.sql",
)


def test_shop_identity_resolution_sql_asset():
    sql_path = Path("sql/semantic/shop_identity_resolution_candidates.sql")
    assert sql_path.exists()

    sql_text = sql_path.read_text(encoding="utf-8")
    assert "CREATE SCHEMA IF NOT EXISTS semantic" in sql_text
    assert "CREATE OR REPLACE VIEW semantic.shop_identity_resolution_candidates AS" in sql_text
    assert "core.shop_accounts" in sql_text
    assert "core.shop_account_aliases" in sql_text
    assert "platform_shop_id" in sql_text
    assert "shop_account_id" in sql_text
    assert "resolution_method" in sql_text
    assert "resolved_shop_id" in sql_text
    assert "CREATE INDEX IF NOT EXISTS ix_shop_accounts_platform_shop_id_lookup" in sql_text
    assert "CREATE INDEX IF NOT EXISTS ix_shop_accounts_platform_account_id_lookup" in sql_text
    assert "CREATE INDEX IF NOT EXISTS ix_shop_account_aliases_platform_alias_lookup" in sql_text


def test_all_semantic_paths_use_candidate_view_and_pure_aggregate_count():
    """四条语义路径必须统一走候选视图，且候选计数只能是「纯聚合」。

    ① 都引用候选视图（不再各自实现一套匹配逻辑）；
    ② 都用 `count(DISTINCT c.resolved_shop_id)` —— 同一个店通过多种方式命中只算 1 个候选；
    ③ 禁用 `count(DISTINCT ...) OVER ()`：PostgreSQL 不支持 DISTINCT 窗口函数，
       实测直接报 `ERROR: DISTINCT is not implemented for window functions`；
       而 `count(*) OVER ()` 在无 GROUP BY 时恒为 1 → 所有多候选都会被判成 1 个 →
       永远不落 `ambiguous_shop_label` → 正是 D13/A6 要防的静默错配。
    """
    for rel in SEMANTIC_PATHS:
        text = Path(rel).read_text(encoding="utf-8")
        assert "semantic.shop_identity_resolution_candidates" in text, f"{rel} 未统一走候选视图"
        assert "count(DISTINCT c.resolved_shop_id)" in text, f"{rel} 的候选计数不是纯聚合形式"
        assert "OVER ()" not in text, f"{rel} 用了窗口函数做候选计数（PostgreSQL 不支持 DISTINCT 窗口函数）"
