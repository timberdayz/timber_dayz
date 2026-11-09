"""同步侧「身份自洽」拦截的守护测试(WP-4)。

背景
----
云同步的 upsert 冲突键是 ``(platform_code, shop_id, data_domain, granularity,
data_hash)``, 而 ``data_hash`` **不含 raw_data** ⇒ 两行只要核心业务字段相同就会
撞到同一个冲突键。

于是本地第二行(行内身份=A) 命中冲突键后, ``DO UPDATE`` 把 raw_data 改成
另一份 ⇒ 云端留下一行「内容与身份不符」的**混合行**。这是同步侧的**放大器**。

判据演进(2026-11-09)
------------------
旧判据(2026-11-07 上线):「事实表 **列** ``shop_id`` vs ``raw_data['shop_id']``」。

⚠️ **这个判据是错的** —— 事实表的 ``shop_id`` **列不是身份列**:
shopee 上装的是平台店铺编号、tiktok 上装的是导出店名、miaoshou 采集链上装的是
采集方代号 ``xihong``。拿它去和行内账号 ID 比, **同源的两层也永远不相等**。

实测(本地 dev 库 65,197 行):旧判据误杀 **3,781 行正常数据**,
而这些行在语义层能唯一归属到店铺 —— 数据本来是好的, 是在同步侧被扔掉的。

新判据: 行内身份键能否**唯一归属到一个主数据账号**。
详见 :func:`backend.services.cloud_b_class_sync_service.split_rows_by_identity_consistency`。

本测试盯住四件事
----------------
1. **不自洽的行不写云端** —— 宁可少同步一行, 也不把混合行搬进云端;
2. **不再拿「非身份列」判身份** —— 列与行内不同源**不是**矛盾;
3. **真矛盾仍能抓住** —— 行内两个身份键指向不同的店 ⇒ 拦;
4. **``shop_id`` 与 ``raw_data`` 绑定** —— 两者同进同退。
"""

from __future__ import annotations

from backend.services.cloud_b_class_sync_service import (
    SQLAlchemyCloudWriter,
    split_rows_by_identity_consistency,
)
from backend.services.shop_identity_reconciliation_service import build_identity_index


# ---------------------------------------------------------------------------
# 主数据样例(与语义层候选池同口径: 只收在营经营店)
# ---------------------------------------------------------------------------

ACCOUNTS = [
    {
        "id": 1,
        "shop_account_id": "shopee_sg_hx_home_local",
        "platform": "shopee",
        "platform_shop_id": "1391124228",
        "store_name": "hx_home.sg",
        "shop_region": "SG",
        "enabled": True,
        "business_role": "operating_store",
    },
    {
        "id": 2,
        "shop_account_id": "shopee_ph_xhkj11_local",
        "platform": "shopee",
        "platform_shop_id": "1419169771",
        "store_name": "xhkj11.ph",
        "shop_region": "PH",
        "enabled": True,
        "business_role": "operating_store",
    },
    {
        "id": 3,
        "shop_account_id": "tiktok_sg_daone_mall_local",
        "platform": "tiktok",
        "platform_shop_id": "",
        "store_name": "FIORO SG",
        "shop_region": "SG",
        "enabled": True,
        "business_role": "operating_store",
    },
]

ALIASES = [
    {
        "id": 11,
        "shop_account_id": "1",
        "alias_value": "4店包包",
        "alias_normalized": "4店包包",
        "is_active": True,
    },
    {
        "id": 12,
        "shop_account_id": "2",
        "alias_value": "菲律宾1店",
        "alias_normalized": "菲律宾1店",
        "is_active": True,
    },
    {
        "id": 13,
        "shop_account_id": "3",
        "alias_value": "菲律宾1店",
        "alias_normalized": "菲律宾1店",
        "is_active": True,
    },
]

INDEX = build_identity_index(ACCOUNTS, ALIASES)


def _row(shop_id, raw_shop_id=None, raw_platform_shop_id=None, **extra):
    raw_data = {"shop_account_id": "shopee_sg_xhkj11_local"}
    if raw_shop_id is not None:
        raw_data["shop_id"] = raw_shop_id
    if raw_platform_shop_id is not None:
        raw_data["platform_shop_id"] = raw_platform_shop_id
    row = {
        "platform_code": "shopee",
        "shop_id": shop_id,
        "data_domain": "analytics",
        "granularity": "monthly",
        "sub_domain": None,
        "metric_date": "2026-06-22",
        "raw_data": raw_data,
        "data_hash": "hash-1",
    }
    row.update(extra)
    return row


# ---------------------------------------------------------------------------
# 分流: 基本行为
# ---------------------------------------------------------------------------


def test_consistent_row_is_kept():
    """行内身份自洽 ⇒ 照常同步。"""
    rows = [_row("1308200825", raw_shop_id="1308200825")]
    split = split_rows_by_identity_consistency(rows, INDEX)
    assert len(split.consistent) == 1
    assert split.conflicting == []


