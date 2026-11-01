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


def test_sql_assets_map_site_to_region():
    """语义层必须把 raw 的中文站点映射成店铺区域码（大写）。

    只有**有站点来源**的两条 orders 路径需要区域映射 ——
    analytics 的 raw 里既没有站点也没有店铺标签
    （实测 `b_class.fact_tiktok_analytics_monthly` 1263 行，站点 0 / 店铺 0），
    给它硬造一个区域字段只会多一个永远是 NULL 的列。
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    for rel in (
        "sql/semantic/orders_atomic.sql",
        "sql/semantic/orders_monthly_atomic_mv.sql",
    ):
        text = (root / rel).read_text(encoding="utf-8")
        assert "source_region" in text, f"{rel} 没有把站点映射成区域"
        assert "'菲律宾'" in text, f"{rel} 缺少站点映射表"


def test_site_map_matches_python_side():
    """SQL 的站点→区域映射必须与 `account_alignment.py` 的 `site_map` **逐项**一致。

    只比 key→value，**不比 fallback** —— 两侧 fallback 的大小写本来就不同，是有意的：
    Python 侧（`account_alignment.py:806`）产出小写，只用于生成建议 id（`:820-821`）；
    SQL 侧产出大写，要与 `core.shop_accounts.shop_region`（实测存大写 `MY`/`PH`/`SG`）比较。

    这条断言让「只锁 8 项映射」真的成为事实，而不是靠文档承诺。
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]

    src = (root / "backend" / "domains" / "collection" / "routers"
           / "account_alignment.py").read_text(encoding="utf-8")
    site_map = None
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "site_map" for t in node.targets
        ):
            site_map = ast.literal_eval(node.value)
            break
    assert site_map, "account_alignment.py 里找不到 site_map"

    for rel in (
        "sql/semantic/orders_atomic.sql",
        "sql/semantic/orders_monthly_atomic_mv.sql",
    ):
        text = (root / rel).read_text(encoding="utf-8")
        for site, code in site_map.items():
            assert f"WHEN '{site}' THEN '{code.upper()}'" in text, (
                f"{rel} 缺少站点映射 {site} -> {code.upper()}"
                f"（与 account_alignment.py 的 site_map 不一致）"
            )


def test_analytics_assets_do_not_get_region_column():
    """反向护栏：两条 analytics 路径**不得**出现区域列。

    它们没有站点来源（raw 里 `站点` / `店铺` 都是 0 行），
    加了只会是永远 NULL 的列，还会让"区域感知匹配"的适用范围变得含糊。
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    for rel in (
        "sql/semantic/analytics_atomic.sql",
        "sql/semantic/analytics_monthly_atomic_mv.sql",
    ):
        text = (root / rel).read_text(encoding="utf-8")
        # 只匹配「真的定义了列」的形态，避免一句解释性注释就误红
        assert not re.search(r"AS\s+source_region\b", text, re.I), (
            f"{rel} 不该有区域列（raw 里没有站点来源）"
        )
        assert not re.search(r"WHEN\s+'[^']+'\s+THEN\s+'[A-Z]{2}'", text), (
            f"{rel} 不该有站点映射表"
        )
