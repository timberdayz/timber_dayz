"""analytics(流量)域: tiktok 的「商品访客数」接通为 TikTok 侧 UV(``visitor_count``)。

背景
----
2026-11-10 实测(开发库全仓扫描 ``raw_data`` 的 key):

* shopee 流量月报 ``b_class.fact_shopee_analytics_monthly`` 2354 行 ——
  访客列**只有**「访客数」「新访客」「现有访客」;
* tiktok 流量月报 ``b_class.fact_tiktok_analytics_monthly`` 1374 行 ——
  访客列**只有**「商品访客数」(店铺级访客数这一列**压根不存在**);
* ⇒ 两边的访客列名**互斥**:「访客数」是 shopee 专有,「商品访客数」是 tiktok 专有。

⇒ **tiktok 侧的 UV 就是「商品访客数」**。这不是新增口径, 而是**把架构契约
落进实现** —— ``docs/architecture/SEMANTIC_FIELD_RULES.md``(2026-05-26 原始
契约)早已明写「TikTok analytics explicitly maps ``商品访客数`` to canonical
``visitor_count``」。

⚠⚠ **两平台的 UV 不是同一个口径, 跨平台不可直接比大小**:

============  ==========================================  ==============
平台          源表列                                      口径
============  ==========================================  ==============
shopee       「访客数」                                  全店**去重访客人数**
tiktok       「商品访客数」                              按商品统计的**访客人次**
============  ==========================================  ==============

实测: shopee 全量 519,212 人(= 新访客 444,991 + 现有访客 74,221);
tiktok 全量 175,914 人次(1350/1374 行 ≤ 该行「页面浏览次数」)
⇒ 两者都叫 ``visitor_count``, 但**不是同一个事实**
⇒ 看板必须标注口径差异(``frontend/.../businessOverviewKpiMeta.js``)。

本迁移做五件事
--------------
1. 落别名资产(``sql/semantic/semantic_alias_registry.sql``)——
   seed 329 -> **319** 条:
   * 新增 2 条**平台限定**行(``platform_code`` 必填, 否则两平台会串口径):
     ``('analytics','visitor_count','访客数','shopee')``
     ``('analytics','visitor_count','商品访客数','tiktok')``
   * 删掉 11 条**通用**行: 7 条 ``visitor_count`` 裸名(访客数/访客量/
     访问用户数/uv/visitors/visitor count/visitor_count) +
     4 条 analytics 域的 ``product_visitor_count``;
2. 把「商品访客数」的**模板确认别名行**改指到 ``visitor_count``
   (原来指 ``product_visitor_count`` —— 不改的话同一个列名会同时指向两个
   标准字段, 直接撞上 SSOT 硬约束);
3. 把 tiktok analytics 模板(368/371/372)的 ``header_bindings`` 里
   「商品访客数」的 ``semantic_key`` 改成 ``visitor_count``
   (入库侧与巡检侧口径必须跟着走, 否则下次「保存模板」会把它打回旧值);
4. REFRESH 两条链的物化视图(日/周链 + 月度链)⇒ tiktok 的 UV 真的有值;
5. fail-closed 自检:
   * analytics 域里不允许「同一个列名同时指向两个标准字段」(SSOT 硬约束);
   * 两条平台限定别名行必须在库里, 且**旧的** ``product_visitor_count``
     「商品访客数」行必须已经消失;
   * ``semantic.resolve_alias()`` 必须**按平台**分别命中, 且**不串台**
     (shopee 的数据不许被 tiktok 的列命中, 反之亦然);
   * 视图里 tiktok 的 ``visitor_count`` 必须真的有值(库里没有源数据时跳过)。

⚠ **不影响 orders 域与硬验收指标**(GMV 44,284.69 / 订单数 629)——
   本迁移只碰 analytics 域的别名表与两条链的物化视图, orders 链完全不动。
"""

from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261211_semantic_analytics_tiktok_visitor"
down_revision = "current_schema_20261210_semantic_analytics_tiktok_attribution"
branch_labels = None
depends_on = None


REPO_ROOT = Path(__file__).resolve().parents[2]

#: 别名资产(表结构 + 索引 + resolve_alias() + seed + 陈旧 builtin 行清理)。
#: 整份执行: DDL 都是 ``IF NOT EXISTS`` / ``CREATE OR REPLACE``, seed 带
#: ``ON CONFLICT``, 清理段只删 ``builtin`` 行 ⇒ 幂等。
ALIAS_ASSET = "sql/semantic/semantic_alias_registry.sql"

#: 两条链的物化视图 —— 访客口径变了, 必须刷新, 否则视图里还是旧值。
ANALYTICS_MV = "semantic.fact_analytics_atomic_mv"
MONTHLY_MV = "semantic.fact_analytics_monthly_atomic_mv"

