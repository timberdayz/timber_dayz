"""把订单/流量事实原子层物化，修掉业务概览与 B 成本页的 20 秒级慢查询。

背景
----
生产实测（2026-11-04，容器内直连）：

    /api/dashboard/business-overview/operational-metrics   22.77 秒
    /api/dashboard/business-overview/bootstrap             23.22 秒

``EXPLAIN SELECT count(*) FROM mart.shop_day_kpi WHERE period_date = '2026-09-15'``
→ **20.2 秒**。执行计划显示 9 张 B 类订单表全部 ``Seq Scan``，
``metric_date`` 过滤**无法下推**到去重窗口
（``ROW_NUMBER() OVER (PARTITION BY platform_code, shop_id, data_hash ...)``）之下，
于是每次请求都要重做：9 表全量扫描 + 逐行 JSON 解析 + 逐行 ``LEFT JOIN LATERAL``
店铺身份解析。

为什么物化的是「整个原子视图」
--------------------------
``semantic.fact_orders_atomic`` / ``semantic.fact_analytics_atomic`` 是普通视图，
每行都要跑一次店铺别名解析。本迁移建的两个物化视图，
**正文就是对应普通视图的正文**（``SELECT * FROM <普通视图>``）——
同一份定义、同一套去重、同一套身份解析。

⇒ **口径零变化**：物化只改变「什么时候算」，不改变「算什么」。
   （替代方案「按粒度各建一个 MV 并换源」会换掉行集合：实测去重窗口在生产上
   38,607 行全部唯一，实际生效的是 daily 477 / weekly 1,506 / monthly 36,624
   三种粒度混合累加；换源会让 B 成本金额漂移 → 已否决。）

消费方（6 个，全部改为读物化视图）
--------------------------------
    mart.shop_day_kpi            mart.shop_week_kpi
    mart.platform_day_kpi        mart.platform_week_kpi
    mart.b_cost_shop_month
    api.b_cost_analysis_order_detail_module

本迁移做三件事
--------------
1. 建 ``semantic.fact_orders_atomic_mv``（物化）+ 2 个索引；
2. 建 ``semantic.fact_analytics_atomic_mv``（物化）+ 2 个索引；
3. 用 ``sql/`` 下的**资产文件**重建上面 6 个视图，让它们改读物化视图。

关于第 3 步为什么读资产文件而不是把视图定义抄进迁移
--------------------------------------------------
视图定义的 SSOT 是 ``sql/`` 下的资产文件。抄进迁移 = 两份定义 = 必然漂移。
资产文件缺失时**跳过该视图并告警**，不阻断迁移（迁移只保证物化层就位，
视图重建还有 deploy 的 ``rebuild_views.py`` 与 dashboard bootstrap 两道兜底）。

物化视图为什么不用 ``DROP MATERIALIZED VIEW ... CASCADE``
--------------------------------------------------------
CASCADE 会连带删掉下游。下游里有两个**不是 refresh registry 可重建目标**的对象
—— ``mart.hr_shop_monthly_profit`` 与 ``mart.inventory_backlog_base_mv``；
而 ``mart.b_cost_shop_month`` / ``api.b_cost_analysis_order_detail_module``
也不在 dashboard bootstrap 的 core 计划里。一旦被 CASCADE 删掉就没人重建
→ B 成本页直接挂。所以物化视图的刷新统一走
``sql/semantic/orders_atomic_mv.sql`` 里的「存在则 REFRESH（原地刷新）/
不存在则 CREATE」写法：既不删任何下游，也避开「DROP 与重建之间视图短暂消失」
的窗口。
"""

from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261106_create_atomic_materialized_views"
down_revision = "current_schema_20261105_create_identity_candidates_mv"
branch_labels = None
depends_on = None


REPO_ROOT = Path(__file__).resolve().parents[2]

ORDERS_MV = "semantic.fact_orders_atomic_mv"
ANALYTICS_MV = "semantic.fact_analytics_atomic_mv"

#: (物化视图, 它的数据来源普通视图)
MATERIALIZED_VIEWS = (
    (ORDERS_MV, "semantic.fact_orders_atomic"),
    (ANALYTICS_MV, "semantic.fact_analytics_atomic"),
)

