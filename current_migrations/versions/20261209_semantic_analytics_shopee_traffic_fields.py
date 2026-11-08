"""analytics(流量)域补登 shopee 独有的 5 个流量指标。

背景
----
2026-11-09 实测(开发库 ``b_class.fact_shopee_analytics_monthly`` 2354 行):

* shopee 的流量报表有 5 列**之前既没有标准字段、也没进语义层**:
  「新访客」「现有访客」「新关注者」「平均停留时长」「平均页面访问数」;
* 这 5 列 **2354/2354 行全部有值**, 按既有清洗链(去千分位逗号 / 空格 /
  破折号 → 正则校验)**2354/2354 全部可解析**;
* 「访客数」==「新访客」+「现有访客」—— **2354/2354 行精确相等**
  ⇒ 三者是同一个「访客」事实的三个切面(总量 / 新客 / 老客)⇒ 各自独立成
  标准字段, **不合并**(合并会让人以为「访客数 == 新访客」);
* 「新关注者」≤「访客数」—— **0 行违反**(关注者是访客的子集);
* 「平均页面访问数」≈「页面浏览数」÷「访客数」—— 1814 行可用行里
  **全部**落在 ±0.02 内 ⇒ 它是**派生均值**, 与 page_views / visitor_count
  **不是同一个事实** ⇒ 独立成字段;
* 「平均停留时长」是 **HH:MM:SS 字符串**(形如 ``00:00:42``, 区间 0~215 秒,
  均值 36.5 秒)⇒ **不能**套普通数值清洗(``01:30:00`` 会被当成 ``13000``)
  ⇒ 字段口径是**秒数**, 由视图专门换算;
* tiktok 侧**没有**这 5 列(实测 tiktok monthly 1374 行的 raw_data key 里
  一个都没有)⇒ 走**平台限定**别名(``platform_code='shopee'``),
  PG 侧 ``resolve_alias(..., platform_code)`` 只在 shopee 数据上命中。

本迁移做五件事
--------------
1. 落别名资产(``sql/semantic/semantic_alias_registry.sql``)——
   seed 311 -> **316** 条(新增 5 条 ``analytics``/``shopee`` 平台限定行)。
2. 重建 ``semantic.fact_analytics_atomic`` —— **末尾追加** 5 列
   (``new_visitor_count`` / ``returning_visitor_count`` / ``new_follower_count`` /
   ``avg_session_duration_seconds`` / ``avg_page_views_per_visitor``)。
   ⚠ **只能追加在末尾**: ``CREATE OR REPLACE VIEW`` 不能删列、不能改列序
   ⇒ 物化视图的列集变了 ⇒ 必须 DROP + 重建。
3. 重建 ``semantic.fact_analytics_atomic_mv`` + 索引,
   前后重建 4 个下游 mart 视图(解除依赖 -> 重建 -> 改回)。
4. 重建**月度链**(与日/周链**同源同口径**: 同一个指标在两条链上必须取到
   同一个列、同一套清洗规则)⇒ 日链与月链的数必须对得上。
   重建顺序不能反: 先删月度普通视图(CASCADE 连带删两个 mart) -> 删月度 MV ->
   建 MV -> 建普通视图 -> 建两个 mart。
5. fail-closed 自检:
   * analytics 域里不允许「同一个列名同时指向两个标准字段」(SSOT 硬约束);
   * 新增 5 个标准字段的**平台限定别名行必须在库里**;
   * 重建后的 4 个视图**必须输出这 5 列**, 且这 5 列必须是**追加**上去的
     (齐全 + 相对顺序不变 + 连续成块 + 追加在锚点列 ``identity_candidates``
     之后)—— 否则就是「字典登记了、但没真正接进语义层」。
     ⚠ 断言**不是**「必须是最后 5 列」: 后续迁移继续在末尾追加列是正常的,
       用绝对末尾会让本迁移的自检被后续迁移永久打断(空库链断裂)。

⚠ **不影响 orders 域与硬验收指标**(GMV 44,284.69 / 订单数 629)——
   本迁移只碰 analytics 域的视图与别名表, orders 链完全不动。
"""

from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261209_semantic_analytics_shopee_traffic"
down_revision = "current_schema_20261208_semantic_analytics_alias_resolve"
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

#: 物化时的语句超时预算(毫秒)—— 同 20261106 / 20261207 / 20261208 迁移。
MATERIALIZE_STATEMENT_TIMEOUT_MS = 30 * 60 * 1000

