"""重锚店铺身份候选集: ``shop_account_id`` 升为 priority 1 + 候选池只收在营经营店。

背景
----
``semantic.shop_identity_resolution_candidates`` 的四路候选优先级原来是::

    platform_shop_id(1) → shop_account_id(2) → alias_match(3) → store_name_match(4)

**最不稳的那个排在最前**。``platform_shop_id`` 会被采集器污染(把 URL 里读到的
编号当成主数据)、平台换 ID 就失效; ``shop_account_id`` 才是唯一正确锚点
(改名不变、跨平台一致、采集器写不坏)。

同时, 候选池**漏抄**了系统其它每个环节都有的过滤: ``enabled IS TRUE`` 与
``business_role = 'operating_store'``。实测候选池 138 行里 69 行(50%)来自停用店。

本次改动
--------
1. **锚点优先级倒置** —— ``shop_account_id`` → 1, ``platform_shop_id`` → 2;
2. **候选池补过滤** —— 只收在营经营店;
3. **别名路不再认领平台店铺编号** —— 自别名/跨账号认领会让同一串身份值
   指向两个账号 ⇒ 候选数变 2 ⇒ 整行落 unknown。

⚠️ **只动排序与候选池, 不动计数口径**
------------------------------------
候选数仍然是 ``count(DISTINCT c.resolved_shop_id)`` —— 歧义判定**完全不变**
(歧义行照样落 ``unknown``, 绝不静默挑一个)。变的是「歧义行**声称**自己属于谁」:
以前歧义行被 ``platform_shop_id`` 那一路带去**被污染的邻居**, 现在由
``shop_account_id`` 那一路带去**真正当事的账号**。

实测(live 开发库, ``semantic.fact_analytics_monthly_atomic_mv`` 前后对比):

=========================================  ======  =========
变化                                        行数   UV 变化
=========================================  ======  =========
歧义行归属改对(xhkj1.my → xh_home.ph 等)      18   0
停用店历史落 unknown(eternalbloom/chenewei666) 213   **0**
=========================================  ======  =========

⇒ **看板数字零变化**, 只把「谁被指控」改对。

为什么必须**重建**物化副本
--------------------------
``sql/semantic/shop_identity_resolution_candidates_v2_mv.sql`` 的刷新语义是
「存在则 REFRESH / 不存在则 CREATE」—— REFRESH 只重算**数据**, 不换**定义**。
口径改了之后, 光 REFRESH 刷出来的还是旧口径 ⇒ 必须 DROP 重建。

重建顺序(缺一步就失败)
-----------------------
1. 正本先改口径(``CREATE OR REPLACE VIEW``, OID 不变 ⇒ 下游不用重建);
2. 依赖物化副本的对象先让开 —— 把**解析函数**与**两个原子层普通视图**的正文
   里的副本引用换成正本:
   * 解析函数是 ``LANGUAGE sql`` ⇒ 它对副本的依赖**被跟踪**
     (``semantic.fact_inventory_snapshot`` / ``fact_products_atomic`` /
     ``fact_services_atomic`` 都依赖它) —— 不让开就 DROP 不掉副本;
   * 函数体换成正本之后口径完全等价(正本与副本正文同构), 中间态照样可用;
   * ``CREATE OR REPLACE FUNCTION`` **保持函数 OID** ⇒ 依赖它的视图不受影响;
3. ``DROP MATERIALIZED VIEW`` —— **不带 CASCADE**(CASCADE 会连带删下游);
4. 执行副本资产 ⇒ 用新口径重建;
5. 把解析函数与两个原子层普通视图换回副本;
6. **内容指纹比对**: 副本必须与正本逐字节一致, 不一致就抛错回滚。
"""

from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261112_realign_identity_candidates_anchor"
down_revision = "current_schema_20261111_add_refresh_queue_domain_and_retry"
branch_labels = None
depends_on = None


REPO_ROOT = Path(__file__).resolve().parents[2]

