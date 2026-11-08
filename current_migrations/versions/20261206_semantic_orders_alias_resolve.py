"""orders 域取数切到别名表（SSOT）+ 出口去假 0。

背景
----
orders 域的取数写在 ``sql/semantic/orders_atomic.sql`` 与
``sql/semantic/orders_monthly_atomic_mv.sql`` 的**手写 COALESCE 链**里,
别名表只覆盖 products 域 ⇒ 字典描述不了 orders 域到底有哪些列。

2026-11-08 开发库实测暴露的两个硬伤:

1. **兜底会落到裸名列 ⇒ 混币种**。
   源表每个金额列都**成对出现**: ``X``(原币) 与 ``X(RMB)``(人民币)。
   实测(shopee monthly 29629 行)::

       买家支付:   原币均值 240.11 / (RMB) 均值  72.03(非零行 27672, 相等仅 391)
       利润:       原币均值  27.98 / (RMB) 均值  11.06
       仓库操作费: 原币均值  11.56 / (RMB) 均值   4.99
       卖家支付运费: 原币均值 -40.36 / (RMB) 均值 -14.13

   而手写链的兜底顺序是「(RMB) → 裸名」⇒ 取不到 (RMB) 就悄悄用原币。
   旧链里 ``仓库操作费`` / ``订单原始金额`` / ``利润`` / ``服务费`` 命中的
   **就是原币列** ⇒ 平台成本虚高约 3.3 倍
   (视图实测 631,035.08 vs 按 (RMB) 重算 191,010.71)。

2. **出口把「取不到数」伪装成 0**。
   ``COALESCE(x, 0)`` 让缺项与「真的是 0」在下游分不开 ⇒ 平台成本 6 项里
   取不到数的那几项被系统性记 0。

本迁移做四件事
--------------
1. 落别名资产(``sql/semantic/semantic_alias_registry.sql``)—— orders 域的
   列名清单**穷举**登记(只登 ``(RMB)`` 变体), 并新增**平台维度**
   (``platform_code``)以区分「同业务、不同平台不同列名」。
2. 把与人民币口径冲突的模板确认行置为 ``disabled``(保留记录, 不删除)。
3. 重建 ``semantic.fact_orders_atomic`` + ``semantic.fact_orders_monthly_atomic_mv``
   及其物化视图与下游视图。
4. 出口去掉假 0, 并新增 ``platform_total_cost_known_items``(已知成本项数)。

关于「为什么合并成一条迁移」
--------------------------
方案原本把「切别名表」与「出口去假 0」拆成两条迁移。但两条改的是**同一个视图**,
且第 2 条会新增列 ⇒ 物化视图必须 **drop + 重建**(列集变了, REFRESH 会报错)。
拆开 = 物化视图重建两次(生产实测单次全量重算 114.6 秒 + 写 38,607 行 + 建索引),
中间还会出现一个「已切别名但出口仍是假 0」的**半截状态**。
⇒ 合并成一条: 一次重建, 一步到位。

物化视图为什么敢 drop
--------------------
``semantic.fact_orders_atomic_mv`` 的下游**全部**在 refresh registry 里,
都有 ``sql/`` 资产文件可重建:

    mart.shop_day_kpi / mart.shop_week_kpi
    mart.platform_day_kpi / mart.platform_week_kpi
    mart.b_cost_shop_month
    api.b_cost_analysis_order_detail_module

顺序很关键(与 ``20261106_create_atomic_materialized_views`` 的 downgrade 同理):

1. 先把下游视图**改读普通视图**(资产文件里把 MV 名替换成普通视图名);
2. 再 ``DROP MATERIALIZED VIEW``(**不带 CASCADE**)⇒ 此时已无依赖, 不会误伤;
3. 重建普通视图;
4. 建物化视图 + 索引;
5. 再把下游视图**改读物化视图**。

⚠ 刻意不用 ``DROP ... CASCADE``: CASCADE 会连带删掉不在 registry 里的对象。
本迁移全程只碰上面列出来的那几个。

物化视图的时间预算
------------------
生产实测(2026-11-04): ``SELECT count(*) FROM semantic.fact_orders_atomic``
单次就要 **114.6 秒**; CREATE 还要把 38,607 行写进物化存储并建索引。
生产 ``statement_timeout`` 默认 120s ⇒ 必须临时抬高(同 20261106 迁移的做法)。
"""

from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261206_semantic_orders_alias_resolve"
down_revision = "current_schema_20261205_warehouse_name_aliases"
branch_labels = None
depends_on = None


REPO_ROOT = Path(__file__).resolve().parents[2]