#: [*] 本迁移补登的 shopee 独有流量指标: (标准字段, 平台限定别名)。
#:
#: ⚠ 这些别名**必须**带 ``platform_code='shopee'`` ——
#:   tiktok 侧没有这 5 列(实测 1374 行的 raw_data key 里一个都没有),
#:   登记成通用别名会让将来 tiktok 上线同名列时**串口径**。
SHOPEE_TRAFFIC_FIELDS = (
    ("new_visitor_count", "新访客"),
    ("returning_visitor_count", "现有访客"),
    ("new_follower_count", "新关注者"),
    ("avg_session_duration_seconds", "平均停留时长"),
    ("avg_page_views_per_visitor", "平均页面访问数"),
)

#: 必须输出上面 5 列的视图。
TRAFFIC_COLUMN_VIEWS = (
    "semantic.fact_analytics_atomic",
    "semantic.fact_analytics_atomic_mv",
    "semantic.fact_analytics_monthly_atomic",
    "semantic.fact_analytics_monthly_atomic_mv",
)

#: 列序锚点 —— 新增列必须**追加在它之后**(它后面就是本次新增的列)。
TRAFFIC_COLUMN_ANCHOR = "identity_candidates"


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


def _assert_shopee_traffic_aliases() -> None:
    """fail-closed: 5 个 shopee 专属指标的**平台限定别名行**必须在库里。

    为什么单独断言: 这 5 个别名走 ``platform_code='shopee'`` ⇒ 它们**不在**
    域限定别名清单里 ⇒ 少落一行时 ``resolve_alias()`` 不会报错, 只会
    「安静地解析不出来」⇒ 视图输出整列 NULL, 而巡检会把 0% 解析率报成
    「源表没有这一列」= **误导**。
    ⇒ 这里在建视图**之前**就 fail-closed。
    """
    expected = [(field, alias) for field, alias in SHOPEE_TRAFFIC_FIELDS]
    with _driver_connection().cursor() as cursor:
        cursor.execute(
            """
            SELECT standard_field, raw_alias, platform_code
            FROM semantic.semantic_field_aliases
            WHERE data_domain = 'analytics'
              AND status = 'active'
              AND platform_code = 'shopee'
              AND standard_field = ANY(%s)
            """,
            ([field for field, _ in expected],),
        )
        rows = cursor.fetchall()
    found = {(str(row[0]), str(row[1]), str(row[2])) for row in rows}
    missing = [
        "{0} <- {1}".format(field, alias)
        for field, alias in expected
        if (field, alias, "shopee") not in found
    ]
    if missing:
        raise RuntimeError(
            "shopee 专属流量指标的别名行缺失(analytics/shopee): " + "；".join(missing)
        )


def _check_column_block(
    view_name: str,
    columns: list,
    expected: tuple,
    anchor: str,
) -> None:
    """fail-closed: 期望列必须**全部存在**、**相对顺序正确**、**连续成块**,
    且整块**追加在锚点列之后**。

    ⚠ 为什么**不是**「必须是最后 N 列」:
      视图列只允许追加(``CREATE OR REPLACE VIEW`` 不能删列、不能改列序)⇒
      后面再来一个迁移(比如 20261210)继续在末尾追加列是**正常且正确**的。
      若这里断言「这 5 列必须是最后 5 列」, 那么 20261210 一落地, 20261209
      的自检就永久失败 ⇒ **空库迁移链直接断掉**。
      ⇒ 真正要守的不变量是「**新增列只能追加, 既有列一个都不能动**」,
        它等价于: 期望列齐全 + 相对顺序不变 + 连续成块 + 追加在锚点之后。

    :param view_name: 视图名(报错信息用)
    :param columns: 视图当前的实际列序(按 attnum)
    :param expected: 期望存在的列, 顺序即期望的相对顺序
    :param anchor: 锚点列 —— 新增列必须追加在它**之后**
    """
    if not columns:
        raise RuntimeError("视图不存在或没有可见列: {0}".format(view_name))
    missing = [name for name in expected if name not in columns]
    if missing:
        raise RuntimeError(
            "视图 {0} 缺少新登记的 shopee 流量指标列: {1}".format(
                view_name, "、".join(missing)
            )
        )
    positions = [columns.index(name) for name in expected]
    if positions != sorted(positions):
        raise RuntimeError(
            "视图 {0} 的新登记列相对顺序变了(实际下标: {1})".format(
                view_name, positions
            )
        )
    if positions[-1] - positions[0] != len(expected) - 1:
        raise RuntimeError(
            "视图 {0} 的新登记列不是连续的一块(实际下标: {1})".format(
                view_name, positions
            )
        )
    if anchor not in columns:
        raise RuntimeError(
            "视图 {0} 缺少锚点列 {1}, 无法确认新列是追加的".format(view_name, anchor)
        )
    if columns.index(anchor) >= positions[0]:
        raise RuntimeError(
            "视图 {0} 的新登记列没有追加在锚点列 {1} 之后(锚点下标 {2}, 新列起始下标 {3})".format(
                view_name, anchor, columns.index(anchor), positions[0]
            )
        )


