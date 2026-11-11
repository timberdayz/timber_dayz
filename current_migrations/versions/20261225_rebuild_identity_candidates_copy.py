"""重建店铺身份候选集的**物化副本**，让它从正本取数（派生层口径收回在存量库落地）。

背景
----
``sql/semantic/shop_identity_resolution_candidates_v2_mv.sql`` 的刷新语义是
「存在则 REFRESH / 不存在则 CREATE」—— ``REFRESH`` 只重算**数据**, 不换**定义**。

⇒ 仓库里那份「副本只从正本取数」的资产, 在**存量库**上从来没有生效过:
生产上的副本仍是当初**手抄**了一份计算逻辑的旧定义。

生产实测（2026-11-11, 云端库只读探测）
------------------------------------
* 副本定义里仍然出现 ``core.shop_accounts`` / ``core.shop_account_aliases`` /
  ``regexp_replace`` / ``active_shop_accounts`` ⇒ **它在自算**, 没有读正本;
* 副本 **72 行**、正本 **72 行**、双向差集 **0 / 0** ⇒ *当前* 内容一致, 无功能影响;
* 但副本的定义比正本**少一条口径** —— 正本末尾有
  ``AND NOT semantic.is_collection_source_identifier(...)``
  （采集方代号不是店铺身份 ⇒ 不进候选池）, 副本**没有**。

⇒ 这就是「静默分叉」: 现在恰好一致, 但正本哪天多出一行口径 / 候选池哪天出现
一个采集方代号, 副本就**不会跟** —— 而且不会报任何错, 只会表现为「某个店没人了」
或「采集方代号被当成店铺身份」。

为什么**走迁移**而不是在部署流水线里插一步「删副本」
----------------------------------------------------
部署期跑的是 ``scripts/rebuild_views.py --all-plain-views`` —— 它**只重建普通视图**
（物化视图全量重算会超 ``statement_timeout``, 生产实测单个月粒度 MV 就 120s+）。
物化副本不在那份清单里 ⇒ 流水线**不会**用它的新定义。

而「在流水线里直接 DROP 副本」会**打断解析函数**:
``sql/semantic/shop_identity_resolver.sql`` 是 ``LANGUAGE sql`` 函数, 它对副本的
依赖是**被跟踪**的 ⇒ 不先让开就 DROP 不掉; 而让开/换回这两步必须与
「原子层普通视图」同步做（它们存的是副本的 OID）⇒ 天然是一个**原子操作**。

⇒ 所以复用迁移 ``20261112_realign_identity_candidates_anchor`` 已经走通过的
「让开 → DROP → 重建 → 换回 → 比对」这条路径（本次**不动**正本口径）。

重建顺序（缺一步就失败）
-----------------------
1. 解析函数与两个原子层普通视图改成读**正本**（副本的依赖必须先解除）;
2. ``DROP MATERIALIZED VIEW`` —— **不带 CASCADE**(有依赖就让迁移失败, fail-closed);
3. 执行副本资产 ⇒ 按新定义（从正本取数）重建;
4. 把解析函数与两个原子层普通视图换回副本;
5. **内容比对**: 副本必须与正本逐行一致, 不一致就抛错回滚;
6. **定义校验**: 副本定义必须**读正本**, 且**不得**再出现自算逻辑的痕迹。

回滚
----
``downgrade`` 把副本恢复成迁移前的「手抄版」定义（内嵌在迁移里）,
并同样做内容比对 ⇒ 回滚**不会**改变任何一行的业务归属。
"""

from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261225_rebuild_identity_candidates_copy"
down_revision = "current_schema_20261224_shop_identity_conflict_rows"
branch_labels = None
depends_on = None


REPO_ROOT = Path(__file__).resolve().parents[2]