#: 别名资产(表结构 + 索引 + resolve_alias() + seed + 陈旧 builtin 行清理)。
#: 整份执行: DDL 都是 ``IF NOT EXISTS`` / ``CREATE OR REPLACE``, seed 带
#: ``ON CONFLICT``, 清理段只删 ``builtin`` 行 ⇒ 幂等。
ALIAS_ASSET = "sql/semantic/semantic_alias_registry.sql"

#: 原子层普通视图(物化视图的正文来源)。
SOURCE_VIEW_ASSETS = (
    ("semantic.fact_orders_atomic", "sql/semantic/orders_atomic.sql"),
)

#: 月度原子层的物化视图 —— 它是**正本**(普通视图只是它的薄包装)。
MONTHLY_MV_ASSET = "sql/semantic/orders_monthly_atomic_mv.sql"

#: 月度 MV 的下游(``DROP ... CASCADE`` 会把它们一起删掉 ⇒ 必须重建)。
MONTHLY_MV_DEPENDENTS = (
    ("semantic.fact_orders_monthly_atomic", "sql/semantic/orders_monthly_atomic.sql"),
    ("mart.platform_month_kpi", "sql/mart/platform_month_kpi.sql"),
    ("mart.shop_month_kpi", "sql/mart/shop_month_kpi.sql"),
    (
        "api.business_overview_shop_racing_monthly_module",
        "sql/api_modules/business_overview_shop_racing_monthly_module.sql",
    ),
)

#: 订单物化视图的下游(全部在 refresh registry 里, 有资产可重建)。
ORDERS_MV_CONSUMERS = (
    ("mart.shop_day_kpi", "sql/mart/shop_day_kpi.sql"),
    ("mart.shop_week_kpi", "sql/mart/shop_week_kpi.sql"),
    ("mart.platform_day_kpi", "sql/mart/platform_day_kpi.sql"),
    ("mart.platform_week_kpi", "sql/mart/platform_week_kpi.sql"),
    ("mart.b_cost_shop_month", "sql/mart/b_cost_shop_month.sql"),
    (
        "api.b_cost_analysis_order_detail_module",
        "sql/api_modules/b_cost_analysis_order_detail_module.sql",
    ),
)

ORDERS_MV = "semantic.fact_orders_atomic_mv"
ORDERS_VIEW = "semantic.fact_orders_atomic"

INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_fact_orders_atomic_mv_gran_date_platform_shop "
    "ON semantic.fact_orders_atomic_mv (granularity, metric_date, platform_code, shop_id)",
    "CREATE INDEX IF NOT EXISTS ix_fact_orders_atomic_mv_platform_shop_hash "
    "ON semantic.fact_orders_atomic_mv (platform_code, shop_id, data_hash)",
)

#: 物化时的语句超时预算(毫秒)—— 同 20261106 迁移。
MATERIALIZE_STATEMENT_TIMEOUT_MS = 30 * 60 * 1000


#: 与人民币口径冲突的模板确认行 ⇒ 置为 ``disabled``。
#:
#: 为什么必须禁用(而不是"两者并存"):
#:   ``semantic.resolve_alias()`` 的排序是「平台精确匹配 → 粒度精确匹配 →
#:   置信度 → 来源 → id」。模板确认行带 ``granularity='weekly'`` 且置信度
#:   0.950, builtin 行是 ``granularity=NULL`` / 置信度 1.000 —— 但**粒度
#:   匹配排在置信度前面** ⇒ weekly 行会命中模板行 ⇒ 拿到**原币**。
#:   monthly 行走 builtin ⇒ 人民币。**同一张事实表里两种币种** ⇒ 不可接受。
#:
#: 为什么是 ``disabled`` 而不是删除:
#:   ``disabled`` 是这张表既有的「人已裁决不要这条」状态 ⇒ 记录保留、可审计、
#:   不影响 ``template_confirmed`` 的其它行。
CONFLICTING_TEMPLATE_ALIASES = (
    # 利润: 源表的「利润」是**原币**列, 项目口径是人民币 ⇒ 指向「利润(RMB)」。
    ("profit", "利润"),
    # 商品SKU: 源表里「平台SKU」与「商品SKU」是**两个不同的列**
    # (实测 shopee monthly: 平台SKU 非空 29116 行 / 商品SKU 非空 25618 行)。
    # 两条都指向 platform_sku ⇒ 取数时按「平台匹配 + 粒度匹配」排序,
    # weekly 的模板行会**顶掉**字典登记的「平台SKU」⇒ platform_sku 取到
    # 「商品SKU」, 与 product_sku 同值(实测 tiktok weekly 174/208 行同值)。
    # ⇒ 商品SKU 归 ``product_sku``, 平台SKU 归 ``platform_sku``。
    ("platform_sku", "商品SKU"),
)


