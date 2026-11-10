"""店铺身份解析候选集：正本与物化副本的**口径归属**契约。

背景
----
生产 EXPLAIN ANALYZE 实测：全量重算订单原子层（38,607 行）要 **119 秒**，
计划里别名表（只有 21 行）被扫了 **148 万次** ——
候选集只有几十行，却被当成**逐行计算的表达式**（N+1）。

修法是把候选集物化。

2026-11-11「派生层口径收回」
---------------------------
物化副本以前**手抄**了一份正本的完整计算逻辑（4 路 UNION + 采集方代号排除），
两边靠人工保持一致 —— 差一点就漂移，而漂移是**静默**的：
副本多一行少一行，看板上只会表现为「某个店没人了」，不会报任何错。

现在副本**只从正本取数**（``SELECT <显式列清单> FROM <正本>``）⇒
口径的定义**只有正本一处**。本文件守住的不变量：

1. **口径只有一份** —— 副本**不得**再复写计算逻辑（不得直接派生自台账）；
   正本仍是**唯一**从台账派生的那一处；
2. **列名列序一致** —— 副本的显式列清单必须与正本的 SELECT 列表**逐列同名同序**；
3. **顺序不能反** —— 正本必须先于副本存在，否则建 MV 时找不到源视图；
4. **不删任何下游** —— 副本的刷新走「存在则 REFRESH / 不存在则 CREATE」，
   不用 ``DROP ... CASCADE``；删旧版 v1 时也故意不带 CASCADE（fail-closed）；
5. **函数只有一处定义** —— 采集方代号判定函数 ``semantic.is_collection_source_identifier``
   **内联在正本资产开头**（谁执行正本, 函数先落地）⇒ 全新库跑迁移链建得起来；
6. **有机器口径守护** —— 迁移建完副本后比内容指纹，不一致就回滚。

⚠️ 涉及**可执行 SQL** 的断言一律只看**去掉注释后**的正文 ——
   解释性注释里出现同样的字样不算数。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from backend.services.data_pipeline.refresh_registry import (
    ASSET_PREREQUISITES,
    PIPELINE_DEPENDENCIES,
    SQL_TARGET_PATHS,
    topologically_sort_targets,
)


REPO_ROOT = Path(__file__).resolve().parents[3]

CANDIDATES_MV = "semantic.shop_identity_resolution_candidates_v2_mv"
FORWARDING_VIEW = "semantic.shop_identity_resolution_candidates"
CANDIDATES_MV_ASSET = "sql/semantic/shop_identity_resolution_candidates_v2_mv.sql"
FORWARDING_VIEW_ASSET = "sql/semantic/shop_identity_resolution_candidates.sql"

#: 采集方代号判定函数 —— **只允许**定义在正本资产里
COLLECTION_SOURCE_FUNCTION = "semantic.is_collection_source_identifier"

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

#: 建副本的迁移（本次改动：它必须**先**执行正本资产）
CANDIDATES_MV_MIGRATION = (
    "current_migrations/versions/20261105_create_identity_candidates_mv.py"
)
#: 口径变更时走「DROP 重建」的迁移（本次改动**不能**破坏这条路径）
REALIGN_MIGRATION = (
    "current_migrations/versions/20261112_realign_identity_candidates_anchor.py"
)

#: 当前迁移链（``current_migrations/`` 是唯一事实源）
CURRENT_CHAIN_CONFIG = "alembic-current.ini"
CURRENT_BASELINE_REVISION = "current_schema_20260805"
CANDIDATES_MV_REVISION = "current_schema_20261105_create_identity_candidates_mv"


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


def _canonical_select_columns(sql_text: str) -> list[str]:
    """解析正本资产**最后那个 SELECT** 的列清单（正本里只有一个这样的 SELECT）。"""
    match = re.search(
        r"\)\s*\nSELECT\s*\n(?P<columns>.*?)\nFROM identity_rows",
        sql_text,
        re.S,
    )
    assert match, "没找到正本的最终 SELECT —— 资产结构变了，断言需要同步维护"
    return [column.strip() for column in match.group("columns").split(",")]


def _copy_select_columns(sql_text: str) -> list[str]:
    """解析副本资产里 ``CREATE MATERIALIZED VIEW ... AS SELECT`` 的列清单。"""
    match = re.search(
        r"CREATE\s+MATERIALIZED\s+VIEW\s+"
        + re.escape(CANDIDATES_MV)
        + r"\s+AS\s*\n\s*SELECT\s*\n(?P<columns>.*?)\n\s*FROM\s+"
        + re.escape(FORWARDING_VIEW),
        sql_text,
        re.S,
    )
    assert (
        match
    ), "没找到副本的 CREATE MATERIALIZED VIEW ... AS SELECT —— 断言需要同步维护"
    return [column.strip() for column in match.group("columns").split(",")]


# ---------------------------------------------------------------------------
# 1. 口径只有一份
# ---------------------------------------------------------------------------


def test_candidates_materialized_view_asset_exists() -> None:
    assert (REPO_ROOT / CANDIDATES_MV_ASSET).is_file()
    assert (REPO_ROOT / FORWARDING_VIEW_ASSET).is_file()


def test_copy_asset_no_longer_reimplements_the_caliber() -> None:
    """副本**不得**再复写计算逻辑 —— 它只从正本取数。

    副本以前手抄了一份正本的完整计算逻辑（4 路 UNION + 采集方代号排除），
    两边靠人工保持一致 ⇒ 差一点就漂移，而漂移是**静默**的。
    """
    executable = _strip_sql_comments(_read(CANDIDATES_MV_ASSET))

    # 不再直接派生自台账
    assert "core.shop_accounts" not in executable
    assert "core.shop_account_aliases" not in executable
    assert "FROM core.shop_accounts" not in _read(CANDIDATES_MV_ASSET)
    assert "FROM core.shop_account_aliases" not in _read(CANDIDATES_MV_ASSET)

    # 不再复写四路 UNION
    assert "UNION ALL" not in executable
    assert "active_shop_accounts" not in executable
    assert "identity_rows" not in executable
    assert "alias_match" not in executable
    assert "store_name_match" not in executable

    # 只从正本取数
    assert "FROM " + FORWARDING_VIEW in executable


def test_canonical_asset_is_the_only_place_derived_from_the_ledger() -> None:
    """正本仍是**唯一**从台账派生的地方（口径的唯一定义处）。"""
    executable = _strip_sql_comments(_read(FORWARDING_VIEW_ASSET))

    assert "FROM core.shop_accounts" in executable
    assert "core.shop_account_aliases" in executable
    assert executable.count("UNION ALL") == 3, "候选集的 UNION 分支数变了（应为 4 路）"
    assert "identity_shop_region" in executable
    assert "candidate_shop_region" in executable


def test_copy_asset_column_list_matches_the_canonical_select_list() -> None:
    """副本的显式列清单必须与正本的 SELECT 列表**逐列同名同序**。

    列序错位是**静默**的：下游（原子层视图、物化副本、看板消费方）
    按列名 JOIN 不会报错，但按位置取数会取错列。
    """
    canonical_columns = _canonical_select_columns(_read(FORWARDING_VIEW_ASSET))
    copy_columns = _copy_select_columns(_read(CANDIDATES_MV_ASSET))

    assert (
        copy_columns == canonical_columns
    ), "副本的列清单与正本的 SELECT 列表不一致（列名或列序）"
    assert len(copy_columns) == len(set(copy_columns)), "副本列清单里有重复列"


def test_canonical_asset_declares_itself_the_single_source_of_truth() -> None:
    """正本资产必须声明自己是口径的**唯一定义处**（给下一个改它的人看）。"""
    sql_text = _read(FORWARDING_VIEW_ASSET)
    assert "唯一定义处" in sql_text
    assert "不得复写" in sql_text


# ---------------------------------------------------------------------------
# 2. 刷新顺序与注册
# ---------------------------------------------------------------------------


def test_materialized_view_is_registered_as_refresh_target() -> None:
    assert SQL_TARGET_PATHS[CANDIDATES_MV] == CANDIDATES_MV_ASSET
    assert SQL_TARGET_PATHS[FORWARDING_VIEW] == FORWARDING_VIEW_ASSET


def test_materialized_view_comes_after_the_source_view() -> None:
    """顺序反了就建不出 MV（副本的正文从正本取数）。"""
    assert PIPELINE_DEPENDENCIES[CANDIDATES_MV] == [FORWARDING_VIEW]

    ordered = topologically_sort_targets([CANDIDATES_MV, FORWARDING_VIEW])
    assert ordered.index(FORWARDING_VIEW) < ordered.index(CANDIDATES_MV)


def test_canonical_view_is_an_asset_prerequisite_of_the_copy() -> None:
    """副本的正文引用正本 ⇒ 正本不存在时建副本直接报 ``relation does not exist``。"""
    assert FORWARDING_VIEW in ASSET_PREREQUISITES.get(CANDIDATES_MV, [])


# ---------------------------------------------------------------------------
# 3. 不删任何下游
# ---------------------------------------------------------------------------


def test_materialized_view_asset_never_drops_cascade() -> None:
    """CASCADE 会连带删下游（含不是 registry 可重建目标的对象）。"""
    sql_text = _strip_sql_comments(_read(CANDIDATES_MV_ASSET)).upper()
    assert "DROP MATERIALIZED VIEW" not in sql_text
    assert "CASCADE" not in sql_text
    assert "REFRESH MATERIALIZED VIEW" in sql_text


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


# ---------------------------------------------------------------------------
# 4. 采集方代号判定函数：**只**在正本里定义
# ---------------------------------------------------------------------------


def test_collection_source_function_is_defined_only_in_the_canonical_asset() -> None:
    """函数定义**只**允许出现在正本资产里。

    副本以前手抄口径时**没有**内联这个函数 ⇒ 全新库跑迁移链时函数还不存在
    ⇒ 建视图报 "function semantic.is_collection_source_identifier does not exist"。
    现在副本从正本取数 ⇒ 不再需要自己定义 ⇒ 但**正本里必须还在**
    （谁执行正本, 函数先落地）。
    """
    canonical = _read(FORWARDING_VIEW_ASSET)
    copy = _read(CANDIDATES_MV_ASSET)

    assert "CREATE OR REPLACE FUNCTION " + COLLECTION_SOURCE_FUNCTION in canonical
    assert "CREATE OR REPLACE FUNCTION " + COLLECTION_SOURCE_FUNCTION not in copy
    assert "CREATE FUNCTION " + COLLECTION_SOURCE_FUNCTION not in copy
    # 副本的**可执行**正文里也不该再出现这个函数（它只从正本取数）
    assert COLLECTION_SOURCE_FUNCTION not in _strip_sql_comments(copy)


def test_canonical_asset_defines_the_function_before_the_view() -> None:
    """函数定义必须排在视图定义**之前**（同一文件里自举）。

    这正是 ``sql/semantic/shop_identity_resolution_candidates.sql`` 开头
    注释里点名的历史坑：函数放别的资产 ⇒ 全新库跑迁移链时函数还不存在。
    """
    canonical = _read(FORWARDING_VIEW_ASSET)
    function_index = canonical.index(
        "CREATE OR REPLACE FUNCTION " + COLLECTION_SOURCE_FUNCTION
    )
    view_index = canonical.index("CREATE OR REPLACE VIEW " + FORWARDING_VIEW + " AS")
    assert function_index < view_index, "函数定义必须排在视图定义之前"


# ---------------------------------------------------------------------------
# 5. 迁移链：建副本的迁移必须**先**执行正本资产
# ---------------------------------------------------------------------------


def test_copy_migration_executes_the_canonical_asset_before_the_copy() -> None:
    """建副本的迁移必须**先**执行正本资产。

    副本的列集合 = 正本的列集合；而 ``20260805`` 基线建的候选池正本是
    **7 列旧版**（缺 ``identity_shop_region``）⇒ 不先对齐，副本就是 7 列 ⇒
    下一条迁移 ``20261106`` 重建原子层视图时引用
    ``c.identity_shop_region`` 直接报「column does not exist」。
    """
    migration = _read(CANDIDATES_MV_MIGRATION)
    assert "CANDIDATES_VIEW_ASSET" in migration
    assert "sql/semantic/shop_identity_resolution_candidates.sql" in migration

    upgrade_body = migration[migration.index("def upgrade()") :]
    view_index = upgrade_body.index("_execute_asset(CANDIDATES_VIEW_ASSET)")
    copy_index = upgrade_body.index("_execute_asset(CANDIDATES_MV_ASSET)")
    assert view_index < copy_index, "正本资产必须先于副本资产执行"


def test_migration_guards_content_fingerprint() -> None:
    """迁移必须做「副本 == 正本」的内容指纹比对，不一致就回滚。"""
    migration = _read(CANDIDATES_MV_MIGRATION)
    assert "_fingerprint" in migration
    assert "md5(" in migration
    assert "拒绝继续" in migration


def test_migration_is_chained_before_atomic_materialization() -> None:
    candidates_migration = _read(CANDIDATES_MV_MIGRATION)
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


def test_caliber_change_still_requires_drop_rebuild() -> None:
    """口径变更（列数变化）仍需 **DROP 重建** —— 这条路径没被本次改动破坏。

    ``REFRESH MATERIALIZED VIEW`` 只重算**数据**，不换**定义**；
    而 ``DROP MATERIALIZED VIEW``（不带 CASCADE）会被下游
    ``LANGUAGE sql`` 对象的**被跟踪依赖**挡住 ⇒ 必须先让它们让开。
    """
    migration = _read(REALIGN_MIGRATION)

    # ① 先让开（解析函数 + 两个原子层普通视图改成读正本）
    assert "to_source_view=True" in migration
    # ② DROP 副本（不带 CASCADE）
    assert "DROP MATERIALIZED VIEW IF EXISTS" in migration
    # ③ 用副本资产重建
    assert CANDIDATES_MV_ASSET in migration
    # ④ 内容指纹比对
    assert "_assert_copy_matches_source" in migration

    upgrade_body = migration[
        migration.index("def upgrade()") : migration.index("def downgrade()")
    ]
    assert upgrade_body.index("to_source_view=True") < upgrade_body.index(
        "DROP MATERIALIZED VIEW"
    )
    assert upgrade_body.index("DROP MATERIALIZED VIEW") < upgrade_body.index(
        "_execute_asset(CANDIDATES_MV_ASSET)"
    )


# ---------------------------------------------------------------------------
# 6. 真库断言（真实 PostgreSQL）
# ---------------------------------------------------------------------------


def _fingerprint_sql(relation: str) -> str:
    """关系的内容指纹：行数 + 全量内容 md5。

    口径与迁移 ``20261105`` 的 ``_fingerprint`` 完全一致
    （``row_to_json`` 而不是 ``t::text``：record 的文本输出形式依赖列类型
    渲染规则，``row_to_json`` 更稳定）。
    """
    return (
        "SELECT count(*)::int AS row_count, "
        "md5(coalesce(string_agg(row_json, '|' ORDER BY row_json), '')) AS digest "
        "FROM (SELECT row_to_json(t)::text AS row_json FROM {relation} t) s"
    ).format(relation=relation)


def _run_alembic(args: list[str], env: dict[str, str]) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", CURRENT_CHAIN_CONFIG, *args],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "alembic failed: "
            + " ".join(args)
            + "\nstdout:\n"
            + completed.stdout
            + "\nstderr:\n"
            + completed.stderr
        )


def _seed_candidate_pool(engine) -> None:
    """播种一批店铺账号，让候选池**不是空的**（空池比不出内容指纹）。"""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO core.main_accounts (
                    platform, main_account_id, username, password_encrypted, main_account_name
                ) VALUES ('shopee', 'guard-main-account', 'guard', 'x', 'Guard Main Account')
                """
            )
        )
        rows = [
            # 在营经营店：进候选池
            (
                "sa_guard_1",
                "8001",
                "Guard Store One",
                "MY",
                True,
                "operating_store",
            ),
            (
                "sa_guard_2",
                "8002",
                "Guard Store Two",
                "SG",
                True,
                "operating_store",
            ),
            # 停用的经营店：被正本过滤掉
            (
                "sa_guard_3",
                "8003",
                "Guard Store Disabled",
                "MY",
                False,
                "operating_store",
            ),
            # 采集源账号：不是店铺身份，进不了候选池
            (
                "sa_guard_4",
                "8004",
                "Guard Collection Source",
                "MY",
                True,
                "collection_source",
            ),
        ]
        for account_id, platform_shop_id, store_name, region, enabled, role in rows:
            conn.execute(
                text(
                    """
                    INSERT INTO core.shop_accounts (
                        platform, shop_account_id, main_account_id, store_name,
                        platform_shop_id, shop_region, enabled, business_role
                    ) VALUES (
                        'shopee', :account_id, 'guard-main-account', :store_name,
                        :platform_shop_id, :shop_region, :enabled, :business_role
                    )
                    """
                ),
                {
                    "account_id": account_id,
                    "store_name": store_name,
                    "platform_shop_id": platform_shop_id,
                    "shop_region": region,
                    "enabled": enabled,
                    "business_role": role,
                },
            )
        # 别名：别名那一路也要进候选池
        conn.execute(
            text(
                """
                INSERT INTO core.shop_account_aliases (
                    shop_account_id, platform, alias_value, alias_normalized,
                    alias_type, source, is_primary, is_active
                )
                SELECT sa.id, 'shopee', 'Guard Alias One', 'guardaliasone',
                       'store_name', 'guard', FALSE, TRUE
                FROM core.shop_accounts sa
                WHERE sa.shop_account_id = 'sa_guard_1'
                """
            )
        )


