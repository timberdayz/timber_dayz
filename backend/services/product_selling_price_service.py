"""基准售价治理的服务层（阶段 4）。

阶段 4 交付四样工具，本模块是其中三样的实现：

======================  ==========================================  ====================
工具                    在哪里实现                                  需要写库吗
======================  ==========================================  ====================
1 来源可追溯（枚举）      迁移 ``20261121_selling_price_source_enum``  迁移时清洗一次
2 确认日期（自动写入）    `apply_selling_price_confirmation`          写 SKU 主数据时
3 即时影响预览            `build_selling_price_preview`               不写库
4 偏差校验 + 过期巡检     `assess_selling_price_deviation` / 巡检服务  不写库
======================  ==========================================  ====================

口径纪律
--------

**预览必须走共享定价入口**（``product_pricing_query_service.compute_pricing_state``），
不能在这里另写一套底线算法。否则会出现「预览说会涨到 63，保存后实际变成 58」——
运营会以为系统坏了，而这种不一致比没有预览更糟。

**偏差校验的「历史成交价」有明确口径**：

- 币种用 **CNY**，与基准售价同币种；
- 成交价 = **买家实付金额**（Shopee 取 ``买家支付(RMB)``，TikTok 取 ``买家实付金额(RMB)``），
  取自订单事实表 ``raw_data`` 里的**妙手系统自己折算的人民币金额**。

  为什么不用语义视图的 ``order_original_amount``：那一列是**平台币种**（MYR）
  且**含运费**（实测同一行的 ``订单原始金额`` 264.0 与 ``订单原始金额(RMB)`` 28.17
  相差 9 倍，差额是运费补贴与折扣）⇒ 直接当单价用会把中位数抬到 2~3 倍，
  偏差校验会变成「全线报警」的假阳性机器。
  用 ``(RMB)`` 版本还顺带避开了汇率表（``core.dim_exchange_rates`` 的汇率是
  2025-11-01 手工种子值，已经陈旧近一年）。
- **算不出来就不给结论**：没有成交记录、样本太少、没有汇率，一律返回「不可用」，
  绝不拿一个猜出来的数去提示运营。

过期巡检
--------

「基准售价已 N 天未确认」比「基准售价与成交价差多少」更该先看见：前者是**确定性**的
（时间一比就知道），后者依赖成交数据是否齐备。所以过期判定放在**列表接口**里
（纯计算，零成本），偏差校验放在**批量巡检**里（要扫订单事实表，慢）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from backend.schemas.product_center import (
    SELLING_PRICE_DEVIATION_THRESHOLD,
    SELLING_PRICE_STALE_DAYS,
)


#: 底线来源的中文标签（与前端 ``PRICING_SOURCE_LABELS`` 对齐）。
#:
#: ⚠️ 这里的「折扣纪律」是**旧叫法**的延续 —— 方案 §8 的改名总表把 SKU 资料 tab 的
#: 「参考售价」改成了「基准售价」，但**底线来源**这个标签不在改名范围内
#: （改名总表覆盖的是「SKU 资料 tab / 利润测算 tab / 定价设置抽屉 / 飞书投影」四处列名）。
#: 两边必须一致，否则页面上一处写「折扣纪律」另一处写「基准售价纪律」，
#: 运营会以为是两个东西。
PRICING_SOURCE_LABELS = {
    "manual_override": "人工设定",
    "discount_guard": "基准售价纪律",
    "cost_floor": "成本底线",
    "unavailable": "无法计算",
}


def _money(value) -> Optional[float]:
    return None if value is None else float(value)


def compute_selling_price_age(
    confirmed_at: Optional[datetime], *, now: Optional[datetime] = None
) -> tuple[Optional[int], bool]:
    """基准售价距上次确认过了多少天，以及是否已过期。

    返回 ``(age_days, stale)``：

    - ``confirmed_at`` 为 None ⇒ ``(None, False)``。
      **没有确认日期不等于「今天刚确认」** —— 它表示「从来没确认过」，
      这与「刚确认」是两回事，不能混成同一个 0。
      这类行的 ``stale`` 也是 False：它们没有「过期」，而是「从未确认」，
      真正的提醒由「有价格但没确认日期」这个事实本身承担。
    - ``stale`` = ``age_days > SELLING_PRICE_STALE_DAYS``（默认 90 天）。
    """
    if confirmed_at is None:
        return None, False
    reference = now or datetime.now(timezone.utc)
    if confirmed_at.tzinfo is None:
        confirmed_at = confirmed_at.replace(tzinfo=timezone.utc)
    age_days = (reference - confirmed_at).days
    if age_days < 0:
        # 确认日期在未来：不是「很新」，是数据有问题。记 0 天 + 不标过期，
        # 免得一条脏数据把整个巡检刷成黄色。
        return 0, False
    return age_days, age_days > SELLING_PRICE_STALE_DAYS


def apply_selling_price_confirmation(
    values: dict,
    *,
    current_price,
    current_confirmed_at: Optional[datetime],
    now: Optional[datetime] = None,
    confirmed_at_provided: Optional[bool] = None,
) -> dict:
    """基准售价变更时自动维护「确认日期」（阶段 4 工具 2）。

    ``values`` 是**将要写入**的字段字典，本函数就地修改它并返回同一个字典。

    规则：

    1. **基准售价变了** ⇒ 确认日期自动写成现在。
       这是一次新的「定价决定」，日期必须跟着走 —— 否则确认日期永远停在第一次填写时，
       过期巡检就永远不会报警。
    2. **基准售价被清空** ⇒ 确认日期一并清空。价格没了，「什么时候确认过」没有意义。
    3. **客户端给的确认日期与库里现有的一样** ⇒ 视为「页面把旧值原样回传」，自动写入。
    4. **客户端给的确认日期与库里现有的不同** ⇒ 视为「有意修正」，以客户端为准。

    ⚠️ 第 3 条是第 1 条能不能生效的关键：SKU 资料页是**整行回传**的，
    页面上读到的 ``selling_price_confirmed_at`` 会跟着请求体一起回来。
    如果只按「客户端给过日期」判断，「显式优先」就会把自动写入**挡掉** ——
    运营改了价格，确认日期却停在旧值，过期巡检从此永远不响。

    ``confirmed_at_provided``：
    「客户端有没有给确认日期」。默认按 ``"selling_price_confirmed_at" in values`` 推断
    —— 这对 ``exclude_unset=True`` 的字典是对的。**新建 SKU** 时字典里一定有
    ``selling_price_confirmed_at``（值为 None 的完整 dump），推断会得出「显式给过」，
    所以那种场景必须显式传这个参数。
    """
    if "reference_selling_price" not in values:
        return values

    if confirmed_at_provided is None:
        confirmed_at_provided = "selling_price_confirmed_at" in values

    new_price = values.get("reference_selling_price")
    if new_price is None:
        values["selling_price_confirmed_at"] = None
        return values

    # 客户端给的确认日期与库里现有的是**同一刻** ⇒ 是回传，不是有意修正
    client_date = values.get("selling_price_confirmed_at")
    if confirmed_at_provided and client_date is not None:
        if _same_instant(client_date, current_confirmed_at):
            confirmed_at_provided = False

    if confirmed_at_provided:
        # 有意修正 ⇒ 以客户端为准
        return values

    old_price = _money(current_price)
    new_price_money = _money(new_price)
    if old_price is not None and new_price_money is not None and old_price == new_price_money:
        # 价格没变 ⇒ 这不是一次新的确认，保留原确认日期
        values.pop("selling_price_confirmed_at", None)
        return values

    values["selling_price_confirmed_at"] = now or datetime.now(timezone.utc)
    return values


def _same_instant(left: datetime, right: Optional[datetime]) -> bool:
    """两个时间戳是不是同一刻（时区表示不同也算同一刻）。"""
    if right is None:
        return False
    if left.tzinfo is None:
        left = left.replace(tzinfo=timezone.utc)
    if right.tzinfo is None:
        right = right.replace(tzinfo=timezone.utc)
    return left == right


def build_selling_price_preview(
    *,
    context: dict,
    sku_row,
    linked_spu,
    reference_selling_price,
) -> dict:
    """基准售价的**即时影响预览**（阶段 4 工具 3）。

    回答运营的问题：「我把基准售价改成这个数，最低售价会怎么变？」

    ⚠️ 这里**不重新实现**底线算法：现在值与预览值都走
    ``compute_pricing_state``（共享定价入口），所以预览结果与保存后的真实结果
    **必然一致**。预览只是把同一个函数跑了两遍，一遍用旧价、一遍用新价。

    返回结构与 ``SkuSellingPricePreviewResponse`` 对应。
    """
    from .product_pricing_query_service import compute_pricing_state

    platform_codes = list(context.get("priceable_platform_codes") or [])
    platforms: list[dict] = []
    warnings: list[str] = []

    tier_label = None
    tier_min_restock_days = None

    for code in platform_codes:
        current_state = compute_pricing_state(
            context=context, sku_row=sku_row, linked_spu=linked_spu, platform_code=code
        )
        preview_state = compute_pricing_state(
            context=context,
            sku_row=sku_row,
            linked_spu=linked_spu,
            platform_code=code,
            reference_selling_price=reference_selling_price,
        )

        if tier_label is None:
            policy = current_state.get("policy")
            if policy:
                tier_label = policy.get("tier_label")
                tier_min_restock_days = policy.get("min_restock_days")

        current_pricing = current_state["pricing"]
        preview_pricing = preview_state["pricing"]

        current_value = _money(current_pricing.get("min_selling_price"))
        preview_value = _money(preview_pricing.get("min_selling_price"))
        change = None
        change_pct = None
        if current_value is not None and preview_value is not None:
            change = round(preview_value - current_value, 2)
            if current_value:
                change_pct = round((preview_value - current_value) / current_value * 100, 1)

        override_locked = bool(current_pricing.get("min_selling_price_is_override"))

        platforms.append(
            {
                "platform_code": code,
                "min_selling_price_current": current_value,
                "min_selling_price_preview": preview_value,
                "change": change,
                "change_pct": change_pct,
                "source_current": current_pricing.get("min_selling_price_source"),
                "source_preview": preview_pricing.get("min_selling_price_source"),
                "override_locked": override_locked,
                "message": _preview_message(
                    platform_code=code,
                    current_value=current_value,
                    preview_value=preview_value,
                    change=change,
                    change_pct=change_pct,
                    source_current=current_pricing.get("min_selling_price_source"),
                    source_preview=preview_pricing.get("min_selling_price_source"),
                    override_locked=override_locked,
                ),
            }
        )

    warnings.extend(_preview_warnings(platforms))
    return {
        "sku_id": getattr(sku_row, "sku_id", None),
        "sku_key": getattr(sku_row, "sku_key", None),
        "reference_selling_price_current": _money(getattr(sku_row, "reference_selling_price", None)),
        "reference_selling_price_preview": _money(reference_selling_price),
        "pricing_tier_label": tier_label,
        "pricing_tier_min_restock_days": tier_min_restock_days,
        "platforms": platforms,
        "warnings": warnings,
    }


def _preview_message(
    *,
    platform_code: str,
    current_value: Optional[float],
    preview_value: Optional[float],
    change: Optional[float],
    change_pct: Optional[float],
    source_current: Optional[str],
    source_preview: Optional[str],
    override_locked: bool,
) -> Optional[str]:
    """一句话说明这个平台上的底线会怎么变（直接给运营看的中文）。"""
    if override_locked:
        return (
            f"{platform_code}：已有人工覆盖，最低售价不受基准售价影响"
            f"（当前 {_money(current_value)}）"
        )
    if current_value is None and preview_value is None:
        return f"{platform_code}：资料不全，最低售价算不出来，基准售价改了也不影响"
    if current_value is None:
        return f"{platform_code}：最低售价从算不出来变为 {preview_value}"
    if preview_value is None:
        return f"{platform_code}：最低售价从 {current_value} 变为算不出来"
    if change in (None, 0):
        return f"{platform_code}：最低售价仍是 {current_value}，基准售价改动不改变底线"
    direction = "抬高" if change > 0 else "降低"
    reason = (
        "纪律线生效"
        if source_preview == "discount_guard" and source_current != "discount_guard"
        else PRICING_SOURCE_LABELS.get(source_preview or "", "底线口径变化")
    )
    return (
        f"{platform_code}：最低售价从 {current_value} {direction}到 {preview_value}"
        f"（{change_pct:+.0f}%，{reason}）"
    )


def _preview_warnings(platforms: list[dict]) -> list[str]:
    """整体提示。

    ⚠️ 只提示**值得注意**的变化（抬高超过 20%），不把每一次小数点后的变化都喊出来。
    基准售价填错的真正风险是「货卖不动」（纪律线抬高 → 护栏把品拦死），
    所以抬价才是要警告的方向；降价不警告 —— 降价最多是少赚，不是卖不动。
    """
    warnings: list[str] = []
    for item in platforms:
        if item.get("override_locked"):
            continue
        change_pct = item.get("change_pct")
        if change_pct is None:
            continue
        if change_pct >= 20:
            warnings.append(
                f"{item['platform_code']} 的最低售价将{'抬高' if change_pct > 0 else '降低'}"
                f" {abs(change_pct):.0f}%（{item.get('min_selling_price_current')} → "
                f"{item.get('min_selling_price_preview')}），"
                f"原因是{PRICING_SOURCE_LABELS.get(item.get('source_preview') or '', '底线口径变化')}。"
                f"基准售价填高了，最低售价会被顶上去，品可能被护栏拦死。"
            )
    return warnings


def assess_selling_price_deviation(
    reference_price,
    median_price,
    *,
    threshold: float = SELLING_PRICE_DEVIATION_THRESHOLD,
) -> dict:
    """基准售价与历史成交价中位数的偏差（阶段 4 工具 4 · 偏差校验）。

    **纯函数**：不查库、不看时间，纯算。

    返回 ``{"available": bool, "reason": str|None, "deviation_pct": float|None,
    "exceeds_threshold": bool}``。

    ⚠️ 算不出历史成交价（``median_price`` 为 None）⇒ ``available=False``，
    **不给任何结论**。缺输入宁可不算不可乐观 —— 把「没有数据」当成「没有偏差」
    报上去，运营就会以为这个价没问题。
    """
    reference = _money(reference_price)
    median = _money(median_price)
    if reference is None:
        return {
            "available": False,
            "reason": "no_reference_price",
            "deviation_pct": None,
            "exceeds_threshold": False,
        }
    if median is None or median <= 0:
        return {
            "available": False,
            "reason": "no_transaction_price",
            "deviation_pct": None,
            "exceeds_threshold": False,
        }
    deviation_pct = round((reference - median) / median * 100, 1)
    return {
        "available": True,
        "reason": None,
        "deviation_pct": deviation_pct,
        "exceeds_threshold": abs(deviation_pct) > threshold * 100,
    }
