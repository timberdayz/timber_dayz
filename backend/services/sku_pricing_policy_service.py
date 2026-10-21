"""库龄定价档位规则「当前生效行」的**唯一**读取入口。

商品中心（`backend/domains/business/routers/product_center.py`）与 SKU 级滞销清单
（`backend/services/inventory/sku_clearance_service.py`）都要用同一组谓词筛当前规则行。

谓词一旦分叉成两份，就会出现「商品中心按日常档打折、滞销清单按滞销档」的自相矛盾——
这是评审时最容易被忽略、但业务上最伤的一种 bug。所以谓词与读取函数都放在这里，
路由侧只做转发。
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import SkuPricingPolicy


def policy_current_predicate():
    """当前生效规则行的谓词。

    ⚠️ 用 `effective_to IS NULL` 而不是 `effective_to IS NULL OR effective_to > 今日`：
    后者会把「已关闭但关闭日期在未来」的行也算进来，规则集合与实际生效的集合就分家了。

    ⚠️ 也不允许把当前行直接置成 `inactive`——那等于**静默删掉一档**：
    `_current_policies` 变空后所有 SKU 一起掉进 `missing_pricing_policy`、最低售价算不出来。
    停用请走版本化路径（改 `effective_from` 关旧行 + 建新行）。
    """
    return (
        SkuPricingPolicy.status == "active",
        SkuPricingPolicy.effective_to.is_(None),
        SkuPricingPolicy.effective_from <= date.today(),
    )


async def load_current_policies(db: AsyncSession) -> list[SkuPricingPolicy]:
    """当前生效的规则行，按档位起点升序。"""
    result = await db.execute(
        select(SkuPricingPolicy)
        .where(*policy_current_predicate())
        .order_by(SkuPricingPolicy.min_age_days)
    )
    return list(result.scalars().all())


def to_policy_rows(policies) -> list[dict]:
    """ORM 行 → 纯函数可用的标量字典。

    费率统一转成 `Decimal`：纯函数 `product_pricing_service` 里所有费率都按 Decimal 处理，
    这里转成 float 会引入二进制浮点误差。
    """
    from decimal import Decimal

    return [
        {
            "min_age_days": p.min_age_days,
            "tier_label": p.tier_label,
            "discount_rate": Decimal(str(p.discount_rate)),
            "target_margin_rate": Decimal(str(p.target_margin_rate)),
            "platform_basis": p.platform_basis,
        }
        for p in policies
    ]
