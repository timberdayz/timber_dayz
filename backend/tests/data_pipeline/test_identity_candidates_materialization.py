"""店铺身份解析候选集物化（2026-11-05）的结构契约。

背景
----
生产 EXPLAIN ANALYZE 实测：全量重算订单原子层（38,607 行）要 **119 秒**，
计划里 ``shop_account_aliases``（只有 21 行）被扫了 **148 万次** ——
候选集只有 136 行，却被当成**逐行计算的表达式**（N+1）。

修法是把候选集物化。本文件守住四条不变量：

1. **口径零变化** —— 物化副本的正文就是正本正文的 ``SELECT *``；
   正本（普通视图）一个字都不改，既有断言全部继续有效。
2. **顺序不能反** —— 正本必须先于副本存在，否则建 MV 时找不到源表。
3. **不删任何下游** —— 副本的刷新走「存在则 REFRESH / 不存在则 CREATE」，
   不用 ``DROP ... CASCADE``；删旧版 v1 时也故意不带 CASCADE（fail-closed）。
4. **有机器口径守护** —— 迁移建完副本后比内容指纹，不一致就回滚。
"""

from pathlib import Path

from backend.services.data_pipeline.refresh_registry import (
    PIPELINE_DEPENDENCIES,
    SQL_TARGET_PATHS,
    topologically_sort_targets,
)


REPO_ROOT = Path(__file__).resolve().parents[3]

CANDIDATES_MV = "semantic.shop_identity_resolution_candidates_v2_mv"
FORWARDING_VIEW = "semantic.shop_identity_resolution_candidates"
CANDIDATES_MV_ASSET = "sql/semantic/shop_identity_resolution_candidates_v2_mv.sql"
FORWARDING_VIEW_ASSET = "sql/semantic/shop_identity_resolution_candidates.sql"

#: 改读物化副本的原子层**普通视图**（正文里换掉了候选集引用）
ATOMIC_VIEW_ASSETS = (
    "sql/semantic/orders_atomic.sql",
    "sql/semantic/analytics_atomic.sql",
)

#: **不动**的既有物化视图（完整定义 + DROP CASCADE 重建，改了要动生产）
LEGACY_MONTHLY_MV_ASSETS = (
    "sql/semantic/orders_monthly_atomic_mv.sql",
    "sql/semantic/analytics_monthly_atomic_mv.sql",
)


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def _strip_sql_comments(sql_text: str) -> str:
    """去掉 ``--`` 行注释 —— 断言要检查的是**可执行 SQL**，不是注释里的话。"""
    kept: list[str] = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        kept.append(line.split("--")[0])
    return "\n".join(kept)


def test_candidates_materialized_view_asset_exists() -> None:
    assert (REPO_ROOT / CANDIDATES_MV_ASSET).is_file()
    assert (REPO_ROOT / FORWARDING_VIEW_ASSET).is_file()


def test_materialized_view_is_registered_as_refresh_target() -> None:
    assert SQL_TARGET_PATHS[CANDIDATES_MV] == CANDIDATES_MV_ASSET
    assert SQL_TARGET_PATHS[FORWARDING_VIEW] == FORWARDING_VIEW_ASSET


def test_materialized_view_comes_after_the_source_view() -> None:
    """顺序反了就建不出 MV（副本的正文是 ``SELECT * FROM`` 正本）。"""
    assert PIPELINE_DEPENDENCIES[CANDIDATES_MV] == [FORWARDING_VIEW]

    ordered = topologically_sort_targets([CANDIDATES_MV, FORWARDING_VIEW])
    assert ordered.index(FORWARDING_VIEW) < ordered.index(CANDIDATES_MV)


def test_materialized_view_body_is_self_contained() -> None:
    """副本正文**自包含**（从 core 表现算），不引用正本。

    为什么不能写成 ``SELECT * FROM <正本>``：
    - 正本在不同环境里列数不同 —— 生产是 8 列（含 ``identity_shop_region``），
      全新库 baseline 建的是 7 列旧版（``shop_region`` 列是 20261101 才加的）。
      副本引用正本 ⇒ 全新库建不出 8 列副本。
    - 引用正本 = 副本依赖正本，刷新语义会绕一圈。
    """
    sql_text = _read(CANDIDATES_MV_ASSET)
    assert (
        "CREATE MATERIALIZED VIEW semantic.shop_identity_resolution_candidates_v2_mv"
        in sql_text
    )
    assert "core.shop_accounts" in sql_text
    assert "core.shop_account_aliases" in sql_text
    assert "identity_shop_region" in sql_text
    assert (
        "FROM semantic.shop_identity_resolution_candidates " not in sql_text
    ), "副本正文不应引用正本"


