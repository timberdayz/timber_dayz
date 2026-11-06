"""入库身份门禁 (P2-1): 缺 ``shop_account_id`` 就不许入库。

为什么要有这道门
----------------
``shop_account_id`` 是唯一正确的店铺锚点 —— 改名不变、跨平台一致、采集器写不坏。
``platform_shop_id`` 会被采集器污染(把 URL 里读到的编号当成主数据),
店名/别名只能兜底; 一旦落到兜底, 就可能张冠李戴。

入库链路以前是「能带就带」: ``catalog_files.shop_account_id`` 为空时照样把文件入库,
只是行上没有稳定身份戳, 语义层只能靠店名/别名反查归属。
实测这正是 2026-06-09 那批 analytics(73 个文件 / 2195 行)落进 ``unknown`` 的成因
(那 73 个文件**全都**有 ``shop_id``, 说明它确实是店铺数据, 只是缺稳定身份)。

所以把规则改成**入库前拦截**:

* 店铺数据文件缺 ``shop_account_id`` ⇒ **拒收**, 落 ``needs_shop`` 终态等人工补身份;
* 行内自带 ``shop_account_id`` 且与文件级不一致 ⇒ **拒收**(同一个文件混了两个账号)。

贯穿全案的原则: **歧义宁可落 ``unknown`` 报警, 绝不静默猜一个**。
门禁把「猜」提前到入库那一刻暴露出来, 而不是等看板数字对不上时才发现。

为什么不是「入库后打质量分」
----------------------------
质量分是**事后**指标: 数据已经进了 b_class, 已经进了物化视图, 已经进了看板。
本门禁是**事前**闸门, 目标是不让「归属不上」的数据落库。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

# ── 门禁结论 ────────────────────────────────────────────────────────

#: 文件级缺稳定身份戳
SHOP_IDENTITY_GATE_SKIP_REASON_MISSING = "missing_shop_account_id"
#: 行内自带身份戳且与文件级不一致
SHOP_IDENTITY_GATE_SKIP_REASON_CONFLICT = "shop_account_id_conflict"

#: 参与语义层身份解析的数据域 —— 这些域的数据**必须**带稳定身份戳。
#:
#: 取值依据: 语义层的身份解析(``sql/semantic/analytics_atomic.sql`` /
#: ``orders_atomic.sql``)只消费这些域的事实表; 其余域(如 ``services``)
#: 的数据不参与店铺归属解析, 不该被这道门禁挡住。
SHOP_IDENTITY_GATED_DOMAINS = frozenset(
    {
        "analytics",
        "orders",
        "products",
        "inventory",
    }
)

#: 视为「没有店铺身份」的占位值 —— 采集器在拿不到店铺时写的占位符。
_EMPTY_IDENTITY_PLACEHOLDERS = frozenset({"", "none", "null", "unknown", "n/a"})


@dataclass(frozen=True)
class ShopIdentityGateDecision:
    """门禁判定结论。"""

    allowed: bool
    #: 拒收原因码(放行时为 None); 与 ``ingest_data`` 返回体的 ``skip_reason`` 对齐
    skip_reason: Optional[str] = None
    #: 面向人的说明(直接写进 ``catalog_files.error_message``)
    message: str = ""
    #: 行级冲突时, 行内自称的账号
    conflicting_shop_account_id: Optional[str] = None
    #: 门禁判定依据(留痕用)
    detail: Optional[Dict[str, Any]] = None

    def as_result_fields(self) -> Dict[str, Any]:
        """转成入库结果体里要带的字段。"""
        return {
            "identity_blocked": not self.allowed,
            "skip_reason": self.skip_reason,
            "message": self.message,
        }


def _normalize_identity(value: Any) -> Optional[str]:
    """把身份字段规范化成字符串; 空/占位符返回 None。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in _EMPTY_IDENTITY_PLACEHOLDERS:
        return None
    return text