#: 候选集正本(普通视图)
CANDIDATES_VIEW = "semantic.shop_identity_resolution_candidates"
#: 候选集物化副本
CANDIDATES_MV = "semantic.shop_identity_resolution_candidates_v2_mv"
#: 副本资产(执行它 = 按新定义重建)
CANDIDATES_MV_ASSET = "sql/semantic/shop_identity_resolution_candidates_v2_mv.sql"
#: 解析函数(依赖物化副本; LANGUAGE sql ⇒ 依赖被跟踪)
RESOLVER_FUNCTION_ASSET = "sql/semantic/shop_identity_resolver.sql"

#: 依赖物化副本的原子层**普通视图**(正文里引用了副本)
SOURCE_VIEW_ASSETS = (
    "sql/semantic/orders_atomic.sql",
    "sql/semantic/analytics_atomic.sql",
)

#: 副本定义里**出现即说明它在自算**的痕迹。
LEGACY_DEFINITION_MARKERS = (
    "core.shop_accounts",
    "core.shop_account_aliases",
    "active_shop_accounts",
    "regexp_replace",
)

#: 迁移前生产上的副本定义(手抄版)。
#: ⚠️ 它比正本**少一条**「采集方代号不进候选池」的口径 —— 那正是分叉的证据。
#:    回滚用它把副本恢复成迁移前的形态。
_LEGACY_COPY_BODY = """
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
    WHERE sa.enabled IS TRUE
      AND sa.business_role = 'operating_store'
),
identity_rows AS (
    SELECT
        platform_code,
        resolved_shop_id,
        resolved_shop_account_id,
        'platform_shop_id'::varchar AS resolution_method,
        2 AS resolution_priority,
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
        1 AS resolution_priority,
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
      AND NOT EXISTS (
            SELECT 1
            FROM core.shop_accounts alias_owner
            WHERE alias_owner.enabled IS TRUE
              AND alias_owner.business_role = 'operating_store'
              AND LOWER(NULLIF(TRIM(COALESCE(alias_owner.platform_shop_id, '')), ''))
                  = LOWER(TRIM(COALESCE(saa.alias_normalized, '')))
          )

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


def _relation_definition(relation: str) -> str:
    """关系的定义正文。

    ⚠️ ``pg_get_matviewdef`` 只存在于 PostgreSQL 11 及更早版本;
    生产是 PostgreSQL 15 ⇒ 用 ``pg_get_viewdef``(物化视图也能用它)。
    """
    bind = op.get_bind()
    value = bind.execute(
        sa.text("SELECT pg_get_viewdef(to_regclass(:name), true)").bindparams(
            name=relation
        )
    ).scalar_one_or_none()
    return str(value or "")


def _content_diff(view: str, mv: str) -> tuple[int, int]:
    """正本与副本的**双向**行差集(行数)。"""
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            """
            SELECT
                (SELECT count(*)::int FROM (
                    SELECT * FROM {view} EXCEPT ALL SELECT * FROM {mv}
                ) a) AS view_minus_mv,
                (SELECT count(*)::int FROM (
                    SELECT * FROM {mv} EXCEPT ALL SELECT * FROM {view}
                ) b) AS mv_minus_view
            """.format(
                view=view, mv=mv
            )
        )
    ).one()
    return int(row[0]), int(row[1])


def _rebuild_source_views(*, to_source_view: bool) -> None:
    """重新执行原子层两个普通视图的资产文件。

    它们存的是被引用关系的 **OID** —— 物化副本重建后 OID 变了,
    不重新执行的话, 两个视图会指向「已不存在的旧副本」。

    ``to_source_view=True`` 时把正文里的副本引用换成**正本** ——
    副本重建之前必须先让它们让开。

    ⚠️ **必须去掉资产里的 ``DROP VIEW ... CASCADE``**
    ----------------------------------------------
    ``sql/semantic/analytics_atomic.sql`` 开头有一句
    ``DROP VIEW IF EXISTS semantic.fact_analytics_atomic CASCADE;`` ——
    它的用途是「列变了要重建」。live 实测: 这一句会**连带删掉 10 个对象**
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
    """内容守护: 副本必须与正本**逐行**一致。"""
    view_columns = _column_count(CANDIDATES_VIEW)
    mv_columns = _column_count(CANDIDATES_MV)
    if view_columns != mv_columns:
        raise RuntimeError(
            "候选集物化副本与正本列数不同，拒绝继续：view={view} mv={mv}".format(
                view=view_columns, mv=mv_columns
            )
        )
    view_minus_mv, mv_minus_view = _content_diff(CANDIDATES_VIEW, CANDIDATES_MV)
    if view_minus_mv or mv_minus_view:
        raise RuntimeError(
            "候选集物化副本与正本内容不一致，拒绝继续："
            "view_minus_mv={a} mv_minus_view={b}".format(
                a=view_minus_mv, b=mv_minus_view
            )
        )


