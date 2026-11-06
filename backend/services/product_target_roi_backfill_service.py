"""存量「广告分成率」反解成「目标 ROI」（阶段 3）。

为什么要反解
------------
阶段 3 把**主手填输入**收敛成「目标 ROI」（平台语言：商家实收 ÷ 广告费）。
但存量经营档案里填的是老口径「广告分成率」``expected_ad_rate``（广告费 ÷ 广告前利润）。
如果不管，切换到新口径后这些 SKU 的广告费用会**凭空消失** ⇒ 利润被高估
⇒ 运营照着投广告就是亏（这正是 R2 风险）。

反解公式
--------
::

    等效目标ROI = 保本ROI ÷ 广告分成率
    target_roi  = break_even_roi ÷ expected_ad_rate

口径纪律
--------
- **缺输入宁可不算，不可乐观**：保本 ROI 算不出来（成本不全）就**跳过**，
  绝不用"猜一个数"填进去。
- **反解必须证明等价**：写库前用**回算后的** target_roi 再算一遍利润，
  与老口径的广告费/利润逐一对比；差超过 1 分就**跳过**。
  ⇒ 「切口径不改利润」不是嘴上说说，是每次都验一遍。
- 反解只动 ``target_roi IS NULL`` 的行 ⇒ **幂等**，跑两遍结果一样。

为什么放在服务层而不是 alembic 迁移里
------------------------------------
保本 ROI 需要完整的成本模型（采购/物流/仓储/贴单/平台佣金/达人佣金/货损/退货），
其中物流与仓储的**规则选取**（优先级、计费基准、缺输入降级）非常复杂 ——
在 SQL 里重写一遍就是**第二份口径**，必然随规则表演进漂移。
所以这里复用**页面用的同一个** ``preview_platform_sku_profit``，
保证反解出来的数与运营在页面上看到的数**必然一致**。
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import SkuOperatingProfile

from .product_finance_service import ProductFinanceService

#: 目标 ROI 列的精度（``Numeric(12, 4)``）。
#: 反解出来的值必须按**这个精度**回算，否则"两口径等价"的等式会差一个舍入。
TARGET_ROI_QUANTUM = Decimal("0.0001")

#: 允许的最大金额差（元）。两口径算出来的广告费/利润差超过它 ⇒ 不认为等价，跳过。
MONEY_TOLERANCE = Decimal("0.01")

#: 反解出来的来源标记：不是人填的，是从老口径反算出来的。
MIGRATED_SOURCE = "migrated_from_legacy_rate"


def _round_target_roi(value: Decimal) -> Decimal:
    """按目标 ROI 列的精度回算（存进去的是它，验等价也得用它）。"""
    return value.quantize(TARGET_ROI_QUANTUM, rounding=ROUND_HALF_UP)


def _as_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


async def backfill_target_roi_from_legacy_ad_rate(
    session: AsyncSession, *, dry_run: bool = True
) -> dict:
    """把老口径「广告分成率」反解成「目标 ROI」。

    参数
    ----
    session:
        异步会话。
    dry_run:
        True（默认）= 只算不写；False = 写库并提交。

    返回
    ----
    dict 报告：``{"scanned", "updated", "skipped", "items"}``。
    """
    rows = (
        await session.execute(
            select(SkuOperatingProfile).where(
                SkuOperatingProfile.target_roi.is_(None),
                SkuOperatingProfile.expected_ad_rate.is_not(None),
                SkuOperatingProfile.expected_ad_rate > 0,
                SkuOperatingProfile.status == "active",
                SkuOperatingProfile.effective_to.is_(None),
            )
        )
    ).scalars().all()

    report: dict[str, Any] = {
        "dry_run": dry_run,
        "scanned": len(rows),
        "updated": 0,
        "skipped": [],
        "items": [],
    }
    finance = ProductFinanceService(session)

    for profile in rows:
        base_data = {
            "sku_id": profile.sku_id,
            "platform_code": profile.platform_code,
            "warehouse_code": profile.warehouse_code,
            "transport_type": profile.transport_type,
            "competitor_price": profile.competitor_price,
            "expected_selling_price": profile.expected_selling_price,
            "seller_coupon_amount": profile.seller_coupon_amount or 0,
            "expected_ad_rate": profile.expected_ad_rate,
        }
        identity = {
            "profile_id": profile.profile_id,
            "sku_id": profile.sku_id,
            "platform_code": profile.platform_code,
            "warehouse_code": profile.warehouse_code,
        }
        try:
            legacy = await finance.preview_platform_sku_profit(base_data)
        except ValueError as exc:
            # SKU / 平台 / 仓库不存在、物流方式没选 ⇒ 这行算不了，跳过（不改原样）。
            report["skipped"].append({**identity, "reason": "preview_failed", "detail": str(exc)})
            continue

        legacy_expected = legacy.get("expected") or {}
        break_even_roi = legacy_expected.get("break_even_roi")
        if break_even_roi is None:
            # 成本不全 ⇒ 保本 ROI 不可信 ⇒ 不反解（缺输入宁可不算）。
            report["skipped"].append(
                {
                    **identity,
                    "reason": "break_even_roi_not_computable",
                    "roi_missing_reasons": list(
                        legacy_expected.get("roi_missing_reasons") or []
                    ),
                }
            )
            continue

        legacy_ad_rate = Decimal(str(profile.expected_ad_rate))
        candidate = _round_target_roi(Decimal(str(break_even_roi)) / legacy_ad_rate)
        if candidate <= 0:
            report["skipped"].append({**identity, "reason": "non_positive_target_roi"})
            continue

        # --- 等价性自检：用**回算后的** target_roi 再算一遍，与老口径逐项比 ---
        try:
            check = await finance.preview_platform_sku_profit(
                {**base_data, "target_roi": float(candidate)}
            )
        except ValueError as exc:  # pragma: no cover - 与上面同一份输入，不该发生
            report["skipped"].append({**identity, "reason": "preview_failed", "detail": str(exc)})
            continue
        check_expected = check.get("expected") or {}
        ad_cost_diff = abs(
            _as_decimal(check_expected.get("ad_cost")) - _as_decimal(legacy_expected.get("ad_cost"))
        )
        profit_diff = abs(
            _as_decimal(check_expected.get("profit")) - _as_decimal(legacy_expected.get("profit"))
        )
        if ad_cost_diff > MONEY_TOLERANCE or profit_diff > MONEY_TOLERANCE:
            report["skipped"].append(
                {
                    **identity,
                    "reason": "caliber_not_equivalent",
                    "ad_cost_diff": str(ad_cost_diff),
                    "profit_diff": str(profit_diff),
                }
            )
            continue

        if not dry_run:
            profile.target_roi = candidate
            profile.target_roi_source = MIGRATED_SOURCE
        report["updated"] += 1
        report["items"].append(
            {
                **identity,
                "legacy_ad_rate": str(profile.expected_ad_rate),
                "break_even_roi": str(break_even_roi),
                "target_roi": str(candidate),
                "ad_cost_diff": str(ad_cost_diff),
                "profit_diff": str(profit_diff),
            }
        )

    if dry_run:
        await session.rollback()
    else:
        await session.commit()
    return report
