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

平台维度（阶段 2.1）
--------------------
**底线是「SKU × 平台」的量**：TikTok 与 Shopee 的平台其他成本率差了一截
（27.27% vs 41.65%），同一件商品在两个平台的底线**必须不同**。

以前这里取的是规则表指定的**单一 basis 平台**（`platform_basis`）的费率，
于是所有平台的底线都用 TikTok 的成本结构算 —— Shopee 的底线被低估三到七成，
护栏「预计售价低于最低售价」会放行本该拦住的品。

现在改成：取数层一次把**所有销售平台**读出来（``platforms`` 字典），
计算层按 ``platform_code`` 取该平台的费率。**「basis 平台」这个概念随之消失** ——
规则表里的 ``platform_basis`` 只是历史字段，不再参与费率选择。
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import DimPlatform, SkuPlatformPricing

from .inventory.inventory_age_query_service import load_current_inventory_ages
from .inventory.inventory_restock_query_service import load_current_restock_days
from .product_pricing_service import compute_sku_pricing, select_restock_tier
from .sku_pricing_policy_service import load_current_policies, to_policy_rows


async def load_pricing_platforms(
    db: AsyncSession, platform_codes: Iterable[str] | None = None
) -> dict[str, DimPlatform]:
    """可定价平台：``{platform_code: DimPlatform}``。

    「可定价」= ``platform_role = 'sales'``（真正对外销售的平台）。
    ``source`` / ``test`` 平台没有对外售价，不参与底线计算。

    传了 ``platform_codes`` 就只取那几个（外加全部销售平台，保证调用方要的平台一定在）。
    """
    codes: set[str] = set(platform_codes or ())
    rows = (
        await db.execute(select(DimPlatform).where(DimPlatform.platform_role == "sales"))
    ).scalars().all()
    platforms = {row.platform_code: row for row in rows}
    if codes:
        missing = codes - set(platforms)
        if missing:
            extra = (
                await db.execute(
                    select(DimPlatform).where(DimPlatform.platform_code.in_(missing))
                )
            ).scalars().all()
            platforms.update({row.platform_code: row for row in extra})
    return platforms


async def load_pricing_context(
    db: AsyncSession,
    sku_ids: list[int],
    platform_codes: Iterable[str] | None = None,
) -> dict:
    """一次性把规则表、平台成本率、库龄、平台级人工覆盖读出来，供批量计算。

    返回：

    - ``policies``：当前生效的规则行（标量字典，已转 Decimal 费率）
    - ``platforms``：``{platform_code: DimPlatform}`` —— **按平台各一条底线**要用它
    - ``platform``：历史别名，仍指向规则表 basis 平台（**仅向后兼容**，
      新代码请用 ``platforms[platform_code]``）
    - ``overrides``：``{(sku_id, platform_code): SkuPlatformPricing}`` —— 平台级人工覆盖
    - ``days_since_restock``：``{sku_id: 距上次进货天数}``，缺失的 SKU **不在字典里**
    - ``restock_rows``：``{sku_id: {"days_since_restock", "current_qty", "inventory_value"}}``，
      通知侧要写库存数量/库存金额时用这一份

    ⚠️ **「距上次进货天数」才是业务上的库龄**（西虹卖完不补货，货进来才重新开始计时）。
    档位表的门槛（0/60/90/120）与折扣率**不动**，只是喂进去的量换了。
    """
    policy_rows = to_policy_rows(await load_current_policies(db))
    basis = policy_rows[0]["platform_basis"] if policy_rows else "tiktok"
    platforms = await load_pricing_platforms(db, platform_codes)
    basis_platform = platforms.get(basis)
    if basis_platform is None:
        basis_platform = await db.get(DimPlatform, basis)
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

    overrides = await load_platform_pricing_overrides(db, sku_ids, platforms)
    # 「可定价平台」= 有平台其他成本率的销售平台。
    # 没有 other_cost_rate 的平台算不出底线（成本线分母里缺这一项），
    # 建了基线也是一列 NULL —— 不如不跟踪，等它配了费率再进来。
    priceable = {
        code
        for code, row in platforms.items()
        if row.platform_role == "sales" and row.other_cost_rate is not None
    }
    return {
        "policies": policy_rows,
        "platform": basis_platform,
        "platforms": platforms,
        "priceable_platform_codes": sorted(priceable),
        "overrides": overrides,
        "days_since_restock": days_since_restock,
        "restock_rows": restock_rows,
        "restock_source": restock_source,
        # 向后兼容别名：老下游按 age_days / age_rows 取值，指向的是同一份新数据
        "age_days": days_since_restock,
        "age_rows": restock_rows,
    }


async def load_platform_pricing_overrides(
    db: AsyncSession,
    sku_ids: list[int],
    platforms: dict[str, DimPlatform],
) -> dict[tuple[int, str], SkuPlatformPricing]:
    """平台级人工覆盖：``{(sku_id, platform_code): SkuPlatformPricing}``。

    只读**有覆盖值**的行 —— 没有人工覆盖的 SKU 不占内存，
    底线的来源标记仍然是 ``cost_floor`` / ``discount_guard``。
    """
    if not sku_ids or not platforms:
        return {}
    rows = (
        await db.execute(
            select(SkuPlatformPricing).where(
                SkuPlatformPricing.sku_id.in_(sku_ids),
                SkuPlatformPricing.platform_code.in_(list(platforms)),
                SkuPlatformPricing.min_selling_price_override.is_not(None),
            )
        )
    ).scalars().all()
    return {(row.sku_id, row.platform_code): row for row in rows}


