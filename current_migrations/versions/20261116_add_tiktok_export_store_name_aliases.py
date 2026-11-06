"""补 6 条 TikTok「导出店名」别名 —— 让 720 行历史流量归位到正确的店。

背景
----
TikTok 的月度/日度导出里, 有一批文件的「店铺」列写的是**英文商场名**
(``DAONE Mall`` / ``Malaysia(Flora Mall)`` 这种), 而**店铺账号档案**里存的是
「品牌 + 地区」(``FIORO SG`` / ``KIDD0 MY``)。两边字面完全不同 ⇒ 身份解析匹配不上。

实测(live 开发库, ``semantic.fact_analytics_monthly_atomic_mv``):

* 2026-02 ~ 2026-05 的 **720 行**(6 个店 × 120 天)全部落 ``unmatched_shop_label``
  ⇒ **108,764 UV** 从看板上消失;
* 这批行的 ``raw_data`` 里**没有** ``shop_account_id``(那是 2026-06 起才有的),
  ``store_name`` / ``store_label_raw`` 也是空的 ⇒ 四路候选里只剩「原始 shop_id」
  这一路, 而原始 shop_id 的值就是那个英文商场名;
* 2026-06 起那批行带 ``shop_account_id`` ⇒ 已经 100% 正确认领 ⇒ **历史缺口**。

也就是说: **缺口只在 2026-02 ~ 2026-05 这一段**, 补上别名即可闭合。

为什么用别名而不是改账号档案
----------------------------
账号档案里的 ``store_name``(``FIORO SG``)是**看板显示名**的来源
(``core.dim_shops.shop_name``), 改它会动到所有历史行的显示口径。
而别名表的语义就是「同一个店的另一个叫法」⇒ **只影响身份匹配, 不影响显示名**。
这是代价最小、影响面最窄的修法。

别名键必须与 ``normalize_alias_key`` 逐字一致
--------------------------------------------
归一化的**唯一真源**是 ``backend/utils/text_normalization.py::normalize_alias_key``
(剥平台前缀 → 小写 → 删 ``[\\s_()/-]+``)。SQL 侧只允许使用**存好的**
``alias_normalized``, 不得再做第二次规范化。

本迁移因此做**三方交叉校验**:

1. 本文件里硬编码的 ``alias_normalized``(数据);
2. 迁移在 SQL 里用与 ``normalize_alias_key`` 等价的表达式**重新算**一遍;
3. 守护测试 ``backend/tests/data_pipeline/test_tiktok_export_store_name_aliases.py``
   断言「1 == ``normalize_alias_key(alias_value)``」。

三者任一不一致 ⇒ 迁移直接抛错回滚(fail-closed)。

实测效果(live 开发库, 单事务内插别名 → 重刷候选集资产 → 刷 MV → 量测 → 回滚):

=========================================  =======  =========
指标                                        改前      改后
=========================================  =======  =========
unmatched 行数 / UV                    933 / 108,772  213 / 8
ambiguous 行数 / UV                      18 / 8,409   18 / 8,409
总行数 / 总 UV                          3634 / 683,497 3634 / 683,497
=========================================  =======  =========

⇒ **只是把 720 行从未知搬回正确的店, 总量一字未动**。

迁移后**必须**刷的物化视图
-------------------------
别名表是**实时**读的, 但下游有两个**快照**:

* ``semantic.shop_identity_resolution_candidates_v2_mv`` —— 候选集的物化副本;
* ``semantic.fact_*_atomic_mv`` / ``semantic.fact_*_monthly_atomic_mv`` —— 原子层快照。

正本是普通视图(实时), 副本与原子层是物化视图 ⇒ **只插别名不刷 ⇒ 新别名不生效**。
:data:`_REQUIRED_REFRESH_TARGETS` 把这条链列全, 守护测试会校验它没漏。

⚠️ ``REFRESH MATERIALIZED VIEW`` 在生产要 115 秒量级(见
``backend/services/data_pipeline/refresh_runner.py`` 的超时预算说明) ⇒ 本迁移
**不做**内联刷新(会把锁一直按到提交), 刷新走既有的刷新管道(见 ``_REQUIRED_REFRESH_TARGETS``)。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261116_add_tiktok_export_store_name_aliases"
down_revision = "current_schema_20261114_add_sku_roi_columns"
branch_labels = None
depends_on = None


#: 别名来源标记 —— 回滚靠它精确定位「本次插进去的那几行」, 不误伤别的别名。
ALIAS_SOURCE = "shop_identity_remediation"

#: 别名类型: 「这个导出标签被这家店认领」。
#:
#: 不用 ``former_name`` —— 那表示「曾用名」(改名流程写的), 语义不对:
#: 这里不是店改名了, 而是**导出文件里的叫法**与账号档案里的叫法不同。
ALIAS_TYPE = "claimed"

#: 平台
PLATFORM = "tiktok"

#: 补录的 6 条别名。
#:
#: ``alias_normalized`` 刻意**硬编码** —— 迁移内容必须稳定可复核, 不从实时数据推导。
#: 它与 ``normalize_alias_key(alias_value)`` 的一致性由守护测试守住(跨层校验)。
_TIKTOK_EXPORT_ALIASES = (
    ("DAONE Mall", "daonemall", "tiktok_sg_daone_mall_local", "SG"),
    ("DAWIE Mall", "dawiemall", "tiktok_my_dawie_mall_local", "MY"),
    ("Explorers Mall", "explorersmall", "tiktok_ph_explorers_mall_local", "PH"),
    ("Malaysia(Flora Mall)", "malaysiafloramall", "tiktok_my_flora_mall_local", "MY"),
    ("Philippines(DAJU Mall)", "philippinesdajumall", "tiktok_ph_daju_mall_local", "PH"),
    ("Singapore(HX Home)", "singaporehxhome", "tiktok_sg_hx_home_local", "SG"),
)

#: 归一化表达式模板 —— 与 ``normalize_alias_key`` 逐字等价。
#:
#: 顺序对齐 Python 侧: ``strip`` → 剥平台前缀 → ``lower`` → 删分隔符 → ``strip``。
#: 平台前缀的正则**不区分大小写**, 所以「先剥前缀再小写」与「先小写再剥前缀」等价。
#: 分隔符类 ``[\\s_()/-]`` 在 SQL 侧写成 POSIX 的 ``[[:space:]_()/-]``(等价)。
#:
#: ``{value}`` 是「要归一化的表达式」占位: 写库时填绑定参数, 校验时填存量列。
_NORMALIZE_SQL = r"""
LOWER(
    TRIM(
        REGEXP_REPLACE(
            REGEXP_REPLACE(
                TRIM({value}),
                '^(shopee|tiktok\s*shop|tiktok|tk|miaoshou|amazon|lazada)\s*',
                '',
                'i'
            ),
            '[[:space:]_()/-]+',
            '',
            'g'
        )
    )
)
"""


def _normalize_sql(value_expression: str) -> str:
    """把归一化模板套上「要归一化的表达式」。"""
    return _NORMALIZE_SQL.format(value=value_expression)

#: 迁移落地后**必须**刷的物化视图(别名表是实时的, 这些是快照)。
#:
#: 顺序 = 依赖顺序(与 ``backend/services/data_pipeline/refresh_registry.py`` 的
#: ``PIPELINE_DEPENDENCIES`` 一致)。守护测试会校验这条链没漏。
_REQUIRED_REFRESH_TARGETS = (
    "semantic.shop_identity_resolution_candidates_v2_mv",
    "semantic.fact_analytics_atomic_mv",
    "semantic.fact_analytics_monthly_atomic_mv",
    "semantic.fact_orders_atomic_mv",
    "semantic.fact_orders_monthly_atomic_mv",
    "semantic.fact_products_atomic_mv",
)


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def _bind():
    return op.get_bind()


def _assert_targets_resolvable() -> None:
    """前置检查: 6 个目标账号必须存在、在营、是经营店, 且区域与硬编码一致。

    fail-closed —— 账号被停用/改区域时, **宁可迁移失败**, 也不要静默把别名
    挂到别处(那等于编数据)。
    """
    rows = _bind().execute(
        sa.text(
            """
            SELECT sa.shop_account_id, sa.shop_region, sa.enabled, sa.business_role
            FROM core.shop_accounts sa
            WHERE sa.platform = :platform
              AND sa.shop_account_id = ANY(CAST(:shop_account_ids AS text[]))
            """
        ),
        {
            "platform": PLATFORM,
            "shop_account_ids": [item[2] for item in _TIKTOK_EXPORT_ALIASES],
        },
    ).all()
    found = {str(row[0]): row for row in rows}

    problems: list[str] = []
    for alias_value, alias_normalized, shop_account_id, shop_region in _TIKTOK_EXPORT_ALIASES:
        row = found.get(shop_account_id)
        if row is None:
            problems.append(
                "账号不存在: {sid}（别名 {value}）".format(sid=shop_account_id, value=alias_value)
            )
            continue
        actual_region = str(row[1] or "").strip()
        if actual_region != shop_region:
            problems.append(
                "区域不符: {sid} 期望 {want}，实际 {got}".format(
                    sid=shop_account_id, want=shop_region, got=actual_region or "(空)"
                )
            )
        if not row[2]:
            problems.append("账号已停用: {sid}".format(sid=shop_account_id))
        if str(row[3] or "") != "operating_store":
            problems.append(
                "不是经营店: {sid}（business_role={role}）".format(
                    sid=shop_account_id, role=row[3]
                )
            )

    problems.extend(_alias_key_conflicts())

    if problems:
        raise RuntimeError(
            "TikTok 别名补录的前置检查未通过，拒绝继续：" + "；".join(problems)
        )


def _alias_key_conflicts() -> list[str]:
    """找出「这个别名键已经会让别人出事」的两种情况。

    ① **已被别的账号认领**(哪怕区域不同) —— 候选集按 ``platform_code`` +
       ``identity_value_normalized`` 匹配, **不看区域** ⇒ 同一串键挂在两个账号上
       ⇒ 候选数变 2 ⇒ 整片行落 unknown。宁可迁移失败, 也不能制造这种歧义。

       ⚠️ **本次迁移自己写进去的**不算冲突(否则重跑迁移会把自己当成冲突源,
       幂等性直接坏掉) ⇒ 只报 ``source <> ALIAS_SOURCE`` 的那些。

    ② **撞上某个账号的平台店铺编号** —— 候选集的别名路有一条 ``NOT EXISTS``
       守护(别名不得认领任何账号的 platform_shop_id), 撞上了这条别名会被
       **静默排除** ⇒ 「认领了却匹配不上」。
    """
    problems: list[str] = []
    keys = [item[1] for item in _TIKTOK_EXPORT_ALIASES]

    claimed_rows = _bind().execute(
        sa.text(
            """
            SELECT saa.alias_normalized, sa.shop_account_id, saa.shop_region
            FROM core.shop_account_aliases saa
            INNER JOIN core.shop_accounts sa ON sa.id = saa.shop_account_id
            WHERE saa.platform = :platform
              AND saa.is_active IS TRUE
              AND saa.source IS DISTINCT FROM :source
              AND saa.alias_normalized = ANY(CAST(:keys AS text[]))
            """
        ),
        {"platform": PLATFORM, "source": ALIAS_SOURCE, "keys": keys},
    ).all()
    for alias_normalized, shop_account_id, shop_region in claimed_rows:
        problems.append(
            "别名键已被账号 {sid} 认领（区域 {region}）：{key}".format(
                sid=shop_account_id,
                region=shop_region or "(空)",
                key=alias_normalized,
            )
        )

    collision_rows = _bind().execute(
        sa.text(
            """
            SELECT sa.platform_shop_id, sa.shop_account_id
            FROM core.shop_accounts sa
            WHERE sa.enabled IS TRUE
              AND sa.business_role = 'operating_store'
              AND LOWER(NULLIF(TRIM(COALESCE(sa.platform_shop_id, '')), '')) = ANY(CAST(:keys AS text[]))
            """
        ),
        {"keys": keys},
    ).all()
    for platform_shop_id, shop_account_id in collision_rows:
        problems.append(
            "别名键撞上账号 {sid} 的平台店铺编号 {psid}".format(
                sid=shop_account_id, psid=platform_shop_id
            )
        )

    return problems


def _insert_alias(
    alias_value: str,
    alias_normalized: str,
    shop_account_id: str,
) -> None:
    """插一条别名(幂等)。

    ``alias_normalized`` 由 SQL 按 :data:`_NORMALIZE_SQL` 现算 —— 算出来必须
    等于硬编码的期望值, 不等就**不插**(下面的校验会因此发现少了一条并抛错)。
    """
    _bind().execute(
        sa.text(
            """
            INSERT INTO core.shop_account_aliases (
                shop_account_id,
                platform,
                alias_value,
                alias_normalized,
                alias_type,
                source,
                shop_region,
                is_primary,
                is_active
            )
            SELECT
                sa.id,
                :platform,
                :alias_value,
                {normalize},
                :alias_type,
                :source,
                sa.shop_region,
                FALSE,
                TRUE
            FROM core.shop_accounts sa
            WHERE sa.shop_account_id = :shop_account_id
              AND sa.enabled IS TRUE
              AND sa.business_role = 'operating_store'
              AND {normalize} = :alias_normalized
            ON CONFLICT DO NOTHING
            """.format(normalize=_normalize_sql(":alias_value"))
        ),
        {
            "platform": PLATFORM,
            "alias_value": alias_value,
            "alias_normalized": alias_normalized,
            "alias_type": ALIAS_TYPE,
            "source": ALIAS_SOURCE,
            "shop_account_id": shop_account_id,
        },
    )


def _assert_aliases_present() -> None:
    """事后校验: 6 条别名都在、归属正确、且「存的值」与「现算的值」一致。

    这一步同时兜住两件事:

    1. 迁移漏插 / 被唯一约束挡掉(比如同一个别名已经挂在别的账号上);
    2. **归一化规则漂移** —— 存好的 ``alias_normalized`` 与按当前规则现算的值
       不一致 ⇒ 候选集永远匹配不上(「认领了却匹配不上」)。
    """
    rows = _bind().execute(
        sa.text(
            """
            SELECT
                sa.shop_account_id,
                saa.alias_value,
                saa.alias_normalized,
                saa.shop_region,
                {normalize} AS derived_normalized
            FROM core.shop_account_aliases saa
            INNER JOIN core.shop_accounts sa ON sa.id = saa.shop_account_id
            WHERE saa.platform = :platform
              AND saa.is_active IS TRUE
              AND saa.alias_normalized = ANY(CAST(:alias_normalized_keys AS text[]))
            """.format(normalize=_normalize_sql("saa.alias_value"))
        ),
        {
            "platform": PLATFORM,
            "alias_normalized_keys": [item[1] for item in _TIKTOK_EXPORT_ALIASES],
        },
    ).all()

    found: dict[str, tuple] = {}
    for row in rows:
        found[str(row[0])] = row

    problems: list[str] = []
    for alias_value, alias_normalized, shop_account_id, shop_region in _TIKTOK_EXPORT_ALIASES:
        row = found.get(shop_account_id)
        if row is None:
            problems.append(
                "别名未落库: {value} → {sid}".format(value=alias_value, sid=shop_account_id)
            )
            continue
        stored = str(row[2] or "")
        derived = str(row[4] or "")
        if stored != derived:
            problems.append(
                "归一化不一致: {value} 存的是 {stored}，按规则现算是 {derived}".format(
                    value=alias_value, stored=stored, derived=derived
                )
            )
        if str(row[3] or "").strip() != shop_region:
            problems.append(
                "别名区域不符: {value} 期望 {want}，实际 {got}".format(
                    value=alias_value, want=shop_region, got=str(row[3] or "") or "(空)"
                )
            )

    if problems:
        raise RuntimeError("TikTok 别名补录的校验未通过，拒绝提交：" + "；".join(problems))


# ---------------------------------------------------------------------------
# 升级 / 回滚
# ---------------------------------------------------------------------------


def upgrade() -> None:
    _assert_targets_resolvable()

    for alias_value, alias_normalized, shop_account_id, _region in _TIKTOK_EXPORT_ALIASES:
        _insert_alias(alias_value, alias_normalized, shop_account_id)

    _assert_aliases_present()

    print(
        "[OK] 已补录 {count} 条 TikTok 导出店名别名（source={source}）；"
        "请刷新这些物化视图：{targets}".format(
            count=len(_TIKTOK_EXPORT_ALIASES),
            source=ALIAS_SOURCE,
            targets=", ".join(_REQUIRED_REFRESH_TARGETS),
        )
    )


def downgrade() -> None:
    """回滚: 删掉**本次插进去的**那几行。

    靠 ``source`` 标记 + 精确的别名键定位 ⇒ 不会误伤运维手工加的别名,
    也不会误伤同键但来源不同的行(那种行本来就在, 不该由本迁移回滚)。
    """
    result = _bind().execute(
        sa.text(
            """
            DELETE FROM core.shop_account_aliases
            WHERE platform = :platform
              AND source = :source
              AND alias_normalized = ANY(CAST(:alias_normalized_keys AS text[]))
            """
        ),
        {
            "platform": PLATFORM,
            "source": ALIAS_SOURCE,
            "alias_normalized_keys": [item[1] for item in _TIKTOK_EXPORT_ALIASES],
        },
    )
    print(
        "[OK] 已回滚 TikTok 导出店名别名：删除 {count} 行；"
        "请刷新这些物化视图：{targets}".format(
            count=int(result.rowcount or 0),
            targets=", ".join(_REQUIRED_REFRESH_TARGETS),
        )
    )
