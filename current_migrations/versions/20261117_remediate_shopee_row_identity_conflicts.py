"""订正 Shopee 事实行里「互相矛盾的行内身份」—— 让 1,946 行重新归属到正确的店。

背景
----
采集侧算错 Shopee 平台店铺编号(硬编码覆盖表漏了 3 个在营店), 导致落库的行里
**同时带着两套互相矛盾的身份**:

    shop_id        = 1419169771   ← xhkj11.**ph** 的编号
    store_name     = xhkj11.sg     ← xhkj11.**sg** 的店名
    shop_account_id= shopee_sg_xhkj11_local

语义层把 ``shop_id`` / ``shop_account_id`` / ``store_name`` 当**三路独立候选**去计数
⇒ 命中两个账号 ⇒ 候选数 2 ⇒ 整行落 ``unknown``。

实测影响(开发库):

===========================================  =======  =========
数据域                                          行数     后果
===========================================  =======  =========
``fact_shopee_analytics_monthly``                  18  8,409 UV 从看板消失
``fact_shopee_products_monthly``                1,909  账号归属解析不出来
``fact_shopee_services_agent_monthly``             19  同上
===========================================  =======  =========

**编号是权威的, 标签是错的**
--------------------------------
这不是「猜哪个对」的问题, 是有证据的:

* 行内 UV 的量级与**编号所属**的店吻合(786/天 vs xhkj11.ph 的 898/天),
  与**标签所属**的店不吻合(786/天 vs xhkj11.sg 的 315/天);
* 标签所属的店在同一天**本该有**自己的一行、却查无此行(编号所属的店那几天完全没数据);
* 错配是**成对互换**的(``xhkj11.sg`` ↔ ``xhkj11.ph``、``xh_home.ph`` ↔ ``xhkj1.my``),
  像是同一批次里两个店的标签被换了个位置。

⇒ 所以订正方向是: **用行内编号反查主数据账号, 用该账号的登记身份覆盖标签**。

本迁移做什么
------------
对三个受影响的表, 把「行内编号能反查到账号 B、而行内标签指向账号 A(A≠B)」的行:
把 ``shop_id``(列) 与 ``raw_data`` 里的 ``shop_id`` / ``shop_account_id`` /
``store_name`` / ``platform_shop_id`` 全部改成**账号 B 在 ``core.shop_accounts`` 里的登记值**。

安全边界
--------
1. **只改身份字段**, 一个业务字段都不动(访客数 / GMV / 日期 / 页面浏览数 …)。
2. **``data_hash`` 绝不改**。
   ``data_hash`` 由「核心去重字段(analytics 是 ``metric_date``)」+ 作用域
   (``platform_code`` + 文件级 ``shop_account_id``)算出, **不含 raw_data**。
   作用域不变 ⇒ hash 不变 ⇒ 将来重新采集同一份文件时, upsert 冲突键
   ``(platform_code, shop_id, data_domain, granularity, data_hash)`` 与订正后的行**一致**
   ⇒ 覆盖同一行, **不会产生重复行**。
3. **原始身份留痕**: 改之前把 4 个原始身份字段存进 ``raw_data['_pre_remediation_identity']``
   ⇒ 可回滚 + 可审计(「这行原来被贴错成什么样」查得到)。
4. **幂等**: 订正后 ``shop_account_id`` 已等于目标账号 ⇒ 条件不再命中 ⇒ 重跑 0 行。
5. **只订正在营经营店**: 反查到的账号必须 ``enabled IS TRUE`` 且
   ``business_role='operating_store'`` —— 停用店的编号本来就不在候选池里, 不构成歧义。
6. **编号未登记的行不动**: ``xhkj12.my`` 那 28 行带的编号 ``1638198770`` 在主数据里不存在
   ⇒ 无法反查 ⇒ 保持原样(它不命中任何候选 ⇒ 不产生歧义, 且 UV 全为 0)。

回滚
----
``downgrade`` 从 ``raw_data['_pre_remediation_identity']`` 把 4 个字段原样还原,
并删掉该留痕键(原本不存在的键不会被加回来 —— 留痕是用 ``jsonb_strip_nulls`` 存的)。

⚠️ 本迁移**不碰** ``core.shop_account_aliases``、``core.shop_accounts``、``public.catalog_files``。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261117_remediate_shopee_row_identity_conflicts"
down_revision = "current_schema_20261116_add_tiktok_export_store_name_aliases"
branch_labels = None
depends_on = None


#: 受影响的数据域 → (b_class 表名, 刷新目标)。
#:
#: 只有**analytics** 与 **products** 有物化快照要刷;
#: ``services`` 走的是普通视图(实时), 改完立刻生效。
_TARGETS = (
    ("b_class.fact_shopee_analytics_monthly", None),
    ("b_class.fact_shopee_products_monthly", "semantic.fact_products_atomic_mv"),
    ("b_class.fact_shopee_services_agent_monthly", None),
)

#: 订正后**必须**刷的物化视图。
_REQUIRED_REFRESH_TARGETS = (
    "semantic.fact_analytics_atomic_mv",
    "semantic.fact_analytics_monthly_atomic_mv",
    "semantic.fact_products_atomic_mv",
)

#: 留痕键
_AUDIT_KEY = "_pre_remediation_identity"


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def _bind():
    return op.get_bind()


def _table_exists(qualified_name: str) -> bool:
    schema, _, table = qualified_name.partition(".")
    return sa.inspect(_bind()).has_table(table, schema=schema)


def _conflict_rows_sql(table: str) -> str:
    """「行内编号能反查到账号 B、行内标签指向账号 A(A≠B)」的行。

    ⚠️ 与标签所属账号的 JOIN 用 ``raw_data->>'shop_account_id'``;
    编号所属账号的 JOIN 用**列** ``shop_id``(它与 ``raw_data->>'shop_id'`` 一致)。
    """
    return """
        SELECT r.id
        FROM {table} r
        INNER JOIN core.shop_accounts owner
                ON owner.shop_account_id = r.raw_data ->> 'shop_account_id'
        INNER JOIN core.shop_accounts target
                ON LOWER(NULLIF(TRIM(target.platform_shop_id), ''))
                   = LOWER(NULLIF(TRIM(r.shop_id), ''))
               AND LOWER(TRIM(COALESCE(target.platform, '')))
                   = LOWER(TRIM(COALESCE(r.platform_code, '')))
        WHERE owner.enabled IS TRUE
          AND owner.business_role = 'operating_store'
          AND target.enabled IS TRUE
          AND target.business_role = 'operating_store'
          AND owner.id <> target.id
    """.format(table=table)


def _affected_rows_sql(table: str) -> str:
    """受影响行的 ``(id, data_hash)`` —— 订正前后必须**逐行一致**。

    ⚠️ 不能用「订正后再跑一次冲突查询」来比对: 订正后冲突本来就消失了,
    那样比出来的 digest 必然不同。这里按**行 id** 取, 才是真正的「hash 没被动过」。
    """
    return """
        SELECT r.id::bigint, r.data_hash
        FROM {table} r
        WHERE r.id IN ({conflict_rows})
        ORDER BY r.id
    """.format(table=table, conflict_rows=_conflict_rows_sql(table))


#: 订正语句。
#:
#: ``raw_data`` 的 4 个身份键: 先删干净, 再按主数据登记值写回, 最后挂上留痕。
#: 留痕用 ``jsonb_strip_nulls`` ⇒ 原本不存在的键不会被记成 null, 回滚时也不会被加回来。
_UPDATE_SQL = """
    UPDATE {table} r
    SET
        shop_id = NULLIF(TRIM(target.platform_shop_id), ''),
        raw_data = (
            (r.raw_data - 'shop_id' - 'shop_account_id' - 'store_name' - 'platform_shop_id')
            || jsonb_build_object(
                'shop_id', NULLIF(TRIM(target.platform_shop_id), ''),
                'shop_account_id', target.shop_account_id,
                'store_name', COALESCE(target.store_name, ''),
                'platform_shop_id', NULLIF(TRIM(target.platform_shop_id), '')
            )
            || jsonb_build_object(
                '{audit_key}',
                COALESCE(
                    r.raw_data -> '{audit_key}',
                    jsonb_strip_nulls(jsonb_build_object(
                        'shop_id', r.raw_data -> 'shop_id',
                        'shop_account_id', r.raw_data -> 'shop_account_id',
                        'store_name', r.raw_data -> 'store_name',
                        'platform_shop_id', r.raw_data -> 'platform_shop_id'
                    ))
                )
            )
        )
    FROM core.shop_accounts owner, core.shop_accounts target
    WHERE owner.shop_account_id = r.raw_data ->> 'shop_account_id'
      AND LOWER(NULLIF(TRIM(target.platform_shop_id), ''))
          = LOWER(NULLIF(TRIM(r.shop_id), ''))
      AND LOWER(TRIM(COALESCE(target.platform, '')))
          = LOWER(TRIM(COALESCE(r.platform_code, '')))
      AND owner.enabled IS TRUE
      AND owner.business_role = 'operating_store'
      AND target.enabled IS TRUE
      AND target.business_role = 'operating_store'
      AND owner.id <> target.id