def test_materialized_copy_matches_the_source_view_definition() -> None:
    """两份定义（正本 + 副本）必须保持同构 —— 副本是手抄的，会有漂移风险。

    守住两处最容易漂移的地方：4 路 UNION 的分支数、以及区域维度列。
    """
    source = _read(FORWARDING_VIEW_ASSET)
    copy = _read(CANDIDATES_MV_ASSET)
    for text in (source, copy):
        assert text.count("UNION ALL") == 3, "候选集的 UNION 分支数变了（应为 4 路）"
        assert "identity_shop_region" in text
        assert "candidate_shop_region" in text


def test_source_view_asset_is_untouched() -> None:
    """正本仍是从 core 表现算的普通视图（既有断言继续有效）。"""
    sql_text = _read(FORWARDING_VIEW_ASSET)
    assert (
        "CREATE OR REPLACE VIEW semantic.shop_identity_resolution_candidates AS"
        in sql_text
    )
    assert "core.shop_accounts" in sql_text
    assert "core.shop_account_aliases" in sql_text


def test_atomic_views_read_the_materialized_copy() -> None:
    """两个原子层普通视图必须读物化副本（否则 N+1 还在）。"""
    for rel_path in ATOMIC_VIEW_ASSETS:
        sql_text = _read(rel_path)
        assert CANDIDATES_MV in sql_text, rel_path
        # 不再直接引用正本（否则等于没物化）
        assert (
            "FROM semantic.shop_identity_resolution_candidates " not in sql_text
        ), rel_path


def test_legacy_monthly_materialized_views_are_left_alone() -> None:
    """既有 monthly MV 的定义是 ``DROP ... CASCADE`` + ``CREATE``，改了要动生产。"""
    for rel_path in LEGACY_MONTHLY_MV_ASSETS:
        sql_text = _read(rel_path)
        assert CANDIDATES_MV not in sql_text, rel_path
        assert FORWARDING_VIEW in sql_text, rel_path


def test_materialized_view_asset_never_drops_cascade() -> None:
    """CASCADE 会连带删下游（含不是 registry 可重建目标的对象）。"""
    sql_text = _strip_sql_comments(_read(CANDIDATES_MV_ASSET)).upper()
    assert "DROP MATERIALIZED VIEW" not in sql_text
    assert "CASCADE" not in sql_text
    assert "REFRESH MATERIALIZED VIEW" in sql_text


def test_migration_guards_content_fingerprint() -> None:
    """迁移必须做「副本 == 正本」的内容指纹比对，不一致就回滚。"""
    migration = _read(
        "current_migrations/versions/20261105_create_identity_candidates_mv.py"
    )
    assert "_fingerprint" in migration
    assert "md5(" in migration
    assert "拒绝继续" in migration


def test_migration_is_chained_before_atomic_materialization() -> None:
    candidates_migration = _read(
        "current_migrations/versions/20261105_create_identity_candidates_mv.py"
    )
    atomic_migration = _read(
        "current_migrations/versions/20261106_create_atomic_materialized_views.py"
    )
    assert (
        'down_revision = "current_schema_20261104_drop_clearance_ranking_module"'
        in candidates_migration
    )
    assert (
        'down_revision = "current_schema_20261105_create_identity_candidates_mv"'
        in atomic_migration
    )


def test_atomic_migration_rebuilds_source_views_before_materializing() -> None:
    """原子层普通视图必须先重建（引用已切换 + 数值校验），再建物化视图。"""
    atomic_migration = _read(
        "current_migrations/versions/20261106_create_atomic_materialized_views.py"
    )
    assert "SOURCE_VIEW_ASSETS" in atomic_migration
    source_index = atomic_migration.index("SOURCE_VIEW_ASSETS")
    materialize_index = atomic_migration.index("_materialize()")
    assert source_index < materialize_index