def test_column_vs_raw_data_mismatch_is_no_longer_a_conflict():
    """★ 关键回归: 事实表「列」与行内不同源**不是**矛盾。

    这一列不是身份列(装的是采集层原始标识), 拿它判身份会把正常数据全误杀。
    实测旧判据误杀 3,781 行 ⇒ 本条是那次丢数事故的守护。
    """
    rows = [_row("1308200825", raw_shop_id="1419169771")]
    split = split_rows_by_identity_consistency(rows, INDEX)
    assert len(split.consistent) == 1, "列与行内不同源不应被判成矛盾"
    assert split.conflicting == []


def test_empty_values_are_not_treated_as_conflict():
    """空值没有可比基准 ⇒ 不算矛盾(否则会大面积误杀)。"""
    rows = [_row("", raw_shop_id="")]
    split = split_rows_by_identity_consistency(rows, INDEX)
    assert len(split.consistent) == 1
    assert split.conflicting == []


def test_missing_raw_data_is_not_treated_as_conflict():
    """没有 raw_data 就无从判矛盾 ⇒ 照常同步。"""
    rows = [_row("1308200825")]
    rows[0]["raw_data"] = None
    split = split_rows_by_identity_consistency(rows, INDEX)
    assert len(split.consistent) == 1
    assert split.conflicting == []


def test_mixed_batch_is_split_correctly():
    """一批里自洽与矛盾的行要分得干净。"""
    rows = [
        _row("1391124228", raw_shop_id="1391124228", raw_platform_shop_id="1391124228"),
        # 行内编号属 hx_home、账号属 xhkj11 ⇒ 真矛盾
        _row("1419169771", raw_shop_id="1419169771", raw_platform_shop_id="1391124228"),
        _row("1419169771", raw_shop_id="1419169771", raw_platform_shop_id="1419169771"),
    ]
    split = split_rows_by_identity_consistency(rows, INDEX)
    assert len(split.consistent) == 2
    assert len(split.conflicting) == 1


# ---------------------------------------------------------------------------
# 分流: 真矛盾必须抓住(判据改造不能把「拦住坏数据」的能力弄丢)
# ---------------------------------------------------------------------------


def test_row_identity_pointing_to_two_accounts_is_conflicting():
    """★ 行内两个身份键指向**不同账号** ⇒ 真矛盾 ⇒ 拦。

    这是本次判据改造的底线: 判据从「跨层比字符串」换成「查主数据判唯一归属」,
    但**拦坏数据的能力不能丢**。
    """
    rows = [
        {
            "platform_code": "shopee",
            "shop_id": "1419169771",
            "raw_data": {
                "platform_shop_id": "1391124228",  # → shopee_sg_hx_home_local
                "shop_account_id": "shopee_ph_xhkj11_local",  # → 另一个账号
            },
        }
    ]
    split = split_rows_by_identity_consistency(rows, INDEX)
    assert split.consistent == []
    assert len(split.conflicting) == 1


def test_store_label_pointing_to_another_account_is_conflicting():
    """行内中文店名指向别的店 ⇒ 矛盾。"""
    rows = [
        {
            "platform_code": "shopee",
            "shop_id": "1391124228",
            "raw_data": {
                "shop_account_id": "shopee_sg_hx_home_local",
                "店铺": "菲律宾1店",  # → shopee_ph_xhkj11_local
            },
        }
    ]
    split = split_rows_by_identity_consistency(rows, INDEX)
    assert split.consistent == []
    assert len(split.conflicting) == 1


def test_same_account_across_platforms_is_not_a_conflict():
    """★ 同名店名挂在**不同平台**的账号上 ⇒ 按平台过滤后**不算**矛盾。

    实测: 中文名「菲律宾1店」既指向 shopee_ph_xhkj11_local,
    也指向 tiktok_ph_explorers_mall_local。若不按平台过滤,
    shopee 的行会被解析出两个账号 ⇒ 19,504 行正常订单被误杀。
    """
    rows = [
        {
            "platform_code": "shopee",
            "shop_id": "1419169771",
            "raw_data": {"店铺": "菲律宾1店"},
        },
        {
            "platform_code": "tiktok",
            "shop_id": "FIORO SG",
            "raw_data": {"店铺": "菲律宾1店"},
        },
    ]
    split = split_rows_by_identity_consistency(rows, INDEX)
    assert len(split.consistent) == 2, "跨平台同名店名不应造成矛盾"
    assert split.conflicting == []


def test_collection_source_ids_are_not_treated_as_shop_identity():
    """★ 采集方标识(``xihong`` / ``miaoshou_real_001``)不是店铺身份。

    事实表的列与行内 ``shop_id`` 在 miaoshou 采集链上装的都是采集方代号,
    拿它当身份比对会得出错误结论。
    """
    rows = [
        {
            "platform_code": "shopee",
            "shop_id": "xihong",
            "raw_data": {
                "shop_id": "xihong",
                "shop_account_id": "miaoshou_real_001",
                "店铺": "4店包包",  # → shopee_sg_hx_home_local
            },
        }
    ]
    split = split_rows_by_identity_consistency(rows, INDEX)
    assert len(split.consistent) == 1, "采集方标识不应被当成店铺身份"
    assert split.conflicting == []