def _driver_connection():
    """拿到原生 psycopg2 连接(见 20261106 迁移的同名函数)。"""
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
    """在 ``action`` 执行期间把语句超时提到物化预算, 结束后恢复原值。

    用会话级 ``SET``(不是 ``SET LOCAL``): alembic 迁移在事务里跑,
    ``SET LOCAL`` 只在事务内有效, 而这里要跨语句生效(建 MV 与建索引是多条语句)。
    """
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


def _disable_conflicting_template_aliases() -> None:
    """把与人民币口径冲突的模板确认行置为 ``disabled``(保留记录)。"""
    for standard_field, raw_alias in CONFLICTING_TEMPLATE_ALIASES:
        _exec_sql(
            """
            UPDATE semantic.semantic_field_aliases
               SET status = 'disabled',
                   updated_at = NOW()
             WHERE data_domain = 'orders'
               AND source = 'template_confirmed'
               AND status = 'active'
               AND standard_field = '{field}'
               AND raw_alias = '{alias}'
            """.format(
                field=standard_field.replace("'", "''"),
                alias=raw_alias.replace("'", "''"),
            )
        )


def upgrade() -> None:
    # 1) 别名资产: 表结构 + 索引 + resolve_alias() + orders 域 seed + 清理段
    alias_sql = _read_asset(ALIAS_ASSET)
    if alias_sql:
        _exec_sql_text(alias_sql)

    # 2) 口径冲突的模板确认行置为 disabled(必须在重建视图之前 ——
    #    否则重建出来的视图第一次解析就会命中原币列)
    _disable_conflicting_template_aliases()

    # 3) 下游视图先改读普通视图 ⇒ 此时物化视图没有依赖 ⇒ 可以安全 DROP
    for view_name, asset_rel_path in ORDERS_MV_CONSUMERS:
        _rebuild_view(asset_rel_path, replace=ORDERS_MV, with_=ORDERS_VIEW)

    # 4) 物化视图的正文来源(普通视图)—— 先重建, 再建物化视图
    for view_name, asset_rel_path in SOURCE_VIEW_ASSETS:
        _rebuild_view(asset_rel_path)

    def _materialize() -> None:
        # 4a) 列集变了(新增 platform_total_cost_known_items)⇒ REFRESH 会报
        #     "cannot refresh ... has more columns", 只能 drop + 重建。
        if _exists(ORDERS_MV):
            _exec_sql("DROP MATERIALIZED VIEW {mv}".format(mv=ORDERS_MV))
        _exec_sql(
            "CREATE MATERIALIZED VIEW {mv} AS SELECT * FROM {src}".format(
                mv=ORDERS_MV, src=ORDERS_VIEW
            )
        )
        for statement in INDEX_STATEMENTS:
            _exec_sql(statement)

        # 4b) 月度链路: MV 的正本。它的资产是 DROP ... CASCADE + CREATE,
        #     会连带删掉下游 ⇒ 紧接着重建。
        monthly_sql = _read_asset(MONTHLY_MV_ASSET)
        if monthly_sql:
            _exec_sql_text(monthly_sql)
        for view_name, asset_rel_path in MONTHLY_MV_DEPENDENTS:
            _rebuild_view(asset_rel_path)

    _with_extended_statement_timeout(_materialize)

    # 5) 下游视图改回读物化视图
    for view_name, asset_rel_path in ORDERS_MV_CONSUMERS:
        _rebuild_view(asset_rel_path)


def downgrade() -> None:
    """回滚。

    ⚠ **不回退视图定义** —— 视图定义的正本是 ``sql/`` 下的资产文件,
    回退 = 把资产文件改回旧版再跑一遍, 那是**代码回滚**的事, 不是迁移的职责。
    本迁移的数据库侧效果只有两类:
    1. 别名资产(可重新 seed, 幂等);
    2. 物化视图 / 下游视图的**内容**(可 REFRESH 回当前定义)。

    ⇒ 这里只做「按当前资产定义重建一遍」, 保证 schema 与资产一致。
    """
    for view_name, asset_rel_path in ORDERS_MV_CONSUMERS:
        _rebuild_view(asset_rel_path, replace=ORDERS_MV, with_=ORDERS_VIEW)
    for view_name, asset_rel_path in SOURCE_VIEW_ASSETS:
        _rebuild_view(asset_rel_path)

    def _materialize() -> None:
        if _exists(ORDERS_MV):
            _exec_sql("DROP MATERIALIZED VIEW {mv}".format(mv=ORDERS_MV))
        _exec_sql(
            "CREATE MATERIALIZED VIEW {mv} AS SELECT * FROM {src}".format(
                mv=ORDERS_MV, src=ORDERS_VIEW
            )
        )
        for statement in INDEX_STATEMENTS:
            _exec_sql(statement)

    _with_extended_statement_timeout(_materialize)

    for view_name, asset_rel_path in ORDERS_MV_CONSUMERS:
        _rebuild_view(asset_rel_path)
