"""行内身份收敛(``shop_identity_reconciliation_service``)的守护测试。

背景
----
2026-11 的「店铺身份未对齐」事故: 采集侧算错平台店铺编号 ⇒ 一行事实同时带着
「别的店的编号」和「本店的标签」⇒ 语义层候选数 2 ⇒ 整行落 ``unknown``
(1,946 行、8,409 UV 从看板消失)。

本模块的职责是**入库时**把行内身份收敛成「只带一套身份」。

本文件盯住三件事
----------------
1. **归属判定正确** —— 账号章权威(与 SSOT / 语义层候选池优先级一致);
2. **歧义不猜** —— 一串值被多个账号认领时该信号不可用, 绝不静默挑一个;
3. **只改身份键** —— 业务字段一个都不动。
"""

from __future__ import annotations

import re

import pytest

from backend.services.shop_identity_gate_service import (
    evaluate_row_identity_consistency,
)
from backend.services.shop_identity_reconciliation_service import (
    STATUS_CONFLICT,
    STATUS_CONVERGED,
    STATUS_UNRESOLVED,
    apply_reconciliation,
    build_identity_index,
    collect_row_signals,
    converged_shop_id_value,
    reconcile_identity,
)
from backend.utils.text_normalization import normalize_alias_key


# ---------------------------------------------------------------------------
# 主数据样例
# ---------------------------------------------------------------------------

#: 在营 Shopee 店 —— 编号 / 店名都唯一
SHOPEE_SG = {
    "id": 11,
    "shop_account_id": "shopee_sg_xhkj11_local",
    "platform": "shopee",
    "platform_shop_id": "1308200825",
    "store_name": "xhkj11.sg",
    "shop_region": "SG",
    "enabled": True,
    "business_role": "operating_store",
}
SHOPEE_PH = {
    "id": 12,
    "shop_account_id": "shopee_ph_xhkj11_local",
    "platform": "shopee",
    "platform_shop_id": "1419169771",
    "store_name": "xhkj11.ph",
    "shop_region": "PH",
    "enabled": True,
    "business_role": "operating_store",
}
#: TikTok 店 —— **没有** platform_shop_id(锚点只能靠别名表)
TIKTOK_SG = {
    "id": 62,
    "shop_account_id": "tiktok_sg_daone_mall_local",
    "platform": "tiktok",
    "platform_shop_id": "",
    "store_name": "FIORO SG",
    "shop_region": "SG",
    "enabled": True,
    "business_role": "operating_store",
}
#: 停用店 —— 不该进候选池
SHOPEE_DISABLED = {
    "id": 20,
    "shop_account_id": "shopee_my_off_local",
    "platform": "shopee",
    "platform_shop_id": "9999999",
    "store_name": "off.shop",
    "shop_region": "MY",
    "enabled": False,
    "business_role": "operating_store",
}

ACCOUNTS = [SHOPEE_SG, SHOPEE_PH, TIKTOK_SG, SHOPEE_DISABLED]

#: 别名 —— ⚠️ ``shop_account_id`` 是**整数 PK**(FK → core.shop_accounts.id),
#: 与账号的字符串编码 ``tiktok_sg_daone_mall_local`` **不是同一个东西**。
ALIASES = [
    {
        "id": 1,
        "shop_account_id": 62,
        "platform": "tiktok",
        "alias_value": "DAONE Mall",
        "alias_normalized": "daonemall",
        "is_active": True,
    },
]


@pytest.fixture()
def index():
    return build_identity_index(ACCOUNTS, ALIASES)


# ---------------------------------------------------------------------------
# ① 归属判定 —— 账号章优先
# ---------------------------------------------------------------------------


def test_account_id_wins_over_platform_number(index):
    """行内编号指向**别的**账号、账号章指向**正确的**账号 ⇒ 归到**账号章**那个账号。

    SSOT(``modules/core/fact_identity_columns.py``)与语义层候选池
    (``sql/semantic/shop_identity_resolution_candidates.sql``)都是账号章 priority 1:
    账号章**改名不变、跨平台一致、采集器写不坏**;
    平台编号**会被采集器污染、平台换 ID 就失效** ⇒ 只能次之。
    """
    row = {
        "platform_shop_id": "1419169771",  # xhkj11.**ph** 的编号(别的账号)
        "shop_account_id": "shopee_sg_xhkj11_local",  # 账号章 —— 正确的账号
        "store_name": "xhkj11.sg",
        "访客数": "807",
    }
    result = reconcile_identity(
        index, platform_code="shopee", signals=collect_row_signals(row)
    )
    assert result.status == STATUS_CONVERGED
    assert result.identity.shop_account_id == "shopee_sg_xhkj11_local"
    # 编号信号与归属不一致 ⇒ 记为冲突, 但**不推翻**账号章权威
    assert "platform_shop_id" in result.conflict_signals
    assert "shop_account_id" in result.matched_signals


