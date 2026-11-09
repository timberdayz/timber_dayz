"""analytics(流量)域补登 tiktok 的 13 个 GMV 归因列(一列一个字段, 绝不聚合)。

背景
----
2026-11-09 实测(开发库 ``b_class.fact_tiktok_analytics_monthly`` 1374 行):
tiktok 的流量报表里有 13 个 GMV 归因列, 之前**既没有标准字段、也没进语义层**:

    商品卡 GMV / 商家直播 GMV / 商家直播间接 GMV / 商家视频 GMV /
    商家视频间接 GMV / 绑定账号直播归因 GMV / 绑定账号视频归因 GMV /
    联盟视频归因 GMV / 达人直播 GMV / 达人直播归因 GMV /
    达人直播间接 GMV / 达人视频 GMV / 达人视频间接 GMV

⚠⚠ **这批列绝不能相加** —— 这是本迁移最关键的一条:
    13 列合计 1,072,030.01, 总成交额 1,092,456.33(占 98.13%);
    **逐行**看: 741 个可比行里 **376 行(50.7%)归因和 > 该行总额**,
    比值中位 **1.019**、最大 **2.000**
    ⇒ 同一笔成交被多个维度**重复记账**(在直播间看到 → 点商品卡下单 →
      分享出去 ⇒ 平台把这单记到达人直播、商品卡等多个口径上)。
    ⇒ 用户 2026-11-09 决定: **一列一个标准字段, 只单列展示, 绝不聚合**。
    ⇒ 本迁移**不做任何跨列求和**, 也不把这批列铺到看板。

其它实测事实:
    * 「商家直播 GMV」「商家直播间接 GMV」「绑定账号直播归因 GMV」
      **1374 行恒为 0** ⇒ 业务方 **2026-11-09 确认: 我们没有做直播**
      ⇒ 这几列的 0 是**真实值**(没这个渠道), 不是「平台没回传」
      ⇒ 字典里如实写明, 不再留悬案; 也**不能**当成「渠道变差」的信号;
    * 「商品卡 GMV」只有 **198/1374 行有值**(147 行非零)⇒ 稀疏指标;
    * shopee 侧**一列都没有**(实测 2354 行 raw_data key 里找不到)
      ⇒ 别名走**平台限定**(``platform_code='tiktok'``);
    * 4 个既有字段(``live_gmv`` / ``live_indirect_gmv`` / ``video_gmv`` /
      ``video_indirect_gmv``)的**逐字别名**与源表列名完全一致 ⇒ **复用**,
      不另造重复字段(SSOT: 一个业务事实只允许一个标准字段);
      另 2 个既有字段(``live_attributed_gmv`` / ``video_attributed_gmv``)
      的别名「商家直播/视频归因 GMV」在源表里**不存在** ⇒ 推测性,
      本轮**不登记**(它们在别名表里没有行 ⇒ 巡检不会报缺口)。

本迁移做四件事
--------------
1. 落别名资产(``sql/semantic/semantic_alias_registry.sql``)——
   seed 316 -> **329** 条(新增 13 条 ``analytics``/``tiktok`` 平台限定行)。
2. 重建 ``semantic.fact_analytics_atomic`` —— **末尾追加** 13 列。
   ⚠ **只能追加在末尾**: ``CREATE OR REPLACE VIEW`` 不能删列、不能改列序
   ⇒ 物化视图的列集变了 ⇒ 必须 DROP + 重建。
3. 重建 ``semantic.fact_analytics_atomic_mv`` + 索引,
   前后重建 4 个下游 mart 视图(解除依赖 -> 重建 -> 改回);
   并重建**月度链**(与日/周链**同源同口径**)。
4. fail-closed 自检:
   * analytics 域里不允许「同一个列名同时指向两个标准字段」(SSOT 硬约束);
   * 13 个归因列的**平台限定别名行必须在库**;
   * 重建后的 4 个视图**必须输出这 13 列**, 且这 13 列必须是**追加**上去的
     (齐全 + 相对顺序不变 + 连续成块 + 追加在锚点列 ``identity_candidates``
     之后)。⚠ 断言**不是**「必须是最后 13 列」: 后续迁移继续在末尾追加列是
     正常的, 用绝对末尾会让本迁移的自检被后续迁移永久打断(空库链断裂)。

⚠ **不影响 orders 域与硬验收指标**(GMV 44,284.69 / 订单数 629)——
   本迁移只碰 analytics 域的视图与别名表, orders 链完全不动。
"""

