"""把库存事实语义层物化，修掉库存链路的 197 毫秒级慢查询。

背景
----
生产实测（2026-11-14，3855 行，容器内直连）::

    COPY (SELECT * FROM b_class.fact_miaoshou_inventory_snapshot) TO '/dev/null'
        → 4.4 ms
    COPY (SELECT * FROM semantic.fact_inventory_snapshot) TO '/dev/null'
        → 197 ms

``semantic.fact_inventory_snapshot`` 是**普通视图**：每行都要跑一次查表函数
（``semantic.is_collection_source_identifier()`` / ``semantic.resolve_warehouse_code()``），
两张只有 5~72 行的小对照表因此被扫了 650 万次；候选池与 ``scoped`` CTE 也会被逐行重算。

受影响的业务面：库存快照族（``mart.inventory_snapshot_history`` /
``mart.inventory_current``）、库存状态层（``mart.inventory_state``，
由 ``InventoryStateRefreshService`` 写入）、库龄层、滞销清单与低库存告警。

为什么物化的是「整个语义视图」
-----------------------------
物化视图的正文**就是**普通视图的正文（``SELECT * FROM <普通视图>``）——
同一份定义、同一套去重、同一套身份解析。

⇒ **口径零变化**：物化只改变「什么时候算」，不改变「算什么」。

消费方（3 处）
--------------
1. ``mart.inventory_snapshot_history``（视图）
2. ``mart.inventory_current``（视图）
3. ``backend/services/data_pipeline/inventory_state_refresh_service.py``
   的两条 SQL（状态层与库龄层的取数）

本迁移做两件事
--------------
1. 建 ``semantic.fact_inventory_snapshot_mv``（物化）+ 2 个索引；
2. （回滚时）把消费方改回读普通视图，再无 CASCADE 删掉物化视图。

消费方视图**不在本迁移里**改读物化视图
--------------------------------------
这是实测踩到坑之后的决定，不是省事：

* 视图定义的 SSOT 是 ``sql/`` 下的资产文件。抄进迁移 = 两份定义 = 必然漂移。
* 更硬的约束：``mart.inventory_snapshot_history`` 选的正本列里含
  ``observed_at`` / ``checklist_sales_*``，而这些列**不在迁移链里**
  —— 基线 ``current_schema_20260805`` 是 2026-08-05 的静态快照，
  这些列只在生产/开发库上由部署期的视图重建落地。
  ⇒ 迁移里执行**当前**资产文件时，正本视图的列集可能还是旧的 ⇒
  ``column "observed_at" does not exist`` ⇒ 整条迁移失败
  （空库预演 ``test_schema_cleanup_rehearsal`` 实测复现）。
* 迁移只保证「物化层就位」，不依赖任何视图的**当前列集** ⇒ 空库/生产都能过。

⇒ 视图切换交给既有机制（两条都已在库里跑过）：
  1. 部署期 ``scripts/rebuild_views.py --all-plain-views``：
     清单 = refresh registry ∩ 库里已存在的普通视图 ⇒ 必然包含这两个视图；
  2. 刷新计划按依赖顺序刷新（副本 → history/current → 下游），
     依赖表里已登记 ``mart.inventory_snapshot_history → 副本``。

物化视图为什么不用 ``DROP MATERIALIZED VIEW ... CASCADE``
--------------------------------------------------------
CASCADE 会连带删掉下游。本 MV 的消费方都在 refresh registry 里是可重建的目标，
但它们**不在** dashboard bootstrap 的 core 计划里 ⇒ 被 CASCADE 删掉时没人保证重建。
所以物化视图的刷新统一走 ``sql/semantic/inventory_snapshot_mv.sql`` 里的
「存在则 REFRESH（原地刷新）/ 不存在则 CREATE」写法：既不删任何下游，
也避开「DROP 与重建之间视图短暂消失」的窗口。

超时预算
--------
生产 ``statement_timeout=120s``（docker-compose.prod.yml）。物料化要全量重算
库存语义层**并把全部行写进物化存储并建索引**，比只读更重 ⇒ 临时抬高预算，
否则会被数据库静默掐断（v7.13.0 首次发布就是这么失败的：迁移事务整体回滚，
生产自动回滚）。预算按「订单/商品原子层的同款口径」给 30 分钟
（参照 ``20261110`` 迁移的 ``MATERIALIZE_STATEMENT_TIMEOUT_MS``）。
"""

from pathlib import Path

from alembic import op
import sqlalchemy as sa


# ⚠️ revision id **最长 64 字符**（``version_num`` 列是 ``String(64)``，
# 见 ``current_migrations/env.py`` 的 version_table_impl）⇒ 超长会在
# ``alembic upgrade`` 写版本号时报 StringDataRightTruncation。
revision = "current_schema_20261231_inventory_snapshot_mv"
down_revision = "current_schema_20261230_drop_residual_test_accounts"
branch_labels = None
depends_on = None


REPO_ROOT = Path(__file__).resolve().parents[2]

INVENTORY_MV = "semantic.fact_inventory_snapshot_mv"
SOURCE_VIEW = "semantic.fact_inventory_snapshot"

#: 需要改读物化视图的消费方 → 对应的 SQL 资产文件（相对仓库根）
CONSUMER_VIEW_ASSETS = (
    ("mart.inventory_snapshot_history", "sql/mart/inventory_snapshot_history.sql"),
    ("mart.inventory_current", "sql/mart/inventory_current.sql"),
)

INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_fact_inventory_snapshot_mv_gran_date_platform_shop "
    "ON semantic.fact_inventory_snapshot_mv (granularity, metric_date, platform_code, shop_id)",
    "CREATE INDEX IF NOT EXISTS ix_fact_inventory_snapshot_mv_platform_shop_hash "
    "ON semantic.fact_inventory_snapshot_mv (platform_code, shop_id, data_hash)",
)

#: 物化时用的语句超时预算（毫秒）—— 参照 20261110 迁移的同款口径。
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


def upgrade() -> None:
    # 1) 物化视图与索引。
    #    这一步是**长任务**：全量重算库存语义层并把全部行写进物化存储，
    #    远超生产默认的 statement_timeout=120s ⇒ 必须临时抬高预算。
    def _materialize() -> None:
        _create_materialized_view(INVENTORY_MV, SOURCE_VIEW)
        for statement in INDEX_STATEMENTS:
            _exec_sql(statement)

    _with_extended_statement_timeout(_materialize)

    # 2) **不**在这里重建消费方视图。
    #    视图定义的 SSOT 是 sql/ 下的资产文件；迁移里重建 = 两份定义 = 必然漂移，
    #    而且会因「正本视图的列集在迁移链里是旧版」而失败
    #    （observed_at / checklist_sales_* 不在基线 20260805 的快照里）。
    #    切换由部署期的 rebuild_views.py --all-plain-views 与刷新计划负责。


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
        sql_text = sql_text.replace(INVENTORY_MV, SOURCE_VIEW)
        _exec_sql_text(sql_text)

    if _exists(INVENTORY_MV):
        _exec_sql("DROP MATERIALIZED VIEW IF EXISTS {mv}".format(mv=INVENTORY_MV))
