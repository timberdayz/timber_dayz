"""把商品事实原子层物化，修掉商品经营分析页 14 秒级的慢查询。

背景
----
生产实测（2026-11-05，容器内直连，强制全量物化）：

    COPY (SELECT * FROM semantic.fact_products_atomic) TO '/dev/null'  → 23.2 秒
    COPY (SELECT * FROM mart.product_day_kpi)        TO '/dev/null'  → 14.1 秒

``semantic.fact_products_atomic`` 是**普通视图**，每行都要跑一次店铺别名解析
（``LEFT JOIN LATERAL → semantic.resolve_shop_identity``）；而它的去重窗口
（``ROW_NUMBER() OVER (PARTITION BY ... data_hash)``）之上做不了日期/粒度下推，
于是每次请求都要重做「多表 UNION + 逐行 JSON 解析 + 逐行身份解析」。

受影响的业务面：``mart.product_day_kpi`` 被
``backend/domains/business/routers/performance_management.py``（商品经营分析/转化率）
与 ``backend/services/sync_standardization_quality_service.py``（标准化质量核对）读取。

为什么物化的是「整个原子视图」
---------------------------
物化视图的正文**就是**普通视图的正文（``SELECT * FROM <普通视图>``）——
同一份定义、同一套去重、同一套身份解析。

⇒ **口径零变化**：物化只改变「什么时候算」，不改变「算什么」。
   （替代方案「按粒度各建一个 MV 并换源」会换掉行集合：商品表里同时有
   daily/weekly/monthly 三种粒度，而商品日 KPI 只取 daily ⇒ 金额会漂。）

消费方（1 个）
------------
    mart.product_day_kpi

本迁移做三件事
--------------
1. 建 ``semantic.fact_products_atomic_mv``（物化）+ 2 个索引；
2. 用 ``sql/`` 下的**资产文件**重建 ``mart.product_day_kpi``，让它改读物化视图；
3. 回滚时把消费方改回读普通视图，再无 CASCADE 删掉物化视图。

关于第 2 步为什么读资产文件而不是把视图定义抄进迁移
--------------------------------------------------
视图定义的 SSOT 是 ``sql/`` 下的资产文件。抄进迁移 = 两份定义 = 必然漂移。
资产文件缺失时**跳过该视图并告警**，不阻断迁移（迁移只保证物化层就位，
视图重建还有 deploy 的 ``rebuild_views.py`` 与 dashboard bootstrap 两道兜底）。

物化视图为什么不用 ``DROP MATERIALIZED VIEW ... CASCADE``
--------------------------------------------------------
CASCADE 会连带删掉下游。本 MV 的唯一消费方 ``mart.product_day_kpi`` 是 registry
里可重建的目标，但它**不在** dashboard bootstrap 的 core 计划里 ⇒ 被 CASCADE
删掉时没人保证重建。所以物化视图的刷新统一走
``sql/semantic/products_atomic_mv.sql`` 里的「存在则 REFRESH（原地刷新）/
不存在则 CREATE」写法：既不删任何下游，也避开「DROP 与重建之间视图短暂消失」
的窗口。

超时预算
--------
生产 ``statement_timeout=120s``（docker-compose.prod.yml）。物料化要全量重算
商品原子层（实测 23.2 秒）**并把全部行写进物化存储**，比只读更重 ⇒ 必须临时
抬高预算，否则会被数据库静默掐断（v7.13.0 首次发布就是这么失败的：迁移事务
整体回滚，生产自动回滚）。预算按「订单原子层的同款口径」给 30 分钟
（参照 ``20261106`` 迁移的 ``MATERIALIZE_STATEMENT_TIMEOUT_MS``）。
"""

from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261110_create_products_atomic_materialized_view"
down_revision = "current_schema_20261109_add_commission_calculation_audit"
branch_labels = None
depends_on = None


REPO_ROOT = Path(__file__).resolve().parents[2]

PRODUCTS_MV = "semantic.fact_products_atomic_mv"
SOURCE_VIEW = "semantic.fact_products_atomic"

#: 需要改读物化视图的消费方 → 对应的 SQL 资产文件（相对仓库根）
CONSUMER_VIEW_ASSETS = (("mart.product_day_kpi", "sql/mart/product_day_kpi.sql"),)

INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_fact_products_atomic_mv_gran_date_platform_shop "
    "ON semantic.fact_products_atomic_mv (granularity, metric_date, platform_code, shop_id)",
    "CREATE INDEX IF NOT EXISTS ix_fact_products_atomic_mv_platform_shop_hash "
    "ON semantic.fact_products_atomic_mv (platform_code, shop_id, data_hash)",
)

#: 物化时用的语句超时预算（毫秒）—— 参照 20261106 迁移的同款口径。
MATERIALIZE_STATEMENT_TIMEOUT_MS = 30 * 60 * 1000


def _driver_connection():
    """拿到原生 psycopg2 连接。

    ``Connection.connection`` 是**属性**（不是方法），返回连接池代理
    ``_ConnectionFairy``；真正的驱动连接在它的 ``driver_connection`` 上。
    注意后面**不能加括号** —— 返回的对象不可调用，加括号会报
    ``TypeError: '_ConnectionFairy' object is not callable``。
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
        # 那会把**原始错误盖掉**。这里吞掉恢复异常，让原始错误冒到最外层。
        try:
            _exec_sql(restore_sql)
        except Exception:  # noqa: BLE001
            pass
        raise
    _exec_sql(restore_sql)
    return result


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
    # 1) 物化视图与索引。
    #    这一步是**长任务**：全量重算商品原子层（实测 23.2 秒）还要把全部行
    #    写进物化存储并建 2 个索引，远超生产默认的 statement_timeout=120s
    #    ⇒ 必须临时抬高预算。
    def _materialize() -> None:
        _create_materialized_view(PRODUCTS_MV, SOURCE_VIEW)
        for statement in INDEX_STATEMENTS:
            _exec_sql(statement)

    _with_extended_statement_timeout(_materialize)

    # 2) 消费方视图改读物化视图。
    for view_name, asset_rel_path in CONSUMER_VIEW_ASSETS:
        _rebuild_consumer_view(view_name, asset_rel_path)


def downgrade() -> None:
    """回滚：把消费方视图改回读普通视图，再删掉物化视图。

    **顺序很关键**：必须先把消费方改回普通视图，再删物化视图。
    反过来（先删 MV）会失败 —— MV 上有依赖。

    刻意**不用** ``DROP MATERIALIZED VIEW ... CASCADE``：
    CASCADE 会连带删掉下游对象，而下游里存在**不是 refresh registry 可重建
    目标**的对象 ⇒ 删了就没人重建。先改引用、再无 CASCADE 删除 ⇒ 不会误伤。
    """
    for view_name, asset_rel_path in CONSUMER_VIEW_ASSETS:
        asset_path = REPO_ROOT / asset_rel_path
        if not asset_path.is_file():
            continue
        sql_text = asset_path.read_text(encoding="utf-8")
        sql_text = sql_text.replace(
            "semantic.fact_products_atomic_mv", "semantic.fact_products_atomic"
        )
        _exec_sql_text(sql_text)

    if _exists(PRODUCTS_MV):
        _exec_sql("DROP MATERIALIZED VIEW IF EXISTS {mv}".format(mv=PRODUCTS_MV))