#: 候选集正本(普通视图)
CANDIDATES_VIEW = "semantic.shop_identity_resolution_candidates"
#: 候选集物化副本(正本快照)
CANDIDATES_MV = "semantic.shop_identity_resolution_candidates_v2_mv"
#: 候选集正本(普通视图)
CANDIDATES_VIEW_ASSET = "sql/semantic/shop_identity_resolution_candidates.sql"
#: 候选集物化副本(正本快照)
CANDIDATES_MV_ASSET = "sql/semantic/shop_identity_resolution_candidates_v2_mv.sql"
#: 解析函数(依赖物化副本; LANGUAGE sql ⇒ 依赖被跟踪)
RESOLVER_FUNCTION_ASSET = "sql/semantic/shop_identity_resolver.sql"

#: 依赖物化副本的原子层**普通视图**(正文里引用了副本)
SOURCE_VIEW_ASSETS = (
    "sql/semantic/orders_atomic.sql",
    "sql/semantic/analytics_atomic.sql",
)


# ---------------------------------------------------------------------------
# 旧口径的候选集正文(回滚用)
#
# 为什么要在迁移里**内嵌**一份旧的正文:
#   旧口径只存在于 git 历史里, 没有对应的资产文件(资产文件已被本次改动覆盖)。
#   回滚必须真的把口径换回去 —— 否则「回滚」只是把副本删了, 口径没回,
#   看板显示名 JOIN 会落空。
# ---------------------------------------------------------------------------
_LEGACY_CANDIDATES_BODY = """
WITH active_shop_accounts AS (
    SELECT
        sa.id AS shop_account_pk,
        LOWER(COALESCE(sa.platform, '')) AS platform_code,
        NULLIF(TRIM(COALESCE(sa.shop_account_id, '')), '') AS resolved_shop_account_id,
        NULLIF(TRIM(COALESCE(sa.platform_shop_id, '')), '') AS candidate_platform_shop_id,
        NULLIF(TRIM(COALESCE(sa.store_name, '')), '') AS candidate_store_label,
        NULLIF(TRIM(COALESCE(sa.shop_region, '')), '') AS candidate_shop_region,
        COALESCE(
            NULLIF(TRIM(COALESCE(sa.platform_shop_id, '')), ''),
            NULLIF(TRIM(COALESCE(sa.shop_account_id, '')), ''),
            sa.id::text
        ) AS resolved_shop_id
    FROM core.shop_accounts sa
),
identity_rows AS (
    SELECT
        platform_code,
        resolved_shop_id,
        resolved_shop_account_id,
        'platform_shop_id'::varchar AS resolution_method,
        1 AS resolution_priority,
        LOWER(candidate_platform_shop_id) AS identity_value_normalized,
        candidate_platform_shop_id AS identity_source_value,
        candidate_shop_region AS identity_shop_region
    FROM active_shop_accounts
    WHERE candidate_platform_shop_id IS NOT NULL

    UNION ALL

    SELECT
        platform_code,
        resolved_shop_id,
        resolved_shop_account_id,
        'shop_account_id'::varchar AS resolution_method,
        2 AS resolution_priority,
        LOWER(resolved_shop_account_id) AS identity_value_normalized,
        resolved_shop_account_id AS identity_source_value,
        candidate_shop_region AS identity_shop_region
    FROM active_shop_accounts
    WHERE resolved_shop_account_id IS NOT NULL

    UNION ALL

    SELECT
        asa.platform_code,
        asa.resolved_shop_id,
        asa.resolved_shop_account_id,
        'alias_match'::varchar AS resolution_method,
        3 AS resolution_priority,
        LOWER(TRIM(saa.alias_normalized)) AS identity_value_normalized,
        saa.alias_value AS identity_source_value,
        NULLIF(TRIM(COALESCE(saa.shop_region, '')), '') AS identity_shop_region
    FROM active_shop_accounts asa
    INNER JOIN core.shop_account_aliases saa
      ON saa.shop_account_id = asa.shop_account_pk
     AND saa.is_active = TRUE
    WHERE NULLIF(TRIM(COALESCE(saa.alias_normalized, '')), '') IS NOT NULL

    UNION ALL

    SELECT
        platform_code,
        resolved_shop_id,
        resolved_shop_account_id,
        'store_name_match'::varchar AS resolution_method,
        4 AS resolution_priority,
        REGEXP_REPLACE(
            LOWER(
                TRIM(BOTH FROM REGEXP_REPLACE(
                    TRIM(BOTH FROM COALESCE(active_shop_accounts.candidate_store_label, '')),
                    '^(shopee|tiktok\\s*shop|tiktok|tk|miaoshou|amazon|lazada)\\s*',
                    '',
                    'i'
                ))
            ),
            '[\\s_()/-]+',
            '',
            'g'
        ) AS identity_value_normalized,
        candidate_store_label AS identity_source_value,
        candidate_shop_region AS identity_shop_region
    FROM active_shop_accounts
    WHERE candidate_store_label IS NOT NULL
)
SELECT
    platform_code,
    identity_value_normalized,
    identity_source_value,
    resolved_shop_id,
    resolved_shop_account_id,
    resolution_method,
    resolution_priority,
    identity_shop_region
FROM identity_rows
WHERE NULLIF(TRIM(COALESCE(identity_value_normalized, '')), '') IS NOT NULL
"""


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def _asset_text(rel_path: str) -> str | None:
    asset_path = REPO_ROOT / rel_path
    if not asset_path.is_file():
        print("[WARN] 资产文件缺失，跳过：{path}".format(path=rel_path))
        return None
    return asset_path.read_text(encoding="utf-8")


