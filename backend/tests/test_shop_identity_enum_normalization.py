"""枚举归一化(SSOT)的守护测试 —— 防止 2026-11-07 采集同步丢数事故复发。

事故回顾
--------
2026-11-07 上线的 ``shop_identity_reconciliation_service`` 里, ``business_role``
这个 SAEnum 列用 ``str(value)`` 读取, 得到的是
``'ShopAccountBusinessRole.operating_store'``, 与字面量 ``'operating_store'``
**永不相等**。

⇒ ``MasterIdentity.is_operating_store`` 恒为 ``False``
⇒ ``build_identity_index`` 把**全部**账号过滤掉, 反查索引恒为空
⇒ 行内身份收敛 **100% 静默失效**(不报错、不告警)
⇒ 同日上线的同步侧拦截器发现「事实表列 shop_id 与行内身份不同源」,
   把 3,714 行**正常数据**当成矛盾行全部丢弃,
   而账本记「completed」、检查点照常推进 ⇒ 永久丢数。

为什么需要这个文件
------------------
``test_shop_identity_reconciliation.py`` 的 444 行用例**全部**用手写 ``dict``
喂给 ``build_identity_index``, 其中 ``"business_role": "operating_store"``
是**普通字符串**, 天然绕过了 ORM 的枚举包装。

⇒ 那套用例**测的是纯逻辑**, 从未覆盖「从真实 ORM 行读出来」这条**生产路径**。
⇒ 本文件专门补上这个缺口。

关键设计
--------
用**真的 SAEnum 成员**(而不是字符串)构造索引输入, 断言:
1. 枚举成员与字面量比较时**必须相等**(归一化生效);
2. 用枚举成员构造索引 ⇒ 索引**非空**(生产路径可用);
3. 同一份账号数据, 枚举形态与字符串形态建出的索引**完全一致**;
4. ``modules.core.validators.normalize_enum_value`` 是唯一真相点,
   两个服务都从它取值(不再各写一份)。
"""

from __future__ import annotations

import enum

import pytest

from modules.core.validators import normalize_enum_value


# ---------------------------------------------------------------------------
# 用真的 SAEnum 复现生产形态
# ---------------------------------------------------------------------------


class _ShopAccountBusinessRole(str, enum.Enum):
    """与 ``modules/core/db/schema_parts/platform.py`` 同构的枚举。

    刻意**不在**这里 import 真实的 SAEnum —— 那会把 DB 会话带进单元测试。
    行为与真实枚举一致即可: ``str(member)`` 返回 ``'Cls.member'``。
    """

    operating_store = "operating_store"
    collection_source = "collection_source"


def _orm_row(
    shop_account_id: str,
    platform: str = "shopee",
    platform_shop_id: str = "",
    store_name: str = "demo.sg",
    shop_region: str = "SG",
    enabled: bool = True,
    business_role: object = _ShopAccountBusinessRole.operating_store,
) -> dict:
    """构造一条**枚举形态**的账号行(dict + 真实枚举成员)。

    用 dict 承载、但 ``business_role`` 放**真的枚举成员** ——
    这样既不碰数据库, 又能复现生产上 ORM 返回值的形态。
    """
    return {
        "id": 1,
        "shop_account_id": shop_account_id,
        "platform": platform,
        "platform_shop_id": platform_shop_id,
        "store_name": store_name,
        "shop_region": shop_region,
        "enabled": enabled,
        "business_role": business_role,
    }


# ---------------------------------------------------------------------------
# ① 归一化本身
# ---------------------------------------------------------------------------


def test_str_of_enum_member_is_not_the_bare_value():
    """守住事故的根因形态: ``str(枚举成员)`` **不等于**字面量。

    如果哪天 Python/SAEnum 的行为变了导致 ``str(member) == 'operating_store'``,
    这条用例会提醒我们重新评估 —— 但**不能**依赖它, 必须显式解包。
    """
    member = _ShopAccountBusinessRole.operating_store
    assert str(member) != "operating_store"
    assert str(member) == "_ShopAccountBusinessRole.operating_store"


def test_normalize_enum_value_unpacks_saenum_member():
    """枚举成员 → 裸值。"""
    assert (
        normalize_enum_value(_ShopAccountBusinessRole.operating_store)
        == "operating_store"
    )
    assert (
        normalize_enum_value(_ShopAccountBusinessRole.collection_source)
        == "collection_source"
    )


def test_normalize_enum_value_passes_through_plain_strings():
    """普通字符串原样返回(空值 → 空串)。"""
    assert normalize_enum_value("operating_store") == "operating_store"
    assert normalize_enum_value("") == ""
    assert normalize_enum_value(None) == ""
    assert normalize_enum_value("  operating_store  ") == "operating_store"


# ---------------------------------------------------------------------------
# ② 生产路径: 用枚举形态的账号建索引
# ---------------------------------------------------------------------------


