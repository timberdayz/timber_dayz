"""商品中心 SKU 定价底线的纯计算逻辑。

设计约束（来自 docs/superpowers/specs/2026-10-20-sku-pricing-guardrails-design.md
与 docs/superpowers/plans/2026-11-19-product-center-cost-floor-caliber-closure.md）：
- 所有金额用 Decimal；费率只做 Decimal(str(x)) 转换，**不得量化**
- **平台佣金率单独进分母**（批次 9）：`other_cost_rate` 只装「佣金与尾程之外」的平台侧扣款
- 达人佣金率优先用 SKU 值，NULL 时由调用方传入平台默认值
- 档位由当前库龄决定；库龄缺失回落 min_restock_days 最小的一行

**成本底线口径（批次 9，2026-11-19 拍板）**

```
分子 = (采购成本 + 履约按件成本 + 尾程配送费) × (1 + SPU退货率 + SPU货损率)
分母 = 1 − 平台佣金率 − 平台其他成本率(桶) − 达人佣金率 − 目标利润率
```

- **按件的钱进分子**：采购、头程、仓储、贴单、尾程。
- **按比例的钱进分母**：平台佣金、平台其他成本率(桶)、达人佣金。
- **风险折成钱也进分子**：SPU 退货率 / 货损率是**行业基准的件损率**
  （"这个款在行业主流数据下，发 100 件坏/退几件"）⇒ 发 100 件只卖出 (1−R−D) 件
  ⇒ 每卖 1 件要多摊 (1+R+D) 倍的按件成本。
  ⚠️ 旧口径把它们当**收入比例**扣（分母减 R/D），那是"少收钱"的意思，
  与件损率**不是一回事** ⇒ 批次 9 改成按件折进分子。
- **尾程直接进分子**（批次 9 B 路线）：旧的「尾程占收入比」字段与「成对生效」补丁一并退役
  —— 桶里的运费既然拆不出来，就不跟它对冲，直接按 SKU 重量段算好的单件尾程进分子。

本模块**不持有任何平台参数**——费率由调用方从 dim_platforms 读出后传入，
避免平台口径变化时服务里的常量悄悄过期。

**本模块不 import ORM、不碰 DB**：所有函数都是纯函数，
因此降级链的 `missing_reasons`、分母 ≤ 0、折扣纪律兜底都能写成无 DB 单测。
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
    platform_fee_rate,
    other_cost_rate,
    creator_commission_rate,
    spu_return_loss_rate,
    spu_damage_rate,
    target_margin_rate,
    delivery_cost=None,
    logistics_cost=None,
    storage_cost=None,
    label_fee=None,
) -> Optional[Decimal]:
    """采购成本反解出的保价底线；分母非正时返回 None。

    口径（批次 9）
    ------------------
    ``分子 = (采购成本 + 头程 + 仓储 + 贴单 + 尾程) × (1 + 退货率 + 货损率)``
    ``分母 = 1 − 平台佣金率 − 平台其他成本率(桶) − 达人佣金率 − 目标利润率``

    - **平台佣金率单独进分母**（``platform_fee_rate``）：批次 9 之前它藏在
      ``other_cost_rate`` 里，界面上填了也不生效。现在「各扣各的，填的都生效」。
    - **``other_cost_rate`` 只装「佣金与尾程之外」的平台侧扣款**（人工填）。
    - **SPU 两率按件折进分子**：它们是行业基准的**件损率**（发 100 件坏/退几件），
      所以每卖 1 件要多摊 (1 + 退货率 + 货损率) 倍的按件成本。
    - **尾程直接进分子**（``delivery_cost``，元/件）：旧的「尾程占收入比」字段
      与「成对生效」补丁已退役（桶里的运费拆不出来，对冲永远无解）。

    ``logistics_cost``（头程）/ ``storage_cost``（仓储）/ ``label_fee``（贴单）
    是批次 9 P2 的履约按件成本：**缺一项就少算那一项**，但**不因此不算底线**
    —— 它们是「逐步补齐型」成本（等业务录 SKU 体积），与采购成本 / SPU 两率
    这类「不可省略型」缺料不同；缺料原因由取数层报进 ``missing_reasons``，
    界面明示「未计入」。
    """
    cost = _decimal(purchase_cost)
    if cost is None:
        return None
    per_piece_cost = cost
    for extra in (logistics_cost, storage_cost, label_fee, delivery_cost):
        per_piece_cost += _decimal(extra) or Decimal("0")
    loss_multiplier = (
        Decimal("1")
        + (_decimal(spu_return_loss_rate) or Decimal("0"))
        + (_decimal(spu_damage_rate) or Decimal("0"))
    )
    numerator = per_piece_cost * loss_multiplier
    denominator = (
        Decimal("1")
        - (_decimal(platform_fee_rate) or Decimal("0"))
        - (_decimal(other_cost_rate) or Decimal("0"))
        - (_decimal(creator_commission_rate) or Decimal("0"))
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
    platform_fee_rate,
    other_cost_rate,
    spu_bound,
    spu_return_loss_rate,
    spu_damage_rate,
    policy,
    deepest_policy,
    min_selling_price_override,
    days_since_restock=None,
    delivery_cost=None,
    logistics_cost=None,
    storage_cost=None,
    label_fee=None,
    fulfillment_missing_reasons: Iterable[str] = (),
    free_shipping=True,
) -> dict:
    """单个 SKU 的完整定价字段。**纯函数**：无 ORM、无 DB、无 I/O。

    参数全是标量/字典，ORM 适配放在路由侧（`_compute_pricing_for_sku`）。
    这样降级链的 `missing_reasons`、分母 ≤ 0、折扣纪律的兜底
    都能写成**无 DB 单测**（spec §5.1「实现时只写一处」的要求）。

    `creator_commission_rate` 是 **SKU 自己的值**（可能为 None = 未单独设置）；
    `platform_creator_commission_rate` 是平台兜底，只用于**计算**，**不回填到返回值**——
    返回值里的 `creator_commission_rate` 必须仍是 None，前端输入框才显示「空 = 按平台默认」。

    `spu_bound` 与两个 SPU 率分开传，是为了区分两种缺料：
    没绑 SPU -> `missing_spu_binding`；绑了但率没维护 -> `missing_spu_rates`。

    平台佣金率（批次 9）：`platform_fee_rate` **单独进分母**，
    缺它 ⇒ `missing_platform_fee_rate` 且**不算底线**（不可省略型成本项）。

    尾程配送费（批次 9 B 路线）：`delivery_cost` 是这个 SKU 的**单件尾程**（元），
    **直接进分子**；旧的「尾程占收入比」与「成对生效」机制已退役。
    ⚠️ 不包邮 ⇒ 买家付运费 ⇒ 商家不承担尾程 ⇒ 尾程**完全不适用**：
    不进底线分子，**并且不报「缺尾程费率」**（不包邮的 SKU 压根不需要尾程费率，
    报缺是噪声，会把真缺料淹掉）。

    履约按件成本（批次 9 P2）：`logistics_cost`（头程）/ `storage_cost`（仓储）/
    `label_fee`（贴单）。**缺项不阻止计算**（逐步补齐型，等业务录 SKU 体积），
    缺料原因由取数层通过 `fulfillment_missing_reasons` 带进来。
    """
    missing_reasons: list[str] = []
    cost_floor = None
    discount_guard = None

    creator_rate = _decimal(creator_commission_rate)
    if creator_rate is None:
        creator_rate = _decimal(platform_creator_commission_rate)

    # 尾程（批次 9 B 路线）：直接进分子，不再有「成对生效」。
    # ⚠️ 不包邮 ⇒ 尾程不适用 ⇒ 分子不动（宁可不扣，也不要重复扣）。
    delivery_applied = bool(free_shipping) and delivery_cost is not None
    if free_shipping and delivery_cost is None:
        missing_reasons.append("missing_delivery_cost")

    missing_reasons.extend(fulfillment_missing_reasons)

    if policy is None:
        missing_reasons.append("missing_pricing_policy")
    else:
        fee_rate = _decimal(platform_fee_rate)
        other_rate = _decimal(other_cost_rate)
        return_loss_rate = _decimal(spu_return_loss_rate)
        damage_rate = _decimal(spu_damage_rate)
        purchase = _decimal(purchase_cost)
        if fee_rate is None:
            missing_reasons.append("missing_platform_fee_rate")
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
            and fee_rate is not None
            and other_rate is not None
            and creator_rate is not None
            and spu_bound
            and return_loss_rate is not None
            and damage_rate is not None
        ):
            cost_floor = compute_cost_floor(
                purchase_cost=purchase,
                platform_fee_rate=fee_rate,
                other_cost_rate=other_rate,
                creator_commission_rate=creator_rate,
                spu_return_loss_rate=return_loss_rate,
                spu_damage_rate=damage_rate,
                target_margin_rate=policy["target_margin_rate"],
                delivery_cost=delivery_cost if delivery_applied else None,
                logistics_cost=logistics_cost,
                storage_cost=storage_cost,
                label_fee=label_fee,
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
        # 尾程配送费（批次 9 B 路线）是否进了成本底线。
        # ⚠️ 现在**不再成对**：尾程只要有值（且该 SKU 包邮）就直接进分子。
        "delivery_cost_in_cost_floor": delivery_applied,
        # 包邮开关（批次 6）：前端要显示「不包邮 ⇒ 尾程不计入成本底线」。
        "free_shipping": bool(free_shipping),
        "cost_floor_delivery_cost": (
            float(_decimal(delivery_cost)) if delivery_applied else None
        ),
        # 履约按件成本（批次 9 P2）：头程 / 仓储 / 贴单。
        # ⚠️ None = 该项**未计入**（缺 SKU 体积或缺仓规则），不是「这项不要钱」。
        #    前端据此明示「未计入」，避免把偏松的底线当成算全了的数。
        "cost_floor_logistics_cost": (
            float(_decimal(logistics_cost)) if logistics_cost is not None else None
        ),
        "cost_floor_storage_cost": (
            float(_decimal(storage_cost)) if storage_cost is not None else None
        ),
        "cost_floor_label_fee": (
            float(_decimal(label_fee)) if label_fee is not None else None
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
