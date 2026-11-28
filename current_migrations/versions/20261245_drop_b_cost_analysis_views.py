"""下线「B类成本分析」模块：删除 4 个视图（mart 1 个 + api 3 个）。

背景
----
「B类成本分析」是 2026-04 立项的一个只读观察页（设计稿：
``docs/superpowers/specs/2026-04-04-b-class-cost-analysis-design.md``），
想回答的是「妙手只给一个『利润』黑盒总数，里面到底装了什么」。

2026-11-28 复核结论：**这个诉求站得住，但这套实现算错了**，且没有接入任何业务：

1. **口径与系统真实利润不一致，且差数量级。**
   业务概览 / 月结 / 提成绩效用的都是妙手导出的「利润(RMB)」黑盒列
   （``mart.shop_month_kpi.profit`` → ``finance.shop_profit_basis``）。
   而本模块是**另起炉灶**拿 8 个源列自己重算一遍成本，再倒推利润。
   实测（本地库 2026-01 ~ 2026-11，按月）：本模块推算的利润是妙手口径的
   **2~4 倍**（如 2026-06：妙手 37,005.32 vs 本模块 158,149.56）。

2. **它自己的两套口径也互相对不上。**
   ``platform_total_cost_itemized``（6 项分项合计）只覆盖妙手真实总成本的
   8.8%（2026-01）；``platform_total_cost_derived``（倒推）又把
   「订单原始金额 vs 买家实付」的**折扣让利**算进了成本，超出真实总成本。
   文档 §3.5 设计的「两口径比对可校验映射是否正确」从未被执行，也没有告警。

3. **零业务消费方。** 全仓检索：``mart.b_cost_shop_month`` 只被本模块自己的
   3 个 api 视图读取；这 3 个 api 视图只被本模块自己的 3 个后端端点读取；
   这 3 个端点只被本模块自己的前端页面调用。财务总览、月度利润看板、
   年度数据总结、绩效、产品中心**全部不读**它的数据。

⇒ 下线对业务功能零影响；同时省掉每次订单刷新重建这 4 个视图的开销
（``mart.b_cost_shop_month`` 要扫 3.5 万行订单做月度聚合，3 个 api 视图
再各自聚合一遍）。

删什么
------
* ``mart.b_cost_shop_month``
* ``api.b_cost_analysis_overview_module``
* ``api.b_cost_analysis_shop_month_module``
* ``api.b_cost_analysis_order_detail_module``

删序
----
**先下游后上游**：3 个 api 视图都依赖 ``mart.b_cost_shop_month``，
所以必须先删 api 再删 mart。

⚠️ 不用 CASCADE
--------------
沿用 ``20261241`` / ``20261242`` 的口径：万一还有意料之外的引用，
宁可报错停下，也不静默删掉别的东西。

⚠️ 刷新登记同步下线
------------------
这 4 个视图原先登记在 ``backend/services/data_pipeline/refresh_registry.py`` 的
``PIPELINE_DEPENDENCIES`` / ``SQL_TARGET_PATHS`` 里。**必须同步删除** ——
``expand_downstream_targets()`` 会从 ``semantic.fact_orders_atomic``
**自动展开全部已登记下游**，登记不删 ⇒ 每次订单刷新仍会尝试重建
已删除的视图 ⇒ 刷新任务持续报错。本迁移的代码侧下线已一并处理。

downgrade
---------
视图**没有数据**，重建即完整恢复 ⇒ downgrade 内嵌被删视图的**原始定义**
（逐字取自被删的 4 个 ``sql/`` 资产文件），按「先上游后下游」顺序重建。

⚠️ 内嵌定义不构成第二份 SSOT：这些视图已下线，**没有任何活动路径会重建
它们**（不在 ``SQL_TARGET_PATHS`` 里 ⇒ 刷新流程与 bootstrap 都不会碰），
内嵌定义只服务于 downgrade 回滚 ⇒ 漂移风险为零。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261245_drop_b_cost_analysis_views"
# ⚠️ 改接在 20261246 之后（2026-11-28 费用管理分支合并时调整）。
# 原先与「清理费用占位行」迁移同父（20261244），两条迁移会形成**两个 head**，
# `alembic upgrade head` 直接失败。链表现为：
#   20261244 → 20261246_cleanup_expense_placeholder_rows → 20261245_drop_b_cost_analysis_views
down_revision = "current_schema_20261246_cleanup_expense_placeholder_rows"
branch_labels = None
depends_on = None


#: 被删除的视图 —— **按删除顺序排列**（下游 api 在前，上游 mart 在后）。
#:
#: 依赖方向：3 个 api 视图 → ``mart.b_cost_shop_month``。
DROPPED_VIEWS = (
    "api.b_cost_analysis_order_detail_module",
    "api.b_cost_analysis_shop_month_module",
    "api.b_cost_analysis_overview_module",
    "mart.b_cost_shop_month",
)


#: downgrade 时重建视图用的原始定义 —— **按创建顺序排列**（上游 mart 在前）。
#:
#: 逐字取自已删除的 4 个 ``sql/`` 资产文件：
#:   * ``sql/mart/b_cost_shop_month.sql``
#:   * ``sql/api_modules/b_cost_analysis_overview_module.sql``
#:   * ``sql/api_modules/b_cost_analysis_shop_month_module.sql``
#:   * ``sql/api_modules/b_cost_analysis_order_detail_module.sql``
#:
#: ⚠️ 这些定义引用的上游是 ``semantic.fact_orders_atomic_mv``（物化视图），
#:    该上游**保留在线** ⇒ downgrade 不需要额外重建它。
RECREATE_VIEW_STATEMENTS: tuple[str, ...] = (
    # ── sql/mart/b_cost_shop_month.sql ──────────────────────────────
    """CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.b_cost_shop_month AS