def _driver_connection():
    """拿到原生 psycopg2 连接（``Connection.connection`` 是**属性**，不是可调用对象）。"""
    pool_conn = op.get_bind().connection
    return getattr(pool_conn, "driver_connection", pool_conn)


def _exec_sql(statement: str) -> None:
    """执行一条原生 SQL。

    不用 ``exec_driver_sql``: 它会把空参数字典交给 psycopg2, 而 psycopg2 只接受
    真正的 ``dict``/序列 ⇒ ``TypeError: ... is not a sequence``。
    """
    with _driver_connection().cursor() as cursor:
        cursor.execute(statement)


def _exec_sql_text(sql_text: str) -> None:
    """执行一段原生 SQL（可以含多条语句）。

    走 psycopg2 的**简单查询协议** —— 数据库自己按分号切分, 并且自己认
    dollar-quoted 块(``DO $$ ... $$`` 不会被切坏)。
    """
    with _driver_connection().cursor() as cursor:
        cursor.execute(sql_text)


def _execute_asset(rel_path: str) -> bool:
    """执行一个 SQL 资产文件（整文件一次执行）。"""
    sql_text = _asset_text(rel_path)
    if sql_text is None:
        return False
    _exec_sql_text(sql_text)
    return True


def _exists(name: str) -> bool:
    bind = op.get_bind()
    return (
        bind.execute(
            sa.text("SELECT to_regclass(:name)"), {"name": name}
        ).scalar_one_or_none()
        is not None
    )


def _column_count(relation: str) -> int:
    """关系(普通视图 / 物化视图)的列数。

    ``information_schema.columns`` **不包含物化视图**, 所以物化视图走 ``pg_attribute``。
    """
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            """
            SELECT count(*)::int
            FROM pg_attribute a
            WHERE a.attrelid = to_regclass(:name)
              AND a.attnum > 0
              AND NOT a.attisdropped
            """
        ).bindparams(name=relation)
    ).one()
    return int(row[0])


def _fingerprint(relation: str) -> tuple[int, str]:
    """关系的内容指纹: 行数 + 全量内容 md5（按行文本排序后拼接）。"""
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            """
            SELECT count(*)::int AS row_count,
                   md5(coalesce(string_agg(row_json, '|' ORDER BY row_json), '')) AS digest
            FROM (
                SELECT row_to_json(t)::text AS row_json
                FROM {relation} t
            ) s
            """.format(
                relation=relation
            )
        )
    ).one()
    return int(row[0]), str(row[1])


