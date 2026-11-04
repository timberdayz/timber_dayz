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


revision = "current_schema_20261105_create_atomic_materialized_views"
down_revision = "current_schema_20261104_drop_clearance_ranking_module"
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
    不用 ``op.execute(statement, parameters)``：本仓库锁定的 alembic 版本
    不接受第二个位置参数，必须自己绑参或用 driver 级执行。
    """
    if _exists(mv_name):
        return
    op.get_bind().exec_driver_sql(
        "CREATE MATERIALIZED VIEW {mv} AS SELECT * FROM {src}".format(
            mv=mv_name, src=source_view
        )
    )


def _split_statements(sql_text: str) -> list[str]:
    """按 ``;`` 切分语句（跳过字符串字面量与行注释里的分号）。

    应用侧用的是 asyncpg，**不支持一次执行多条语句**，所以必须切。
    这里只处理本迁移会用到的资产文件形态：普通 SQL + 单引号字符串 + ``--`` 注释。
    """
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    index = 0
    length = len(sql_text)
    while index < length:
        char = sql_text[index]
        next_char = sql_text[index + 1] if index + 1 < length else ""
        if not in_single_quote and char == "-" and next_char == "-":
            end_of_line = sql_text.find("\n", index)
            if end_of_line == -1:
                break
            current.append(sql_text[index:end_of_line])
            index = end_of_line
            continue
        if char == "'":
            in_single_quote = not in_single_quote
        if char == ";" and not in_single_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def _rebuild_consumer_view(view_name: str, asset_rel_path: str) -> bool:
    """用 ``sql/`` 下的资产文件重建消费方视图。

    资产文件缺失 → 返回 False（跳过并告警），不阻断迁移。
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
    if "$$" in sql_text:
        raise RuntimeError(
            "{path} 含 dollar-quoted 块，本迁移的执行器不支持".format(
                path=asset_rel_path
            )
        )
    for statement in _split_statements(sql_text):
        op.get_bind().exec_driver_sql(statement)
    return True


def upgrade() -> None:
    # 1) + 2) 物化视图与索引
    for mv_name, source_view in MATERIALIZED_VIEWS:
        _create_materialized_view(mv_name, source_view)
    for statement in INDEX_STATEMENTS:
        op.get_bind().exec_driver_sql(statement)

    # 3) 消费方视图改读物化视图
    for view_name, asset_rel_path in CONSUMER_VIEW_ASSETS:
        _rebuild_consumer_view(view_name, asset_rel_path)


def downgrade() -> None:
    """回滚：删掉两个物化视图，并把消费方视图改回读普通视图。

    消费方视图用资产文件重建 —— 资产文件里此刻已经是「读物化视图」的版本，
    所以回滚时改读**基线里那份普通视图口径**：直接把 FROM 换回去即可，
    语义与本迁移前完全一致（物化视图正文 = 普通视图正文）。
    """
    for mv_name, _source_view in MATERIALIZED_VIEWS:
        if _exists(mv_name):
            op.get_bind().exec_driver_sql(
                "DROP MATERIALIZED VIEW IF EXISTS {mv} CASCADE".format(mv=mv_name)
            )

    for view_name, asset_rel_path in CONSUMER_VIEW_ASSETS:
        asset_path = REPO_ROOT / asset_rel_path
        if not asset_path.is_file():
            continue
        sql_text = asset_path.read_text(encoding="utf-8")
        sql_text = sql_text.replace(
            "semantic.fact_orders_atomic_mv", "semantic.fact_orders_atomic"
        ).replace(
            "semantic.fact_analytics_atomic_mv", "semantic.fact_analytics_atomic"
        )
        for statement in _split_statements(sql_text):
            op.get_bind().exec_driver_sql(statement)