def test_account_id_wins_over_number_in_shop_id_column(index):
    """事实列 ``shop_id`` 里存的是平台编号 ⇒ 它指向别的账号时也不该盖过账号章。"""
    row = {
        "shop_id": "1419169771",  # xhkj11.**ph** 的编号(别的账号)
        "shop_account_id": "shopee_sg_xhkj11_local",  # 账号章 —— 正确的账号
        "store_name": "xhkj11.sg",
    }
    result = reconcile_identity(
        index, platform_code="shopee", signals=collect_row_signals(row)
    )
    assert result.status == STATUS_CONVERGED
    assert result.identity.shop_account_id == "shopee_sg_xhkj11_local"
    assert "shop_id" in result.conflict_signals


def test_missing_account_id_falls_back_to_next_signal(index):
    """账号章**查不到**(空)⇒ 自动落到下一个信号(编号), 不得变成冲突/未归属。"""
    row = {"shop_id": "1419169771", "shop_account_id": "", "store_name": ""}
    result = reconcile_identity(
        index, platform_code="shopee", signals=collect_row_signals(row)
    )
    assert result.status == STATUS_CONVERGED
    assert result.identity.shop_account_id == "shopee_ph_xhkj11_local"
    assert result.matched_signals == ("shop_id",)


def test_account_id_pointing_to_disabled_store_falls_back_to_next_signal(index):
    """账号章指向**不在索引里**的账号(停用店)⇒ 跳过它, 落到下一个信号。

    停用店不进候选池(见 ``build_identity_index``), 所以它的账号章查不到任何账号
    ⇒ 不能因此把整行判成「冲突」或「未归属」。
    """
    row = {
        "shop_id": "1419169771",
        "shop_account_id": "shopee_my_off_local",  # 停用店 ⇒ 不在索引里
        "store_name": "xhkj11.sg",
    }
    result = reconcile_identity(
        index, platform_code="shopee", signals=collect_row_signals(row)
    )
    # ⇒ 退到下一个信号即可, 不是 conflict, 也不是 unresolved
    assert result.status == STATUS_CONVERGED
    assert result.identity.shop_account_id == "shopee_ph_xhkj11_local"


def test_self_consistent_row_resolves_to_itself(index):
    """自洽行(编号/标签都指向同一个店)⇒ 归属不变, 且无冲突。"""
    row = {
        "shop_id": "1308200825",
        "shop_account_id": "shopee_sg_xhkj11_local",
        "store_name": "xhkj11.sg",
    }
    result = reconcile_identity(
        index, platform_code="shopee", signals=collect_row_signals(row)
    )
    assert result.status == STATUS_CONVERGED
    assert result.identity.shop_account_id == "shopee_sg_xhkj11_local"
    assert result.conflict_signals == ()


def test_tiktok_anchors_on_alias(index):
    """TikTok 没有 platform_shop_id ⇒ 锚点是别名表里的导出店名。"""
    row = {"shop_id": "DAONE Mall", "store_name": "", "shop_account_id": ""}
    result = reconcile_identity(
        index, platform_code="tiktok", signals=collect_row_signals(row)
    )
    assert result.status == STATUS_CONVERGED
    assert result.identity.shop_account_id == "tiktok_sg_daone_mall_local"


def test_alias_links_by_integer_pk_not_by_code():
    """回归: 别名的 FK 是**整数主键**, 早先按字符串账号编码关联 ⇒ 别名索引全空
    ⇒ TikTok 永远锚不上。"""
    idx = build_identity_index(ACCOUNTS, ALIASES)
    assert idx.by_alias_normalized.get("daonemall"), "别名索引不该是空的"
    owners = idx.by_alias_normalized["daonemall"]
    assert [o.shop_account_id for o in owners] == ["tiktok_sg_daone_mall_local"]

    # 字符串账号编码也认(防御: 某些调用方可能按编码传别名)
    idx2 = build_identity_index(
        ACCOUNTS,
        [
            {
                "shop_account_id": "tiktok_sg_daone_mall_local",
                "alias_value": "DAONE Mall",
                "alias_normalized": "daonemall",
                "is_active": True,
            }
        ],
    )
    assert idx2.by_alias_normalized.get("daonemall")