from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261210_semantic_analytics_tiktok_attribution"
down_revision = "current_schema_20261209_semantic_analytics_shopee_traffic"
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

#: [*] 本迁移补登的 tiktok GMV 归因列: (标准字段, 平台限定别名)。
#:
#: ⚠ 这些别名**必须**带 ``platform_code='tiktok'`` ——
#:   shopee 侧**一列都没有**(实测 2354 行的 raw_data key 里找不到),
#:   登记成通用别名会让 shopee 数据上出现同名列时**串口径**。
#:
#: ⚠⚠ **这批列绝不聚合** —— 实测 50.7% 的行归因和超过该行总额
#:   (同一笔成交被多个维度重复记账)⇒ 只单列看占比。
TIKTOK_ATTRIBUTION_FIELDS = (
    ("product_card_gmv", "商品卡 GMV"),
    ("live_gmv", "商家直播 GMV"),
    ("live_indirect_gmv", "商家直播间接 GMV"),
    ("video_gmv", "商家视频 GMV"),
    ("video_indirect_gmv", "商家视频间接 GMV"),
    ("bound_account_live_attributed_gmv", "绑定账号直播归因 GMV"),
    ("bound_account_video_attributed_gmv", "绑定账号视频归因 GMV"),
    ("affiliate_video_attributed_gmv", "联盟视频归因 GMV"),
    ("creator_live_gmv", "达人直播 GMV"),
    ("creator_live_attributed_gmv", "达人直播归因 GMV"),
    ("creator_live_indirect_gmv", "达人直播间接 GMV"),
    ("creator_video_gmv", "达人视频 GMV"),
    ("creator_video_indirect_gmv", "达人视频间接 GMV"),
)

#: 视图末尾必须出现的列(顺序固定)。
#:
#: = 20261209 补的 5 个 shopee 流量指标 + 本迁移的 13 个 tiktok 归因列。
TRAFFIC_TAIL_COLUMNS = (
    "new_visitor_count",
    "returning_visitor_count",
    "new_follower_count",
    "avg_session_duration_seconds",
    "avg_page_views_per_visitor",
) + tuple(field for field, _alias in TIKTOK_ATTRIBUTION_FIELDS)

#: 必须输出上面这些列的视图。
TRAFFIC_COLUMN_VIEWS = (
    "semantic.fact_analytics_atomic",
    "semantic.fact_analytics_atomic_mv",
    "semantic.fact_analytics_monthly_atomic",
    "semantic.fact_analytics_monthly_atomic_mv",
)

#: 列序锚点 —— 新增列必须**追加在它之后**(它后面就是 analytics 域新增的列)。
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


def _assert_tiktok_attribution_aliases() -> None:
    """fail-closed: 13 个 GMV 归因列的**平台限定别名行**必须在库里。

    为什么单独断言: 这些别名走 ``platform_code='tiktok'`` ⇒ 它们**不在**
    域限定别名清单里 ⇒ 少落一行时 ``resolve_alias()`` 不会报错, 只会
    「安静地解析不出来」⇒ 视图输出整列 NULL, 而巡检会把 0% 解析率报成
    「源表没有这一列」= **误导**。
    ⇒ 这里在建视图**之前**就 fail-closed。
    """
    expected = [(field, alias) for field, alias in TIKTOK_ATTRIBUTION_FIELDS]
    with _driver_connection().cursor() as cursor:
        cursor.execute(
            """
            SELECT standard_field, raw_alias, platform_code
            FROM semantic.semantic_field_aliases
            WHERE data_domain = 'analytics'
              AND status = 'active'
              AND platform_code = 'tiktok'
              AND standard_field = ANY(%s)
            """,
            ([field for field, _ in expected],),
        )
        rows = cursor.fetchall()
    found = {(str(row[0]), str(row[1]), str(row[2])) for row in rows}
    missing = [
        "{0} <- {1}".format(field, alias)
        for field, alias in expected
        if (field, alias, "tiktok") not in found
    ]
    if missing:
        raise RuntimeError(
            "tiktok GMV 归因列的别名行缺失(analytics/tiktok): " + "；".join(missing)
        )


