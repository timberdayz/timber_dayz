"""analytics(流量)域取数改走别名表 + 出口去掉假 0。

背景
----
``semantic.fact_analytics_atomic`` 的取数是 12 段**手写** ``COALESCE(raw_data->>'...')``
链, 与真实表头对不上的地方全靠「找不到就填 0」掩盖。实测(开发库, 2026-11-08):

* shopee 2355 行、tiktok 1446 行里, ``impressions`` / ``clicks`` / ``gmv`` /
  ``order_count`` 的**合计全是 0** —— 其中绝大多数是**取不到值**而不是真的没有;
* 「曝光次数」「点击次数」对不上 tiktok 的真实列名(「商品曝光次数」「商品点击量」);
* 「跳出率」对不上全局别名(「跳失率」);
* 「SKU 订单数」「总成交额」「GMV」同理。

⇒ 出口再套一层 ``COALESCE(x, 0)`` ⇒ **「不知道」被伪装成「0」**。

本迁移做五件事
--------------
1. 落别名资产(``sql/semantic/semantic_alias_registry.sql``)——
   seed 234 -> **311** 条(新增 **analytics 域**: 该域此前**一条 builtin 行都没有**,
   ``semantic.resolve_alias()`` 只能命中 9 条模板确认行 ⇒ 域限定别名清单形同虚设)。
2. 重建 ``semantic.fact_analytics_atomic`` —— 取数改走 ``semantic.resolve_alias()``,
   出口去掉 12 处 ``COALESCE(x, 0)``。
   ⚠ **输出列名与列序一个都没改** ⇒ 物化视图的列集不变。
3. 重建 ``semantic.fact_analytics_atomic_mv`` + 索引,
   前后重建 4 个下游 mart 视图(解除依赖 -> 重建 -> 改回)。
4. 重建**月度链**(与日/周链同源: 两者都从 b_class 的 analytics 月度源表取数)
   —— 同一个指标在两条链上必须取到**同一个列** ⇒ 两条链必须一起改,
   否则看板的月度数会和日/周数对不上。重建顺序不能反:
   先删月度普通视图(CASCADE 连带删两个 mart) -> 删月度 MV -> 建 MV ->
   建普通视图 -> 建两个 mart。
5. fail-closed 自检: analytics 域里不允许出现「同一个列名同时指向两个标准字段」
   (SSOT 的「一个列名只认一个标准字段」硬约束)。
"""

from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261208_semantic_analytics_alias_resolve"
down_revision = "current_schema_20261207_semantic_orders_new_fields"
branch_labels = None
depends_on = None


REPO_ROOT = Path(__file__).resolve().parents[2]

#: 别名资产(表结构 + 索引 + resolve_alias() + seed + 陈旧 builtin 行清理)。
#: 整份执行: DDL 都是 ``IF NOT EXISTS`` / ``CREATE OR REPLACE``, seed 带
#: ``ON CONFLICT``, 清理段只删 ``builtin`` 行 ⇒ 幂等。
ALIAS_ASSET = "sql/semantic/semantic_alias_registry.sql"

#: 原子层普通视图(物化视图的正文来源)。
SOURCE_VIEW_ASSETS = (
    ("semantic.fact_analytics_atomic", "sql/semantic/analytics_atomic.sql"),
)

#: 物化视图资产(存在则 REFRESH / 不存在则 CREATE)。
MV_ASSET = "sql/semantic/analytics_atomic_mv.sql"

#: 物化视图的下游(全部按**具体列名**取数 ⇒ 加列/改值都不影响它们)。
ANALYTICS_MV_CONSUMERS = (
    ("mart.shop_day_kpi", "sql/mart/shop_day_kpi.sql"),
    ("mart.shop_week_kpi", "sql/mart/shop_week_kpi.sql"),
    ("mart.platform_day_kpi", "sql/mart/platform_day_kpi.sql"),
    ("mart.platform_week_kpi", "sql/mart/platform_week_kpi.sql"),
)

ANALYTICS_MV = "semantic.fact_analytics_atomic_mv"
ANALYTICS_VIEW = "semantic.fact_analytics_atomic"

#: 月度链的资产 —— 与日/周链**同源**(b_class 的 analytics 月度源表),
#: 同一个指标在两条链上必须取到**同一个列** ⇒ 两条链一起改。
MONTHLY_MV_ASSET = "sql/semantic/analytics_monthly_atomic_mv.sql"
MONTHLY_VIEW_ASSET = "sql/semantic/analytics_monthly_atomic.sql"

#: 月度链的下游(读月度普通视图)。
MONTHLY_KPI_ASSETS = (
    "sql/mart/platform_month_kpi.sql",
    "sql/mart/shop_month_kpi.sql",
)

MONTHLY_MV = "semantic.fact_analytics_monthly_atomic_mv"
MONTHLY_VIEW = "semantic.fact_analytics_monthly_atomic"

