"""最低售价变更检测与通知。

**职责边界**（与飞书侧的分工，写死在本模块里）：

| 侧 | 负责什么 |
|---|---|
| ERP（本模块） | 检测最低售价变化 → 记录基线 → **只新增**行到飞书「调价记录表」 |
| 飞书（机器人） | 监听「完成」勾选 → 归档处理 |

ERP 侧**不做 update、不删除行、不管行归档到哪**。所以这里没有 search、没有
record_id 管理，只有一件事：算出「变了」并写进去。

**通知口径（2026-11-22 业务决定）：只通知「库龄跨档」**

原设计是「凡是底线变了的 SKU 全部通知」。现在**收紧**成「只有库龄跨档才通知」。

业务原话：*平台费率还在实践阶段，会经常调整* ⇒ 费率一动底线就动 ⇒ 通知表
被费率类变化刷屏，运营看不过来。采购成本、规则调整、参考售价补齐、数据缺失
（保护失效）、人工覆盖是同一类问题：它们变的是**定价输入**，不是**库龄档位**。

| 这次变化 | 现在怎么做 |
|---|---|
| 库龄跨档（档位身份真的变了） | **通知**（推飞书「调价记录表」） |
| 平台费率 / 采购成本 / 规则 / 参考售价补齐 / 数据缺失 / 人工覆盖 | **不通知**，但**留痕**（写进 outbox，`status='suppressed'`），日后可回溯 |

⚠️ **静默 ≠ 不管**：被静默的变化照样**推进基线**。否则明天还会被判定成同一次
变化，永远卡在同一天；后面真实的跨档也会被这坨噪音挡住。

⚠️ **静默要留痕**：被静默的变化照样写一行 outbox（`entity_type='price_adjust_suppressed'`、
`status='suppressed'`），保留归因上下文，供日后查「哪天因为什么变过」——
但**永不投递**到飞书。

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

# SKU ↔ SPU 归属关系的「当前有效」判定只从真源取（律 1）。
from backend.services.product_spu_binding import current_binding_condition

from .product_delivery_cost_service import compute_delivery_cost
from .product_finance_service import ProductFinanceService
from .product_pricing_query_service import (
    compute_pricing_state,
    load_pricing_context,
    resolve_effective_creator_rate,
)
from .product_fulfillment_cost_service import load_fulfillment_costs

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

# 被静默的调价变化在 outbox 里的标注（**留痕用**，不进飞书）。
#
# 2026-11-22 新口径：只有「库龄跨档」才通知；其余变化静默但留痕，
# 方便日后查「哪天因为什么变过」。
SUPPRESSED_REASON_NOT_TIER = "非库龄跨档"

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
    # 平台佣金率（批次 9）：它现在**单独进分母** ⇒ 变它必须能归因出来。
    "platform_fee_rate",
    "creator_commission_rate",
    "spu_return_loss_rate",
    "spu_damage_rate",
    "reference_selling_price",
    "min_selling_price",
    # 尾程配送费（批次 9 B 路线）：单件尾程，**直接进分子**。
    # ⚠️ 旧的「尾程占收入比」字段已随 core.dim_platforms.delivery_cost_rate 退役。
    "delivery_cost",
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


def classify_direction(old_price: Any, new_price: Any) -> Optional[str]:
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

    # 4) 平台费率（平台佣金率 / 平台其他成本率 / 达人佣金率）
    if (
        _numeric_changed(prev.get("platform_fee_rate"), cur.get("platform_fee_rate"))
        or _numeric_changed(prev.get("other_cost_rate"), cur.get("other_cost_rate"))
        or (
            _numeric_changed(
                prev.get("creator_commission_rate"), cur.get("creator_commission_rate")
            )
        )
    ):
        return REASON_PLATFORM_RATE

    # 5) 命中的档位本身变了 = 库龄跨档
    #    ⚠️ 比的是档位的**身份**（库龄起点），不是它的**显示名** ——
    #    显示名是可以改的（阶段 3 就把「滞销30天」改成「库龄≥60天」），
    #    拿显示名当身份 ⇒ 改一次名字，全库 SKU 都看起来"跨了档"
    #    ⇒ 最低售价变更通知会误报成「库龄跨档」⇒ 通知风暴。
    if tier_identity_changed(prev, cur):
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
        "platform_fee_rate",
        "creator_commission_rate",
        "spu_return_loss_rate",
        "spu_damage_rate",
        "reference_selling_price",
        # 尾程配送费（批次 9 B 路线）也是定价输入：它变了 ⇒ 这次跳高不只是"下架"造成的
        # ⇒ 仍然要通知（宁可多报，不可把真实变化静默吞掉）。
        "delivery_cost",
    ):
        if _numeric_changed(prev.get(key), cur.get(key)):
            return False
    if bool(prev.get("min_selling_price_is_override")) != bool(
        cur.get("min_selling_price_is_override")
    ):
        return False
    return True


def tier_identity_changed(prev: dict, cur: dict) -> bool:
    """库龄档位（**身份**）是否变了。

    ⚠️ 比的是**身份**（库龄起点 `pricing_tier_min_restock_days`），不是显示名 ——
    显示名是可以改的（阶段 3 就把「滞销30天」改成「库龄≥60天」），
    拿显示名当身份 ⇒ 改一次名字，全库 SKU 都看起来"跨了档" ⇒ 通知风暴。

    老快照（身份字段上线之前存下来的）没有身份字段 ⇒ 退回比显示名。
    """
    prev_key = prev.get("pricing_tier_min_restock_days")
    cur_key = cur.get("pricing_tier_min_restock_days")
    if prev_key is not None and cur_key is not None:
        return prev_key != cur_key
    return prev.get("pricing_tier_label") != cur.get("pricing_tier_label")


def is_tier_crossing(prev: dict, cur: dict) -> bool:
    """这次底线变化是不是「库龄跨档」造成的——**唯一会被通知的那一类**。

    判据（三条全中才算跨档）：

    1. **两次快照都有库龄数据**（`age_days` 都不是 None）
       ——没有库龄就没有"跨档"这回事：那是缺料（算不出底线）或下架。
    2. **两次快照都有档位身份**
       ——身份字段是后加的，老快照没有 ⇒ 无法判断，宁可**不通知**
       （也不用显示名硬猜：改一次档位显示名就会全库误报）。
    3. **身份真的不同**。

    ⚠️ 为什么把「有库龄数据」和「有档位身份」都设成硬条件：
    现在的通知口径是"只推库龄跨档"，所以判据必须**只认库龄**这一件事。
    缺料导致的档位塌陷、下架导致的回落档，都不是库龄调整，静默掉；
    老快照靠显示名硬猜，会在改档位显示名那天炸出一次通知风暴。
    """
    if prev.get("age_days") is None or cur.get("age_days") is None:
        return False
    prev_key = prev.get("pricing_tier_min_restock_days")
    cur_key = cur.get("pricing_tier_min_restock_days")
    if prev_key is None or cur_key is None:
        return False
    return prev_key != cur_key


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
    platform_code: Optional[str] = None,
    warehouse_code: Optional[str] = None,
    platform_fee_rate: Any = None,
    delivery_cost: Any = None,
) -> dict:
    """组装归因上下文快照。

    存的是**归因需要的全部输入**，这样下一次变化时能准确说出"为什么变"。

    ⚠️ `platform_code` 也要存进去：底线是「SKU × 平台 × 仓」的量，
    归因时得知道这次变的是哪个平台、哪个仓的底线。

    ⚠️ `warehouse_code`（批次 4）：底线拆到仓之后，**仓是归因的一部分**——
    同一个 SKU 在马来仓与新加坡仓的底线可以不同，不记仓就分不清是"哪边变了"。

    ⚠️ `platform_fee_rate`（批次 9）：平台佣金率现在**单独进分母** ⇒ 它是定价输入，
    变了必须归因出来。旧的 `delivery_cost_rate`（尾程占收入比）已随
    `core.dim_platforms.delivery_cost_rate` 退役 —— 尾程改成**直接进分子**，
    快照里只留单件 `delivery_cost` 就够说清"这次变是因为尾程费率调整"。
    """
    return {
        "platform_code": platform_code,
        "warehouse_code": warehouse_code,
        "min_selling_price": pricing.get("min_selling_price"),
        "min_selling_price_source": pricing.get("min_selling_price_source"),
        "min_selling_price_is_override": bool(
            pricing.get("min_selling_price_is_override")
        ),
        "pricing_tier_source": pricing.get("pricing_tier_source"),
        "pricing_tier_label": pricing.get("pricing_tier_label"),
        # 档位的**身份**（库龄起点）：显示名可以改（阶段 3 就改过），
        # 拿它当身份 ⇒ 改一次名字全库看起来都"跨了档" ⇒ 通知风暴。
        "pricing_tier_min_restock_days": pricing.get("pricing_tier_min_restock_days"),
        "target_margin_rate": _decimal_to_str(target_margin_rate),
        "discount_rate": _decimal_to_str(discount_rate),
        "age_days": age_days,
        "purchase_cost": _decimal_to_str(purchase_cost),
        "other_cost_rate": _decimal_to_str(other_cost_rate),
        "platform_fee_rate": _decimal_to_str(platform_fee_rate),
        "creator_commission_rate": _decimal_to_str(creator_commission_rate),
        "spu_return_loss_rate": _decimal_to_str(spu_return_loss_rate),
        "spu_damage_rate": _decimal_to_str(spu_damage_rate),
        "reference_selling_price": _decimal_to_str(reference_selling_price),
        "delivery_cost": _decimal_to_str(delivery_cost),
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
                    *current_binding_condition(),
                )
            )
        ).all()
        spu_by_sku = {row.sku_id: row.spu for row in bindings}
        if not spu_by_sku:
            return {sku_id: None for sku_id in sku_ids}

        spu_rows = (
            (
                await self.db.execute(
                    select(DimSpu).where(DimSpu.spu.in_(set(spu_by_sku.values())))
                )
            )
            .scalars()
            .all()
        )
        spu_map = {row.spu: row for row in spu_rows}
        return {sku_id: spu_map.get(spu_by_sku.get(sku_id)) for sku_id in sku_ids}

    async def collect_pricing_states(self) -> dict[tuple[int, str, str], dict]:
        """全量重算所有 active SKU 在**每个可定价平台 × 每个有库存的仓**上的最低售价与归因上下文。

        与商品中心走**同一个**计算函数、**同一份**库龄取数
        （`backend/services/product_pricing_query_service.py`），
        所以「页面显示的最低售价」和「通知里说的最低售价」必然一致。

        ⚠️ **键是 (sku_id, platform_code, warehouse_code)**（批次 4 仓维度统一）：
        底线是「SKU × 平台 × 仓」的量 —— 尾程配送费按「平台 × 仓 × 重量段」计价，
        同一件商品在不同仓的底线不同 ⇒ 基线也必须按仓分开记。

        ⚠️ **只对有库存的仓建状态**：一个仓里没有这个货，它的底线没有业务含义
        （那个仓的库龄档位也不存在）。状态层按 ``available_stock > 0`` 过滤，
        正好就是"这个仓还在卖这个品"。

        ⚠️ **仓维度数据整体取不到时**（状态层不可用 / 库存表为空），
        退回「SKU × 平台」口径（warehouse_code 用空串），
        行为与批次 4 之前逐字一致 —— 宁可少一个维度，也不能什么都不通知。
        """
        sku_rows = (
            (
                await self.db.execute(
                    select(DimErpSku).where(DimErpSku.status == "active")
                )
            )
            .scalars()
            .all()
        )
        if not sku_rows:
            return {}

        sku_ids = [row.sku_id for row in sku_rows]
        context = await load_pricing_context(self.db, sku_ids)
        spu_by_sku = await self._load_spu_by_sku(sku_ids)
        platform_codes = list(context.get("priceable_platform_codes") or [])
        restock_rows = context["restock_rows"]
        warehouse_restocks = context.get("warehouse_restocks") or {}

        # 有库存的仓（状态层按 available_stock > 0 过滤 ⇒ 正好是"还在卖的仓"）。
        warehouse_codes = sorted(
            {
                code
                for per_sku in warehouse_restocks.values()
                for code in per_sku.keys()
                if code
            }
        )
        # ⚠️ 仓维度数据整体缺失 ⇒ 退回 SKU × 平台口径（空串仓）。
        if not warehouse_codes:
            warehouse_codes = [""]
        finance = ProductFinanceService(self.db)

        # 履约按件成本（批次 9 P2）：头程 / 仓储 / 贴单是**仓级规则 × SKU 体积**。
        # ⚠️ 这里按**每个仓各取一份**（仓不一样 ⇒ 规则不一样 ⇒ 成本不一样），
        #    再注入各自的 context —— 与商品中心页面「按当前选中的仓算」同口径，
        #    两边算出来的底线必然一致（否则通知会误报「底线变了」）。
        fulfillment_by_warehouse: dict[str, dict[int, dict]] = {}
        for code in warehouse_codes:
            fulfillment_by_warehouse[code] = await load_fulfillment_costs(
                self.db, sku_rows, code or None
            )

        states: dict[tuple[int, str, str], dict] = {}
        for platform_code in platform_codes:
            platform = context["platforms"].get(platform_code)
            other_cost_rate = platform.other_cost_rate if platform else None
            # 尾程费率（批次 4）：按仓定价 ⇒ 一次取该平台**所有仓**的档位，
            # 内存里按仓分组（避免逐仓查库）。
            all_tiers = await finance.find_delivery_rate_tiers(platform_code)
            tiers_by_warehouse: dict[str, list] = {}
            for tier in all_tiers:
                tiers_by_warehouse.setdefault(tier.warehouse_code, []).append(tier)
            for warehouse_code in warehouse_codes:
                # 每个仓用**自己的库龄**算档位（阶段 6 的仓维度口径）。
                # 履约按件成本（批次 9 P2）也按仓注入 —— 与页面的仓口径一致。
                warehouse_context = {
                    **context,
                    "fulfillment_costs": fulfillment_by_warehouse.get(
                        warehouse_code, {}
                    ),
                }
                if warehouse_code:
                    warehouse_context = {
                        **warehouse_context,
                        "days_since_restock": {
                            sku_id: (
                                (warehouse_restocks.get(sku_id) or {}).get(
                                    warehouse_code
                                )
                                or {}
                            ).get("days_since_restock")
                            for sku_id in context["days_since_restock"]
                        },
                    }
                for row in sku_rows:
                    if warehouse_code and warehouse_code not in (
                        warehouse_restocks.get(row.sku_id) or {}
                    ):
                        # 这个仓没有这个货 ⇒ 不建状态（底线没有业务含义）。
                        continue
                    linked_spu = spu_by_sku.get(row.sku_id)
                    # 尾程配送费（批次 4）：按「平台 × 仓 × 重量段」算。
                    # ⚠️ 包邮开关由 ``compute_pricing_state`` 内部按 SKU × 平台判定
                    #    （不包邮 ⇒ 尾程不进底线，也不报缺费率）。
                    delivery_result = compute_delivery_cost(
                        tiers_by_warehouse.get(warehouse_code, []),
                        row.weight_tier_code,
                        fallback_tiers=all_tiers,
                    )
                    state = compute_pricing_state(
                        context=warehouse_context,
                        sku_row=row,
                        linked_spu=linked_spu,
                        platform_code=platform_code,
                        delivery_cost=delivery_result.amount,
                    )
                    pricing = state["pricing"]
                    policy = state["policy"]
                    days_since_restock = state["days_since_restock"]
                    # ⚠️ **包邮开关**（批次 6）：快照里记的必须是**实际计入**的尾程。
                    #    不包邮 ⇒ 商家不承担 ⇒ 记 0；否则归因会说"尾程涨了 5 元所以底线跳高"，
                    #    而这笔尾程压根没进底线（会误导排查）。
                    applied_delivery_cost = (
                        delivery_result.amount
                        if state.get("free_shipping")
                        else Decimal("0")
                    )
                    restock_row = (
                        (warehouse_restocks.get(row.sku_id) or {}).get(warehouse_code)
                        if warehouse_code
                        else restock_rows.get(row.sku_id)
                    )

                    snapshot = build_context(
                        pricing=pricing,
                        age_days=days_since_restock,
                        target_margin_rate=(
                            policy["target_margin_rate"] if policy else None
                        ),
                        discount_rate=(policy["discount_rate"] if policy else None),
                        purchase_cost=row.default_purchase_cost,
                        other_cost_rate=other_cost_rate,
                        creator_commission_rate=resolve_effective_creator_rate(
                            context=context,
                            sku_row=row,
                            platform_code=platform_code,
                        ),
                        spu_return_loss_rate=(
                            linked_spu.return_loss_rate if linked_spu else None
                        ),
                        spu_damage_rate=(
                            linked_spu.logistics_damage_rate if linked_spu else None
                        ),
                        reference_selling_price=row.reference_selling_price,
                        platform_code=platform_code,
                        warehouse_code=warehouse_code,
                        delivery_cost=applied_delivery_cost,
                        platform_fee_rate=(
                            platform.default_fee_rate if platform else None
                        ),
                    )

                    states[(row.sku_id, platform_code, warehouse_code)] = {
                        "sku_id": row.sku_id,
                        "platform_code": platform_code,
                        "warehouse_code": warehouse_code,
                        "sku_key": row.sku_key,
                        "spu": linked_spu.spu if linked_spu else None,
                        "sku_name": row.sku_name,
                        "specification": row.specification,
                        "min_selling_price": pricing.get("min_selling_price"),
                        "context": snapshot,
                        "age_days": days_since_restock,
                        "current_qty": (
                            restock_row.get("current_qty") if restock_row else None
                        ),
                        "inventory_value": (
                            restock_row.get("inventory_value") if restock_row else None
                        ),
                    }
        return states

    async def load_baselines(self) -> dict[tuple[int, str, str], dict]:
        """已建基线的 SKU × 平台 × 仓：``{(sku_id, platform_code, warehouse_code): {...}}``。

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
                    PriceAdjustBaseline.platform_code,
                    PriceAdjustBaseline.warehouse_code,
                    PriceAdjustBaseline.last_notified_min_price,
                    PriceAdjustBaseline.last_notified_context,
                )
            )
        ).all()
        baselines: dict[tuple[int, str, str], dict] = {}
        for row in rows:
            baselines[(row.sku_id, row.platform_code, row.warehouse_code)] = {
                "min_selling_price": row.last_notified_min_price,
                "context": dict(row.last_notified_context or {}),
            }
        return baselines

    # ------------------------------------------------------------------
    # 比对
    # ------------------------------------------------------------------

    async def detect_changes(self) -> tuple[list[dict], list[dict], list[dict]]:
        """比对当前状态与基线。

        返回 ``(需要通知的变更, 需要静默推进基线的条目, 被静默但留痕的变更)``。

        **通知口径（2026-11-22）**：只有「库龄跨档」才通知（见模块说明）。

        - **需要通知**：库龄跨档 ⇒ 底线变了，且变的原因是档位真的挪了。
        - **静默推进基线**（不通知、不留痕）：
          1. 首次建基线（此前没有基线）——不通知，但要有基线，否则明天会误判成"变了"
          2. 底线没变（只是库龄在档内前进）——顺手把基线上下文刷新成当前状态
          3. 「下架造成的跳高」——语义上不成立的变更，不通知，但基线必须跟上，
             否则明天还会重复判定为同一次跳高
        - **静默但留痕**：底线变了，但不是库龄跨档（费率 / 采购成本 / 规则 /
          参考售价补齐 / 数据缺失 / 人工覆盖）——写进 outbox 供回溯，**不推飞书**。
          基线照样推进（否则明天还会重复判定为同一次变化）。
        """
        states = await self.collect_pricing_states()
        baselines = await self.load_baselines()

        notify: list[dict] = []
        silent: list[dict] = []
        suppressed: list[dict] = []

        for (sku_id, platform_code, warehouse_code), cur in states.items():
            prev = baselines.get((sku_id, platform_code, warehouse_code))
            new_price = cur["min_selling_price"]

            if prev is None:
                # 首次建基线：只记基线，不通知
                silent.append(
                    {
                        "sku_id": sku_id,
                        "platform_code": platform_code,
                        "warehouse_code": warehouse_code,
                        "min_selling_price": new_price,
                        "context": cur["context"],
                    }
                )
                continue

            old_price = prev["min_selling_price"]
            direction = classify_direction(old_price, new_price)
            if direction is None:
                # 底线没变 → 不是一次变更。
                # ⚠️ 但**要把基线上下文刷新成当前状态**：老快照可能压根没有档位身份
                #    （身份字段上线之前存下来的），不刷新的话后面真的跨档也判不出来；
                #    而且上下文过期会让下一次变化被归因到错误的原因上。
                silent.append(
                    {
                        "sku_id": sku_id,
                        "platform_code": platform_code,
                        "warehouse_code": warehouse_code,
                        "min_selling_price": new_price,
                        "context": cur["context"],
                    }
                )
                continue

            prev_context = prev["context"]
            cur_context = cur["context"]

            if direction == DIRECTION_UP and is_delisting_jump(
                prev_context, cur_context
            ):
                # 下架造成的跳高：排除，但基线要跟上
                silent.append(
                    {
                        "sku_id": sku_id,
                        "platform_code": platform_code,
                        "warehouse_code": warehouse_code,
                        "min_selling_price": new_price,
                        "context": cur_context,
                    }
                )
                continue

            change = {
                "sku_id": sku_id,
                "platform_code": platform_code,
                "warehouse_code": warehouse_code,
                "sku_key": cur["sku_key"],
                "spu": cur["spu"],
                "sku_name": cur["sku_name"],
                "specification": cur["specification"],
                # 基线推进要用的是**原始数值**（`_decimal_to_str` 出来的是字符串）。
                "min_selling_price": new_price,
                "old_min_selling_price": _decimal_to_str(old_price),
                "new_min_selling_price": _decimal_to_str(new_price),
                "change_rate": compute_change_rate(old_price, new_price),
                "direction": direction,
                "pricing_tier_label": cur_context.get("pricing_tier_label"),
                "age_days": cur.get("age_days"),
                "current_qty": cur.get("current_qty"),
                "inventory_value": cur.get("inventory_value"),
                "context": cur_context,
            }

            if is_tier_crossing(prev_context, cur_context):
                # 库龄跨档 —— **唯一会被通知的那一类**。
                # 「变动原因」固定写「库龄档位变化」：这一列在飞书表里是单选，
                # 写别的值只会让运营看到"库龄跨档的行却写着平台费率变化"。
                change["reason"] = REASON_TIER_CHANGE
                notify.append(change)
                continue

            # 不是库龄跨档 → 不推送，但**留痕**（归因写清楚，静默原因也写清楚）。
            change["reason"] = classify_change_reason(prev_context, cur_context)
            change["suppressed"] = True
            change["suppression_reason"] = SUPPRESSED_REASON_NOT_TIER
            suppressed.append(change)

        return notify, silent, suppressed

    # ------------------------------------------------------------------
    # 基线推进
    # ------------------------------------------------------------------

    async def advance_baselines(self, entries: list[dict]) -> int:
        """批量推进基线（首次建基线 / 被排除的变更）。

        一次 SELECT 把已有基线读出来，内存里 upsert，再批量写回——
        逐条 SELECT+INSERT 会让上千个 SKU × 平台跑成两千多次往返。

        写的是 ``ops.price_adjust_baselines``，**不碰** ``core.dim_erp_sku``：
        后者会被商品中心同步 TRUNCATE 掉。
        """
        if not entries:
            return 0

        sku_ids = {entry["sku_id"] for entry in entries}
        platform_codes = {entry["platform_code"] for entry in entries}
        existing = {
            (row.sku_id, row.platform_code, row.warehouse_code): row
            for row in (
                await self.db.execute(
                    select(PriceAdjustBaseline).where(
                        PriceAdjustBaseline.sku_id.in_(sku_ids),
                        PriceAdjustBaseline.platform_code.in_(platform_codes),
                    )
                )
            )
            .scalars()
            .all()
        }

        for entry in entries:
            sku_id = entry["sku_id"]
            platform_code = entry["platform_code"]
            # ⚠️ 仓维度（批次 4）：主键是 (sku_id, platform_code, warehouse_code)。
            #    空串 = 「没有仓维度」的回落口径（仓维度数据整体缺失时用）。
            warehouse_code = entry.get("warehouse_code") or ""
            price = entry["min_selling_price"]
            context = entry["context"]
            row = existing.get((sku_id, platform_code, warehouse_code))
            if row is None:
                self.db.add(
                    PriceAdjustBaseline(
                        sku_id=sku_id,
                        platform_code=platform_code,
                        warehouse_code=warehouse_code,
                        last_notified_min_price=_to_decimal(price),
                        last_notified_context=context,
                    )
                )
            else:
                row.last_notified_min_price = _to_decimal(price)
                row.last_notified_context = context
        await self.db.flush()
        return len(entries)

    async def advance_baseline_for_sku(
        self,
        sku_id: int,
        price: Any,
        context: dict,
        platform_code: str | None = None,
        warehouse_code: str | None = None,
    ) -> None:
        """推进单个 SKU 在某平台某仓的基线——**投递成功后**调用。

        写入 ``ops.price_adjust_baselines``，不碰 ``core.dim_erp_sku``——
        后者会被商品中心同步 TRUNCATE 掉。

        这里用「先查后写」而不是方言专属的 ``ON CONFLICT``：
        基线写入是低频（每天一次 × 变更数）且由单个任务串行执行，
        先查后写在 PostgreSQL / SQLite 上行为一致，不必写两套方言分支。

        ⚠️ `platform_code` 不传时回落到历史 basis 平台，
        只为兼容老调用方；新代码必须显式传平台。

        ⚠️ `warehouse_code` 不传时回落到快照里的仓，再回落到空串
        （= 没有仓维度的回落口径）。新代码必须显式传仓。
        """
        platform_code = platform_code or context.get("platform_code") or "tiktok"
        warehouse_code = (
            warehouse_code
            if warehouse_code is not None
            else (context.get("warehouse_code") or "")
        )
        row = (
            await self.db.execute(
                select(PriceAdjustBaseline).where(
                    PriceAdjustBaseline.sku_id == sku_id,
                    PriceAdjustBaseline.platform_code == platform_code,
                    PriceAdjustBaseline.warehouse_code == warehouse_code,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            self.db.add(
                PriceAdjustBaseline(
                    sku_id=sku_id,
                    platform_code=platform_code,
                    warehouse_code=warehouse_code,
                    last_notified_min_price=_to_decimal(price),
                    last_notified_context=context,
                )
            )
        else:
            row.last_notified_min_price = _to_decimal(price)
            row.last_notified_context = context
        await self.db.flush()