def _assert_copy_reads_source() -> None:
    """定义守护: 副本必须**从正本取数**, 且不得再自算。"""
    definition = _relation_definition(CANDIDATES_MV)
    if not definition:
        raise RuntimeError("候选集物化副本读取不到定义，拒绝继续")
    if CANDIDATES_VIEW not in definition:
        raise RuntimeError(
            "候选集物化副本的定义没有引用正本，拒绝继续：{view}".format(
                view=CANDIDATES_VIEW
            )
        )
    leftovers = [
        marker
        for marker in LEGACY_DEFINITION_MARKERS
        if marker.lower() in definition.lower()
    ]
    if leftovers:
        raise RuntimeError(
            "候选集物化副本仍在自算逻辑，拒绝继续：{markers}".format(
                markers=",".join(leftovers)
            )
        )


# ---------------------------------------------------------------------------
# 升级 / 回滚
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # 1) 依赖副本的对象先让开: 解析函数与两个原子层普通视图都改成读**正本**。
    #    * 解析函数是 LANGUAGE sql ⇒ 它的依赖**被跟踪**;
    #    * 两个原子层普通视图也**被跟踪**(live 实测)。
    #    不让开就 DROP 不掉副本; 换成正本之后口径完全等价, 中间态照样可用;
    #    ``CREATE OR REPLACE`` **保持 OID** ⇒ 下游对象不受影响。
    _rebuild_resolver_function(to_source_view=True)
    _rebuild_source_views(to_source_view=True)

    # 2) 删副本 —— **不带 CASCADE**(有依赖就让迁移失败, fail-closed)。
    if _exists(CANDIDATES_MV):
        _exec_sql("DROP MATERIALIZED VIEW IF EXISTS {mv}".format(mv=CANDIDATES_MV))

    # 3) 用新定义重建副本（资产文件的语义是「存在则 REFRESH / 不存在则 CREATE」）。
    if not _execute_asset(CANDIDATES_MV_ASSET):
        raise RuntimeError("候选集物化副本资产缺失，拒绝继续")

    # 4) 把让开的对象换回副本。
    _rebuild_resolver_function(to_source_view=False)
    _rebuild_source_views(to_source_view=False)

    # 5) 内容守护: 副本 == 正本, 逐行。
    _assert_copy_matches_source()

    # 6) 定义守护: 副本必须读正本, 不得再自算。
    _assert_copy_reads_source()


def downgrade() -> None:
    """回滚: 把副本恢复成迁移前的「手抄版」定义。

    顺序与升级对称:
    1. 解析函数与两个原子层普通视图改成读**正本**(让开副本);
    2. DROP 副本;
    3. 用**迁移前的定义正文**重建副本;
    4. 把解析函数与两个原子层普通视图换回副本;
    5. 内容比对 —— 回滚**不允许**改变任何一行的业务归属。
    """
    _rebuild_resolver_function(to_source_view=True)
    _rebuild_source_views(to_source_view=True)

    if _exists(CANDIDATES_MV):
        _exec_sql("DROP MATERIALIZED VIEW IF EXISTS {mv}".format(mv=CANDIDATES_MV))

    _exec_sql_text(
        "CREATE MATERIALIZED VIEW {mv} AS\n{body}".format(
            mv=CANDIDATES_MV, body=_LEGACY_COPY_BODY
        )
    )

    _rebuild_resolver_function(to_source_view=False)
    _rebuild_source_views(to_source_view=False)
    _assert_copy_matches_source()