WITH monthly_base AS (
    SELECT
        date_trunc('month', metric_date)::date AS period_month,
        platform_code,
        shop_id,
        currency_code,
        SUM(paid_amount) AS gmv,
        SUM(purchase_amount) AS purchase_amount,
        SUM(warehouse_operation_fee) AS warehouse_operation_fee,
        SUM(shipping_fee) AS shipping_fee,
        SUM(promotion_fee) AS promotion_fee,
        SUM(platform_commission) AS platform_commission,
        SUM(platform_deduction_fee) AS platform_deduction_fee,
        SUM(platform_voucher) AS platform_voucher,
        SUM(platform_service_fee) AS platform_service_fee,
        SUM(platform_total_cost_itemized) AS platform_total_cost_itemized
    FROM semantic.fact_orders_atomic_mv
    GROUP BY date_trunc('month', metric_date)::date, platform_code, shop_id, currency_code
),
costed AS (
    SELECT
        period_month,
        platform_code,
        shop_id,
        currency_code,
        platform_code || '|' || shop_id AS shop_key,
        gmv,
        purchase_amount,
        warehouse_operation_fee,
        shipping_fee,
        promotion_fee,
        platform_commission,
        platform_deduction_fee,
        platform_voucher,
        platform_service_fee,
        platform_total_cost_itemized,
        (
            COALESCE(purchase_amount, 0)
            + COALESCE(warehouse_operation_fee, 0)
            + COALESCE(platform_total_cost_itemized, 0)
        ) AS total_cost_b
    FROM monthly_base
)
SELECT
    period_month,
    platform_code,
    shop_id,
    shop_key,
    currency_code,
    gmv,
    purchase_amount,
    warehouse_operation_fee,
    shipping_fee,
    promotion_fee,
    platform_commission,
    platform_deduction_fee,
    platform_voucher,
    platform_service_fee,
    platform_total_cost_itemized,
    total_cost_b,
    (gmv - purchase_amount) / NULLIF(gmv, 0) AS gross_margin_ref,
    (gmv - total_cost_b) / NULLIF(gmv, 0) AS net_margin_ref
FROM costed;""",
    # ── sql/api_modules/b_cost_analysis_overview_module.sql ─────────
    """CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.b_cost_analysis_overview_module AS