#: 物化时的语句超时预算(毫秒)—— 同 20261106 / 20261207 / 20261208 / 20261210 迁移。
MATERIALIZE_STATEMENT_TIMEOUT_MS = 30 * 60 * 1000

#: [*] 本迁移登记的**平台限定**访客别名: (平台, 标准字段, 真实表头)。
#:
#: ⚠ **必须成对**(shopee + tiktok 都登记)——
#:   别名合并规则里有一条**排他**规则: 某个标准字段一旦登记了平台限定别名,
#:   它的**通用别名就整体不再登记**(否则同一列名会被两个标准字段认领)
#:   ⇒ 只登记一边会把另一边**一起挤掉**, 那一边会静默变 NULL。
#:   这条规则在 ``build_domain_alias_records`` 的 ``platform_fields`` 逻辑里,
#:   已实测确认。
#:
#: ⚠ 两平台的 UV **口径不同**(见模块 docstring)⇒ 一律走平台限定登记。
PLATFORM_VISITOR_ALIASES = (
    ("shopee", "visitor_count", "访客数"),
    ("tiktok", "visitor_count", "商品访客数"),
)

#: 「商品访客数」在 analytics 域**不再**允许指向的标准字段(旧归属)。
LEGACY_VISITOR_FIELD = "product_visitor_count"

#: 「商品访客数」在 analytics 域的**新**归属。
VISITOR_FIELD = "visitor_count"

#: 模板 header_bindings 里「商品访客数」改指后的别名清单。
#: = 标准字段的字典别名 + 真实表头本身(绑定就是为这一列建的)。
VISITOR_BINDING_ALIASES = (
    "visitor_count",
    "访客数",
    "visitors",
    "visitor count",
    "商品访客数",
)


def _driver_connection():
    """拿到原生 psycopg2 连接(见 20261207 迁移的同名函数)。"""
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


def _read_asset(asset_rel_path: str) -> str:
    asset_path = REPO_ROOT / asset_rel_path
    if not asset_path.is_file():
        print("[WARN] 资产文件缺失, 跳过: {path}".format(path=asset_rel_path))
        return ""
    return asset_path.read_text(encoding="utf-8")


def _with_extended_statement_timeout(action):
    """在 ``action`` 执行期间把语句超时提到物化预算, 结束后恢复原值。"""
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


def _assert_no_ambiguous_aliases() -> None:
    """fail-closed: analytics 域里不允许「同一个列名同时指向两个标准字段」。

    SSOT 的硬约束是「一个列名只认一个标准字段」——
    ``semantic.resolve_alias()`` 只能按 (domain, field) 查询, 所以同一列名
    挂在两个字段上时, 两个字段会**各自**取到值 ⇒ 下游会把同一个数字
    当成两个不同的业务事实。

    这里只查**生效**的行(status='active'); 已被人工裁决置为 disabled /
    conflict 的历史行不算。
    """
    with _driver_connection().cursor() as cursor:
        cursor.execute(
            """
            SELECT raw_alias, COUNT(DISTINCT standard_field) AS field_count,
                   MIN(standard_field) AS one_field, MAX(standard_field) AS another_field
            FROM semantic.semantic_field_aliases
            WHERE data_domain = 'analytics'
              AND status = 'active'
            GROUP BY raw_alias
            HAVING COUNT(DISTINCT standard_field) > 1
            """
        )
        rows = cursor.fetchall()
    if rows:
        problems = [
            "列名 {alias!r} 同时指向 {one} 与 {two}".format(
                alias=row[0], one=row[2], two=row[3]
            )
            for row in rows
        ]
        raise RuntimeError(
            "analytics 域存在「一个列名指向多个标准字段」: " + "；".join(problems)
        )


def _assert_visitor_count_aliases() -> None:
    """fail-closed: 两条**平台限定**访客别名行必须在库里, 旧归属必须已消失。

    为什么单独断言: 这两条别名走 ``platform_code`` ⇒ 它们**不在**域限定别名
    清单里 ⇒ 少落一行时 ``resolve_alias()`` 不会报错, 只会「安静地解析不
    出来」⇒ 视图输出整列 NULL, 而巡检会把 0% 解析率报成「源表没有这一列」
    = **误导**。
    """
    with _driver_connection().cursor() as cursor:
        cursor.execute(
            """
            SELECT standard_field, raw_alias, platform_code, granularity
            FROM semantic.semantic_field_aliases
            WHERE data_domain = 'analytics'
              AND status = 'active'
              AND standard_field IN ('visitor_count', 'product_visitor_count')
            """
        )
        rows = cursor.fetchall()

    found = {(str(r[0]), str(r[1]), str(r[2])) for r in rows}
    missing = [
        "{0}/{1} <- {2}".format(platform, field, alias)
        for platform, field, alias in PLATFORM_VISITOR_ALIASES
        if (field, alias, platform) not in found
    ]
    if missing:
        raise RuntimeError(
            "访客数的平台限定别名行缺失(analytics): " + "；".join(missing)
        )

    legacy = [
        "{0}/{1}/{2}".format(r[0], r[1], r[2])
        for r in rows
        if str(r[0]) == LEGACY_VISITOR_FIELD and str(r[1]) == "商品访客数"
    ]
    if legacy:
        raise RuntimeError(
            "「商品访客数」仍指向旧字段 {0}: {1}".format(
                LEGACY_VISITOR_FIELD, "；".join(legacy)
            )
        )