""".format(table="{table}", audit_key=_AUDIT_KEY)


#: 回滚语句: 从留痕还原 4 个身份字段, 并删掉留痕键。
#:
#: ⚠️ 2026-11-07 修正：**模板里只能有「一次」格式化**。
#: 这段 SQL 在模块加载时已经 ``.format(table="{table}", audit_key=...)`` 过一次
#: ⇒ 里面的 ``{{}}`` 已经变成字面 ``{}``（JSONB 空对象）。
#: 如果运行期再走一次 ``.format(table=table)``，那个裸 ``{}`` 会被当成
#: **自动编号字段** ⇒ ``IndexError: Replacement index 0 out of range for
#: positional args tuple`` ⇒ ``alembic downgrade`` 直接炸、回滚不可用。
#:
#: 所以运行期一律用 ``.replace("{table}", table)``（守护测试
#: ``backend/tests/data_pipeline/test_shopee_row_identity_remediation.py``
#: 的 ``_update_sql`` / ``_rollback_sql`` 本来就是这么写的，两边口径一致）。
_ROLLBACK_SQL = """
    UPDATE {table} r
    SET
        shop_id = COALESCE(
            r.raw_data -> '{audit_key}' ->> 'shop_id',
            r.shop_id
        ),
        raw_data = (
            (r.raw_data - 'shop_id' - 'shop_account_id' - 'store_name' - 'platform_shop_id')
            || COALESCE(r.raw_data -> '{audit_key}', '{{}}'::jsonb)
        ) - '{audit_key}'
    WHERE r.raw_data ? '{audit_key}'
