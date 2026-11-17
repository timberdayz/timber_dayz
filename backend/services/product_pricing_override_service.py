"""平台级「最低售价人工覆盖」的**写入路径**（阶段 2.1b）。

为什么要有这个模块
----------------

人工覆盖以前写在 ``core.dim_erp_sku.min_selling_price_override`` 上，有两个问题：

1. **口径错位**：底线是 **SKU × 平台** 的量（平台其他成本率 TikTok 27.27% vs
   Shopee 41.65%），而那一列是**公司级**的 —— 一个数套所有平台。
2. **会被同步抹掉**：``core.dim_erp_sku`` 参与「采集机 → 云端」同步，
   同步脚本对它做 ``TRUNCATE ... RESTART IDENTITY CASCADE``
   ⇒ 运营刚设的覆盖值每次同步都人间蒸发 ⇒ 护栏上限形同虚设。

所以覆盖值搬到了 ``finance.sku_platform_pricing``（不参与同步，且刻意不带外键）。
写入路径也从「SKU 主数据的通用 setattr」里摘出来，单独走这里 ——
**平台级的值不该挂在 SKU 主数据的保存流程上**。

读路径仍在 ``backend/services/product_pricing_query_service.py``
（``load_platform_pricing_overrides`` / ``resolve_pricing_override``），
本模块只负责写。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import SkuPlatformPricing


#: 人工覆盖的来源标记。
MANUAL_OVERRIDE_SOURCE = "manual_override"


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


async def get_platform_override(
    db: AsyncSession, sku_id: int, platform_code: str
) -> Optional[Decimal]:
    """取某 SKU 在某平台的人工覆盖值；没有则 None。"""
    row = (
        (
            await db.execute(
                select(SkuPlatformPricing).where(
                    SkuPlatformPricing.sku_id == sku_id,
                    SkuPlatformPricing.platform_code == platform_code,
                )
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        return None
    return _to_decimal(row.min_selling_price_override)


async def set_platform_override(
    db: AsyncSession,
    *,
    sku_id: int,
    platform_code: str,
    value: Any,
    user_id: Optional[int] = None,
) -> SkuPlatformPricing:
    """设置某 SKU 在某平台的最低售价人工覆盖。

    - 已有行 ⇒ 覆盖值 + 来源标记 + 操作人更新；
    - 没有行 ⇒ 新建一行。

    ⚠️ **覆盖值必须 > 0**：0 或负数不是「不设覆盖」，而是「把底线压到 0」，
    等于把护栏关掉。传 None 走 :func:`clear_platform_override`（重置为自动值）。
    """
    amount = _to_decimal(value)
    if amount is None:
        raise ValueError("set_platform_override 需要一个非 None 的覆盖值")
    if amount <= 0:
        raise ValueError("人工覆盖的最低售价必须大于 0")

    row = (
        (
            await db.execute(
                select(SkuPlatformPricing).where(
                    SkuPlatformPricing.sku_id == sku_id,
                    SkuPlatformPricing.platform_code == platform_code,
                )
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        row = SkuPlatformPricing(
            sku_id=sku_id,
            platform_code=platform_code,
            min_selling_price_override=amount,
            min_selling_price_source=MANUAL_OVERRIDE_SOURCE,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(row)
    else:
        row.min_selling_price_override = amount
        row.min_selling_price_source = MANUAL_OVERRIDE_SOURCE
        row.updated_by = user_id
    await db.flush()
    return row


async def clear_platform_override(
    db: AsyncSession, *, sku_id: int, platform_code: str
) -> bool:
    """重置为自动值：清掉该 SKU 在该平台的人工覆盖。

    做法是**把覆盖值置 NULL**而不是删行：
    - 读路径 ``load_platform_pricing_overrides`` 只取覆盖值非 NULL 的行 ⇒
      置 NULL 之后这条 SKU 立刻回到「系统算的底线」，行为与没有这行一样；
    - 行本身留着，可以继续记派生快照（档位 / 库龄），下次有人改同一行时
      不用再 INSERT 一次。
    """
    row = (
        (
            await db.execute(
                select(SkuPlatformPricing).where(
                    SkuPlatformPricing.sku_id == sku_id,
                    SkuPlatformPricing.platform_code == platform_code,
                )
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        return False
    row.min_selling_price_override = None
    row.min_selling_price_source = None
    await db.flush()
    return True


async def set_free_shipping(
    db: AsyncSession,
    *,
    sku_id: int,
    platform_code: str,
    free_shipping: bool,
    user_id: Optional[int] = None,
) -> SkuPlatformPricing:
    """设置某 SKU 在某平台的**包邮开关**（批次 6，2026-11-17）。

    业务前提：跨境电商**不是默认包邮**，而是**选择性包邮** ⇒
    「包不包邮」是 **SKU × 平台** 的经营选择。

    - 已有行 ⇒ 只改包邮开关，**不动**人工覆盖值（两件事互不相干）；
    - 没有行 ⇒ 新建一行（只带包邮开关）。

    ⚠️ 这里**不删行、也不置 NULL**：包邮开关与人工覆盖共住一张表，但语义不同 ——
    人工覆盖置 NULL 表示「回到自动值」，包邮置 NULL 只会让「没设置」和
    「明确不包邮」混成一团。明确写 FALSE 才能表达「这个品确定不包邮」。
    """
    row = (
        (
            await db.execute(
                select(SkuPlatformPricing).where(
                    SkuPlatformPricing.sku_id == sku_id,
                    SkuPlatformPricing.platform_code == platform_code,
                )
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        row = SkuPlatformPricing(
            sku_id=sku_id,
            platform_code=platform_code,
            free_shipping=bool(free_shipping),
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(row)
    else:
        row.free_shipping = bool(free_shipping)
        row.updated_by = user_id
    await db.flush()
    return row
