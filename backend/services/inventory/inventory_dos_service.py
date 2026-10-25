"""DOS（可售天数）—— **唯一实现**，但**只作参考值**。

为什么只作参考
--------------
妙手「近 XX 天销量」是**行级存储快照**，只在那一行被写入时才刷新；
增量采集实测只覆盖约 13.6% 的 SKU，其余行的分母停在旧值。
→ DOS **不得**用作判定依据（滞销判据用距上次进货时长，见 inventory_restock_service）。

本模块仍然保留，因为运营需要一个量级感：「这批货按最近一次采集到的销量算，还能卖多少天」。

口径
----
    DOS = 可用库存 ÷ (窗口销量 ÷ 窗口天数)    单位：天

- 分子取**可用库存**（预占与次品卖不掉，不计入「还能卖多久」）
- 不可算一律返回 ``None`` + 独立状态标签，**绝不用 9999 之类的哨兵值**

本模块是**纯函数**：无 ORM、无 DB、无 I/O，可写无 DB 单测。
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional

# 状态用显式标签表达，不用数值哨兵
DOS_STATUS_COMPUTABLE = "computable"
DOS_STATUS_ZERO_SALES = "zero_sales"
DOS_STATUS_STOCKOUT = "stockout"
DOS_STATUS_NO_STOCK = "no_stock"

DEFAULT_WINDOW_DAYS = 90


def _to_decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def classify_dos_status(*, available_stock, window_sales) -> str:
    """DOS 的四态。缺料与「不可算」都归到明确状态，不静默回落。"""
    stock = _to_decimal(available_stock)
    sales = _to_decimal(window_sales)
    if sales is None:
        return (
            DOS_STATUS_NO_STOCK
            if stock is None or stock <= 0
            else DOS_STATUS_COMPUTABLE
        )
    if sales <= 0:
        return DOS_STATUS_ZERO_SALES
    if stock is None or stock <= 0:
        return DOS_STATUS_STOCKOUT
    return DOS_STATUS_COMPUTABLE


def compute_dos(
    *,
    available_stock,
    window_sales,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> Optional[Decimal]:
    """DOS = 可用库存 ÷ (窗口销量 ÷ 窗口天数)，单位：天。

    不可算一律返回 ``None`` —— **绝不用 9999 之类的哨兵**。

    - ``window_sales is None``：销量列不存在（非妙手域 / 该行取不到）→ 不可算
    - ``window_sales <= 0``：窗口内零销量 → 不是「算得出」，交给状态标签表达
    - ``available_stock <= 0``：没货 → 不是「算得出」
    """
    stock = _to_decimal(available_stock)
    sales = _to_decimal(window_sales)
    if stock is None or sales is None:
        return None
    if sales <= 0 or stock <= 0 or window_days <= 0:
        return None
    daily_sales = sales / Decimal(window_days)
    if daily_sales <= 0:
        return None
    return (stock / daily_sales).quantize(Decimal("0.1"))