def _rebuild_source_views(*, to_source_view: bool) -> None:
    """重新执行原子层两个普通视图的资产文件。

    它们存的是被引用关系的 **OID** —— 物化副本重建后 OID 变了,
    不重新执行的话, 两个视图会指向「已不存在的旧副本」。

    ``to_source_view=True`` 时把正文里的副本引用换成**正本** ——
    副本重建之前必须先让它们让开(视图对被引用关系的依赖不被跟踪,
    但它们存的是 OID, 副本没了就会指向空气)。

    ⚠️ **必须去掉资产里的 ``DROP VIEW ... CASCADE``**
    ----------------------------------------------
    ``sql/semantic/analytics_atomic.sql`` 开头有一句
    ``DROP VIEW IF EXISTS semantic.fact_analytics_atomic CASCADE;`` ——
    它的用途是「列变了要重建」。live 开发库实测: 这一句会**连带删掉 10 个对象**
    (物化视图 ``semantic.fact_analytics_atomic_mv`` + ``mart.shop_day_kpi`` /
    ``mart.shop_week_kpi`` / ``mart.platform_day_kpi`` / ``mart.platform_week_kpi``
    + 5 个 ``api.business_overview_*`` 视图)。

    本迁移**只换引用, 不改列**, 所以用 ``CREATE OR REPLACE VIEW`` 就够了 ——
    它**保持视图自己的 OID** ⇒ 上面那 10 个下游对象一个都不用重建。
    """
    for rel_path in SOURCE_VIEW_ASSETS:
        sql_text = _asset_text(rel_path)
        if sql_text is None:
            print("[WARN] 资产文件缺失，跳过视图重建：{path}".format(path=rel_path))
            continue
        sql_text = _strip_cascade_drop(sql_text)
        if to_source_view:
            sql_text = sql_text.replace(
                "semantic.shop_identity_resolution_candidates_v2_mv",
                CANDIDATES_VIEW,
            )
        _exec_sql_text(sql_text)


def _strip_cascade_drop(sql_text: str) -> str:
    """去掉资产里的 ``DROP VIEW ... CASCADE;`` 语句(见 :func:`_rebuild_source_views`)。"""
    kept: list[str] = []
    for line in sql_text.splitlines():
        if line.strip().upper().startswith("DROP VIEW"):
            continue
        kept.append(line)
    return "\n".join(kept)


def _rebuild_resolver_function(*, to_source_view: bool) -> None:
    """重建解析函数。

    ``LANGUAGE sql`` 的函数体在**定义时**就被解析 ⇒ 它对物化副本的依赖是
    **被跟踪**的 ⇒ 删副本之前必须先让它不再依赖副本。

    做法与视图同理: 先把函数体里的副本引用换成**正本**(口径等价, 函数照常可用),
    副本重建之后再换回来。

    ⚠️ ``CREATE OR REPLACE FUNCTION`` **保持函数的 OID** ⇒
    ``semantic.fact_inventory_snapshot`` / ``fact_products_atomic`` /
    ``fact_services_atomic`` 这些依赖它的视图**不受影响**。
    """
    sql_text = _asset_text(RESOLVER_FUNCTION_ASSET)
    if sql_text is None:
        print("[WARN] 解析函数资产缺失，跳过重建")
        return
    if to_source_view:
        sql_text = sql_text.replace(
            "semantic.shop_identity_resolution_candidates_v2_mv",
            CANDIDATES_VIEW,
        )
    _exec_sql_text(sql_text)


