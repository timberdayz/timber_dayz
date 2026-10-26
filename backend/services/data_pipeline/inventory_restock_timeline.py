"""「上次进货时间」的唯一实现 —— 库存总量逐帧回放。

口径（2026-10-26 定案）
-----------------------
- **信号字段**：库存**总量**（``on_hand`` / ``on_hand_stock``）。
  订单占用 / 取消订单只动可用库存、不动总量；
  用可用库存会把「取消订单」误判成进货。
- **判定**：逐帧比库存总量 —— 增加 = 进货（计时器清零）；减少 / 不变 = 继续累加。
- **起算点**：最后一次进货的帧；从未进货 = 首次出现的帧。
- **数据源**：行级快照事实，按 ``snapshot_date`` 逐帧回放。
- **粒度**：仓级（SKU×仓）为准；SKU 级由各仓**取最长**汇总而来
  （一个仓压着没补货，这货整体就压着）。

为什么收成这一个实现
--------------------
仓库里曾有两套实现，算出来不一样（实测同 458 个 SKU：
655~656 天 vs 17~30 天，差 19~656 天，**0 行一致**）：

- **库龄层**（``InventoryAgeRefreshService``）：读全部历史快照逐帧比 → 起算点**准**，
  但信号用**可用库存** → 取消订单会被误判成进货
- **状态层**（``InventoryStateRefreshService``）：只跟状态层自己入库后的上一批比 →
  第一次见某 SKU 时没有上一笔可比，只能拿「妙手商品创建时间」凑数 → 起算点**不准**

本模块是唯一实现，库龄层与状态层都调它 → 「何时算进货」只有一个定义，
以后改规则只改一处。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# 判定「进货」用的字段：**库存总量**
RESTOCK_SIGNAL_FIELD = "on_hand"

# 锚点来源的原因（与库龄层看板上的分类一一对应）
REASON_ZERO_STOCK = "zero_stock"
REASON_FIRST_SEEN = "first_positive"
REASON_REAPPEARED = "reappeared_after_zero"
REASON_RESTOCKED = "stock_increase"
REASON_CONTINUED = "continued"

WarehouseKey = Tuple[str, str, str]
SkuKey = Tuple[str, str]


def _transition(
    is_active: bool,
    anchor_date: Optional[date],
    age_days: Optional[int],
    reset_reason: str,
    anchor_reset: bool,
) -> Dict[str, Any]:
    return {
        "is_active": is_active,
        "age_anchor_date": anchor_date,
        "age_days": age_days,
        "reset_reason": reset_reason,
        "anchor_reset": anchor_reset,
    }


def compute_restock_transition(
    *,
    previous_qty: Optional[int],
    current_qty: int,
    snapshot_date: Optional[date],
    previous_anchor_date: Optional[date],
) -> Dict[str, Any]:
    """逐帧判定：**只有库存总量增加（进货）才重置计时器**。

    返回 ``{"is_active", "age_anchor_date", "age_days", "reset_reason", "anchor_reset"}``。

    - 库存清零 → 不活跃（不压资金，不进看板当前值）
    - 首次出现 → 从这一帧起算
    - 从 0 变正 → 重新出现，从这一帧起算
    - 库存总量增加（进货）→ 计时器清零，从这一帧起算
    - 减少 / 不变（销售、订单占用、取消订单）→ **保留上一次的锚点，继续累加**

    ``anchor_reset`` 表示「这一帧是否重置了计时器」——
    用来区分「锚点是从哪来的」与「这一帧判定成什么」。
    """
    if current_qty <= 0:
        return _transition(False, None, None, REASON_ZERO_STOCK, False)
    if previous_qty is None:
        return _transition(True, snapshot_date, 0, REASON_FIRST_SEEN, True)
    if previous_qty <= 0:
        return _transition(True, snapshot_date, 0, REASON_REAPPEARED, True)
    if current_qty > previous_qty:
        return _transition(True, snapshot_date, 0, REASON_RESTOCKED, True)
    anchor_date = previous_anchor_date or snapshot_date
    return _transition(
        True,
        anchor_date,
        age_days_between(anchor_date, snapshot_date),
        REASON_CONTINUED,
        False,
    )


@dataclass(frozen=True)
class RestockFrame:
    """一帧（某次采集时这个 SKU×仓 的样子）。"""

    snapshot_date: Optional[date]
    quantity: int
    previous_quantity: Optional[int]
    anchor_date: Optional[date]
    anchor_reason: str


@dataclass(frozen=True)
class RestockTimeline:
    """某个 SKU×仓 的进货时间线（回放结果）。"""

    platform_code: str
    sku_key: str
    warehouse_name: str
    #: 上次进货的帧日期；从未进货时 = 首次出现的帧日期
    anchor_date: Optional[date]
    #: 锚点是怎么来的：restocked（进货）/ first_seen（首次见到）
    anchor_reason: str
    #: 最后一帧的库存总量
    current_qty: int
    #: 倒数第二帧的库存总量（只有一帧时为 None）
    previous_qty: Optional[int]
    #: 最后一帧的日期
    current_date: Optional[date]
    #: 逐帧明细（按快照日期升序）
    frames: Tuple[RestockFrame, ...] = ()

    @property
    def key(self) -> WarehouseKey:
        return (self.platform_code, self.sku_key, self.warehouse_name)


@dataclass(frozen=True)
class SkuTimeline:
    """SKU 级汇总：各仓取最长（最晚进货 = 最早锚点）。"""

    platform_code: str
    sku_key: str
    anchor_date: Optional[date]
    anchor_reason: str
    current_qty: int
    previous_qty: Optional[int]
    current_date: Optional[date]
    warehouse_count: int


def _row_quantity(row: Dict[str, Any]) -> int:
    """取这一帧的库存总量。

    兼容两种字段名：语义层用 ``on_hand_stock``，快照族用 ``on_hand_qty``。
    """
    for field in ("on_hand_stock", "on_hand_qty"):
        value = row.get(field)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return 0


def _row_date(row: Dict[str, Any]) -> Optional[date]:
    for field in ("snapshot_date", "metric_date", "period_start_date"):
        value = row.get(field)
        if isinstance(value, date):
            return value
    return None


def _sort_key(row: Dict[str, Any]) -> Tuple[Any, ...]:
    stamp = row.get("last_ingest_timestamp") or row.get("ingest_timestamp") or ""
    return (_row_date(row) or date.min, str(stamp))


def _replay_frames(frames: List[Dict[str, Any]]) -> RestockTimeline:
    """回放一个 SKU×仓 的帧序列。"""
    anchor_date: Optional[date] = None
    anchor_reason = REASON_CONTINUED
    last_qty: Optional[int] = None
    last_anchor: Optional[date] = None
    second_last_qty: Optional[int] = None
    current_date: Optional[date] = None
    replayed: List[RestockFrame] = []

    for frame in frames:
        frame_date = _row_date(frame)
        current_qty = _row_quantity(frame)
        transition = compute_restock_transition(
            previous_qty=last_qty,
            current_qty=current_qty,
            snapshot_date=frame_date,
            previous_anchor_date=last_anchor,
        )
        if transition["anchor_reset"]:
            # 计时器被重置 → 锚点来源也更新
            anchor_date = transition["age_anchor_date"]
            anchor_reason = transition["reset_reason"]
        replayed.append(
            RestockFrame(
                snapshot_date=frame_date,
                quantity=current_qty,
                previous_quantity=last_qty,
                anchor_date=transition["age_anchor_date"],
                anchor_reason=transition["reset_reason"],
            )
        )
        second_last_qty = last_qty
        last_qty = current_qty
        last_anchor = transition["age_anchor_date"]
        current_date = frame_date

    return RestockTimeline(
        platform_code=str(frames[0].get("platform_code") or "") if frames else "",
        sku_key=str(frames[0].get("sku_key") or "") if frames else "",
        warehouse_name=str(frames[0].get("warehouse_name") or "") if frames else "",
        anchor_date=anchor_date,
        anchor_reason=anchor_reason,
        current_qty=last_qty or 0,
        previous_qty=second_last_qty,
        current_date=current_date,
        frames=tuple(replayed),
    )


def replay_restock_timeline(
    rows: Iterable[Dict[str, Any]],
) -> Dict[WarehouseKey, RestockTimeline]:
    """逐帧回放 → 每个 SKU×仓 的「上次进货时间」。

    同一 ``(platform_code, sku_key, warehouse_name)`` 的所有帧一起回放；
    帧按 ``(快照日期, 采集时刻)`` 排序。
    """
    grouped: Dict[WarehouseKey, List[Dict[str, Any]]] = {}
    for row in rows:
        key = (
            str(row.get("platform_code") or ""),
            str(row.get("sku_key") or ""),
            str(row.get("warehouse_name") or ""),
        )
        grouped.setdefault(key, []).append(row)

    result: Dict[WarehouseKey, RestockTimeline] = {}
    for key, frames in grouped.items():
        ordered = sorted(frames, key=_sort_key)
        timeline = _replay_frames(ordered)
        result[key] = RestockTimeline(
            platform_code=key[0],
            sku_key=key[1],
            warehouse_name=key[2],
            anchor_date=timeline.anchor_date,
            anchor_reason=timeline.anchor_reason,
            current_qty=timeline.current_qty,
            previous_qty=timeline.previous_qty,
            current_date=timeline.current_date,
            frames=timeline.frames,
        )
    return result


def aggregate_sku_timeline(
    timelines: Dict[WarehouseKey, RestockTimeline],
) -> Dict[SkuKey, SkuTimeline]:
    """仓级 → SKU 级：**各仓取最长**（最晚进货 = 最早锚点）。

    「一个仓压着没补货，这货整体就压着」——所以取**最早**的锚点。

    ⚠️ 这条规则在滞销链的 SQL 里也有一份
    （``api.sku_clearance_ranking_module`` 的 ``MAX(...)`` 聚合）。
    本函数是它的**可执行定义**：用测试锁住行为，防止两边悄悄漂移。
    """
    grouped: Dict[SkuKey, List[RestockTimeline]] = {}
    for timeline in timelines.values():
        grouped.setdefault((timeline.platform_code, timeline.sku_key), []).append(
            timeline
        )

    result: Dict[SkuKey, SkuTimeline] = {}
    for sku_key, items in grouped.items():
        dated = [item for item in items if item.anchor_date is not None]
        earliest = min(dated, key=lambda item: item.anchor_date) if dated else None
        result[sku_key] = SkuTimeline(
            platform_code=sku_key[0],
            sku_key=sku_key[1],
            anchor_date=earliest.anchor_date if earliest else None,
            anchor_reason=earliest.anchor_reason if earliest else REASON_CONTINUED,
            current_qty=sum(item.current_qty for item in items),
            previous_qty=(
                sum(item.previous_qty or 0 for item in items)
                if any(item.previous_qty is not None for item in items)
                else None
            ),
            current_date=max(
                (item.current_date for item in items if item.current_date is not None),
                default=None,
            ),
            warehouse_count=sum(1 for item in items if item.current_qty > 0),
        )
    return result


def age_days_between(
    anchor_date: Optional[date], as_of: Optional[date]
) -> Optional[int]:
    """距锚点的天数（自然日）。"""
    if anchor_date is None or as_of is None:
        return None
    return max((as_of - anchor_date).days, 0)