def _column_names(engine, relation: str) -> list[tuple[int, str]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT a.attnum, a.attname
                FROM pg_attribute a
                WHERE a.attrelid = to_regclass(:relation)
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                ORDER BY a.attnum
                """
            ),
            {"relation": relation},
        ).all()
    return [(int(row[0]), str(row[1])) for row in rows]


def _fingerprint(engine, relation: str) -> tuple[int, str]:
    with engine.connect() as conn:
        row = conn.execute(text(_fingerprint_sql(relation))).one()
    return int(row[0]), str(row[1])


def _view_definition(engine, relation: str) -> str:
    with engine.connect() as conn:
        return str(
            conn.execute(
                text("SELECT pg_get_viewdef(to_regclass(:relation), true)"),
                {"relation": relation},
            ).scalar_one()
        )


def test_fresh_database_chain_builds_the_derived_copy_from_the_canonical_view() -> None:
    """**全新库**跑迁移链 ⇒ 副本必须建得起来，且与正本**逐项一致**。

    这是本次改动的关键回归点：
    - 副本改成「从正本取数」⇒ 副本的列集合 = 正本的列集合；
    - ``20260805`` 基线建的候选池正本是 **7 列旧版** ⇒ 建副本的迁移必须
      **先**执行正本资产，否则副本是 7 列，``20261106`` 重建原子层视图时
      引用 ``c.identity_shop_region`` 直接报「column does not exist」。

    做法与仓库既有的 fresh-db drill 一致（见
    ``backend/tests/test_dim_shops_public_retirement_rehearsal.py``）：
    在隔离库的临时库上重放当前链，播种数据后比对。
    """
    from backend.utils.config import get_settings

    base_url = make_url(get_settings().DATABASE_URL)
    admin_engine = create_engine(
        base_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        future=True,
    )
    database_name = "candidates_derive_guard_{}".format(uuid.uuid4().hex[:10])
    temp_url = base_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    env = os.environ.copy()
    env["DATABASE_URL"] = temp_url

    try:
        with admin_engine.connect() as conn:
            conn.execute(
                text(
                    'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'.format(
                        db=database_name
                    )
                )
            )
            conn.execute(text('CREATE DATABASE "{db}"'.format(db=database_name)))

        _run_alembic(["upgrade", CURRENT_BASELINE_REVISION], env)
        _run_alembic(["upgrade", CANDIDATES_MV_REVISION], env)

        temp_engine = create_engine(temp_url, future=True)
        try:
            _seed_candidate_pool(temp_engine)

            # 正本与副本都必须存在
            with temp_engine.connect() as conn:
                for relation in (FORWARDING_VIEW, CANDIDATES_MV):
                    exists = conn.execute(
                        text("SELECT to_regclass(:relation)"),
                        {"relation": relation},
                    ).scalar_one()
                    assert exists is not None, relation

            canonical_columns = _column_names(temp_engine, FORWARDING_VIEW)
            copy_columns = _column_names(temp_engine, CANDIDATES_MV)

            # ① 列名与列序必须一致
            assert copy_columns == canonical_columns, "副本与正本的列名/列序不一致"
            assert (
                len(canonical_columns) == 8
            ), "候选池应当是 8 列（含 identity_shop_region）"

            # ② 副本必须**从正本取数**（定义里能看见正本，看不见台账）
            copy_definition = _view_definition(temp_engine, CANDIDATES_MV)
            assert FORWARDING_VIEW in copy_definition, copy_definition
            assert "shop_accounts" not in copy_definition, copy_definition

            # ③ 内容一致：行数 + 全量内容 md5（指纹口径同迁移 20261105 的 _fingerprint）
            #    先刷新副本 —— 物化视图是**快照**, 播种之后必须 REFRESH 才拿到新数据
            #    （这正是 refresh_runner 的日常路径: ``REFRESH MATERIALIZED VIEW``）。
            with temp_engine.begin() as conn:
                conn.execute(text("REFRESH MATERIALIZED VIEW " + CANDIDATES_MV))

            canonical_fingerprint = _fingerprint(temp_engine, FORWARDING_VIEW)
            copy_fingerprint = _fingerprint(temp_engine, CANDIDATES_MV)
            assert canonical_fingerprint[0] > 0, "候选池是空的 —— 播种没生效，断言失效"
            assert (
                copy_fingerprint == canonical_fingerprint
            ), "副本与正本的内容指纹不一致：view={view} copy={copy}".format(
                view=canonical_fingerprint, copy=copy_fingerprint
            )
        finally:
            temp_engine.dispose()
    finally:
        with admin_engine.connect() as conn:
            conn.execute(
                text(
                    'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'.format(
                        db=database_name
                    )
                )
            )
        admin_engine.dispose()


#: 真库断言的**显式开关** —— 默认不连任何业务库。
#:
#: 为什么默认关闭
#: ------------
#: 仓库的 pytest 护栏明令「测试绝不能连上真实业务库」（``backend/tests/conftest.py``）。
#: 要在**开发库**上复核「副本 == 正本」，必须由人**显式**给出连接串：
#:
#:     $env:XIHONG_CANDIDATES_LIVE_DATABASE_URL = "<开发库连接串>"
#:     python -m pytest backend/tests/data_pipeline/test_identity_candidates_materialization.py -v
#:
#: 本用例**只读**（全是 SELECT），不改任何数据。
LIVE_DATABASE_URL_ENV_VAR = "XIHONG_CANDIDATES_LIVE_DATABASE_URL"


@pytest.mark.skipif(
    not os.environ.get(LIVE_DATABASE_URL_ENV_VAR),
    reason="未设置 {var} —— 真库复核默认关闭（pytest 护栏禁止测试连业务库）".format(
        var=LIVE_DATABASE_URL_ENV_VAR
    ),
)
def test_live_copy_matches_the_canonical_view() -> None:
    """开发库上复核：副本与正本**行数相同、列名列序相同、内容一致**。

    只读（全是 SELECT）。指纹口径同迁移 ``20261105`` 的 ``_fingerprint``。
    """
    raw_url = os.environ[LIVE_DATABASE_URL_ENV_VAR]
    engine = create_engine(raw_url, future=True)
    try:
        canonical_columns = _column_names(engine, FORWARDING_VIEW)
        copy_columns = _column_names(engine, CANDIDATES_MV)

        assert copy_columns == canonical_columns, "副本与正本的列名/列序不一致"

        canonical_fingerprint = _fingerprint(engine, FORWARDING_VIEW)
        copy_fingerprint = _fingerprint(engine, CANDIDATES_MV)

        assert (
            canonical_fingerprint[0] == copy_fingerprint[0]
        ), "副本与正本的行数不一致：view={view} copy={copy}".format(
            view=canonical_fingerprint[0], copy=copy_fingerprint[0]
        )
        assert (
            canonical_fingerprint[1] == copy_fingerprint[1]
        ), "副本与正本的内容指纹不一致：view={view} copy={copy}".format(
            view=canonical_fingerprint[1], copy=copy_fingerprint[1]
        )
    finally:
        engine.dispose()