def test_identity_index_is_not_empty_when_rows_carry_enum_members():
    """★ 核心守护: 枚举形态的账号行 ⇒ 索引**非空**。

    这正是事故现场: 索引为空 ⇒ 收敛恒失效 ⇒ 同步侧误杀 3,714 行。
    """
    from backend.services.shop_identity_reconciliation_service import (
        build_identity_index,
    )

    accounts = [
        _orm_row("shopee_sg_hx_home_local", platform_shop_id="1391124228"),
        _orm_row(
            "shopee_my_xhkj1_local", platform="shopee", platform_shop_id="1540271739"
        ),
        _orm_row(
            "tiktok_my_dawie_mall_local",
            platform="tiktok",
            platform_shop_id="",
            store_name="FIORO MY",
            shop_region="MY",
        ),
    ]

    index = build_identity_index(accounts, [])

    assert index.by_shop_account_id, "索引为空 ⇒ 收敛必然失效(事故根因)"
    assert len(index.by_shop_account_id) == 3
    assert index.by_platform_shop_id, "平台编号索引为空 ⇒ 编号兜底失效"
    assert len(index.by_platform_shop_id) == 2  # tiktok 无编号
    assert index.by_store_name, "店名索引为空 ⇒ 店名兜底失效"


def test_enum_rows_and_string_rows_build_identical_indexes():
    """枚举形态与字符串形态必须建出**完全一致**的索引。

    这条把「生产路径」与「既有测试路径」钉在一起 ——
    以后任何人改坏归一化, 都会在这里露出来。
    """
    from backend.services.shop_identity_reconciliation_service import (
        build_identity_index,
    )

    base = {
        "id": 1,
        "shop_account_id": "shopee_sg_hx_home_local",
        "platform": "shopee",
        "platform_shop_id": "1391124228",
        "store_name": "hx_home.sg",
        "shop_region": "SG",
        "enabled": True,
    }
    enum_rows = [{**base, "business_role": _ShopAccountBusinessRole.operating_store}]
    string_rows = [{**base, "business_role": "operating_store"}]

    enum_index = build_identity_index(enum_rows, [])
    string_index = build_identity_index(string_rows, [])

    assert set(enum_index.by_shop_account_id) == set(string_index.by_shop_account_id)
    assert set(enum_index.by_platform_shop_id) == set(string_index.by_platform_shop_id)
    assert set(enum_index.by_store_name) == set(string_index.by_store_name)


def test_disabled_or_non_operating_accounts_still_excluded():
    """归一化修复**不能**放宽候选池口径: 停用店 / 非经营店仍不进索引。"""
    from backend.services.shop_identity_reconciliation_service import (
        build_identity_index,
    )

    accounts = [
        _orm_row("shopee_sg_enabled_local"),
        _orm_row("shopee_sg_disabled_local", enabled=False),
        _orm_row(
            "shopee_sg_source_local",
            business_role=_ShopAccountBusinessRole.collection_source,
        ),
    ]

    index = build_identity_index(accounts, [])

    assert set(index.by_shop_account_id) == {"shopee_sg_enabled_local"}


# ---------------------------------------------------------------------------
# ③ 端到端: 枚举形态的行能被正确收敛
# ---------------------------------------------------------------------------


def test_row_with_enum_shaped_account_converges_to_correct_shop():
    """★ 端到端守护: 枚举形态的账号 ⇒ 收敛成功且归属正确。

    事故形态下这一步会 ``unresolved``, 于是同步侧把正常行判成矛盾丢弃。
    """
    from backend.services.shop_identity_reconciliation_service import (
        build_identity_index,
        collect_row_signals,
        reconcile_identity,
    )

    accounts = [
        _orm_row("shopee_sg_hx_home_local", platform_shop_id="1391124228"),
    ]
    index = build_identity_index(accounts, [])

    result = reconcile_identity(
        index,
        platform_code="shopee",
        signals=collect_row_signals(
            {
                "shop_account_id": "shopee_sg_hx_home_local",
                "store_name": "hx_home.sg",
            }
        ),
    )

    assert result.status == "converged"
    assert result.identity is not None
    assert result.identity.shop_account_id == "shopee_sg_hx_home_local"
    assert result.identity.platform_shop_id == "1391124228"


# ---------------------------------------------------------------------------
# ④ 单一真相点: 两个服务不得各写一份
# ---------------------------------------------------------------------------


def test_both_services_use_the_shared_single_source_of_truth():
    """两个店铺身份服务必须共用 ``normalize_enum_value``。

    事故的直接成因就是「同一个归一化逻辑写成两个版本, 其中一份漏了解包」。
    这条用例会挡住任何「又写一份」的回归。
    """
    from backend.services import (
        shop_account_identity_service,
        shop_identity_reconciliation_service,
    )

    assert (
        shop_account_identity_service._enum_value is not None
    ), "shop_account_identity_service._enum_value 应保留为薄封装"

    # 收敛服务不再自带实现 —— 必须走共用函数
    source = shop_identity_reconciliation_service.__file__
    with open(source, "r", encoding="utf-8") as handle:
        text = handle.read()

    assert "normalize_enum_value" in text, "收敛服务必须使用共用的归一化函数"
    # 旧的错误写法必须已经消失
    assert (
        'business_role=_identity_text(_get(row, "business_role"))' not in text
    ), "收敛服务仍在用 _identity_text 读枚举(事故根因写法)"


def test_enum_normalization_is_consistent_across_both_services():
    """两个服务对同一个枚举成员给出**相同**结果。"""
    from backend.services.shop_account_identity_service import _enum_value

    member = _ShopAccountBusinessRole.operating_store
    assert _enum_value(member) == normalize_enum_value(member)
    assert _enum_value(member) == "operating_store"