def _resolve_file_identity_signals(file_record: Any) -> Dict[str, Optional[str]]:
    """取文件级的四个身份字段, 并规范化。"""
    return {
        "shop_account_id": _normalize_identity(
            getattr(file_record, "shop_account_id", None)
        ),
        "platform_shop_id": _normalize_identity(
            getattr(file_record, "platform_shop_id", None)
        ),
        "shop_id": _normalize_identity(getattr(file_record, "shop_id", None)),
        "store_name": _normalize_identity(getattr(file_record, "store_name", None)),
    }


def is_shop_scoped_file(
    *,
    domain: Optional[str],
    signals: Mapping[str, Optional[str]],
) -> bool:
    """判断这份文件是不是「店铺数据」(= 应该有稳定身份戳)。

    两个条件取**并集**, 任何一个成立就算店铺数据:

    1. **数据域在门禁清单里** —— 语义层会用它的数据做店铺归属;
    2. **文件自己带了任一店铺身份信号**(平台店铺编号 / 店铺ID / 店名) ——
       说明采集时知道这是哪家店, 只是没给出稳定账号 ID。

    两者都不成立 ⇒ 这份文件根本不是店铺数据(例如纯系统级文件),
    不该被门禁挡住。
    """
    normalized_domain = _normalize_identity(domain)
    if normalized_domain and normalized_domain.lower() in SHOP_IDENTITY_GATED_DOMAINS:
        return True
    for key in ("platform_shop_id", "shop_id", "store_name"):
        if signals.get(key):
            return True
    return False


def evaluate_shop_identity_gate(
    *,
    file_record: Any,
    domain: Optional[str] = None,
    rows: Optional[Iterable[Mapping[str, Any]]] = None,
) -> ShopIdentityGateDecision:
    """入库前的身份门禁判定。

    Args:
        file_record: ``catalog_files`` 记录(会被读 ``shop_account_id`` 等身份字段)
        domain: 本次入库的数据域(用于判断是否参与店铺归属解析)
        rows: 本次要入库的**盖戳前**数据行(用于行级自洽校验)

    Returns:
        :class:`ShopIdentityGateDecision`
    """
    signals = _resolve_file_identity_signals(file_record)
    shop_account_id = signals.get("shop_account_id")

    if not is_shop_scoped_file(domain=domain, signals=signals):
        # 不是店铺数据 —— 放行。行上没有身份戳是正常的(语义层也不解析它)。
        return ShopIdentityGateDecision(
            allowed=True,
            detail={"scope": "not_shop_scoped", "domain": domain},
        )

    if not shop_account_id:
        # 文件级门禁: 店铺数据却没有稳定身份戳 ⇒ 拒收。
        missing = [
            key
            for key in ("platform_shop_id", "shop_id", "store_name")
            if signals.get(key)
        ]
        return ShopIdentityGateDecision(
            allowed=False,
            skip_reason=SHOP_IDENTITY_GATE_SKIP_REASON_MISSING,
            message=(
                "店铺数据缺少稳定身份编号(shop_account_id), 已拒绝入库: "
                f"已知的店铺线索={missing or ['(无)']}。"
                "请先在店铺账号管理里确认该文件的账号归属, 再重新触发入库。"
            ),
            detail={
                "scope": "file_level",
                "domain": domain,
                "known_signals": missing,
            },
        )

    # 行级自洽校验: 行内自带身份戳时, 必须与文件级一致。
    # (盖戳只填空的, 不覆盖行内已有的值 —— 所以不一致会一直带进 b_class)
    conflicting: Optional[str] = None
    for row in rows or []:
        row_account_id = _normalize_identity(
            row.get("shop_account_id") if hasattr(row, "get") else None
        )
        if row_account_id and row_account_id != shop_account_id:
            conflicting = row_account_id
            break

    if conflicting:
        return ShopIdentityGateDecision(
            allowed=False,
            skip_reason=SHOP_IDENTITY_GATE_SKIP_REASON_CONFLICT,
            message=(
                "文件级店铺账号与行内店铺账号不一致, 已拒绝入库: "
                f"文件级={shop_account_id}, 行内={conflicting}。"
                "同一份文件不应混有两个店铺账号, 请核对导出内容后重试。"
            ),
            conflicting_shop_account_id=conflicting,
            detail={
                "scope": "row_level",
                "domain": domain,
                "file_shop_account_id": shop_account_id,
                "row_shop_account_id": conflicting,
            },
        )

    return ShopIdentityGateDecision(
        allowed=True,
        detail={
            "scope": "file_level",
            "domain": domain,
            "shop_account_id": shop_account_id,
        },
    )