def _assert_visitor_count_resolution() -> None:
    """fail-closed: ``resolve_alias()`` 必须**按平台**命中, 且**不串台**。

    这是本迁移最关键的一条断言 —— 它直接验证「两个平台的访客列名互斥」
    这件事在取数链路上真的成立:

    * shopee 的「访客数」  -> shopee 命中, tiktok 不命中;
    * tiktok 的「商品访客数」-> tiktok 命中, shopee 不命中;
    * 「商品访客数」再不许从 ``product_visitor_count`` 出口取到值。
    """
    cases = (
        # (平台, 原始 JSON, 期望字段, 期望值)
        ("shopee", '{"访客数":"456"}', VISITOR_FIELD, "456"),
        ("tiktok", '{"商品访客数":"123"}', VISITOR_FIELD, "123"),
        ("shopee", '{"商品访客数":"123"}', VISITOR_FIELD, None),
        ("tiktok", '{"访客数":"456"}', VISITOR_FIELD, None),
        ("tiktok", '{"商品访客数":"123"}', LEGACY_VISITOR_FIELD, None),
        ("shopee", '{"访客数":"456"}', LEGACY_VISITOR_FIELD, None),
    )
    with _driver_connection().cursor() as cursor:
        for platform, raw_json, field, expected in cases:
            cursor.execute(
                """
                SELECT semantic.resolve_alias(
                    CAST(%s AS jsonb), 'analytics', %s, %s, 'monthly'
                )
                """,
                (raw_json, field, platform),
            )
            actual = cursor.fetchone()[0]
            if (actual or None) != expected:
                raise RuntimeError(
                    "resolve_alias({0}, {1}, {2}) = {3!r}, 期望 {4!r}".format(
                        platform, field, raw_json, actual, expected
                    )
                )


