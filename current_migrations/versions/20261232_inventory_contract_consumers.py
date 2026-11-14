"""B5：补登记库存域的**真实消费方**（语义契约 consumer）。

背景
----
``core.semantic_field_contracts`` 是「这个字段改了会影响谁」的登记表。
库存域只有 ``consumer='business_overview'`` 一个消费方 ⇒ **库存的影响面查不全**。

而实际上库存语义层有 **4 个**真实消费方（全部从代码里核出来的，**没有编**）：

======================  ==========================================  ==========================
consumer                代码锚点                                     读什么
======================  ==========================================  ==========================
``business_overview``   ``api.business_overview_*`` 模块群            ``mart.inventory_backlog_base``
``product_center``      ``backend/domains/business/routers/          ``mart.inventory_age_current``
                        product_center.py`` + ``inventory_age_        （库龄层 → 快照族）
                        query_service.py``
``sku_clearance_``      ``backend/services/inventory/sku_clearance_  ``api.sku_clearance_ranking_``
``ranking``             service.py``                                 ``module`` → ``mart.inventory_state``
``low_stock_alert``     ``backend/tasks/scheduled_tasks.py::          ``mart.inventory_current``
                        check_low_stock_alert``
======================  ==========================================  ==========================

命名的依据（不是凭空起的）
------------------------
既有的 ``business_overview`` 对应 refresh registry 里的
``api.business_overview_kpi_module`` 等模块 ⇒ 规律是「去掉 ``api.`` 前缀与
``_module`` 后缀」。照此规律：
``api.sku_clearance_ranking_module`` → ``sku_clearance_ranking``；
``product_center`` / ``low_stock_alert`` 直接取自代码里的模块名与 celery 任务名。

口径
----
* ``importance`` 一律 ``'optional'`` ⇒ **不改变任何阻断口径**
  （契约的 ``required`` 是运行时阻断源；库存域的 6 个键全是 optional）。
* ``platform`` / ``granularity`` / ``sub_domain`` 一律 ``NULL``
  ⇒ 按「或匹配」语义覆盖该域的所有粒度（与现有 6 行并存不冲突）。
* **不新增 required**：这次只是把「谁在用」登记清楚，让影响面可查。

为什么是「惰性登记」
------------------
``semantic_field_contract_service`` 判定时**按 consumer 过滤**（``_load_contracts_from_db``），
而全仓只有 ``business_overview`` 这一个 consumer 被真正传入过
⇒ 新登记的 3 个 consumer **不会被任何判定链读到** ⇒ **零功能影响**，
只是把「改了字段影响谁」变成**可查**（``scripts/query_semantic_contract_impact.py``）。

downgrade：删除本次插入的行（按 data_domain + consumer 精确定位）。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261232_inventory_contract_consumers"
down_revision = "current_schema_20261231_inventory_snapshot_mv"
branch_labels = None
depends_on = None


_SCHEMA = "core"
_CONTRACTS = f"{_SCHEMA}.semantic_field_contracts"

#: 库存域的 6 个语义键（与 ``business_overview`` 已登记的 6 行**完全一致**）。
_INVENTORY_SEMANTIC_KEYS = (
    "platform_sku",
    "sku_id",
    "product_id",
    "product_name",
    "warehouse_name",
    "metric_date",
)

#: 本次补登记的 consumer → 影响面说明（代码锚点 + 读的视图 + 命中的语义键）。
_CONSUMER_IMPACTS = (
    (
        "product_center",
        "商品中心（backend/domains/business/routers/product_center.py；"
        "库龄/定价取数 backend/services/inventory/inventory_age_query_service.py"
        " → mart.inventory_age_current）",
    ),
    (
        "sku_clearance_ranking",
        "滞销清单（backend/services/inventory/sku_clearance_service.py"
        " → api.sku_clearance_ranking_module → mart.inventory_state）",
    ),
    (
        "low_stock_alert",
        "低库存告警（backend/tasks/scheduled_tasks.py::check_low_stock_alert"
        " → mart.inventory_current）",
    ),
)

#: 判定「已登记」时的唯一定位：域 + consumer + 语义键（platform/粒度/子类型 全 NULL）。
_MATCH_CONSUMERS = tuple(consumer for consumer, _impact in _CONSUMER_IMPACTS)


def apply_upgrade(bind) -> dict:
    """upgrade 的真实逻辑（守护测试直接调它）。"""
    stats = {"contract_rows_inserted": 0, "contract_consumers_registered": 0}

    for consumer, impact in _CONSUMER_IMPACTS:
        for semantic_key in _INVENTORY_SEMANTIC_KEYS:
            result = bind.execute(
                sa.text(
                    f"""
                    INSERT INTO {_CONTRACTS} (
                        platform, data_domain, granularity, sub_domain,
                        semantic_key, importance, consumer, impact_description, enabled
                    )
                    SELECT
                        NULL, 'inventory', NULL, NULL,
                        :semantic_key, 'optional', :consumer, :impact, TRUE
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM {_CONTRACTS} c
                        WHERE c.data_domain = 'inventory'
                          AND c.semantic_key = :semantic_key
                          AND c.consumer = :consumer
                          AND c.platform IS NULL
                          AND c.granularity IS NULL
                          AND c.sub_domain IS NULL
                    )
                    """
                ),
                {
                    "semantic_key": semantic_key,
                    "consumer": consumer,
                    "impact": impact,
                },
            )
            stats["contract_rows_inserted"] += int(result.rowcount or 0)

    stats["contract_consumers_registered"] = int(
        bind.execute(
            sa.text(
                f"""
                SELECT count(DISTINCT consumer)
                FROM {_CONTRACTS}
                WHERE enabled IS TRUE
                  AND data_domain = 'inventory'
                """
            )
        ).scalar()
        or 0
    )

    return stats


def apply_downgrade(bind) -> dict:
    """downgrade：只删本次补登记的 3 个 consumer（不碰既有的 business_overview）。"""
    result = bind.execute(
        sa.text(
            f"""
            DELETE FROM {_CONTRACTS}
            WHERE data_domain = 'inventory'
              AND consumer = ANY(:consumers)
              AND platform IS NULL
              AND granularity IS NULL
              AND sub_domain IS NULL
            """
        ),
        {"consumers": list(_MATCH_CONSUMERS)},
    )
    return {"contract_rows_deleted": int(result.rowcount or 0)}


def upgrade() -> None:
    apply_upgrade(op.get_bind())


def downgrade() -> None:
    apply_downgrade(op.get_bind())