def _assert_no_attribution_aggregation() -> None:
    """fail-closed: 视图**不许**对这批归因列做跨列求和。

    实测(2026-11-09): 13 列逐行相加, 741 个可比行里 **376 行(50.7%)**
    归因和**超过该行总额**(比值中位 1.019、最大 2.000)
    ⇒ 同一笔成交被多个维度重复记账 ⇒ 相加出来的数是**错的**。

    用户 2026-11-09 的决定: **一列一个标准字段, 只单列展示, 绝不聚合**。
    ⇒ 这里把「不许聚合」钉进迁移: 视图定义里若出现对归因列的 SUM,
      迁移直接失败。
    """
    attribution_fields = {field for field, _alias in TIKTOK_ATTRIBUTION_FIELDS}
    with _driver_connection().cursor() as cursor:
        cursor.execute(
            """
            SELECT c.relname, pg_get_viewdef(c.oid)
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'semantic'
              AND c.relname = ANY(%s)
            """,
            (
                [
                    "fact_analytics_atomic",
                    "fact_analytics_atomic_mv",
                    "fact_analytics_monthly_atomic",
                    "fact_analytics_monthly_atomic_mv",
                ],
            ),
        )
        rows = cursor.fetchall()
    for relname, viewdef in rows:
        lowered = str(viewdef).lower()
        for field in sorted(attribution_fields):
            if (
                "sum({0})".format(field) in lowered
                or "sum({0} ".format(field) in lowered
            ):
                raise RuntimeError(
                    "视图 {0} 里对归因列 {1} 做了求和 —— 这批列不可聚合".format(
                        relname, field
                    )
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
      视图列只允许追加 ⇒ 后面再来一个迁移继续在末尾追加列是**正常**的。
      若断言「这 18 列必须是最后 18 列」, 那么下一个迁移一落地, 本迁移
      的自检就永久失败 ⇒ **空库迁移链直接断掉**。
      ⇒ 真正要守的不变量是「**新增列只能追加, 既有列一个都不能动**」,
        它等价于: 期望列齐全 + 相对顺序不变 + 连续成块 + 追加在锚点之后。
    """
    if not columns:
        raise RuntimeError("视图不存在或没有可见列: {0}".format(view_name))
    missing = [name for name in expected if name not in columns]
    if missing:
        raise RuntimeError(
            "视图 {0} 缺少新登记的流量指标列: {1}".format(view_name, "、".join(missing))
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
    """fail-closed: 4 个视图必须输出这 18 列, 且这 18 列是**追加**上去的。

    为什么查列序: ``CREATE OR REPLACE VIEW`` 不能改列序 ⇒ 新列只能追加。
    若将来有人把新列插在中间, 物化视图的列集/列序会与既有下游不一致
    ⇒ 这里直接 fail-closed。

    ⚠ 断言的是「齐全 + 相对顺序 + 连续 + 追加在锚点之后」,
      **不是**「必须是最后 18 列」—— 后者会让后续迁移一追加列就把本迁移
      的自检永久打断(空库链断裂)。详见 :func:`_check_column_block`。
    """
    expected = tuple(TRAFFIC_TAIL_COLUMNS)
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
    # 1) 别名资产: 表结构 + 索引 + resolve_alias() + seed(316 -> 329) + 清理段
    alias_sql = _read_asset(ALIAS_ASSET)
    if alias_sql:
        _exec_sql_text(alias_sql)

    # 2) fail-closed 自检: 别名落库后确认没有「一个列名两个语义键」
    _assert_no_ambiguous_aliases()

    # 3) fail-closed 自检: 13 个 GMV 归因列的**平台限定**别名行必须在库里
    _assert_tiktok_attribution_aliases()

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

    # 8) fail-closed 自检: 4 个视图必须输出新登记的 18 列(且在末尾);
    #    并且**不许**对归因列求和(这批列绝不能聚合)。
    _assert_traffic_columns()
    _assert_no_attribution_aggregation()


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