def resolve_pricing_platform(context: dict, platform_code: Optional[str]):
    """取某个平台的费率行；没给平台时回落到历史 basis 平台。"""
    platforms = context.get("platforms") or {}
    if platform_code:
        platform = platforms.get(platform_code)
        if platform is not None:
            return platform
    return context.get("platform")


def resolve_pricing_platform_code(context: dict, platform_code: Optional[str]) -> Optional[str]:
    """这次算底线的**实际**平台代码。

    不传平台时回落到历史 basis 平台 —— 前端要显示出来，
    否则运营不知道自己看的是 TikTok 的底线还是 Shopee 的底线。
    """
    if platform_code:
        platform = (context.get("platforms") or {}).get(platform_code)
        if platform is not None:
            return platform.platform_code
    fallback = context.get("platform")
    return fallback.platform_code if fallback is not None else None


def resolve_pricing_override(context: dict, sku_id: int, platform_code: Optional[str]):
    """取某 SKU 在某平台的**人工覆盖值**；没有则返回 None。

    覆盖值住在 ``finance.sku_platform_pricing``（阶段 2.1b 迁入）——
    **SKU × 平台** 的量，因为底线就是 SKU × 平台的量。

    ⚠️ 以前它住在 ``core.dim_erp_sku.min_selling_price_override``（公司级），
    现在那一列**已删**：
    - 口径错位（一个数套所有平台，而各平台费率差一截）；
    - 而且那张表会被「采集机 → 云端」同步 TRUNCATE ⇒ 覆盖值每次同步都蒸发。

    覆盖值为空 ⇒ 没有人工覆盖（走系统算的底线）。
    """
    overrides = context.get("overrides") or {}
    if not platform_code:
        return None
    row = overrides.get((sku_id, platform_code))
    return row.min_selling_price_override if row is not None else None


def compute_pricing_state(
    *,
    context: dict,
    sku_row,
    linked_spu,
    platform_code: Optional[str] = None,
) -> dict:
    """算出一个 SKU 在**某个平台**上的定价状态（含命中的档位）。

    返回 ``{"pricing": {...}, "policy": 命中的档位|None, "days_since_restock": int|None,
    "platform_code": str|None}``：

    - ``pricing`` 就是纯函数 `compute_sku_pricing` 的返回值（页面直接用）
    - ``policy`` 是命中的档位字典，通知侧要拿它的 ``target_margin_rate`` /
      ``discount_rate`` 做归因（目标利润率不在 ``pricing`` 里）
    - ``days_since_restock`` 是本次用的「距上次进货天数」

    ⚠️ `linked_spu` 传 None 表示「没绑 SPU」或「绑了但 SPU 行查不到」，
    两种情况都按 `missing_spu_binding` 缺料处理——与商品中心页面口径一致。

    ⚠️ `platform_code` 不传时回落到历史 basis 平台 —— 只为兼容老调用方，
    **新代码必须显式传平台**，否则所有平台又会共用一套费率（那正是阶段 2.1 要修的缺陷）。
    """
    policies = context["policies"]
    platform = resolve_pricing_platform(context, platform_code)
    days_since_restock = context["days_since_restock"].get(sku_row.sku_id)

    policy = select_restock_tier(policies, days_since_restock)
    deepest = max(policies, key=lambda p: p["min_restock_days"]) if policies else None

    # 人工覆盖：平台级（SKU × 平台）。以前还有一段「回落 SKU 级旧列」，
    # 阶段 2.1b 起那列已删（口径错位 + 会被同步 TRUNCATE 抹掉）。
    #
    # ⚠️ 必须用**实际生效的平台代码**去查覆盖，不能用调用方传的原始值：
    #    调用方不传平台时，费率走的是回落后的 basis 平台（见上面的 `platform`），
    #    而覆盖如果按 None 查 ⇒ 找不到 ⇒ **人工覆盖被静默忽略**。
    #    这两处必须是**同一个平台**，否则「覆盖值设了却不生效」，
    #    运营会以为系统坏了。`resolve_pricing_platform_code` 出来的就是
    #    本次算底线实际用的那个平台代码。
    effective_platform_code = resolve_pricing_platform_code(context, platform_code)
    override = resolve_pricing_override(
        context, sku_row.sku_id, effective_platform_code
    )

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
        min_selling_price_override=override,
        days_since_restock=days_since_restock,
    )
    return {
        "pricing": pricing,
        "policy": policy,
        "days_since_restock": days_since_restock,
        "platform_code": platform_code,
    }


def compute_pricing_for_sku(
    *,
    context: dict,
    sku_row,
    linked_spu,
    platform_code: Optional[str] = None,
) -> dict:
    """只要定价字段本身（页面用）。

    是 `compute_pricing_state` 的薄封装——**同一个**计算函数，
    不存在"页面走一条、通知走另一条"的可能。
    """
    return compute_pricing_state(
        context=context,
        sku_row=sku_row,
        linked_spu=linked_spu,
        platform_code=platform_code,
    )["pricing"]


def resolve_effective_creator_rate(
    *,
    context: dict,
    sku_row,
    platform_code: Optional[str] = None,
) -> Optional[Any]:
    """实际生效的达人佣金率：SKU 自己设了就用它的，没设就用平台默认值。

    只用于**归因快照**（回答"这次变化是不是达人佣金率变了"），
    不参与底线计算——底线计算里的两级费率由 `compute_sku_pricing` 自己处理。
    """
    from decimal import Decimal

    platform = resolve_pricing_platform(context, platform_code)
    platform_rate = platform.default_creator_commission_rate if platform else None

    sku_rate = sku_row.creator_commission_rate
    if sku_rate is not None:
        return sku_rate
    if platform_rate is None:
        return None
    return Decimal(str(platform_rate))