#: 物化时的语句超时预算(毫秒)—— 同 20261106 / 20261207 迁移。
MATERIALIZE_STATEMENT_TIMEOUT_MS = 30 * 60 * 1000


def _driver_connection():
    """拿到原生 psycopg2 连接(见 20261207 迁移的同名函数)。"""
    pool_conn = op.get_bind().connection
    return getattr(pool_conn, "driver_connection", pool_conn)


def _exec_sql(statement: str) -> None:
    """执行一条原生 SQL(不用 ``exec_driver_sql``: immutabledict 不是序列)。"""
    with _driver_connection().cursor() as cursor:
        cursor.execute(statement)


def _exec_sql_text(sql_text: str) -> None:
    """执行一段原生 SQL(可含多条语句)。

    psycopg2 走简单查询协议, 数据库自己切分语句、也认 dollar-quoted 块
    (``DO $$ ... $$`` 不会被切坏), 且整批在同一个隐式事务里。
    """
    with _driver_connection().cursor() as cursor:
        cursor.execute(sql_text)


def _exists(name: str) -> bool:
    bind = op.get_bind()
    return (
        bind.execute(
            sa.text("SELECT to_regclass(:name)"), {"name": name}
        ).scalar_one_or_none()
        is not None
    )


def _read_asset(asset_rel_path: str) -> str:
    asset_path = REPO_ROOT / asset_rel_path
    if not asset_path.is_file():
        print("[WARN] 资产文件缺失, 跳过: {path}".format(path=asset_rel_path))
        return ""
    return asset_path.read_text(encoding="utf-8")


def _rebuild_view(asset_rel_path: str, *, replace: str = "", with_: str = "") -> bool:
    """用 ``sql/`` 下的资产文件重建一个视图。

    ``replace``/``with_`` 用于在**不改资产文件**的前提下改写视图正文里的
    物化视图名 —— 物化视图重建前后要来回切一次下游视图的引用。
    资产文件缺失 ⇒ 返回 False(跳过并告警), 不阻断迁移。
    """
    sql_text = _read_asset(asset_rel_path)
    if not sql_text:
        return False
    if replace:
        sql_text = sql_text.replace(replace, with_)
    _exec_sql_text(sql_text)
    return True


def _with_extended_statement_timeout(action):
    """在 ``action`` 执行期间把语句超时提到物化预算, 结束后恢复原值。"""
    bind = op.get_bind()
    original = bind.execute(sa.text("SHOW statement_timeout")).scalar_one()
    restore_sql = "SET statement_timeout = '{value}'".format(value=original)
    _exec_sql(
        "SET statement_timeout = '{ms}'".format(ms=MATERIALIZE_STATEMENT_TIMEOUT_MS)
    )
    try:
        result = action()
    except BaseException:
        # 失败时事务已 aborted, 再执行 SET 会抛 InFailedSqlTransaction ——
        # 那会把**原始错误**盖掉。这里吞掉恢复异常, 让原始错误冒到最外层。
        try:
            _exec_sql(restore_sql)
        except Exception:  # noqa: BLE001
            pass
        raise
    _exec_sql(restore_sql)
    return result


def _assert_no_ambiguous_aliases() -> None:
    """fail-closed: analytics 域里不允许「同一个列名同时指向两个标准字段」。

    SSOT 的硬约束是「一个列名只认一个标准字段」——
    ``semantic.resolve_alias()`` 只能按 (domain, field) 查询, 所以同一列名
    挂在两个字段上时, 两个字段会**各自**取到值 ⇒ 下游会把同一个数字
    当成两个不同的业务事实。

    这里只查**生效**的行(status='active'); 已被人工裁决置为 disabled /
    conflict 的历史行不算。
    """
    with _driver_connection().cursor() as cursor:
        cursor.execute(
            """
            SELECT raw_alias, COUNT(DISTINCT standard_field) AS field_count,
                   MIN(standard_field) AS one_field, MAX(standard_field) AS another_field
            FROM semantic.semantic_field_aliases
            WHERE data_domain = 'analytics'
              AND status = 'active'
            GROUP BY raw_alias
            HAVING COUNT(DISTINCT standard_field) > 1
            """
        )
        rows = cursor.fetchall()
    if rows:
        problems = [
            "列名 {alias!r} 同时指向 {one} 与 {two}".format(
                alias=row[0], one=row[2], two=row[3]
            )
            for row in rows
        ]
        raise RuntimeError(
            "analytics 域存在「一个列名指向多个标准字段」: " + "；".join(problems)
        )