""".format(table="{table}", audit_key=_AUDIT_KEY)


# ---------------------------------------------------------------------------
# 升级 / 回滚
# ---------------------------------------------------------------------------


def upgrade() -> None:
    total = 0
    for table, _mv in _TARGETS:
        if not _table_exists(table):
            print("[WARN] 表不存在，跳过：{0}".format(table))
            continue

        before_rows = _bind().execute(
            sa.text(_affected_rows_sql(table))
        ).all()
        if not before_rows:
            print("[INFO] {0}: 无自相矛盾行，跳过".format(table))
            continue

        result = _bind().execute(
            sa.text(_UPDATE_SQL.replace("{table}", table))
        )
        changed = int(result.rowcount or 0)

        # ① data_hash 必须一个字节都没变(按行 id 逐行比)
        after_rows = _bind().execute(
            sa.text(
                "SELECT id::bigint, data_hash FROM {0} WHERE id = ANY(CAST(:ids AS bigint[])) "
                "ORDER BY id".format(table)
            ),
            {"ids": [int(row[0]) for row in before_rows]},
        ).all()
        if len(after_rows) != len(before_rows):
            raise RuntimeError(
                "订正后行数对不上，拒绝提交：{0} before={1} after={2}".format(
                    table, len(before_rows), len(after_rows)
                )
            )
        for before_row, after_row in zip(before_rows, after_rows):
            if str(before_row[1]) != str(after_row[1]):
                raise RuntimeError(
                    "data_hash 被改动了，拒绝提交：{0} id={1}".format(
                        table, int(before_row[0])
                    )
                )

        # ② 订正后不该再有自相矛盾行
        remaining = _bind().execute(
            sa.text(_conflict_rows_sql(table))
        ).all()
        if remaining:
            raise RuntimeError(
                "订正后仍有自相矛盾行，拒绝提交：{0} 剩余 {1}".format(
                    table, len(remaining)
                )
            )

        total += changed
        print("[OK] {0}: 订正 {1} 行".format(table, changed))

    print(
        "[OK] Shopee 行内身份订正完成：共 {0} 行；"
        "请刷新这些物化视图：{1}".format(
            total, ", ".join(_REQUIRED_REFRESH_TARGETS)
        )
    )


def downgrade() -> None:
    total = 0
    for table, _mv in _TARGETS:
        if not _table_exists(table):
            continue
        result = _bind().execute(
            sa.text(_ROLLBACK_SQL.replace("{table}", table))
        )
        changed = int(result.rowcount or 0)
        total += changed
        print("[OK] {0}: 还原 {1} 行".format(table, changed))

    print(
        "[OK] 已还原 Shopee 行内身份；"
        "请刷新这些物化视图：{0}".format(", ".join(_REQUIRED_REFRESH_TARGETS))
    )