#: 需要改读物化视图的消费方 → 对应的 SQL 资产文件（相对仓库根）
CONSUMER_VIEW_ASSETS = (
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

#: 需要**先重建**的原子层普通视图（它们是物化视图的正文来源）。
#:
#: 两个改动叠在一起，必须在建物化视图**之前**重建：
#: 1. 改读物化候选集（``semantic.shop_identity_resolution_candidates_v2_mv``，
#:    迁移 20261105 建的）—— 根治「每行订单事实重算候选集」的 N+1；
#: 2. ``analytics_atomic.sql`` 补了数值合法性校验 —— 之前的清洗正则
#:    ``'[^0-9.-]'`` 会**保留** ``.`` 与 ``-``，脏值 ``"-"`` 清洗后仍是 ``"-"``，
#:    ``'.'::numeric`` 直接抛 ``invalid input syntax for type numeric``。
#:    这个缺陷平时被 PostgreSQL 的**列裁剪**掩盖了（``SELECT count(*)`` 不算
#:    这些列），直到 ``CREATE MATERIALIZED VIEW`` 要物化**全部列**才炸出来。
#:
#: 正文仍然是 ``sql/`` 下的资产文件（SSOT），迁移不抄第二份。
SOURCE_VIEW_ASSETS = (
    ("semantic.fact_orders_atomic", "sql/semantic/orders_atomic.sql"),
    ("semantic.fact_analytics_atomic", "sql/semantic/analytics_atomic.sql"),
)

INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_fact_orders_atomic_mv_gran_date_platform_shop "
    "ON semantic.fact_orders_atomic_mv (granularity, metric_date, platform_code, shop_id)",
    "CREATE INDEX IF NOT EXISTS ix_fact_orders_atomic_mv_platform_shop_hash "
    "ON semantic.fact_orders_atomic_mv (platform_code, shop_id, data_hash)",
    "CREATE INDEX IF NOT EXISTS ix_fact_analytics_atomic_mv_gran_date_platform_shop "
    "ON semantic.fact_analytics_atomic_mv (granularity, metric_date, platform_code, shop_id)",
    "CREATE INDEX IF NOT EXISTS ix_fact_analytics_atomic_mv_platform_shop_hash "
    "ON semantic.fact_analytics_atomic_mv (platform_code, shop_id, data_hash)",
)

#: 物化时用的语句超时预算（毫秒）。
#:
#: 生产实测（2026-11-04）：``SELECT count(*) FROM semantic.fact_orders_atomic``
#: 单独就要 **114.6 秒**（38,607 行，9 表全量 UNION + 逐行 LATERAL 身份解析）。
#: 而生产的 ``statement_timeout`` 是 **2min = 120s** ⇒ 首次 ``CREATE MATERIALIZED
#: VIEW`` 必然被数据库掐断（v7.13.0 首次发布就是这么失败的：迁移事务整体回滚，
#: 生产已自动回滚到 v7.12.9，无残留）。
#:
#: CREATE 还要把 38,607 行**写进物化存储**并建 4 个索引，比只读 count 更重，
#: 所以预算按「count 的 3~4 倍」给，留足余量：30 分钟。
MATERIALIZE_STATEMENT_TIMEOUT_MS = 30 * 60 * 1000


def _with_extended_statement_timeout(action):
    """在 ``action`` 执行期间把语句超时提到物化预算，结束后恢复原值。

    用会话级 ``SET``（不是 ``SET LOCAL``）：alembic 迁移在事务里跑，
    ``SET LOCAL`` 只在事务内有效，而这里要保证**跨语句**生效（建 MV 与建索引
    是多条语句）。会话级设置必须在 ``finally`` 里恢复 —— 迁移用的连接
    之后会归还连接池，带着 30 分钟超时会污染后续应用查询。
    """
    bind = op.get_bind()
    original = bind.execute(sa.text("SHOW statement_timeout")).scalar_one()
    # SET 是 utility statement，**不接受参数占位符**（会退化成
    # ``SET statement_timeout = $1`` → 语法错误），只能拼字面量。
    # 两个值都是可信来源：内部常量 + 数据库自己 ``SHOW`` 出来的原值。
    restore_sql = "SET statement_timeout = '{value}'".format(value=original)
    _exec_sql(
        "SET statement_timeout = '{ms}'".format(ms=MATERIALIZE_STATEMENT_TIMEOUT_MS)
    )
    try:
        result = action()
    except BaseException:
        # 失败时事务已经 aborted，再执行 SET 会抛 InFailedSqlTransaction ——
        # 那会把**原始错误盖掉**（v7.13.1 就是这么把真正的
        # ``invalid input syntax for type numeric`` 藏掉的）。
        # 这里吞掉恢复异常，让原始错误冒到最外层。
        # 事务回滚时 ``SET statement_timeout`` 本身也会被回滚，不会残留。
        try:
            _exec_sql(restore_sql)
        except Exception:  # noqa: BLE001
            pass
        raise
    _exec_sql(restore_sql)
    return result


def _driver_connection():
    """拿到原生 psycopg2 连接。

    ``Connection.connection`` 是**属性**（不是方法），返回连接池代理
    ``_ConnectionFairy``；真正的驱动连接在它的 ``driver_connection`` 上。
    注意后面**不能加括号** —— 返回的对象不可调用，加括号会报
    ``TypeError: '_ConnectionFairy' object is not callable``。

    这与 schema baseline（``20260805_current_schema_baseline.py``）用的是
    同一套取法。
    """
    pool_conn = op.get_bind().connection
    return getattr(pool_conn, "driver_connection", pool_conn)