def test_inactive_account_is_not_a_candidate(index):
    """停用店不进候选池 —— 与语义层候选池口径一致。"""
    row = {"shop_id": "9999999", "store_name": "off.shop"}
    result = reconcile_identity(
        index, platform_code="shopee", signals=collect_row_signals(row)
    )
    assert result.status == STATUS_UNRESOLVED
    assert result.identity is None


# ---------------------------------------------------------------------------
# ② 歧义不猜
# ---------------------------------------------------------------------------


def test_ambiguous_signal_is_skipped_not_guessed():
    """一串值被两个账号认领 ⇒ 该信号**不可用**, 换下一个信号。"""
    accounts = [
        dict(SHOPEE_SG, platform_shop_id="1308200825"),
        dict(SHOPEE_PH, platform_shop_id="1308200825"),  # 编号撞车
    ]
    idx = build_identity_index(accounts, [])
    row = {
        "shop_id": "1308200825",  # 歧义信号
        "shop_account_id": "shopee_sg_xhkj11_local",  # 唯一命中
    }
    result = reconcile_identity(
        idx, platform_code="shopee", signals=collect_row_signals(row)
    )
    assert result.status == STATUS_CONVERGED
    assert result.identity.shop_account_id == "shopee_sg_xhkj11_local"
    assert "shop_id" in result.ambiguous_signals


def test_ambiguous_account_id_is_skipped_and_next_signal_used():
    """账号章被**两个**账号认领 ⇒ 该信号**不可用**, 换下一个信号(编号)。"""
    accounts = [
        dict(SHOPEE_SG),
        # 同一个账号编码被重复登记 ⇒ 账号章这一路成了歧义
        dict(
            SHOPEE_SG, id=111, platform_shop_id="1308200826", store_name="xhkj11.sg#2"
        ),
    ]
    idx = build_identity_index(accounts, [])
    row = {
        "shop_account_id": "shopee_sg_xhkj11_local",  # 歧义信号
        "shop_id": "1308200825",  # 唯一命中
    }
    result = reconcile_identity(
        idx, platform_code="shopee", signals=collect_row_signals(row)
    )
    assert result.status == STATUS_CONVERGED
    assert result.identity.shop_account_id == "shopee_sg_xhkj11_local"
    assert "shop_account_id" in result.ambiguous_signals
    assert result.matched_signals == ("shop_id",)


def test_ambiguous_account_id_alone_leaves_row_untouched():
    """只有账号章这一路、且它歧义 ⇒ 所有信号都不可用 ⇒ **不收敛**(conflict)。"""
    accounts = [
        dict(SHOPEE_SG),
        dict(
            SHOPEE_SG, id=111, platform_shop_id="1308200826", store_name="xhkj11.sg#2"
        ),
    ]
    idx = build_identity_index(accounts, [])
    row = {"shop_account_id": "shopee_sg_xhkj11_local", "访客数": "807"}
    result = reconcile_identity(
        idx, platform_code="shopee", signals=collect_row_signals(row)
    )
    assert result.status == STATUS_CONFLICT
    assert result.identity is None
    assert apply_reconciliation(row, result) == row


def test_all_signals_ambiguous_leaves_row_untouched():
    """所有信号都歧义 ⇒ **不收敛**(保持原样), 绝不挑一个。"""
    accounts = [
        dict(SHOPEE_SG, platform_shop_id="1308200825"),
        dict(SHOPEE_PH, platform_shop_id="1308200825"),
    ]
    idx = build_identity_index(accounts, [])
    row = {"shop_id": "1308200825", "访客数": "807"}
    result = reconcile_identity(
        idx, platform_code="shopee", signals=collect_row_signals(row)
    )
    assert result.status == STATUS_CONFLICT
    assert result.identity is None
    assert apply_reconciliation(row, result) == row


def test_unresolvable_row_is_left_alone(index):
    """一个都命中不了 ⇒ unresolved, 原样返回。"""
    row = {"shop_id": "unknown", "store_name": "xihong"}
    result = reconcile_identity(
        index, platform_code="shopee", signals=collect_row_signals(row)
    )
    assert result.status == STATUS_UNRESOLVED
    assert apply_reconciliation(row, result) == row