WITH aggregated AS (
    SELECT
        period_month,
        platform_code,
        currency_code,
        SUM(gmv) AS gmv,
        SUM(purchase_amount) AS purchase_amount,
        SUM(warehouse_operation_fee) AS warehouse_operation_fee,
        SUM(shipping_fee) AS shipping_fee,
        SUM(promotion_fee) AS promotion_fee,
        SUM(platform_commission) AS platform_commission,
        SUM(platform_deduction_fee) AS platform_deduction_fee,
        SUM(platform_voucher) AS platform_voucher,
        SUM(platform_service_fee) AS platform_service_fee,
        SUM(platform_total_cost_itemized) AS platform_total_cost_itemized,
        SUM(total_cost_b) AS total_cost_b
    FROM mart.b_cost_shop_month
    GROUP BY period_month, platform_code, currency_code
)
SELECT
    period_month,
    platform_code,
    currency_code,
    gmv,
    purchase_amount,
    warehouse_operation_fee,
    shipping_fee,
    promotion_fee,
    platform_commission,
    platform_deduction_fee,
    platform_voucher,
    platform_service_fee,
    platform_total_cost_itemized,
    total_cost_b,
    (gmv - purchase_amount) / NULLIF(gmv, 0) AS gross_margin_ref,
    (gmv - total_cost_b) / NULLIF(gmv, 0) AS net_margin_ref
FROM aggregated;""",
    # ── sql/api_modules/b_cost_analysis_shop_month_module.sql ──────
    """CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.b_cost_analysis_shop_month_module AS
SELECT
    period_month,
    platform_code,
    shop_id,
    shop_key,
    currency_code,
    gmv,
    purchase_amount,
    warehouse_operation_fee,
    shipping_fee,
    promotion_fee,
    platform_commission,
    platform_deduction_fee,
    platform_voucher,
    platform_service_fee,
    platform_total_cost_itemized,
    total_cost_b,
    gross_margin_ref,
    net_margin_ref
FROM mart.b_cost_shop_month;""",
    # ── sql/api_modules/b_cost_analysis_order_detail_module.sql ─────
    """CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.b_cost_analysis_order_detail_module AS
WITH base AS (
    SELECT
        date_trunc('month', metric_date)::date AS period_month,
        platform_code,
        shop_id,
        platform_code || '|' || shop_id AS shop_key,
        currency_code,
        order_id,
        order_status,
        order_time,
        order_date,
        order_original_amount,
        product_id,
        platform_sku,
        sku_id,
        product_sku,
        product_name,
        paid_amount AS gmv,
        purchase_amount,
        warehouse_operation_fee,
        shipping_fee,
        promotion_fee,
        platform_commission,
        platform_deduction_fee,
        platform_voucher,
        platform_service_fee,
        platform_total_cost_itemized,
        platform_total_cost_derived,
        (
            COALESCE(purchase_amount, 0)
            + COALESCE(warehouse_operation_fee, 0)
            + COALESCE(platform_total_cost_itemized, 0)
        ) AS total_cost_b
    FROM semantic.fact_orders_atomic_mv
)
SELECT
    period_month,
    platform_code,
    shop_id,
    shop_key,
    currency_code,
    order_id,
    order_status,
    COALESCE(order_time, order_date::timestamp) AS order_time,
    order_date,
    order_original_amount,
    product_id,
    platform_sku,
    sku_id,
    product_sku,
    product_name,
    gmv,
    purchase_amount,
    warehouse_operation_fee,
    shipping_fee,
    promotion_fee,
    platform_commission,
    platform_deduction_fee,
    platform_voucher,
    platform_service_fee,
    platform_total_cost_itemized,
    platform_total_cost_derived,
    total_cost_b,
    (gmv - purchase_amount) / NULLIF(gmv, 0) AS gross_margin_ref,
    (gmv - total_cost_b) / NULLIF(gmv, 0) AS net_margin_ref
FROM base;""",
)


def upgrade() -> None:
    """删除这 4 个视图（下游 api 在前，上游 mart 在后）。"""
    bind = op.get_bind()
    for view in DROPPED_VIEWS:
        # ⚠️ 不用 CASCADE：万一还有意料之外的引用，宁可报错停下，也不静默删掉别的视图。
        bind.execute(sa.text(f"DROP VIEW IF EXISTS {view}"))


def downgrade() -> None:
    """重建这 4 个视图（上游 mart 在前，下游 api 在后）。"""
    bind = op.get_bind()
    for statement in RECREATE_VIEW_STATEMENTS:
        bind.execute(sa.text(statement))
