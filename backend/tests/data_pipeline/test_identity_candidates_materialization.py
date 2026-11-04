"""店铺身份解析候选集物化（2026-11-06）的结构契约。

背景
----
生产 EXPLAIN ANALYZE 实测：全量重算订单原子层（38,607 行）要 **119 秒**，
计划里 ``shop_account_aliases``（只有 21 行）被扫了 **148 万次** ——
候选集只有 136 行，却被当成**逐行计算的表达式**（N+1）。

修法是把候选集物化。本文件守住四条不变量：

1. **口径零变化** —— 4 个下游原子层视图的正文**一个字都不改**，
   它们继续引用 ``semantic.shop_identity_resolution_candidates``；
   只是这个转发视图改为读物化副本。
2. **顺序不能反** —— 正本（物化副本）必须先于转发视图存在，否则循环依赖。
3. **不删任何下游** —— 物化副本的刷新走「存在则 REFRESH / 不存在则 CREATE」，
   不用 ``DROP ... CASCADE``；删旧版 v1 时也故意不带 CASCADE（fail-closed）。
4. **有机器口径守护** —— 迁移在改造前后比内容指纹，不一致就回滚。
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

#: 4 个下游原子层视图资产（正文不许动）
DOWNSTREAM_ATOMIC_ASSETS = (
    "sql/semantic/orders_atomic.sql",
    "sql/semantic/analytics_atomic.sql",
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


def test_materialized_view_comes_before_forwarding_view() -> None:
    """顺序反了就是循环依赖（正本引用转发视图）。"""
    assert PIPELINE_DEPENDENCIES[CANDIDATES_MV] == []
    assert PIPELINE_DEPENDENCIES[FORWARDING_VIEW] == [CANDIDATES_MV]

    ordered = topologically_sort_targets([CANDIDATES_MV, FORWARDING_VIEW])
    assert ordered.index(CANDIDATES_MV) < ordered.index(FORWARDING_VIEW)


def test_forwarding_view_reads_the_materialized_copy() -> None:
    sql_text = _read(FORWARDING_VIEW_ASSET)
    assert CANDIDATES_MV in sql_text
    assert (
        "SELECT * FROM semantic.shop_identity_resolution_candidates_v2_mv" in sql_text
    )


def test_downstream_atomic_views_keep_reading_the_forwarding_view() -> None:
    """口径零变化的守卫：4 个下游视图的正文不许改引用。

    它们继续引用 ``semantic.shop_identity_resolution_candidates``（转发视图），
    而不是直接引用物化副本 —— 改了就等于改了口径，需要重新验证金额。
    """
    for rel_path in DOWNSTREAM_ATOMIC_ASSETS:
        sql_text = _read(rel_path)
        assert FORWARDING_VIEW in sql_text, rel_path
        assert (
            CANDIDATES_MV not in sql_text
        ), "{path} 不该直接引用物化副本：会让 4 个下游视图的正文发生变化".format(
            path=rel_path
        )


def test_materialized_view_asset_never_drops_cascade() -> None:
    """CASCADE 会连带删下游（含不是 registry 可重建目标的对象）。"""
    sql_text = _strip_sql_comments(_read(CANDIDATES_MV_ASSET)).upper()
    assert "DROP MATERIALIZED VIEW" not in sql_text
    assert "CASCADE" not in sql_text
    assert "REFRESH MATERIALIZED VIEW" in sql_text


def test_migration_guards_content_fingerprint() -> None:
    """迁移必须做「改造前后内容指纹一致」的比对，不一致就回滚。"""
    migration = _read(
        "current_migrations/versions/20261106_materialize_identity_candidates.py"
    )
    assert "_fingerprint" in migration
    assert "md5(" in migration
    assert "拒绝继续" in migration


def test_migration_is_chained_after_atomic_materialization() -> None:
    migration = _read(
        "current_migrations/versions/20261106_materialize_identity_candidates.py"
    )
    assert (
        'down_revision = "current_schema_20261105_create_atomic_materialized_views"'
        in migration
    )