def test_unresolvable_identity_is_not_treated_as_conflict():
    """★ 解析不出账号(停用店 / 历史缺戳)⇒ **不拦**。

    这类行不是「坏数据」, 是「待人工」——
    当成矛盾丢掉就是静默丢数(2026-11-07 事故的形态)。
    """
    rows = [
        {
            "platform_code": "shopee",
            "shop_id": "1292370001",
            "raw_data": {
                "shop_account_id": "shopee_sg_eternalbloom_local",  # 已停用, 不在索引
                "shop_id": "1292370001",
            },
        }
    ]
    split = split_rows_by_identity_consistency(rows, INDEX)
    assert len(split.consistent) == 1, "无法归属的行不该被当成矛盾丢弃"
    assert split.conflicting == []


def test_degraded_mode_without_identity_index_does_not_misfire():
    """没有主数据时降级为「只比同形态的键」⇒ 不能误杀。

    降级的取舍: 拦错会**静默丢数**, 不拦最多留下一批待人工处理 ⇒ 宁可少拦。
    """
    rows = [
        {
            "platform_code": "shopee",
            "shop_id": "1391124228",
            "raw_data": {
                "platform_shop_id": "1391124228",
                "shop_account_id": "shopee_sg_hx_home_local",
            },
        }
    ]
    split = split_rows_by_identity_consistency(rows, None)
    assert len(split.consistent) == 1
    assert split.conflicting == []


# ---------------------------------------------------------------------------
# upsert 语句: shop_id 与 raw_data 绑定
# ---------------------------------------------------------------------------


def test_shop_id_is_updated_together_with_raw_data():
    """``shop_id`` 必须与 ``raw_data`` 同进同退 —— 不能一个更新一个不动。

    ⚠️ 以前 ``shop_id`` 被排除在更新集之外, 而 ``raw_data`` 会被更新
    ⇒ 两者一拆开就必然产生「列是 A、内容是 B」的混合行。
    """
    writer = SQLAlchemyCloudWriter(engine=None)
    sql = writer._build_upsert_sql("fact_shopee_analytics_monthly", "analytics")

    update_clause = sql.split("DO UPDATE SET", 1)[1]
    assert "shop_id = EXCLUDED.shop_id" in update_clause
    assert "raw_data = EXCLUDED.raw_data" in update_clause
    # 冲突键与作用域列仍然不更新
    assert "platform_code = EXCLUDED.platform_code" not in update_clause
    assert "data_hash = EXCLUDED.data_hash" not in update_clause


def test_conflict_clauses_unchanged():
    """冲突键不许动(动了会重复入库)。"""
    writer = SQLAlchemyCloudWriter(engine=None)
    assert (
        "ON CONFLICT (platform_code, shop_id, data_domain, granularity, data_hash)"
        in writer._build_upsert_sql("fact_shopee_analytics_monthly", "analytics")
    )
    assert (
        "ON CONFLICT (data_domain, sub_domain, granularity, data_hash)"
        in writer._build_upsert_sql("fact_shopee_services_agent_daily", "services")
    )


# ---------------------------------------------------------------------------
# 写入入口
# ---------------------------------------------------------------------------


class _FakeConn:
    def __init__(self):
        self.executed = []

    def execute(self, statement, params=None):
        self.executed.append((str(statement), params))


class _FakeEngine:
    def __init__(self):
        self.conn = _FakeConn()

    def begin(self):
        return self

    def __enter__(self):
        return self.conn

    def __exit__(self, *exc_info):
        return False


def test_writer_skips_conflicting_rows_and_reports_count():
    """冲突行不写云端, 且计数要报出来(可观测)。"""
    engine = _FakeEngine()
    writer = SQLAlchemyCloudWriter(engine=engine, identity_index=INDEX)
    rows = [
        _row("1391124228", raw_shop_id="1391124228", raw_platform_shop_id="1391124228"),
        # 行内编号属 hx_home、账号属 xhkj11 ⇒ 真矛盾
        _row("1419169771", raw_shop_id="1419169771", raw_platform_shop_id="1391124228"),
    ]

    result = writer("fact_shopee_analytics_monthly", rows, "analytics")

    assert result["written_rows"] == 1
    assert result["identity_conflict_rows"] == 1
    assert len(engine.conn.executed) == 1
    # 只写进了那一行自洽的
    written_params = engine.conn.executed[0][1]
    assert [p["shop_id"] for p in written_params] == ["1391124228"]


def test_writer_writes_rows_whose_column_differs_from_raw_data():
    """★ 回归: 列与行内不同源的行**照常写云端**。

    旧判据会把这类行全丢掉(实测 3,781 行)—— 那些数据在语义层能唯一归属,
    本来就是好的。
    """
    engine = _FakeEngine()
    writer = SQLAlchemyCloudWriter(engine=engine, identity_index=INDEX)
    rows = [_row("1391124228", raw_shop_id="shopee_sg_hx_home_local")]

    result = writer("fact_shopee_analytics_monthly", rows, "analytics")

    assert result["written_rows"] == 1
    assert result["identity_conflict_rows"] == 0
    assert len(engine.conn.executed) == 1
