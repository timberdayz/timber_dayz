"""《店铺身份唯一台账声明》的守护测试(SSOT-1)。

这一批改的是**声明**, 不是行为
------------------------------
仓库里「哪个身份信号最可信」曾经写在**三个地方**:

1. ``modules/core/fact_identity_columns.py`` 的散文;
2. Python 侧 ``backend/services/shop_identity_reconciliation_service.py``
   的 ``SIGNAL_PRIORITY`` 常量;
3. 两份 SQL 资产(候选池正本 + 物化副本)里的 ``resolution_priority`` 数字。

三处各自成立 ⇒ 下次照样打架(2026-11 的入库收敛就曾与 SSOT 结论**相反**,
把每一批新数据焊上错误的账号归属)。

⇒ 本轮把优先级收成**一处定义**
(``modules/core/shop_identity_ssot.py::IDENTITY_SIGNAL_PRIORITY``),
代码与 SQL 引用它, 并由本文件守护**三者不漂移**。

本文件盯住四件事
----------------
1. **声明 == 两份 SQL 资产** —— 改了 SQL 不改声明 ⇒ 必须红;
2. **Python 侧引用同一个来源** —— ``SIGNAL_PRIORITY`` 不是副本, 就是那一个元组;
3. **分层常量指向台账** —— 台账层必须就是 ``core.shop_accounts`` +
   ``core.shop_account_aliases``;
4. **方向守卫(行为)** —— 行内 ``platform_shop_id`` 指向**别的账号**、
   行内 ``shop_account_id`` 正确时, 收敛结果必须取**账号章**那个账号。

⚠️ 本文件**只读** SQL 资产与数据库, 不改任何口径、不改任何资产。
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.services.shop_identity_reconciliation_service import (
    SIGNAL_PRIORITY,
    apply_reconciliation,
    build_identity_index,
    collect_row_signals,
    reconcile_identity,
)
from modules.core.shop_identity_ssot import (
    CANONICAL_SHOP_KEY_EXPRESSION,
    CANDIDATE_POOL_MATERIALIZED_VIEW,
    CANDIDATE_POOL_VIEW,
    DISPLAY_NAME_MAPPING_TABLE,
    FACT_TABLE_PATTERN,
    IDENTITY_LAYERS,
    IDENTITY_SIGNAL_PRIORITY,
    LAYER_DERIVED,
    LAYER_LEDGER,
    LAYER_MAPPING,
    LAYER_SNAPSHOT,
    RESOLUTION_METHOD_PRIORITY,
    SHOP_ACCOUNT_TABLE,
    SHOP_ALIAS_TABLE,
    SIGNAL_RESOLUTION_METHOD,
)


REPO_ROOT = Path(__file__).resolve().parents[2]

RECONCILIATION_SERVICE_PATH = (
    REPO_ROOT / "backend" / "services" / "shop_identity_reconciliation_service.py"
)
FACT_IDENTITY_COLUMNS_PATH = REPO_ROOT / "modules" / "core" / "fact_identity_columns.py"

CANDIDATE_POOL_ASSETS = (
    REPO_ROOT / "sql" / "semantic" / "shop_identity_resolution_candidates.sql",
    REPO_ROOT / "sql" / "semantic" / "shop_identity_resolution_candidates_v2_mv.sql",
)

#: 候选池资产里「候选方法 + 优先级数字」的写法。
_RESOLUTION_PAIR_PATTERN = re.compile(
    r"'([a-z_]+)'::varchar AS resolution_method,\s*(\d+) AS resolution_priority"
)

#: 语义层「规范店铺键」的派生写法(平台编号优先 —— 已知例外, 见 SSOT 模块)。
_CANONICAL_KEY_PATTERN = re.compile(
    r"COALESCE\(\s*"
    r"NULLIF\(TRIM\(COALESCE\(sa\.platform_shop_id,\s*''\)\),\s*''\),\s*"
    r"NULLIF\(TRIM\(COALESCE\(sa\.shop_account_id,\s*''\)\),\s*''\),\s*"
    r"sa\.id::text\s*\)\s*AS resolved_shop_id",
    re.IGNORECASE,
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_resolution_priority(asset_text: str) -> dict[str, int]:
    """从候选池资产正文解析出 ``resolution_method`` → ``resolution_priority``。"""
    return {
        method: int(priority)
        for method, priority in _RESOLUTION_PAIR_PATTERN.findall(asset_text)
    }


# ---------------------------------------------------------------------------
# ① 声明 == 两份 SQL 资产
# ---------------------------------------------------------------------------


def test_declaration_matches_candidate_pool_assets() -> None:
    """SSOT 声明的优先级必须**逐条等于**两份 SQL 资产里的 ``resolution_priority``。

    改了 SQL 不改声明 ⇒ 这里变红。
    """
    expected = dict(RESOLUTION_METHOD_PRIORITY)
    for asset in CANDIDATE_POOL_ASSETS:
        parsed = _parse_resolution_priority(_read(asset))
        assert parsed == expected, f"{asset.name} 的优先级与 SSOT 声明不一致"


def test_declaration_covers_exactly_the_four_signals() -> None:
    """声明的优先级必须恰好覆盖四路信号, 且与 SQL 侧方法一一对应。"""
    assert len(IDENTITY_SIGNAL_PRIORITY) == 4
    assert set(SIGNAL_RESOLUTION_METHOD) == set(IDENTITY_SIGNAL_PRIORITY)
    assert set(RESOLUTION_METHOD_PRIORITY) == set(SIGNAL_RESOLUTION_METHOD.values())


def test_signal_order_matches_sql_priority_order() -> None:
    """Python 侧四路信号的顺序必须等于 SQL 侧四路候选方法的优先级顺序。

    两边的**名字**不同(``store_name`` vs ``store_name_match``、``shop_id`` vs
    ``alias_match``), **顺序**才是口径。
    """
    sql_order = tuple(
        sorted(RESOLUTION_METHOD_PRIORITY, key=RESOLUTION_METHOD_PRIORITY.get)
    )
    declared_order = tuple(
        SIGNAL_RESOLUTION_METHOD[signal] for signal in IDENTITY_SIGNAL_PRIORITY
    )
    assert declared_order == sql_order


def test_account_id_is_the_most_authoritative_signal() -> None:
    """方向守卫: 账号章必须是第一路(2026-11 的 bug 正是它被排到了第三)。"""
    assert IDENTITY_SIGNAL_PRIORITY[0] == "shop_account_id"
    assert RESOLUTION_METHOD_PRIORITY["shop_account_id"] == 1


# ---------------------------------------------------------------------------
# ② Python 侧引用同一个来源
# ---------------------------------------------------------------------------


def test_python_signal_priority_is_the_declaration_itself() -> None:
    """``SIGNAL_PRIORITY`` 必须**就是** SSOT 那个元组, 不是抄一份。"""
    assert SIGNAL_PRIORITY is IDENTITY_SIGNAL_PRIORITY


def test_reconciliation_service_does_not_redeclare_priority() -> None:
    """收敛服务里不许再出现「自己写一份优先级」的元组字面量。"""
    body = _read(RECONCILIATION_SERVICE_PATH)
    assert "SIGNAL_PRIORITY = (" not in body
    assert "from modules.core.shop_identity_ssot import" in body


def test_fact_identity_columns_no_longer_keeps_its_own_priority_prose() -> None:
    """事实表列的定性文件不再保留第二份优先级散文, 只留指针。"""
    body = _read(FACT_IDENTITY_COLUMNS_PATH)
    assert "shop_identity_ssot" in body
    assert "最可靠的一路" not in body


# ---------------------------------------------------------------------------
# ③ 分层常量指向台账
# ---------------------------------------------------------------------------


def test_ledger_layer_points_at_the_two_master_tables() -> None:
    """台账层必须就是账号本体 + 别名这两张表。"""
    assert SHOP_ACCOUNT_TABLE == "core.shop_accounts"
    assert SHOP_ALIAS_TABLE == "core.shop_account_aliases"
    ledger = [layer for layer in IDENTITY_LAYERS if layer.name == LAYER_LEDGER]
    assert len(ledger) == 1
    assert ledger[0].objects == (SHOP_ACCOUNT_TABLE, SHOP_ALIAS_TABLE)


def test_all_four_layers_are_declared_and_only_ledger_is_the_truth() -> None:
    """四层齐全, 且**只有台账层**自称真源。"""
    assert [layer.name for layer in IDENTITY_LAYERS] == [
        LAYER_LEDGER,
        LAYER_DERIVED,
        LAYER_SNAPSHOT,
        LAYER_MAPPING,
    ]
    truths = [layer.name for layer in IDENTITY_LAYERS if "唯一真源" in layer.authority]
    assert truths == [LAYER_LEDGER]


def test_derived_layer_objects_match_the_candidate_pool_assets() -> None:
    """派生层指向候选池正本与副本; 快照层指向事实表族; 映射层指向显示名映射表。"""
    derived = [layer for layer in IDENTITY_LAYERS if layer.name == LAYER_DERIVED]
    snapshot = [layer for layer in IDENTITY_LAYERS if layer.name == LAYER_SNAPSHOT]
    mapping = [layer for layer in IDENTITY_LAYERS if layer.name == LAYER_MAPPING]
    assert derived[0].objects == (CANDIDATE_POOL_VIEW, CANDIDATE_POOL_MATERIALIZED_VIEW)
    assert snapshot[0].objects == (FACT_TABLE_PATTERN,)
    assert mapping[0].objects == (DISPLAY_NAME_MAPPING_TABLE,)


def test_candidate_pool_assets_derive_from_the_ledger() -> None:
    """候选池必须**从台账算出来** —— 两份资产都要引用台账两张表。"""
    for asset in CANDIDATE_POOL_ASSETS:
        body = _read(asset)
        assert SHOP_ACCOUNT_TABLE in body
        assert SHOP_ALIAS_TABLE in body


def test_known_exception_canonical_key_is_declared_and_untouched() -> None:
    """输出键(规范店铺键)仍是平台编号优先 —— 已知例外, 本轮不动。

    这条断言把「例外」钉成**现状**: 将来解除它时, 必须先改这份声明
    (并同步解耦看板显示名映射表的键依赖), 而不是悄悄改 SQL。
    """
    assert CANONICAL_SHOP_KEY_EXPRESSION == (
        "COALESCE(platform_shop_id, shop_account_id, id)"
    )
    body = _read(CANDIDATE_POOL_ASSETS[0])
    assert _CANONICAL_KEY_PATTERN.search(body), "规范店铺键的派生写法与声明不一致"


# ---------------------------------------------------------------------------
# ④ 方向守卫(行为)—— 账号章优先
# ---------------------------------------------------------------------------

#: 在营 Shopee 店 A(编号 / 店名唯一)。
SHOP_A = {
    "id": 11,
    "shop_account_id": "shopee_sg_xhkj11_local",
    "platform": "shopee",
    "platform_shop_id": "1308200825",
    "store_name": "xhkj11.sg",
    "shop_region": "SG",
    "enabled": True,
    "business_role": "operating_store",
}
#: 在营 Shopee 店 B。
SHOP_B = {
    "id": 12,
    "shop_account_id": "shopee_ph_xhkj11_local",
    "platform": "shopee",
    "platform_shop_id": "1419169771",
    "store_name": "xhkj11.ph",
    "shop_region": "PH",
    "enabled": True,
    "business_role": "operating_store",
}


def test_convergence_takes_the_account_stamp_not_the_foreign_number() -> None:
    """行内编号指向**别的账号**、账号章正确 ⇒ 收敛到**账号章**那个账号。

    这是「认人优先级方向」的核心守卫: 方向反了 ⇒ 每一批新数据都会被焊上
    错误的账号归属, 且行内四路身份被改写成一致的错误值 ⇒ 看板零告警 ⇒
    推到云端后落 ``unknown``。
    """
    index = build_identity_index([SHOP_A, SHOP_B], [])
    row = {
        "platform_shop_id": "1419169771",  # 店 B 的编号(别的账号)
        "shop_account_id": "shopee_sg_xhkj11_local",  # 账号章 —— 正确的账号
        "store_name": "xhkj11.sg",
    }
    result = reconcile_identity(
        index, platform_code="shopee", signals=collect_row_signals(row)
    )
    assert result.identity is not None
    assert result.identity.shop_account_id == "shopee_sg_xhkj11_local"
    assert "platform_shop_id" in result.conflict_signals

    updated = apply_reconciliation(row, result)
    assert updated["shop_account_id"] == "shopee_sg_xhkj11_local"
    assert updated["platform_shop_id"] == "1308200825"


def test_declaration_order_is_what_the_service_actually_applies() -> None:
    """服务实际使用的顺序必须就是声明的顺序(防止声明与实现再次分家)。"""
    assert SIGNAL_PRIORITY == IDENTITY_SIGNAL_PRIORITY
    assert SIGNAL_PRIORITY[0] == "shop_account_id"