def upgrade() -> None:
    # 1) 别名资产: 表结构 + 索引 + resolve_alias() + seed(234 -> 311) + 清理段
    alias_sql = _read_asset(ALIAS_ASSET)
    if alias_sql:
        _exec_sql_text(alias_sql)

    # 2) fail-closed 自检: 别名落库后确认没有「一个列名两个语义键」
    _assert_no_ambiguous_aliases()

    # 3) 下游视图先改读普通视图 ⇒ 此时物化视图没有依赖 ⇒ 可以安全重建
    for view_name, asset_rel_path in ANALYTICS_MV_CONSUMERS:
        _rebuild_view(asset_rel_path, replace=ANALYTICS_MV, with_=ANALYTICS_VIEW)

    # 4) 物化视图的正文来源(普通视图)—— 先重建, 再建物化视图
    for view_name, asset_rel_path in SOURCE_VIEW_ASSETS:
        _rebuild_view(asset_rel_path)

    def _materialize() -> None:
        # ⚠ ``sql/semantic/analytics_atomic.sql`` 开头是 ``DROP VIEW ... CASCADE``
        #   ⇒ 重建普通视图时物化视图**已经被连带删掉** ⇒ 资产里的
        #   「存在则 REFRESH / 不存在则 CREATE」会走 CREATE 分支。
        #   (列集没变, 本来 REFRESH 就够; 但 CASCADE 已经删了, 只能重建。)
        if _exists(ANALYTICS_MV):
            _exec_sql("DROP MATERIALIZED VIEW {mv}".format(mv=ANALYTICS_MV))
        _exec_sql_text(_read_asset(MV_ASSET))

    _with_extended_statement_timeout(_materialize)

    # 5) 下游视图改回读物化视图
    for view_name, asset_rel_path in ANALYTICS_MV_CONSUMERS:
        _rebuild_view(asset_rel_path)

    # 6) 月度链 —— 与日/周链同源, 口径必须一致
    #
    # ⚠ 重建顺序(不能反):
    #   月度 mart 视图 -> 月度普通视图 -> 月度物化视图(MV)
    #   ⇒ 先删普通视图(CASCADE 连带删两个 mart) -> 删 MV -> 建 MV ->
    #     建普通视图 -> 建两个 mart。
    #   若先删 MV, 普通视图与 mart 会因为依赖而失败。
    def _rebuild_monthly_chain() -> None:
        _exec_sql("DROP VIEW IF EXISTS {view} CASCADE".format(view=MONTHLY_VIEW))
        _exec_sql("DROP MATERIALIZED VIEW IF EXISTS {mv} CASCADE".format(mv=MONTHLY_MV))
        _exec_sql_text(_read_asset(MONTHLY_MV_ASSET))
        _exec_sql_text(_read_asset(MONTHLY_VIEW_ASSET))
        for asset_rel_path in MONTHLY_KPI_ASSETS:
            _exec_sql_text(_read_asset(asset_rel_path))

    _with_extended_statement_timeout(_rebuild_monthly_chain)


def downgrade() -> None:
    """回滚。

    ⚠ **不回退视图定义** —— 视图定义的正本是 ``sql/`` 下的资产文件,
    回退 = 把资产文件改回旧版再跑一遍, 那是**代码回滚**的事, 不是迁移的职责。
    本迁移的数据库侧效果只有两类:
    1. 别名资产(可重新 seed, 幂等);
    2. 物化视图 / 下游视图的**内容**(可 REFRESH 回当前定义)。

    ⇒ 这里只做「按当前资产定义重建一遍」, 保证 schema 与资产一致。
    """
    for view_name, asset_rel_path in ANALYTICS_MV_CONSUMERS:
        _rebuild_view(asset_rel_path, replace=ANALYTICS_MV, with_=ANALYTICS_VIEW)
    for view_name, asset_rel_path in SOURCE_VIEW_ASSETS:
        _rebuild_view(asset_rel_path)

    def _materialize() -> None:
        if _exists(ANALYTICS_MV):
            _exec_sql("DROP MATERIALIZED VIEW {mv}".format(mv=ANALYTICS_MV))
        _exec_sql_text(_read_asset(MV_ASSET))

    _with_extended_statement_timeout(_materialize)

    for view_name, asset_rel_path in ANALYTICS_MV_CONSUMERS:
        _rebuild_view(asset_rel_path)

    def _rebuild_monthly_chain() -> None:
        _exec_sql("DROP VIEW IF EXISTS {view} CASCADE".format(view=MONTHLY_VIEW))
        _exec_sql("DROP MATERIALIZED VIEW IF EXISTS {mv} CASCADE".format(mv=MONTHLY_MV))
        _exec_sql_text(_read_asset(MONTHLY_MV_ASSET))
        _exec_sql_text(_read_asset(MONTHLY_VIEW_ASSET))
        for asset_rel_path in MONTHLY_KPI_ASSETS:
            _exec_sql_text(_read_asset(asset_rel_path))

    _with_extended_statement_timeout(_rebuild_monthly_chain)