def _exec_sql(statement: str) -> None:
    """执行一条原生 SQL。

    **不用** ``exec_driver_sql``：它会把空参数字典（SQLAlchemy 的
    ``immutabledict``）交给 psycopg2 的 ``cursor.execute``，而 psycopg2 只接受
    真正的 ``dict``/序列 ⇒
    ``TypeError: sqlalchemy.cyextension.immutabledict.immutabledict is not a sequence``。
    """
    with _driver_connection().cursor() as cursor:
        cursor.execute(statement)


def _exec_sql_text(sql_text: str) -> None:
    """执行一段原生 SQL（**可以含多条语句**）。

    psycopg2 走 PostgreSQL 的**简单查询协议**（``PQexec``），一条 query 里
    可以带多条语句，由数据库自己按分号切分，**并且数据库自己认 dollar-quoted
    块**（``DO $$ ... $$`` 不会被切坏）。

    应用侧走 asyncpg，不支持多语句，所以那边必须自己切（见
    ``backend/services/data_pipeline/sql_loader.py``）。
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


def _create_materialized_view(mv_name: str, source_view: str) -> None:
    """建物化视图（已存在则跳过）。

    正文是 ``SELECT * FROM <普通视图>`` —— 与普通视图同一份定义，口径零变化。
    """
    if _exists(mv_name):
        return
    _exec_sql(
        "CREATE MATERIALIZED VIEW {mv} AS SELECT * FROM {src}".format(
            mv=mv_name, src=source_view
        )
    )


def _rebuild_consumer_view(view_name: str, asset_rel_path: str) -> bool:
    """用 ``sql/`` 下的资产文件重建消费方视图。

    资产文件缺失 → 返回 False（跳过并告警），不阻断迁移。

    整份文件一次执行（psycopg2 简单查询协议，数据库自己切语句）：
    资产里既有 ``CREATE SCHEMA`` 也有视图定义，整批执行保证它们在同一个
    隐式事务里 —— 中途失败会整批回滚，不会留下「schema 建了、视图没建」
    的半截状态。
    """
    asset_path = REPO_ROOT / asset_rel_path
    if not asset_path.is_file():
        print(
            "[WARN] 资产文件缺失，跳过视图重建：{view} ← {path}".format(
                view=view_name, path=asset_rel_path
            )
        )
        return False
    sql_text = asset_path.read_text(encoding="utf-8")
    _exec_sql_text(sql_text)
    return True


def upgrade() -> None:
    # 0) 先重建两个原子层普通视图（它们是物化视图的正文来源）：
    #    改读物化候选集 + analytics 数值合法性校验。
    #    必须在建物化视图**之前** —— 否则物化出来的是旧定义。
    for view_name, asset_rel_path in SOURCE_VIEW_ASSETS:
        _rebuild_consumer_view(view_name, asset_rel_path)

    # 1) + 2) 物化视图与索引
    #    这一步是**长任务**：全量重算原子视图（实测 114.6 秒）还要写 38,607 行
    #    并建 4 个索引，远超生产默认的 statement_timeout=120s ⇒ 必须临时抬高预算，
    #    否则 v7.13.0 首次发布就是这么失败的（迁移事务整体回滚，生产自动回滚到
    #    v7.12.9，无残留）。
    def _materialize() -> None:
        for mv_name, source_view in MATERIALIZED_VIEWS:
            _create_materialized_view(mv_name, source_view)
        for statement in INDEX_STATEMENTS:
            _exec_sql(statement)

    _with_extended_statement_timeout(_materialize)

    # 3) 消费方视图改读物化视图
    for view_name, asset_rel_path in CONSUMER_VIEW_ASSETS:
        _rebuild_consumer_view(view_name, asset_rel_path)


def downgrade() -> None:
    """回滚：把消费方视图改回读普通视图，再删掉两个物化视图。

    **顺序很关键**：必须先把消费方改回普通视图，再删物化视图。
    反过来（先删 MV）会失败 —— MV 上有依赖。

    刻意**不用** ``DROP MATERIALIZED VIEW ... CASCADE``：
    CASCADE 会连带删掉下游对象，而下游里存在**不是 refresh registry 可重建
    目标**的对象（例如 ``mart.inventory_backlog_base_mv``）⇒ 删了就没人重建，
    库存积压口径直接空掉。先改引用、再无 CASCADE 删除 ⇒ 不会误伤任何东西。
    """
    for view_name, asset_rel_path in CONSUMER_VIEW_ASSETS:
        asset_path = REPO_ROOT / asset_rel_path
        if not asset_path.is_file():
            continue
        sql_text = asset_path.read_text(encoding="utf-8")
        sql_text = sql_text.replace(
            "semantic.fact_orders_atomic_mv", "semantic.fact_orders_atomic"
        ).replace("semantic.fact_analytics_atomic_mv", "semantic.fact_analytics_atomic")
        _exec_sql_text(sql_text)

    for mv_name, _source_view in MATERIALIZED_VIEWS:
        if _exists(mv_name):
            _exec_sql("DROP MATERIALIZED VIEW IF EXISTS {mv}".format(mv=mv_name))
