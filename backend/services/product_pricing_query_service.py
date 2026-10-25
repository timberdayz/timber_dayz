"""SKU 定价取数与计算的**共享**入口。

商品中心（页面展示「最低售价」）与最低售价变更通知（判断「底线变没变」）
必须用**同一条**取数路径和**同一个**计算函数。

口径一旦分叉成两份，就会出现「页面按日常档显示、通知却按滞销档发」的自相矛盾——
这是评审时最容易被忽略、但业务上最伤的一种 bug。所以本模块是**唯一**实现，
两边都调它；**不允许**任何一方自己再写一遍「取规则 / 取库龄 / 选档位 / 算底线」。

分层：

- `backend/services/product_pricing_service.py`：纯函数（无 ORM、无 DB、无 I/O）
- **本模块**：ORM 适配 + 批量取数，把 ORM 行喂给上面的纯函数
- 调用方：商品中心路由、最低售价变更通知服务

「口径一致」在这里是**结构性保证**（同一个函数被两边调用），
而不是靠一条容易在别的环境下被跳过的数据库测试来保证。
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import DimPlatform

from .inventory.inventory_age_query_service import load_current_inventory_ages
from .inventory.inventory_restock_query_service import load_current_restock_days
from .product_pricing_service import compute_sku_pricing, select_restock_tier
from .sku_pricing_policy_service import load_current_policies, to_policy_rows


async def load_pricing_context(db: AsyncSession, sku_ids: list[int]) -> dict:
    """一次性把规则表、平台成本率、库龄读出来，供批量计算。

    返回：

    - ``policies``：当前生效的规则行（标量字典，已转 Decimal 费率）
    - ``platform``：规则行指定的平台维度行（``dim_platforms``）
    - ``days_since_restock``：``{sku_id: 距上次进货天数}``，缺失的 SKU **不在字典里**
    - ``restock_rows``：``{sku_id: {"days_since_restock", "current_qty", "inventory_value"}}``，
      通知侧要写库存数量/库存金额时用这一份

    ⚠️ **「距上次进货天数」才是业务上的库龄**（西虹卖完不补货，货进来才重新开始计时）。
    档位表的门槛（0/60/90/120）与折扣率**不动**，只是喂进去的量换了。
    """
    policy_rows = to_policy_rows(await load_current_policies(db))
    basis = policy_rows[0]["platform_basis"] if policy_rows else "tiktok"
    platform = await db.get(DimPlatform, basis)
    restock_rows = await load_current_restock_days(db, sku_ids)
    if restock_rows:
        days_since_restock = {
            sku_id: row.get("days_since_restock")
            for sku_id, row in restock_rows.items()
        }
        restock_source = "inventory_state"
    else:
        # 能力探测回落：状态层表不存在 / 查询失败（SQLite 测试环境、非 PostgreSQL 部署）时，
        # 回落旧库龄路径，行为与改造前完全一致。
        # ⚠️ 旧库龄口径本身是坏的（恒 0~13 天），所以这只是「不崩」的兜底，
        #    生产环境必须有 mart.inventory_state 才走新判据。
        from modules.core.logger import get_logger

        get_logger(__name__).warning(
            "inventory_state unavailable, falling back to legacy age_days caliber"
        )
        restock_rows = await load_current_inventory_ages(db, sku_ids)
        days_since_restock = {
            sku_id: row.get("age_days")
            for sku_id, row in restock_rows.items()
        }
        restock_source = "legacy_age_days"
    return {
        "policies": policy_rows,
        "platform": platform,
        "days_since_restock": days_since_restock,
        "restock_rows": restock_rows,
        "restock_source": restock_source,
        # 向后兼容别名：老下游按 age_days / age_rows 取值，指向的是同一份新数据
        "age_days": days_since_restock,
        "age_rows": restock_rows,
    }


def compute_pricing_state(
    *,
    context: dict,
    sku_row,
    linked_spu,
) -> dict:
    """算出一个 SKU 的定价状态（含命中的档位）。

    返回 ``{"pricing": {...}, "policy": 命中的档位|None, "days_since_restock": int|None}``：

    - ``pricing`` 就是纯函数 `compute_sku_pricing` 的返回值（页面直接用）
    - ``policy`` 是命中的档位字典，通知侧要拿它的 ``target_margin_rate`` /
      ``discount_rate`` 做归因（目标利润率不在 ``pricing`` 里）
    - ``days_since_restock`` 是本次用的「距上次进货天数」

    ⚠️ `linked_spu` 传 None 表示「没绑 SPU」或「绑了但 SPU 行查不到」，
    两种情况都按 `missing_spu_binding` 缺料处理——与商品中心页面口径一致。
    """
    policies = context["policies"]
    platform = context["platform"]
    days_since_restock = context["days_since_restock"].get(sku_row.sku_id)

    policy = select_restock_tier(policies, days_since_restock)
    deepest = max(policies, key=lambda p: p["min_restock_days"]) if policies else None

    pricing = compute_sku_pricing(
        purchase_cost=sku_row.default_purchase_cost,
        reference_selling_price=sku_row.reference_selling_price,
        creator_commission_rate=sku_row.creator_commission_rate,
        platform_creator_commission_rate=(
            platform.default_creator_commission_rate if platform else None
        ),
        other_cost_rate=platform.other_cost_rate if platform else None,
        spu_bound=linked_spu is not None,
        spu_return_loss_rate=linked_spu.return_loss_rate if linked_spu else None,
        spu_damage_rate=linked_spu.logistics_damage_rate if linked_spu else None,
        policy=policy,
        deepest_policy=deepest,
        min_selling_price_override=sku_row.min_selling_price_override,
        days_since_restock=days_since_restock,
    )
    return {
        "pricing": pricing,
        "policy": policy,
        "days_since_restock": days_since_restock,
    }


def compute_pricing_for_sku(
    *,
    context: dict,
    sku_row,
    linked_spu,
) -> dict:
    """只要定价字段本身（页面用）。

    是 `compute_pricing_state` 的薄封装——**同一个**计算函数，
    不存在"页面走一条、通知走另一条"的可能。
    """
    return compute_pricing_state(
        context=context,
        sku_row=sku_row,
        linked_spu=linked_spu,
    )["pricing"]


def resolve_effective_creator_rate(
    *,
    context: dict,
    sku_row,
) -> Optional[Any]:
    """实际生效的达人佣金率：SKU 自己设了就用它的，没设就用平台默认值。

    只用于**归因快照**（回答"这次变化是不是达人佣金率变了"），
    不参与底线计算——底线计算里的两级费率由 `compute_sku_pricing` 自己处理。
    """
    from decimal import Decimal

    platform = context["platform"]
    platform_rate = platform.default_creator_commission_rate if platform else None

    sku_rate = sku_row.creator_commission_rate
    if sku_rate is not None:
        return sku_rate
    if platform_rate is None:
        return None
    return Decimal(str(platform_rate))