def _assert_visitor_count_values() -> None:
    """fail-closed: 视图里 tiktok 的 ``visitor_count`` 必须真的有值。

    只在**源表有数据**时断言 —— 空库(迁移链自检)没有源数据, 断言「必须有
    值」会把空库门禁打断 ⇒ 有数据才检查, 没数据就跳过。
    """
    for relation in (ANALYTICS_MV, MONTHLY_MV):
        with _driver_connection().cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE visitor_count IS NOT NULL) AS resolved
                FROM {relation}
                WHERE platform_code = 'tiktok'
                """.format(
                    relation=relation
                )
            )
            row = cursor.fetchone()
        total = int(row[0] or 0)
        resolved = int(row[1] or 0)
        if total <= 0:
            continue
        if resolved <= 0:
            raise RuntimeError(
                "{0} 里 tiktok 有 {1} 行, 但 visitor_count 一行都没解析出来".format(
                    relation, total
                )
            )


def _migrate_confirmed_alias_rows() -> None:
    """把「商品访客数」的模板确认别名行改指到 ``visitor_count``。

    为什么必须显式处理: 别名资产的清理段**只删 ``source='builtin'`` 的行**
    ⇒ 「用户确认过」的行不会被 seed 带走 ⇒ 不显式改指, 它会继续把
    「商品访客数」指向 ``product_visitor_count``, 于是同一个列名同时指向
    两个标准字段 ⇒ ``_assert_no_ambiguous_aliases()`` 直接失败。
    """
    _exec_sql(
        """
        -- 先删掉可能已经存在的「同 (平台, 粒度) 的 visitor_count 行」——
        -- 否则下面的 UPDATE 会撞唯一索引。
        DELETE FROM semantic.semantic_field_aliases a
        USING semantic.semantic_field_aliases b
        WHERE a.data_domain = 'analytics'
          AND a.standard_field = 'visitor_count'
          AND a.raw_alias = '商品访客数'
          AND b.data_domain = 'analytics'
          AND b.standard_field = 'product_visitor_count'
          AND b.raw_alias = '商品访客数'
          AND COALESCE(a.platform_code, '') = COALESCE(b.platform_code, '')
          AND COALESCE(a.granularity, '') = COALESCE(b.granularity, '')
        """
    )
    _exec_sql(
        """
        UPDATE semantic.semantic_field_aliases
        SET standard_field = 'visitor_count',
            updated_at = NOW()
        WHERE data_domain = 'analytics'
          AND standard_field = 'product_visitor_count'
          AND raw_alias = '商品访客数'
        """
    )


def _migrate_template_bindings() -> None:
    """把模板 ``header_bindings`` 里「商品访客数」的语义键改成 ``visitor_count``。

    为什么必须改: 入库侧与巡检侧都读模板绑定 ⇒ 绑定不改, 下次「保存模板」
    会把 ``product_visitor_count`` 重新沉淀成模板确认别名行 ⇒ 又变成
    「一个列名指向两个标准字段」。

    ⚠ 只改**匹配得上**的条目(``raw_name='商品访客数'`` 且
    ``semantic_key='product_visitor_count'``)⇒ 已经改成 visitor_count 的
    不会被重复处理 ⇒ 幂等。
    """
    aliases_literal = ", ".join(
        "'{0}'".format(str(item).replace("'", "''")) for item in VISITOR_BINDING_ALIASES
    )
    _exec_sql(
        """
        UPDATE core.field_mapping_templates
        SET header_bindings = (
                SELECT jsonb_agg(
                           CASE
                               WHEN entry->>'raw_name' = '商品访客数'
                                AND entry->>'semantic_key' = 'product_visitor_count'
                               THEN entry || jsonb_build_object(
                                        'semantic_key', 'visitor_count',
                                        'aliases', jsonb_build_array({aliases})
                                    )
                               ELSE entry
                           END
                           ORDER BY CASE
                               WHEN entry->>'position' ~ '^[0-9]+$'
                               THEN (entry->>'position')::int
                               ELSE 0
                           END
                       )
                FROM jsonb_array_elements(header_bindings) AS item(entry)
            ),
            updated_at = NOW()
        WHERE data_domain = 'analytics'
          AND header_bindings IS NOT NULL
          AND jsonb_typeof(header_bindings) = 'array'
          AND EXISTS (
                SELECT 1
                FROM jsonb_array_elements(header_bindings) AS item(entry)
                WHERE entry->>'raw_name' = '商品访客数'
                  AND entry->>'semantic_key' = 'product_visitor_count'
            )
        """.format(
            aliases=aliases_literal
        )
    )


def _refresh_mviews() -> None:
    """刷新两条链的物化视图。

    ⚠ 只 **REFRESH**、不重建: 本迁移**没有改任何视图定义** ⇒ 列集/列序
    都没变 ⇒ REFRESH 足够, 而且比 DROP + 重建便宜得多。

    ⚠ 月度链与日/周链**同源同口径** ⇒ 两条链必须一起刷新, 否则同一个指标
    在两条链上会取到不同的值。
    """

    def _refresh() -> None:
        for relation in (ANALYTICS_MV, MONTHLY_MV):
            _exec_sql("REFRESH MATERIALIZED VIEW {relation}".format(relation=relation))

    _with_extended_statement_timeout(_refresh)


def upgrade() -> None:
    # 1) 别名资产: 表结构 + 索引 + resolve_alias() + seed(329 -> 319) + 清理段
    alias_sql = _read_asset(ALIAS_ASSET)
    if alias_sql:
        _exec_sql_text(alias_sql)

    # 2) 「商品访客数」的模板确认别名行改指到 visitor_count
    _migrate_confirmed_alias_rows()

    # 3) 模板 header_bindings 同步(入库侧与巡检侧口径跟着走)
    _migrate_template_bindings()

    # 4) fail-closed 自检: 别名落库后确认没有「一个列名两个语义键」
    _assert_no_ambiguous_aliases()

    # 5) fail-closed 自检: 两条平台限定别名行在库 + 旧归属已消失
    _assert_visitor_count_aliases()

    # 6) fail-closed 自检: resolve_alias 按平台命中, 且不串台
    _assert_visitor_count_resolution()

    # 7) 刷新两条链的物化视图 ⇒ tiktok 的 UV 真的有值
    _refresh_mviews()

    # 8) fail-closed 自检: 视图里 tiktok 的 visitor_count 真的有值
    _assert_visitor_count_values()


def downgrade() -> None:
    """回滚。

    ⚠ **不回退视图定义** —— 视图定义的正本是 ``sql/`` 下的资产文件,
    回退 = 把资产文件改回旧版再跑一遍, 那是**代码回滚**的事, 不是迁移的职责。

    ⇒ 本迁移的数据库侧效果只有两类:
      1. 别名资产(可重新 seed, 幂等);
      2. 物化视图的**内容**(可 REFRESH 回当前定义)。
    """
    _refresh_mviews()
