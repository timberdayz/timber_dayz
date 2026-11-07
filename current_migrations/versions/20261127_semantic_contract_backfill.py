"""补齐语义契约表(批次 F-3): 粒度缺口 + 无契约域。

背景
----
``core.semantic_field_contracts`` 是「这个域无论哪个平台都必须有的字段」的
域级下限字典。批次 F-3 之前它有两个洞:

1. **粒度缺口** —— ``orders/daily`` 与 ``analytics/weekly`` 在表里没有契约行,
   于是判定时**落回代码里的常量兜底**(:data:`DEFAULT_CONTRACTS`)。
   常量是不分粒度的 ⇒ 「orders/daily」实际用的是 orders 域的通用契约,
   「analytics/weekly」用的是 analytics 域的通用契约。
   ⇒ 常量与表两处口径可能漂移, 且无法按粒度演进。

2. **无契约域** —— 5 个数据域里只有 ``analytics`` 与 ``orders`` 有契约,
   ``products`` / ``inventory`` / ``services`` 三个域恒为 ``not_configured``
   ⇒ 既看不到域级字典, 也拿不到「模板离域级下限还缺什么」的引导。

口径
----
* **粒度缺口**: 补的行内容与 ``DEFAULT_CONTRACTS`` **逐条一致**
  ⇒ 补齐前后判定行为**完全不变**(只是不再依赖常量兜底)。
* **无契约域**: 一律 ``importance='optional'``, **不设任何 required**。

  为什么不能给这三个域设 required
  ------------------------------
  契约的 required 是**运行时阻断源**。而这三个域的文件列**解析不出语义键**
  (``DOMAIN_SEMANTIC_ALIASES`` 只覆盖 orders / analytics,
  且模板绑定里的语义键覆盖率极低) ⇒ 只要有 required,
  这些域就会恒为 ``breaking_drift`` ⇒ **新增阻断**。

  ⇒ 先把域级字典落地(required 留空), 等「列名 → 语义键」的命中率上去了,
  再把 required 一条条加上 —— 那时是**数据驱动**的, 不是猜的。

* ``platform`` / ``granularity`` / ``sub_domain`` 一律 ``NULL``
  ⇒ 按「或匹配」语义覆盖该域的**所有粒度**(与现有 4 组带粒度的行并存不冲突)。

downgrade: 删除本次插入的行(按 semantic_key + 域定位)。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261127_semantic_contract_backfill"
down_revision = "current_schema_20261126_legacy_core_fields_backfill"
branch_labels = None
depends_on = None


_SCHEMA = "core"
_CONTRACTS = f"{_SCHEMA}.semantic_field_contracts"
_CONSUMER = "business_overview"


#: ``orders`` 域契约 —— 与 ``DEFAULT_CONTRACTS['orders']`` **逐条一致**。
_ORDERS_CONTRACT = (
    ("order_id", "required", "业务概览订单数无法计算"),
    ("shop_id", "required", "业务概览无法按店铺归属订单"),
    ("order_date", "required", "业务概览无法按期间归集订单"),
    ("sales_volume", "required", "业务概览销售数量无法计算"),
    ("paid_amount", "required", "业务概览销售额和转化率无法计算"),
    ("profit", "required", "业务概览利润指标无法计算"),
    ("estimated_settlement_amount", "optional", None),
    ("settlement_time", "optional", None),
    ("cost_profit_rate", "optional", None),
)

#: ``analytics`` 域契约 —— 与 ``DEFAULT_CONTRACTS['analytics']`` **逐条一致**。
_ANALYTICS_CONTRACT = (
    ("metric_date", "required", "业务概览流量无法按日期归集"),
    ("shop_id", "optional", "业务概览无法按店铺归属流量"),
    ("visitor_count", "required", "业务概览UV无法计算"),
    ("page_views", "required", "业务概览PV无法计算"),
    ("conversion_rate", "optional", None),
    ("order_count", "optional", None),
    ("gmv", "optional", None),
)

#: 无契约域的域级字典(全部 optional —— 见模块 docstring 的口径说明)。
_PRODUCTS_CONTRACT = (
    ("product_id", "optional", None),
    ("platform_sku", "optional", None),
    ("sku_id", "optional", None),
    ("product_name", "optional", None),
    ("item_status", "optional", None),
    ("page_views", "optional", None),
    ("product_visitor_count", "optional", None),
    ("impressions", "optional", None),
    ("clicks", "optional", None),
    ("sales_amount", "optional", None),
    ("order_count", "optional", None),
    ("conversion_rate", "optional", None),
)

_INVENTORY_CONTRACT = (
    ("platform_sku", "optional", None),
    ("sku_id", "optional", None),
    ("product_id", "optional", None),
    ("product_name", "optional", None),
    ("warehouse_name", "optional", None),
    ("metric_date", "optional", None),
)

_SERVICES_CONTRACT = (
    ("service_id", "optional", None),
    ("shop_id", "optional", None),
    ("metric_date", "optional", None),
    ("order_count", "optional", None),
)


#: 本次插入的契约行(域 / 粒度 / 键列表)。
_INSERT_PLAN = (
    ("orders", "daily", _ORDERS_CONTRACT),
    ("analytics", "weekly", _ANALYTICS_CONTRACT),
    ("products", None, _PRODUCTS_CONTRACT),
    ("inventory", None, _INVENTORY_CONTRACT),
    ("services", None, _SERVICES_CONTRACT),
)


def apply_upgrade(bind) -> dict:
    """upgrade 的真实逻辑(守护测试直接调它)。"""
    stats = {"contract_rows_inserted": 0, "contract_domains_covered": 0}

    for data_domain, granularity, definitions in _INSERT_PLAN:
        for semantic_key, importance, impact in definitions:
            result = bind.execute(
                sa.text(
                    f"""
                    INSERT INTO {_CONTRACTS} (
                        platform, data_domain, granularity, sub_domain,
                        semantic_key, importance, consumer, impact_description, enabled
                    )
                    SELECT
                        NULL, :data_domain, :granularity, NULL,
                        :semantic_key, :importance, :consumer, :impact, TRUE
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM {_CONTRACTS} c
                        WHERE c.data_domain = :data_domain
                          AND c.semantic_key = :semantic_key
                          AND c.consumer = :consumer
                          AND c.granularity IS NOT DISTINCT FROM :granularity
                          AND c.platform IS NULL
                          AND c.sub_domain IS NULL
                    )
                    """
                ),
                {
                    "data_domain": data_domain,
                    "granularity": granularity,
                    "semantic_key": semantic_key,
                    "importance": importance,
                    "consumer": _CONSUMER,
                    "impact": impact,
                },
            )
            stats["contract_rows_inserted"] += int(result.rowcount or 0)

    stats["contract_domains_covered"] = int(
        bind.execute(
            sa.text(
                f"""
                SELECT count(DISTINCT data_domain)
                FROM {_CONTRACTS}
                WHERE enabled IS TRUE
                """
            )
        ).scalar()
        or 0
    )

    return stats


def apply_downgrade(bind) -> dict:
    """downgrade 的真实逻辑(守护测试直接调它)。"""
    stats = {"contract_rows_deleted": 0}

    for data_domain, granularity, definitions in _INSERT_PLAN:
        for semantic_key, _importance, _impact in definitions:
            result = bind.execute(
                sa.text(
                    f"""
                    DELETE FROM {_CONTRACTS}
                    WHERE data_domain = :data_domain
                      AND consumer = :consumer
                      AND semantic_key = :semantic_key
                      AND granularity IS NOT DISTINCT FROM :granularity
                      AND platform IS NULL
                      AND sub_domain IS NULL
                    """
                ),
                {
                    "data_domain": data_domain,
                    "granularity": granularity,
                    "semantic_key": semantic_key,
                    "consumer": _CONSUMER,
                },
            )
            stats["contract_rows_deleted"] += int(result.rowcount or 0)

    return stats


def upgrade() -> None:
    bind = op.get_bind()
    apply_upgrade(bind)


def downgrade() -> None:
    bind = op.get_bind()
    apply_downgrade(bind)
