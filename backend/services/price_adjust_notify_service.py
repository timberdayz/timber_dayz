"""最低售价变更检测与通知。

**职责边界**（与飞书侧的分工，写死在本模块里）：

| 侧 | 负责什么 |
|---|---|
| ERP（本模块） | 检测最低售价变化 → 记录基线 → **只新增**行到飞书「调价记录表」 |
| 飞书（机器人） | 监听「完成」勾选 → 归档处理 |

ERP 侧**不做 update、不删除行、不管行归档到哪**。所以这里没有 search、没有
record_id 管理，只有一件事：算出「变了」并写进去。

**为什么需要基线**：自动算出来的最低售价**不落库**（见
`product_pricing_service.compute_sku_pricing` 的设计决策），库里只有一个静态的
人工覆盖值。系统能回答"现在最低卖多少钱"，但从来没有回答过"比上次是高了还是低了"。
`ops.price_adjust_baselines` 就是补上这个记忆的唯一地方。

**基线为什么不住在 `core.dim_erp_sku` 上**：商品中心的 SKU 主数据有一条
「采集机 → 云端」的同步链路，它对 `core.dim_erp_sku` 做的是 **TRUNCATE + 全量重灌**。
基线若住在那张表里，每次同步都会被抹成"从未处理过"——
**同步窗口内真实发生的底线变化会被静默吞掉**，与"一个都不能漏"直接冲突。
所以基线住在 `ops` 域：与 `feishu_projection_tasks`（通知 outbox）同域，语义一致
（都是"通知进度状态"，不是"商品主数据"），且**不参与商品中心同步**。

**基线推进的顺序（不能反）**：ERP 只新增、不更新，没有"重写旧行"这个补救动作。
所以必须**投递成功之后**才推进基线——否则飞书写失败（限流 1254291、网络抖动、
token 过期）时基线已被推进，那次变化就永远不会再被检出，等于把最该通知的变化静默吞掉。

**模块分层**：

- 纯函数（无 ORM、无 DB、无 I/O）：归因、方向、幅度、排除判定 → 可写成无 DB 单测
- 服务类（碰 DB）：批量取数、比对、生成投递任务、推进基线
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import BridgeSpuSku, DimErpSku, DimSpu, PriceAdjustBaseline

from .product_pricing_query_service import (
    compute_pricing_state,
    load_pricing_context,
    resolve_effective_creator_rate,
)

# ---------------------------------------------------------------------------
# 常量：变动原因 / 变动方向
# 与飞书「调价记录表」的「变动原因」「变动方向」单选选项一一对应。
# ---------------------------------------------------------------------------

REASON_TIER_CHANGE = "库龄档位变化"
REASON_PURCHASE_COST = "采购成本变化"
REASON_PLATFORM_RATE = "平台费率变化"
REASON_POLICY = "规则调整"
REASON_REFERENCE_PRICE = "参考售价补齐"
REASON_DATA_MISSING = "数据缺失"
REASON_MANUAL_OVERRIDE = "人工覆盖"

DIRECTION_DOWN = "下降"
DIRECTION_UP = "上升"
DIRECTION_PROTECTION_LOST = "保护失效"

# 库龄来源标记（来自 product_pricing_service.compute_sku_pricing）
TIER_SOURCE_AGE = "restock_days"
TIER_SOURCE_FALLBACK = "fallback_no_restock_days"

# 归因上下文里保存的字段。刻意**不含时间戳**——outbox 的 payload 哈希是去重依据，
# 时间戳每次都变会让同一次变化重跑时哈希不同、去重失效。
CONTEXT_NUMERIC_KEYS = (
    "target_margin_rate",
    "discount_rate",
    "purchase_cost",
    "other_cost_rate",
    "creator_commission_rate",
    "spu_return_loss_rate",
    "spu_damage_rate",
    "reference_selling_price",
    "min_selling_price",
)


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None


def _numeric_changed(old: Any, new: Any) -> bool:
    """两个数值是否真的不同（None 与 None 视为相同）。"""
    old_dec = _to_decimal(old)
    new_dec = _to_decimal(new)
    if old_dec is None and new_dec is None:
        return False
    if old_dec is None or new_dec is None:
        return True
    return old_dec != new_dec


def classify_direction(
    old_price: Any, new_price: Any
) -> Optional[str]:
    """这次变化的方向。

    返回 None 表示「底线数值没变」，不是一次需要通知的变更。

    - 下降：底线降低 = 授权更低价卖（清货机会）
    - 上升：底线抬高 = 收权；**若平台售价没跟上就是在亏本卖**
    - 保护失效：从"算得出"变成"算不出" = 底线保护没了
    """
    old_dec = _to_decimal(old_price)
    new_dec = _to_decimal(new_price)

    if old_dec is None and new_dec is None:
        return None
    if old_dec is None:
        # 从"算不出底线"变成"算得出"：底线从无到有 = 变严格了
        return DIRECTION_UP
    if new_dec is None:
        return DIRECTION_PROTECTION_LOST
    if new_dec > old_dec:
        return DIRECTION_UP
    if new_dec < old_dec:
        return DIRECTION_DOWN
    return None


def compute_change_rate(old_price: Any, new_price: Any) -> Optional[float]:
    """变动幅度 =（新 − 旧）÷ 旧。负数表示底线下降。分母为 0 / 缺失时留空。"""
    old_dec = _to_decimal(old_price)
    new_dec = _to_decimal(new_price)
    if old_dec is None or new_dec is None or old_dec == 0:
        return None
    return float((new_dec - old_dec) / old_dec)


def classify_change_reason(prev: dict, cur: dict) -> str:
    """判断这次底线变化的主因。

    **固定优先级，取第一个匹配的**——不做贡献度拆解（那需要大量额外计算和字段，
    而业务上运营只需要知道"主要因为什么"）。

    优先级从"最具体"到"最宽泛"：单个 SKU 的输入 → 全局规则 → 库龄档位。
    """
    # 1) 降级链状态变了：从"缺料算不出"变"算得出"，或反之
    prev_missing = sorted(prev.get("missing_reasons") or [])
    cur_missing = sorted(cur.get("missing_reasons") or [])
    if prev_missing != cur_missing:
        return REASON_DATA_MISSING

    # 2) 人工接管 / 交回
    if bool(prev.get("min_selling_price_is_override")) != bool(
        cur.get("min_selling_price_is_override")
    ):
        return REASON_MANUAL_OVERRIDE

    # 3) 采购成本
    if _numeric_changed(prev.get("purchase_cost"), cur.get("purchase_cost")):
        return REASON_PURCHASE_COST

    # 4) 平台费率（平台其他成本率 / 达人佣金率）
    if _numeric_changed(prev.get("other_cost_rate"), cur.get("other_cost_rate")) or (
        _numeric_changed(
            prev.get("creator_commission_rate"), cur.get("creator_commission_rate")
        )
    ):
        return REASON_PLATFORM_RATE

    # 5) 命中的档位本身变了 = 库龄跨档
    if prev.get("pricing_tier_label") != cur.get("pricing_tier_label"):
        return REASON_TIER_CHANGE

    # 6) 档位没变但折扣率变了 = 规则表在同一档上改了参数
    if _numeric_changed(prev.get("discount_rate"), cur.get("discount_rate")):
        return REASON_POLICY

    # 7) 参考售价补齐（纪律线开始生效）
    if _numeric_changed(
        prev.get("reference_selling_price"), cur.get("reference_selling_price")
    ):
        return REASON_REFERENCE_PRICE

    # 兜底：目标利润率在同一档被改了
    return REASON_POLICY


def is_delisting_jump(prev: dict, cur: dict) -> bool:
    """这是不是「下架造成的跳高」——语义上不成立的变更，**不该通知**。

    场景：库存清零 → 该 SKU 从库龄表消失 → 库龄回落第 1 档（日常，目标利润率最高）
    → 底线跳回全档最高位。但这个品**已经不卖了**，底线高低没有业务含义。
    不排除的话，机器人会持续收到"某个已下架的品，底线从 ¥90 涨到 ¥128"的通知。

    判定：库龄来源从"按库龄"变成"无库龄回落"，**且其它定价输入一个都没变**。
    只要还有别的输入也变了，这次变化就不只是"下架"造成的 → 仍然要通知。
    """
    if prev.get("pricing_tier_source") != TIER_SOURCE_AGE:
        return False
    if cur.get("pricing_tier_source") != TIER_SOURCE_FALLBACK:
        return False

    for key in (
        "purchase_cost",
        "other_cost_rate",
        "creator_commission_rate",
        "spu_return_loss_rate",
        "spu_damage_rate",
        "reference_selling_price",
    ):
        if _numeric_changed(prev.get(key), cur.get(key)):
            return False
    if bool(prev.get("min_selling_price_is_override")) != bool(
        cur.get("min_selling_price_is_override")
    ):
        return False
    return True


def build_context(
    *,
    pricing: dict,
    age_days: Optional[int],
    target_margin_rate: Any,
    discount_rate: Any,
    purchase_cost: Any,
    other_cost_rate: Any,
    creator_commission_rate: Any,
    spu_return_loss_rate: Any,
    spu_damage_rate: Any,
    reference_selling_price: Any,
) -> dict:
    """组装归因上下文快照。

    存的是**归因需要的全部输入**，这样下一次变化时能准确说出"为什么变"。
    """
    return {
        "min_selling_price": pricing.get("min_selling_price"),
        "min_selling_price_source": pricing.get("min_selling_price_source"),
        "min_selling_price_is_override": bool(pricing.get("min_selling_price_is_override")),
        "pricing_tier_source": pricing.get("pricing_tier_source"),
        "pricing_tier_label": pricing.get("pricing_tier_label"),
        "target_margin_rate": _decimal_to_str(target_margin_rate),
        "discount_rate": _decimal_to_str(discount_rate),
        "age_days": age_days,
        "purchase_cost": _decimal_to_str(purchase_cost),
        "other_cost_rate": _decimal_to_str(other_cost_rate),
        "creator_commission_rate": _decimal_to_str(creator_commission_rate),
        "spu_return_loss_rate": _decimal_to_str(spu_return_loss_rate),
        "spu_damage_rate": _decimal_to_str(spu_damage_rate),
        "reference_selling_price": _decimal_to_str(reference_selling_price),
        "missing_reasons": list(pricing.get("min_selling_price_missing_reasons") or []),
    }


def _decimal_to_str(value: Any) -> Optional[str]:
    """JSON 存不下 Decimal，统一转字符串再存，避免二进制浮点误差。"""
    dec = _to_decimal(value)
    return str(dec) if dec is not None else None


class PriceAdjustNotifyService:
    """最低售价变更检测。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # 取数
    # ------------------------------------------------------------------

    async def _load_spu_by_sku(self, sku_ids: list[int]) -> dict[int, Optional[DimSpu]]:
        """按 SKU 取生效的 SPU 绑定与 SPU 行。

        返回 ``{sku_id: DimSpu | None}``；None 表示「没绑 SPU」或「绑的 SPU 行查不到」
        ——两种情况都按 `missing_spu_binding` 缺料处理，与商品中心页面口径一致。
        """
        if not sku_ids:
            return {}
        bindings = (
            await self.db.execute(
                select(BridgeSpuSku.sku_id, BridgeSpuSku.spu).where(
                    BridgeSpuSku.sku_id.in_(sku_ids),
                    BridgeSpuSku.binding_status == "active",
                    BridgeSpuSku.effective_to.is_(None),
                )
            )
        ).all()
        spu_by_sku = {row.sku_id: row.spu for row in bindings}
        if not spu_by_sku:
            return {sku_id: None for sku_id in sku_ids}

        spu_rows = (
            await self.db.execute(
                select(DimSpu).where(DimSpu.spu.in_(set(spu_by_sku.values())))
            )
        ).scalars().all()
        spu_map = {row.spu: row for row in spu_rows}
        return {sku_id: spu_map.get(spu_by_sku.get(sku_id)) for sku_id in sku_ids}

    async def collect_pricing_states(self) -> dict[int, dict]:
        """全量重算所有 active SKU 的最低售价与归因上下文。

        与商品中心走**同一个**计算函数、**同一份**库龄取数
        （`backend/services/product_pricing_query_service.py`），
        所以「页面显示的最低售价」和「通知里说的最低售价」必然一致。
        """
        sku_rows = (
            await self.db.execute(
                select(DimErpSku).where(DimErpSku.status == "active")
            )
        ).scalars().all()
        if not sku_rows:
            return {}

        sku_ids = [row.sku_id for row in sku_rows]
        context = await load_pricing_context(self.db, sku_ids)
        spu_by_sku = await self._load_spu_by_sku(sku_ids)
        platform = context["platform"]
        other_cost_rate = platform.other_cost_rate if platform else None
        restock_rows = context["restock_rows"]

        states: dict[int, dict] = {}
        for row in sku_rows:
            linked_spu = spu_by_sku.get(row.sku_id)
            state = compute_pricing_state(
                context=context,
                sku_row=row,
                linked_spu=linked_spu,
            )
            pricing = state["pricing"]
            policy = state["policy"]
            days_since_restock = state["days_since_restock"]
            restock_row = restock_rows.get(row.sku_id)

            snapshot = build_context(
                pricing=pricing,
                age_days=days_since_restock,
                target_margin_rate=policy["target_margin_rate"] if policy else None,
                discount_rate=policy["discount_rate"] if policy else None,
                purchase_cost=row.default_purchase_cost,
                other_cost_rate=other_cost_rate,
                creator_commission_rate=resolve_effective_creator_rate(
                    context=context, sku_row=row
                ),
                spu_return_loss_rate=linked_spu.return_loss_rate if linked_spu else None,
                spu_damage_rate=linked_spu.logistics_damage_rate if linked_spu else None,
                reference_selling_price=row.reference_selling_price,
            )

            states[row.sku_id] = {
                "sku_id": row.sku_id,
                "sku_key": row.sku_key,
                "spu": linked_spu.spu if linked_spu else None,
                "sku_name": row.sku_name,
                "specification": row.specification,
                "min_selling_price": pricing.get("min_selling_price"),
                "context": snapshot,
                "age_days": days_since_restock,
                "current_qty": restock_row.get("current_qty") if restock_row else None,
                "inventory_value": restock_row.get("inventory_value") if restock_row else None,
            }
        return states

    async def load_baselines(self) -> dict[int, dict]:
        """已建基线的 SKU：{sku_id: {"min_selling_price": Decimal|None, "context": dict}}。

        基线住在 ``ops.price_adjust_baselines``（**不参与商品中心同步**）：
        ``core.dim_erp_sku`` 会被「采集机 → 云端」同步做 TRUNCATE + 全量重灌，
        基线若住在那儿，每次同步都会被抹掉，同步窗口内的真实变化会被静默吞掉。

        ⚠️ **判据是"有没有基线行"，不是"价格列是不是 NULL"**：
        算不出最低售价的 SKU（缺采购成本 / 缺 SPU 率）它的基线价格本来就是 NULL，
        但它**同样被处理过**、同样有上下文。如果按价格是否为空过滤，
        这些 SKU 会永远被当成"首次建基线"：
        - 每天重复重建基线，白写一次库
        - 更糟：等它哪天**算得出**底线了（补了采购成本），仍然被当成首次建基线 →
          「底线从算不出变成算得出」这个变化**永远不会通知**。
        """
        rows = (
            await self.db.execute(
                select(
                    PriceAdjustBaseline.sku_id,
                    PriceAdjustBaseline.last_notified_min_price,
                    PriceAdjustBaseline.last_notified_context,
                )
            )
        ).all()
        baselines: dict[int, dict] = {}
        for row in rows:
            baselines[row.sku_id] = {
                "min_selling_price": row.last_notified_min_price,
                "context": dict(row.last_notified_context or {}),
            }
        return baselines

    # ------------------------------------------------------------------
    # 比对
    # ------------------------------------------------------------------

    async def detect_changes(self) -> tuple[list[dict], list[dict]]:
        """比对当前状态与基线。

        返回 ``(需要通知的变更, 需要静默推进基线的条目)``。

        静默推进的两类：
        1. 首次建基线（此前没有基线）——不通知，但要有基线，否则明天会误判成"变了"
        2. 「下架造成的跳高」——语义上不成立的变更，不通知，但基线必须跟上，
           否则明天还会重复判定为同一次跳高
        """
        states = await self.collect_pricing_states()
        baselines = await self.load_baselines()

        notify: list[dict] = []
        silent: list[dict] = []

        for sku_id, cur in states.items():
            prev = baselines.get(sku_id)
            new_price = cur["min_selling_price"]

            if prev is None:
                # 首次建基线：只记基线，不通知
                silent.append(
                    {
                        "sku_id": sku_id,
                        "min_selling_price": new_price,
                        "context": cur["context"],
                    }
                )
                continue

            old_price = prev["min_selling_price"]
            direction = classify_direction(old_price, new_price)
            if direction is None:
                # 底线没变 → 不是一次需要通知的变更，基线保持不动
                continue

            prev_context = prev["context"]
            cur_context = cur["context"]
            reason = classify_change_reason(prev_context, cur_context)

            if direction == DIRECTION_UP and is_delisting_jump(prev_context, cur_context):
                # 下架造成的跳高：排除，但基线要跟上
                silent.append(
                    {
                        "sku_id": sku_id,
                        "min_selling_price": new_price,
                        "context": cur_context,
                    }
                )
                continue

            notify.append(
                {
                    "sku_id": sku_id,
                    "sku_key": cur["sku_key"],
                    "spu": cur["spu"],
                    "sku_name": cur["sku_name"],
                    "specification": cur["specification"],
                    "old_min_selling_price": _decimal_to_str(old_price),
                    "new_min_selling_price": _decimal_to_str(new_price),
                    "change_rate": compute_change_rate(old_price, new_price),
                    "direction": direction,
                    "reason": reason,
                    "pricing_tier_label": cur_context.get("pricing_tier_label"),
                    "age_days": cur.get("age_days"),
                    "current_qty": cur.get("current_qty"),
                    "inventory_value": cur.get("inventory_value"),
                    "context": cur_context,
                }
            )

        return notify, silent

    # ------------------------------------------------------------------
    # 基线推进
    # ------------------------------------------------------------------

    async def advance_baselines(self, entries: list[dict]) -> int:
        """批量推进基线（首次建基线 / 被排除的变更）。

        一次 SELECT 把已有基线读出来，内存里 upsert，再批量写回——
        逐条 SELECT+INSERT 会让 1122 个 SKU 跑成两千多次往返。

        写的是 ``ops.price_adjust_baselines``，**不碰** ``core.dim_erp_sku``：
        后者会被商品中心同步 TRUNCATE 掉。
        """
        if not entries:
            return 0

        sku_ids = [entry["sku_id"] for entry in entries]
        existing = {
            row.sku_id: row
            for row in (
                await self.db.execute(
                    select(PriceAdjustBaseline).where(
                        PriceAdjustBaseline.sku_id.in_(sku_ids)
                    )
                )
            ).scalars().all()
        }

        for entry in entries:
            sku_id = entry["sku_id"]
            price = entry["min_selling_price"]
            context = entry["context"]
            row = existing.get(sku_id)
            if row is None:
                self.db.add(
                    PriceAdjustBaseline(
                        sku_id=sku_id,
                        last_notified_min_price=_to_decimal(price),
                        last_notified_context=context,
                    )
                )
            else:
                row.last_notified_min_price = _to_decimal(price)
                row.last_notified_context = context
        await self.db.flush()
        return len(entries)

    async def advance_baseline_for_sku(self, sku_id: int, price: Any, context: dict) -> None:
        """推进单个 SKU 的基线——**投递成功后**调用。

        写入 ``ops.price_adjust_baselines``，不碰 ``core.dim_erp_sku``——
        后者会被商品中心同步 TRUNCATE 掉。

        这里用「先查后写」而不是方言专属的 ``ON CONFLICT``：
        基线写入是低频（每天一次 × 变更数）且由单个任务串行执行，
        先查后写在 PostgreSQL / SQLite 上行为一致，不必写两套方言分支。
        """
        row = (
            await self.db.execute(
                select(PriceAdjustBaseline).where(PriceAdjustBaseline.sku_id == sku_id)
            )
        ).scalar_one_or_none()
        if row is None:
            self.db.add(
                PriceAdjustBaseline(
                    sku_id=sku_id,
                    last_notified_min_price=_to_decimal(price),
                    last_notified_context=context,
                )
            )
        else:
            row.last_notified_min_price = _to_decimal(price)
            row.last_notified_context = context
        await self.db.flush()