# ---------------------------------------------------------------------------
# ③ 只改身份键
# ---------------------------------------------------------------------------


def test_apply_only_touches_identity_keys(index):
    """业务字段一个都不动。"""
    row = {
        "shop_id": "1419169771",
        "shop_account_id": "shopee_sg_xhkj11_local",
        "store_name": "xhkj11.sg",
        "访客数": "807",
        "页面浏览数": "1,234",
        "日期": "22/06/2026",
    }
    result = reconcile_identity(
        index, platform_code="shopee", signals=collect_row_signals(row)
    )
    updated = apply_reconciliation(row, result)
    # 账号章权威 ⇒ 归属 xhkj11.sg, 行内身份键一律改写成它的登记值
    assert result.identity.shop_account_id == "shopee_sg_xhkj11_local"
    assert updated["shop_id"] == "1308200825"
    assert updated["shop_account_id"] == "shopee_sg_xhkj11_local"
    assert updated["store_name"] == "xhkj11.sg"
    for key in ("访客数", "页面浏览数", "日期"):
        assert updated[key] == row[key]
    # 原行不被就地修改
    assert row["shop_account_id"] == "shopee_sg_xhkj11_local"
    assert row["shop_id"] == "1419169771"


def test_apply_rewrites_chinese_identity_keys(index):
    """中文身份键也要一起改 —— 语义层的 store_label_raw 会读到它们。"""
    row = {
        "shop_id": "1308200825",
        "店铺": "xhkj11.sg",
        "平台店铺ID": "1308200825",
        "账号ID": "shopee_sg_xhkj11_local",
        "访客数": "807",
    }
    result = reconcile_identity(
        index, platform_code="shopee", signals=collect_row_signals(row)
    )
    updated = apply_reconciliation(row, result)
    assert updated["店铺"] == "xhkj11.sg"
    assert updated["平台店铺ID"] == "1308200825"
    assert updated["账号ID"] == "shopee_sg_xhkj11_local"
    assert updated["访客数"] == "807"


def test_tiktok_keeps_shop_id_to_protect_upsert_key(index):
    """TikTok 没有平台编号 ⇒ ``shop_id`` **保持原值**。

    ⚠️ 改了它, 文件级 upsert 冲突键
    ``(platform_code, shop_id, data_domain, granularity, data_hash)`` 就变了
    ⇒ 将来重采同一份文件会**插入重复行**而不是覆盖。
    """
    row = {"shop_id": "DAONE Mall", "store_name": "", "shop_account_id": ""}
    result = reconcile_identity(
        index, platform_code="tiktok", signals=collect_row_signals(row)
    )
    updated = apply_reconciliation(row, result)
    assert updated["shop_id"] == "DAONE Mall"
    # 但行内必须补上权威锚点
    assert updated["shop_account_id"] == "tiktok_sg_daone_mall_local"
    assert updated["store_name"] == "FIORO SG"
    assert converged_shop_id_value(result.identity, fallback="DAONE Mall") == (
        "DAONE Mall"
    )


def test_converged_row_matches_migrated_row_shape(index):
    """收敛后的 raw_data 形态必须与历史订正迁移(20261117)写回的形态**同构**。

    迁移写回的是 4 个身份键: ``shop_id`` / ``shop_account_id`` / ``store_name`` /
    ``platform_shop_id``; 收敛必须产出同一组键 ⇒ 新采的行与订正过的历史行
    在语义层看来完全一样(否则重采会覆盖不干净)。

    ⚠️ 键的**形态**相同, 但归属方向已改: 现在按**账号章**归属
    (与 SSOT / 语义层一致), 迁移当年是按**编号**归属。
    """
    row = {
        "shop_id": "1419169771",
        "shop_account_id": "shopee_sg_xhkj11_local",
        "store_name": "xhkj11.sg",
        "访客数": "807",
    }
    result = reconcile_identity(
        index, platform_code="shopee", signals=collect_row_signals(row)
    )
    updated = apply_reconciliation(row, result)
    for key in ("shop_id", "shop_account_id", "store_name", "platform_shop_id"):
        assert key in updated, "收敛后必须带 %s 键" % key
    assert updated["platform_shop_id"] == "1308200825"
    assert updated["shop_account_id"] == "shopee_sg_xhkj11_local"
    assert updated["store_name"] == "xhkj11.sg"


