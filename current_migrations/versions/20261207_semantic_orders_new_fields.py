"""orders 域字典补登两个标准字段(联盟/达人佣金 + 卖家总收入)。

背景
----
2026-11-08 复核对三个"字典未登记但真实存在"的订单级金额列做**原表实测**
(开发库, 2026-11):

* ``shopee 联盟佣金(RMB)``   —— 29629 行**全有值**, 均值 0.76, 合计 22519.01
  对比同平台 ``Shopee平台佣金(RMB)`` 均值 10.24 / 合计 303398.64
  ⇒ 两者量级完全不同 ⇒ **付给达人/联盟的佣金 ≠ 平台佣金**(用户 2026-11-08 确认)
  ⇒ 独立标准字段 ``affiliate_commission``。
* ``tiktok 达人佣金(RMB)``   —— 4589 行有值, 均值 -3.85, 合计 -17662.47
  ⇒ 与 shopee 的「联盟佣金」是**同一业务事实**(给达人) ⇒ 同一字段的平台别名。
* ``tiktok 总收入(RMB)``     —— 4054 行有值(77%), 均值 79.47
  与「买家实付金额(RMB)」**行级相等率仅 12.03%** ⇒ 不是同一个事实;
  与「产品折后价格(RMB)」相等率 69.24%;
  且按订单商品行数分组后, 多商品订单的相等率(72.40%)**反而高于**
  单商品订单(69.73%) ⇒ 它**不是**单品价、也不是折后价之和
  ⇒ 是订单级的商品成交总额 ⇒ 独立标准字段 ``total_income``。
* ``tiktok 回款金额(RMB)``   —— 5254 行 100% 有值, 均值 54.11
  与「总收入(RMB) + 总费用(RMB)」**行级相等率 59.17%**
  ⇒ 回款金额 = 总收入 − 各项费用 = **卖家实际到手**
  ⇒ 归 ``settled_amount``(已结算金额)的 tiktok 平台别名。
* ``tiktok 合作伙伴佣金(RMB)`` 合计 **-13.85**(≈0) ⇒ 不登记;
  ``tiktok 联盟商店广告佣金(RMB)`` 是**广告**佣金 ≠ 达人佣金 ⇒ 不登记。

本迁移做三件事
--------------
1. 落别名资产(``sql/semantic/semantic_alias_registry.sql``)——
   seed 230 → **234** 条。
2. 重建 ``semantic.fact_orders_atomic`` —— **末尾**追加两列
   (``affiliate_commission`` / ``total_income``)。
   ⚠ 只能在末尾加: ``CREATE OR REPLACE VIEW`` 不能删列、不能改列序。
3. DROP + 重建订单物化视图(``SELECT *`` ⇒ 列集变了必须重建) + 索引,
   前后重建 6 个下游视图(解除依赖 → 重建 → 改回)。

⚠ **不并入平台成本口径**: ``affiliate_commission`` 是付给**达人**的钱,
那 6 项是「平台侧成本」⇒ 并进去会与利润口径重复计算 ⇒ 平台成本口径**不变**。

⚠ **不碰月度链**: 月度 MV 与订单 MV 无依赖关系(各自从 b_class 源表独立生成)
⇒ 月度口径与硬验收指标(GMV 44,284.69 / 订单数 629)不受本迁移影响。
"""

from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261207_semantic_orders_new_fields"
down_revision = "current_schema_20261206_semantic_orders_alias_resolve"
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
    # ⚠ 2026-11-08 补登后**没有新的**冲突行: 「联盟佣金」在源表里是原币裸名,
    #   字典只登「联盟佣金(RMB)」(封闭域规则)⇒ 模板确认行里没有指向裸名的行。
    #   这里保留既有两条(幂等) —— 它们在 20261206 已置为 disabled。
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