def summarize_identity_signal(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """统计行内自带身份戳的分布(诊断用, 供测试与日志)。"""
    stamped = 0
    values = set()
    for row in rows or []:
        value = _normalize_identity(
            row.get("shop_account_id") if hasattr(row, "get") else None
        )
        if value:
            stamped += 1
            values.add(value)
    return {
        "rows": len(rows or []),
        "stamped_rows": stamped,
        "distinct_shop_account_ids": sorted(values),
    }


# ── 行内身份自洽性复核(收敛之后的最后一道防线) ──────────────────────────


@dataclass(frozen=True)
class RowIdentityConsistencyReport:
    """行内身份自洽性复核结果。

    为什么需要它
    ------------
    :func:`evaluate_shop_identity_gate` 管的是「**有没有**稳定身份戳」, 它在**盖戳之前**跑,
    所以只比 ``shop_account_id`` —— 本次事故的行里「编号错、标签对」,
    两边账号 ID 一致 ⇒ 门禁放行 ⇒ 矛盾带进了 b_class。

    行内身份收敛(``shop_identity_reconciliation_service``)把矛盾**修好**,
    但它可能被关掉(``SHOP_IDENTITY_RECONCILIATION_ENABLED=0``)或因主数据索引加载失败而跳过。
    本复核就是那道兜底: **收敛之后**再核一次「行内编号 == 主数据登记编号」。

    ⚠️ 本复核**只报告、不拒收** —— 拒收会让「主数据没登记编号的平台」(如 TikTok)
    或「采集器故意用别的编号」的数据整批落 ``needs_shop``, 风险远大于收益。
    它把不一致行数写进日志与入库返回值, 由看板的 ``platform_shop_id_conflict`` 告警承接。
    """

    checked_rows: int
    inconsistent_rows: int
    samples: tuple[Dict[str, Any], ...] = ()


def evaluate_row_identity_consistency(
    rows: Sequence[Mapping[str, Any]],
    account_numbers: Mapping[str, str],
) -> RowIdentityConsistencyReport:
    """复核行内身份与主数据登记编号是否一致。

    Args:
        rows: 事实行(``raw_data`` 形态的 dict)。
        account_numbers: ``{shop_account_id: platform_shop_id}`` ——
            只应包含**主数据登记了平台编号**的账号; 没有编号就没有可比对的基准, 直接跳过。

    Returns:
        :class:`RowIdentityConsistencyReport`。
    """
    checked = 0
    inconsistent = 0
    samples: list[Dict[str, Any]] = []

    for row in rows or []:
        getter = getattr(row, "get", None)
        if getter is None:
            continue
        shop_account_id = _normalize_identity(getter("shop_account_id"))
        if not shop_account_id:
            continue
        expected = account_numbers.get(shop_account_id)
        if not expected:
            # 主数据没登记平台编号(如 TikTok) ⇒ 没有基准可比
            continue
        row_number = _normalize_identity(getter("shop_id"))
        if not row_number:
            # 行内没编号 ⇒ 无从判矛盾
            continue
        checked += 1
        if row_number == expected:
            continue
        inconsistent += 1
        if len(samples) < 5:
            samples.append(
                {
                    "shop_account_id": shop_account_id,
                    "row_shop_id": row_number,
                    "master_platform_shop_id": expected,
                }
            )

    return RowIdentityConsistencyReport(
        checked_rows=checked,
        inconsistent_rows=inconsistent,
        samples=tuple(samples),
    )