def test_tiktok_converged_row_has_no_platform_shop_id(index):
    """TikTok 主数据没登记编号 ⇒ 收敛**不得**凭空造一个 ``platform_shop_id``。"""
    row = {"shop_id": "DAONE Mall", "store_name": "", "shop_account_id": ""}
    result = reconcile_identity(
        index, platform_code="tiktok", signals=collect_row_signals(row)
    )
    updated = apply_reconciliation(row, result)
    assert "platform_shop_id" not in updated


def test_converged_shop_id_prefers_platform_number(index):
    """有平台编号 ⇒ ``shop_id`` 取主数据登记的编号。"""
    row = {"shop_id": "1419169771"}
    result = reconcile_identity(
        index, platform_code="shopee", signals=collect_row_signals(row)
    )
    assert converged_shop_id_value(result.identity) == "1419169771"


# ---------------------------------------------------------------------------
# ④ 归一化口径与语义层 SQL 一致
# ---------------------------------------------------------------------------

#: 语义层 ``shop_identity_resolution_candidates`` 里的归一化规则:
#: 剥平台前缀 → 小写 → 删 ``[\s_()/-]+``
_SQL_STRIP_PREFIX = re.compile(
    r"^(shopee|tiktok\s*shop|tiktok|tk|miaoshou|amazon|lazada)\s*", re.IGNORECASE
)
_SQL_DROP_SEP = re.compile(r"[\s_()/-]+")


def _sql_normalize(value: str) -> str:
    text = _SQL_STRIP_PREFIX.sub("", str(value or "").strip())
    return _SQL_DROP_SEP.sub("", text.lower())


@pytest.mark.parametrize(
    "probe",
    [
        "DAONE Mall",
        "Malaysia(Flora Mall)",
        "Singapore(HX Home)",
        "Tiktok Shop DAONE Mall",
        "xhkj11.sg",
        "XHKJ11_SG",
        "shopee xhkj11.sg",
    ],
)
def test_alias_normalization_matches_semantic_sql(probe):
    """归一化唯一真源与语义层 SQL 规则必须一致(否则两边认不到同一家)。"""
    assert normalize_alias_key(probe) == _sql_normalize(probe)


# ---------------------------------------------------------------------------
# ⑤ 收敛之后的行内身份复核(兜底)
# ---------------------------------------------------------------------------


def test_consistency_check_passes_on_converged_rows():
    """收敛后的行: 行内编号 == 主数据登记编号 ⇒ 0 不一致。"""
    rows = [
        {
            "shop_id": "1308200825",
            "shop_account_id": "shopee_sg_xhkj11_local",
            "访客数": "807",
        }
    ]
    report = evaluate_row_identity_consistency(
        rows, {"shopee_sg_xhkj11_local": "1308200825"}
    )
    assert report.checked_rows == 1
    assert report.inconsistent_rows == 0
    assert report.samples == ()


def test_consistency_check_flags_number_mismatch():
    """收敛没生效(被关掉/索引加载失败)时, 这里要能把矛盾行揪出来。"""
    rows = [
        {
            "shop_id": "1419169771",  # 别的店的编号
            "shop_account_id": "shopee_sg_xhkj11_local",
        }
    ]
    report = evaluate_row_identity_consistency(
        rows, {"shopee_sg_xhkj11_local": "1308200825"}
    )
    assert report.checked_rows == 1
    assert report.inconsistent_rows == 1
    assert report.samples[0]["master_platform_shop_id"] == "1308200825"


def test_consistency_check_skips_accounts_without_registered_number():
    """主数据**没登记编号**的账号(TikTok)没有基准 ⇒ 跳过, 不得误报。"""
    rows = [{"shop_id": "DAONE Mall", "shop_account_id": "tiktok_sg_daone_mall_local"}]
    report = evaluate_row_identity_consistency(
        rows, {"shopee_sg_xhkj11_local": "1308200825"}
    )
    assert report.checked_rows == 0
    assert report.inconsistent_rows == 0


def test_consistency_check_skips_rows_without_number():
    """行内没有编号 ⇒ 无从判矛盾。"""
    rows = [{"shop_id": "", "shop_account_id": "shopee_sg_xhkj11_local"}]
    report = evaluate_row_identity_consistency(
        rows, {"shopee_sg_xhkj11_local": "1308200825"}
    )
    assert report.checked_rows == 0
    assert report.inconsistent_rows == 0