def _assert_copy_matches_source() -> None:
    """内容指纹守护: 副本必须与正本逐字节一致。"""
    view_columns = _column_count(CANDIDATES_VIEW)
    mv_columns = _column_count(CANDIDATES_MV)
    if view_columns != mv_columns:
        print(
            "[INFO] 正本列数({view})与副本列数({mv})不同，跳过内容比对".format(
                view=view_columns, mv=mv_columns
            )
        )
        return
    view_fingerprint = _fingerprint(CANDIDATES_VIEW)
    mv_fingerprint = _fingerprint(CANDIDATES_MV)
    if mv_fingerprint != view_fingerprint:
        raise RuntimeError(
            "候选集物化副本与正本内容不一致，拒绝继续：view={view} mv={mv}".format(
                view=view_fingerprint, mv=mv_fingerprint
            )
        )


# ---------------------------------------------------------------------------
# 升级 / 回滚
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # 1) 正本先改口径。CREATE OR REPLACE VIEW **保持 OID** ⇒ 下游不用重建。
    if not _execute_asset(CANDIDATES_VIEW_ASSET):
        raise RuntimeError("候选集正本资产缺失，拒绝继续")

    # 2) 依赖副本的对象先让开: 解析函数与两个原子层普通视图都改成读**正本**。
    #    * 解析函数是 LANGUAGE sql ⇒ 它的依赖**被跟踪**
    #      (``semantic.fact_inventory_snapshot`` / ``fact_products_atomic`` /
    #      ``fact_services_atomic`` 都依赖它);
    #    * 两个原子层普通视图也**被跟踪**(live 实测: ``view
    #      semantic.fact_orders_atomic depends on materialized view
    #      semantic.shop_identity_resolution_candidates_v2_mv``)。
    #    不让开就 DROP 不掉副本; 换成正本之后口径完全等价(正本与副本正文同构),
    #    中间态照样可用; ``CREATE OR REPLACE`` **保持 OID** ⇒ 下游对象不受影响。
    _rebuild_resolver_function(to_source_view=True)
    _rebuild_source_views(to_source_view=True)

    # 3) 删副本 —— **不带 CASCADE**(有依赖就让迁移失败, fail-closed)。
    if _exists(CANDIDATES_MV):
        _exec_sql("DROP MATERIALIZED VIEW IF EXISTS {mv}".format(mv=CANDIDATES_MV))

    # 4) 用新口径重建副本（资产文件的语义是「存在则 REFRESH / 不存在则 CREATE」）。
    if not _execute_asset(CANDIDATES_MV_ASSET):
        raise RuntimeError("候选集物化副本资产缺失，拒绝继续")

    # 5) 把让开的对象换回副本。
    _rebuild_resolver_function(to_source_view=False)
    _rebuild_source_views(to_source_view=False)

    # 6) 口径守护: 副本 == 正本, 逐字节。
    _assert_copy_matches_source()


def downgrade() -> None:
    """回滚: 把候选集口径换回旧口径。

    顺序与升级对称:
    1. 解析函数与两个原子层普通视图改成读**正本**(让开副本);
    2. DROP 副本;
    3. 用**旧口径正文**重建正本与副本;
    4. 把解析函数与两个原子层普通视图换回副本;
    5. 指纹比对。
    """
    _rebuild_resolver_function(to_source_view=True)
    _rebuild_source_views(to_source_view=True)

    if _exists(CANDIDATES_MV):
        _exec_sql("DROP MATERIALIZED VIEW IF EXISTS {mv}".format(mv=CANDIDATES_MV))

    _exec_sql_text(
        "CREATE SCHEMA IF NOT EXISTS semantic;\n"
        "CREATE OR REPLACE VIEW {view} AS\n{body}".format(
            view=CANDIDATES_VIEW, body=_LEGACY_CANDIDATES_BODY
        )
    )
    _exec_sql_text(
        "CREATE MATERIALIZED VIEW {mv} AS\n{body}".format(
            mv=CANDIDATES_MV, body=_LEGACY_CANDIDATES_BODY
        )
    )

    _rebuild_resolver_function(to_source_view=False)
    _rebuild_source_views(to_source_view=False)
    _assert_copy_matches_source()
