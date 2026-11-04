"""下线业务概览的「滞销清理排名（月度）」模块。

背景
----
``api.clearance_ranking_module`` 这张视图的**设计本身有问题**，不是慢查询能救的：

- 它把「店铺级月度滞销清理排名」和「SKU 级库龄/动销」两套不同口径揉在一张表里
  （字段有 ``clearance_amount`` / ``incentive_amount`` / ``total_incentive``，
  数据源却是 SKU 粒度的 ``mart.inventory_backlog_base``）；
- 排名口径依赖 ``semantic.fact_orders_atomic`` 的窗口销量，
  于是**每次请求都要把 9 张订单表 UNION 出来逐行做窗口去重 + 逐行身份解析**，
  并且过滤条件没有日期下推 → 全量重算，是业务概览 504 的主要来源之一；
- 语义层对不上店的行会被归到 ``unknown`` 桶，排名里就会出现「某个不存在���店铺」。

结论：**整模块下线**（前端区块 + 后端接口 + 服务方法 + 视图 + 刷新注册 + 缓存），
不再投入优化。库存域的「SKU 级滞销清单」（``api.sku_clearance_ranking_module``）
是另一套东西，走 ``mart.inventory_state``，**保持不变**。

本迁移只做五件事
---------------
1. ``DROP VIEW IF EXISTS api.clearance_ranking_module``（不带 CASCADE，
   由 PostgreSQL 对未预料到的依赖直接报错兜底，不静默连带删除下游）；
2. 清掉 ``ops.dashboard_asset_state`` 里 ``module_name='clearance_ranking'``
   的历史行 —— 该模块键已改名为 ``inventory_backlog``，留着旧行会让
   资产状态表里出现一个永远没人更新的幽灵模块；
3. 清掉 ``ops.data_freshness_log`` 里 ``target_name='api.clearance_ranking_module'``
   的行 —— v7.12.9 起监控会**实时核对对象是否存在**，视图被删后这行会被报成
   ``status=missing``，变成僵尸目标；
4. 清掉 ``ops.data_lineage_registry`` 里指向该目标的血缘边（只清 target 侧：
   它是叶子视图，没人以它为源）；
5. ``DROP TABLE IF EXISTS c_class.clearance_rankings``（fail-closed：非空则中止）。
   这张表唯一的写入方 ``backend/services/clearance_ranking_service.py`` 已随
   模块下线删除（零活引用），留着表等于留着一条"复活已退役模块"的写入路径。
   ORM 模型 ``ClearanceRanking`` 同步从 schema SSOT 移除。

迁移后视图由 ``sql/api_modules/`` 下的资产文件管理，本迁移不重建它。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261104_drop_clearance_ranking_module"
down_revision = "current_schema_20261101_shop_identity_region_and_code"
branch_labels = None
depends_on = None


VIEW_NAME = "api.clearance_ranking_module"
LEGACY_MODULE_NAME = "clearance_ranking"
LEGACY_TABLE = "c_class.clearance_rankings"


def _view_exists() -> bool:
    bind = op.get_bind()
    return (
        bind.execute(
            sa.text("SELECT to_regclass(:name)"), {"name": VIEW_NAME}
        ).scalar_one_or_none()
        is not None
    )


def _ops_table_exists(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table, schema="ops")


def _legacy_table_exists() -> bool:
    return sa.inspect(op.get_bind()).has_table(
        "clearance_rankings", schema="c_class"
    )


def _delete_where(table: str, column: str, value: str) -> None:
    """按「列 = 值」删行。

    注意：alembic 的 ``op.execute(statement, parameters)`` 在本仓库锁定的
    alembic 版本里**不接受第二个位置参数**（TypeError），所以必须用
    ``op.get_bind().execute(text(...), params)`` 自己绑参。
    """
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM {table} WHERE {column} = :value".format(
            table=table, column=column
        )),
        {"value": value},
    )


def upgrade() -> None:
    # 1) 幂等：视图不存在就跳过。
    if _view_exists():
        op.execute("DROP VIEW IF EXISTS {view}".format(view=VIEW_NAME))

    # 2) 已下线模块的资产状态行。
    if _ops_table_exists("dashboard_asset_state"):
        _delete_where("ops.dashboard_asset_state", "module_name", LEGACY_MODULE_NAME)

    # 3) 僵尸新鲜度记录（v7.12.9 起会实时核对对象存在性 → 视图没了就会被报 missing）。
    if _ops_table_exists("data_freshness_log"):
        _delete_where("ops.data_freshness_log", "target_name", VIEW_NAME)

    # 4) 僵尸血缘边（只清 target 侧：它是叶子视图，没人以它为源）。
    if _ops_table_exists("data_lineage_registry"):
        _delete_where("ops.data_lineage_registry", "target_name", VIEW_NAME)

    # 5) 死表 c_class.clearance_rankings：
    #    这张表只被 backend/services/clearance_ranking_service.py 写，
    #    而那个 service 在本次下线后已删除（零活引用）——
    #    留着它就等于留着一条"复活已退役模块"的写入路径。
    #    fail-closed：非空则中止，不擅自丢数据。
    if _legacy_table_exists():
        bind = op.get_bind()
        row_count = bind.execute(
            sa.text("SELECT COUNT(*) FROM c_class.clearance_rankings")
        ).scalar_one()
        if row_count:
            raise RuntimeError(
                "c_class.clearance_rankings 非空({0} 行), 拒绝删除; "
                "请先人工确认这些数据是否需要迁移, 再重跑迁移。".format(row_count)
            )
        op.execute("DROP TABLE IF EXISTS c_class.clearance_rankings")


def downgrade() -> None:
    # 回滚：恢复一张与基线一致的兼容视图（SKU 粒度直读积压基表）。
    # 注意这不是下线前那份复杂排名实现 —— 它的口径本身就有问题，
    # 回滚只保证「依赖这个视图的旧代码不会因为对象缺失而直接报错」。
    op.execute(
        """
        CREATE OR REPLACE VIEW api.clearance_ranking_module AS
        SELECT b.snapshot_date,
               b.platform_code,
               b.shop_id,
               b.product_id,
               b.product_name,
               b.platform_sku,
               b.product_sku,
               b.available_stock,
               b.inventory_value,
               0::numeric AS total_sales,
               0::numeric AS total_orders,
               b.daily_avg_sales,
               b.estimated_turnover_days,
               b.stagnant_snapshot_count,
               b.estimated_stagnant_days,
               b.risk_level,
               b.clearance_priority_score
          FROM mart.inventory_backlog_base b
        """
    )
    # ⚠️ c_class.clearance_rankings **不随回滚重建**：
    #    它的 ORM 模型已从 schema SSOT 移除，基线里也不再建表，
    #    重建一张没有模型对应、没有写入方的表只会制造新的漂移。
    #    该表在删除时是空的（fail-closed 已校验），没有数据损失。
    op.execute("DROP TABLE IF EXISTS c_class.clearance_rankings")
