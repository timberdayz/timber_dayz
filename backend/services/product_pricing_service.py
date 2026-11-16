"""商品中心 SKU 定价底线的纯计算逻辑。

设计约束（来自 docs/superpowers/specs/2026-10-20-sku-pricing-guardrails-design.md）：
- 所有金额用 Decimal；费率只做 Decimal(str(x)) 转换，**不得量化**
- 平台佣金率已包含在 other_cost_rate 内，不得单独进入分母
- 达人佣金率优先用 SKU 值，NULL 时由调用方传入平台默认值
- 档位由当前库龄决定；库龄缺失回落 min_restock_days 最小的一行

本模块**不持有任何平台参数**——费率由调用方从 dim_platforms 读出后传入，
避免平台口径变化时服务里的常量悄悄过期。

**本模块不 import ORM、不碰 DB**：所有函数都是纯函数，
因此降级链的 7 种 `missing_reasons`、分母 ≤ 0、折扣纪律兜底都能写成无 DB 单测。
ORM 行 → 标量的适配在路由侧（`backend/domains/business/routers/product_center.py`
的 `_compute_pricing_for_sku`），业务判断只有这一处（spec §5.1「实现时只写一处」）。
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional

MONEY_QUANTUM = Decimal("0.01")


def _decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _money(value: Decimal) -> Decimal:
    """最终金额量化到分。费率不要用这个函数。"""
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def compute_cost_floor(
    *,
    purchase_cost,
    other_cost_rate,
    creator_commission_rate,
    spu_return_loss_rate,
    spu_damage_rate,
    target_margin_rate,
    delivery_cost=None,
    delivery_cost_rate=None,
) -> Optional[Decimal]:
    """采购成本反解出的保价底线；分母非正时返回 None。

    尾程配送费（批次 4）
    ------------------
    ``other_cost_rate`` 是**残差桶**（从实测净利率反推），桶里**已经含运费** ——
    平台的利润列扣过实际运费（生产库实测：TikTok ``总费用`` 内含 ``实际运费``，
    Shopee ``卖家支付运费`` 直接从结算里扣）。

    批次 4 起尾程按 SKU 重量单件计价，要把它放进底线的分子。若分母里那份
    「按收入摊的尾程」不同时剔掉 ⇒ **同一笔尾程扣两次**，底线被抬高。

    所以尾程**成对生效**：``delivery_cost``（元/件）与 ``delivery_cost_rate``
    （尾程占收入比）**必须同时有值**才进底线：

    - 分子 = 采购成本 + 尾程配送费
    - 分母 = 1 − other_cost_rate **+ delivery_cost_rate** − 达人 − 货损 − 退货 − 目标利润率

    缺任何一个 ⇒ **尾程不进底线**（宁可不算，也不重复扣），由调用方把
    缺失原因报出去（``missing_delivery_cost`` / ``missing_delivery_cost_rate_split``）。
    """
    cost = _decimal(purchase_cost)
    if cost is None:
        return None
    delivery_applied = delivery_cost is not None and delivery_cost_rate is not None
    numerator = cost + (
        (_decimal(delivery_cost) or Decimal("0")) if delivery_applied else Decimal("0")
    )
    denominator = (
        Decimal("1")
        - (_decimal(other_cost_rate) or Decimal("0"))
        + (
            (_decimal(delivery_cost_rate) or Decimal("0"))
            if delivery_applied
            else Decimal("0")
        )
        - (_decimal(creator_commission_rate) or Decimal("0"))
        - (_decimal(spu_return_loss_rate) or Decimal("0"))
        - (_decimal(spu_damage_rate) or Decimal("0"))
        - (_decimal(target_margin_rate) or Decimal("0"))
    )
    if denominator <= 0:
        return None
    return _money(numerator / denominator)


def compute_discount_guard(
    *, reference_selling_price, discount_rate
) -> Optional[Decimal]:
    """参考售价按当前档折扣率折算的纪律线。"""
    price = _decimal(reference_selling_price)
    if price is None:
        return None
    rate = _decimal(discount_rate) or Decimal("0")
    return _money(price * (Decimal("1") - rate))


def select_restock_tier(
    policies: Iterable[dict], days_since_restock: Optional[int]
) -> Optional[dict]:
    """按库龄命中档位；库龄缺失时回落 min_restock_days 最小的一行。"""
    rows = [p for p in policies if p is not None]
    if not rows:
        return None
    if days_since_restock is None:
        return min(rows, key=lambda p: p["min_restock_days"])
    eligible = [p for p in rows if p["min_restock_days"] <= days_since_restock]
    if not eligible:
        return min(rows, key=lambda p: p["min_restock_days"])
    return max(eligible, key=lambda p: p["min_restock_days"])


def compute_min_selling_price(
    *,
    cost_floor: Optional[Decimal],
    discount_guard: Optional[Decimal],
    manual_override: Optional[Decimal],
) -> dict:
    """取三条线里的最大值，并给出来源标记。"""
    override = _decimal(manual_override)
    if override is not None:
        return {
            "min_selling_price": _money(override),
            "source": "manual_override",
            "is_override": True,
            "missing_reasons": [],
        }
    candidates = [(cost_floor, "cost_floor"), (discount_guard, "discount_guard")]
    available = [(value, source) for value, source in candidates if value is not None]
    if not available:
        return {
            "min_selling_price": None,
            "source": "unavailable",
            "is_override": False,
            "missing_reasons": ["no_pricing_input"],
        }
    value, source = max(available, key=lambda item: item[0])
    return {
        "min_selling_price": _money(value),
        "source": source,
        "is_override": False,
        "missing_reasons": [],
    }


def compute_sku_pricing(
    *,
    purchase_cost,
    reference_selling_price,
    creator_commission_rate,
    platform_creator_commission_rate,
    other_cost_rate,
    spu_bound,
    spu_return_loss_rate,
    spu_damage_rate,
    policy,
    deepest_policy,
    min_selling_price_override,
    days_since_restock=None,
    delivery_cost=None,
    delivery_cost_rate=None,
) -> dict:
    """单个 SKU 的完整定价字段。**纯函数**：无 ORM、无 DB、无 I/O。

    参数全是标量/字典，ORM 适配放在路由侧（`_compute_pricing_for_sku`）。
    这样降级链的 7 种 `missing_reasons`、分母 ≤ 0、折扣纪律的兜底
    都能写成**无 DB 单测**（spec §5.1「实现时只写一处」的要求）。

    `creator_commission_rate` 是 **SKU 自己的值**（可能为 None = 未单独设置）；
    `platform_creator_commission_rate` 是平台兜底，只用于**计算**，**不回填到返回值**——
    返回值里的 `creator_commission_rate` 必须仍是 None，前端输入框才显示「空 = 按平台默认」。

    `spu_bound` 与两个 SPU 率分开传，是为了区分两种缺料：
    没绑 SPU -> `missing_spu_binding`；绑了但率没维护 -> `missing_spu_rates`。

    尾程配送费（批次 4）：`delivery_cost` 是这个 SKU 的**单件尾程**（元），
    `delivery_cost_rate` 是**平台级**的尾程占收入比（拆分基准）。
    两者**成对生效**才进成本底线（见 `compute_cost_floor` 的口径说明）：
    只有一个 ⇒ 尾程不进底线，并把缺的那一半报进 `missing_reasons`。
    """
    missing_reasons: list[str] = []
    cost_floor = None
    discount_guard = None

    creator_rate = _decimal(creator_commission_rate)
    if creator_rate is None:
        creator_rate = _decimal(platform_creator_commission_rate)

    # 尾程成对生效判定（与 compute_cost_floor 内部同一套规则，不允许两处各判一次）
    delivery_applied = delivery_cost is not None and delivery_cost_rate is not None
    if delivery_cost is None:
        missing_reasons.append("missing_delivery_cost")
    elif delivery_cost_rate is None:
        missing_reasons.append("missing_delivery_cost_rate_split")

    if policy is None:
        missing_reasons.append("missing_pricing_policy")
    else:
        other_rate = _decimal(other_cost_rate)
        return_loss_rate = _decimal(spu_return_loss_rate)
        damage_rate = _decimal(spu_damage_rate)
        purchase = _decimal(purchase_cost)
        if other_rate is None:
            missing_reasons.append("missing_platform_cost_rate")
        if creator_rate is None:
            missing_reasons.append("missing_creator_commission_rate")
        if not spu_bound:
            missing_reasons.append("missing_spu_binding")
        elif return_loss_rate is None or damage_rate is None:
            missing_reasons.append("missing_spu_rates")
        if purchase is None:
            missing_reasons.append("missing_purchase_cost")

        # 只有输入齐全才计算成本线；缺项时算不出底线，
        # 而不是把 None 当 0 代入分母算出偏乐观的结果
        if (
            purchase is not None
            and other_rate is not None
            and creator_rate is not None
            and spu_bound
            and return_loss_rate is not None
            and damage_rate is not None
        ):
            cost_floor = compute_cost_floor(
                purchase_cost=purchase,
                other_cost_rate=other_rate,
                creator_commission_rate=creator_rate,
                spu_return_loss_rate=return_loss_rate,
                spu_damage_rate=damage_rate,
                target_margin_rate=policy["target_margin_rate"],
                delivery_cost=delivery_cost if delivery_applied else None,
                delivery_cost_rate=delivery_cost_rate if delivery_applied else None,
            )
            if cost_floor is None:
                missing_reasons.append("non_positive_cost_denominator")
        discount_guard = compute_discount_guard(
            reference_selling_price=reference_selling_price,
            discount_rate=policy["discount_rate"],
        )

    pricing = compute_min_selling_price(
        cost_floor=cost_floor,
        discount_guard=discount_guard,
        manual_override=min_selling_price_override,
    )
    all_reasons = list(dict.fromkeys(pricing["missing_reasons"] + missing_reasons))
    sku_creator_rate = _decimal(creator_commission_rate)
    platform_creator_rate = _decimal(platform_creator_commission_rate)
    override = _decimal(min_selling_price_override)
    return {
        "creator_commission_rate": (
            float(sku_creator_rate) if sku_creator_rate is not None else None
        ),
        # 平台兜底值：前端要用它做「达人佣金率」输入框的 placeholder
        # （spec §5.4：留空 = 未单独设置 = 按平台默认计算，输入框要提示兜底值）。
        # 它**不是** SKU 的值，不参与任何计算，只用于展示；
        # 注意取的是**平台默认值本身**，不是解析后的 creator_rate
        # （SKU 自己设了 15% 时，兜底值仍是平台的 6.06%）。
        "creator_commission_rate_fallback": (
            float(platform_creator_rate) if platform_creator_rate is not None else None
        ),
        "current_discount_rate": float(policy["discount_rate"]) if policy else None,
        "clearance_max_discount_rate": (
            float(deepest_policy["discount_rate"]) if deepest_policy else None
        ),
        "min_selling_price": (
            float(pricing["min_selling_price"])
            if pricing["min_selling_price"] is not None
            else None
        ),
        "min_selling_price_source": pricing["source"],
        "min_selling_price_is_override": pricing["is_override"],
        "min_selling_price_override": float(override) if override is not None else None,
        "min_selling_price_missing_reasons": all_reasons,
        # 尾程配送费（批次 4）是否进了成本底线。
        # ⚠️ 必须是「成对」才为 True：分子加了尾程，分母也剔掉了残差里的那份。
        #    只有一边有值时为 False —— 此时尾程**没有**进底线（缺的那半边在 missing_reasons 里）。
        "delivery_cost_in_cost_floor": delivery_applied,
        "cost_floor_delivery_cost": (
            float(_decimal(delivery_cost)) if delivery_applied else None
        ),
        "cost_floor_delivery_cost_rate": (
            float(_decimal(delivery_cost_rate)) if delivery_applied else None
        ),
        "pricing_tier_label": policy["tier_label"] if policy else None,
        # 档位的**身份** = 库龄起点（阶段 3）。
        # ⚠️ 为什么要有它：``tier_label`` 是**显示名**，是可以改的
        #    （阶段 3 就把「滞销30天」改成「库龄≥60天」）。
        #    拿显示名当"档位身份" ⇒ 改一次名字，全库 SKU 看起来都"跨了档"
        #    ⇒ 最低售价变更通知会误报成"库龄跨档" ⇒ 通知风暴。
        #    身份必须用**规则行自己的库龄起点**，它不随显示名变化。
        "pricing_tier_min_restock_days": policy["min_restock_days"] if policy else None,
        "pricing_days_since_restock": days_since_restock,
        "pricing_tier_source": (
            "restock_days"
            if days_since_restock is not None
            else "fallback_no_restock_days"
        ),
    }


# 规则更新的拒绝原因（模块级常量：路由、spec §5.1、前端文案共用同一份，
# 不要在多处各写一遍中文提示）
POLICY_REJECT_FUTURE = "生效日期不能晚于今天"
POLICY_REJECT_BACKDATED = "生效日期不能早于当前规则"


class PolicyUpdateRejected(ValueError):
    """规则版本更新被拒绝（未来生效 / 回溯生效 / 档位不存在）。"""


def resolve_policy_update(
    *,
    current: Optional[dict],
    requested: dict,
    today,
) -> dict:
    """规则表版本化更新的纯判定：返回 action 与要写入的字段。

    `current` 是**路径参数指向的档位**（被编辑的那一档）的当前行：
    `{"min_restock_days": int, "effective_from": date}`；该档位没有当前行时传 None。

    `requested` 是请求体，其中 `min_restock_days` 是**该档位的新起点**。
    因此「路径起点 != body 起点」= 运营在改库龄档位的边界，而不是调用方搞混。

    两条拒绝路径（与 spec §5.1 一致）：
    - 生效日期在未来                -> 拒绝（未来生效不允许）
    - 生效日期早于当前行的生效日期    -> 拒绝（回溯生效不允许）

    四条落库路径：
    - 该档位没有当前行            -> action="create"（等价 POST）
    - 起点与生效日期都没变          -> action="update"（原地改，同日不可新建否则撞 UNIQUE）
    - 起点变了（改档位边界）        -> action="retier"（关旧行 + 建新行，新行用新起点）
    - 起点没变但生效日期更晚        -> action="version"（关旧行 + 建新行）

    ⚠️ **回溯拒绝必须排在 retier 判定之前**：否则「同时改起点 + 把生效日期往回拨」
    会绕过回溯拒绝，直接去插一行 effective_from 早于当前行的记录，
    撞 `ck_sku_pricing_policy_window`（effective_to >= effective_from）变成
    IntegrityError(409)，而不是 spec §5.1 要求的 422。
    """
    requested_effective_from = requested["effective_from"]
    requested_min_age = requested["min_restock_days"]

    if requested_effective_from > today:
        raise PolicyUpdateRejected(POLICY_REJECT_FUTURE)
    if current is None:
        return {"action": "create", "close_current": None, "values": dict(requested)}

    current_effective_from = current["effective_from"]
    current_min_age = current["min_restock_days"]

    # 回溯生效一律拒绝——先于 retier / version 判定
    if requested_effective_from < current_effective_from:
        raise PolicyUpdateRejected(POLICY_REJECT_BACKDATED)
    if requested_min_age != current_min_age:
        # 改档位边界：关旧行 + 建新行（新行用新起点）。
        # 新起点与生效日期的组合若已被占用，会撞 UNIQUE(min_restock_days, effective_from) -> 409
        return {
            "action": "retier",
            "close_current": requested_effective_from,
            "values": dict(requested),
        }
    if requested_effective_from == current_effective_from:
        # 同日、同档位：原地 UPDATE。effective_from 不变，因此不会撞 UNIQUE
        values = {k: v for k, v in requested.items() if k != "effective_from"}
        return {"action": "update", "close_current": None, "values": values}
    # 起点没变、生效日期更晚：版本化
    return {
        "action": "version",
        "close_current": requested_effective_from,
        "values": dict(requested),
    }