def _assert_traffic_columns() -> None:
    """fail-closed: 4 个视图必须输出这 5 列, 且这 5 列是**追加**上去的。

    为什么查列序: ``CREATE OR REPLACE VIEW`` 不能改列序 ⇒ 新列只能追加。
    若将来有人把新列插在中间, 物化视图的列集/列序会与既有下游不一致
    ⇒ 这里直接 fail-closed。

    ⚠ 断言的是「齐全 + 相对顺序 + 连续 + 追加在锚点之后」,
      **不是**「必须是最后 5 列」—— 后者会让后续迁移一追加列就把本迁移
      的自检永久打断(空库链断裂)。详见 :func:`_check_column_block`。
    """
    expected = tuple(field for field, _ in SHOPEE_TRAFFIC_FIELDS)
    with _driver_connection().cursor() as cursor:
        for view_name in TRAFFIC_COLUMN_VIEWS:
            cursor.execute(
                """
                SELECT attname
                FROM pg_attribute
                WHERE attrelid = to_regclass(%s)
                  AND attnum > 0
                  AND NOT attisdropped
                ORDER BY attnum
                """,
                (view_name,),
            )
            columns = [str(row[0]) for row in cursor.fetchall()]
            _check_column_block(view_name, columns, expected, TRAFFIC_COLUMN_ANCHOR)


def upgrade() -> None:
    # 1) 别名资产: 表结构 + 索引 + resolve_alias() + seed(311 -> 316) + 清理段
    alias_sql = _read_asset(ALIAS_ASSET)
    if alias_sql:
        _exec_sql_text(alias_sql)

    # 2) fail-closed 自检: 别名落库后确认没有「一个列名两个语义键」
    _assert_no_ambiguous_aliases()

    # 3) fail-closed 自检: 5 个 shopee 专属指标的**平台限定**别名行必须在库里
    _assert_shopee_traffic_aliases()

    # 4) 下游视图先改读普通视图 ⇒ 此时物化视图没有依赖 ⇒ 可以安全重建
    for view_name, asset_rel_path in ANALYTICS_MV_CONSUMERS:
        _rebuild_view(asset_rel_path, replace=ANALYTICS_MV, with_=ANALYTICS_VIEW)

    # 5) 物化视图的正文来源(普通视图)—— 先重建, 再建物化视图
    for view_name, asset_rel_path in SOURCE_VIEW_ASSETS:
        _rebuild_view(asset_rel_path)

    def _materialize() -> None:
        # ⚠ 列集变了(末尾追加 5 列)⇒ REFRESH 会报
        #   "cannot refresh ... has more columns" ⇒ 只能 drop + 重建。
        #   (且 ``sql/semantic/analytics_atomic.sql`` 开头是 ``DROP VIEW ... CASCADE``
        #   ⇒ 重建普通视图时物化视图**已经被连带删掉** ⇒ 资产里的
        #   「存在则 REFRESH / 不存在则 CREATE」会走 CREATE 分支。)
        if _exists(ANALYTICS_MV):
            _exec_sql("DROP MATERIALIZED VIEW {mv}".format(mv=ANALYTICS_MV))
        _exec_sql_text(_read_asset(MV_ASSET))

    _with_extended_statement_timeout(_materialize)

    # 6) 下游视图改回读物化视图
    for view_name, asset_rel_path in ANALYTICS_MV_CONSUMERS:
        _rebuild_view(asset_rel_path)

    # 7) 月度链 —— 与日/周链同源, 口径必须一致
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

    # 8) fail-closed 自检: 4 个视图必须输出新登记的 5 列(且在末尾)
    _assert_traffic_columns()


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
