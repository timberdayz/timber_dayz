"""增量采集的采集窗口计算 —— 水位线 + 断档补采。

为什么要有这个
--------------
妙手「更新时间」维度上的增量采集，窗口必须**接着上次采到的地方往下接**，
而不是「最近 N 天」——相对今天的窗口与水位线推进语义不同，会漏采
（相对今天 = 每次都重采最近 N 天；水位线 = 只补上次之后新变的行）。

口径（2026-10-25 定案）
-----------------------

| 情形 | 窗口 | 理由 |
|---|---|---|
| 配置了 custom 区间 | **原样用配置的区间**（不裁剪、不回填） | 用户显式指定：「我就是要采这一段」。custom 是**一次性补数**，不是常态增量 |
| 未配置（自动推进） | `[水位线 − 重叠余量, now]` | 从上次采到的地方接着采 |
| 自动推进且水位线距今 > 断档阈值 | 起点再向前拉到 `now − 长窗口天数` | **断档补采**：断档越久，水位线精度越不可信 → 至少保证最近长窗口天数被覆盖 |
| 上一批失败 | 起点向前拉到失败批次的起点 | 失败期不能漏 |

「长窗口补采」是**下限**，不是收窄
------------------------------
窗口起点 = `min(水位线 − 重叠余量, now − 长窗口天数)`。

- 水位线比长窗口更久 → **以水位线为准**。收窄窗口 = 跳过中间那几天 = 静默漏采，
  是这个模块最不能犯的错。
- 水位线只比长窗口近一点 → 往前拉到长窗口。断档越久，水位线越可能失真
  （妙手时间戳会被 bulk UPDATE 戳穿、两侧时钟有偏差），宁可多采
  （重复采到的行由落盘 upsert 幂等吃掉），不可漏采。

水位线存在哪
------------
**不另建水位线表**：水位线 = 该平台 ``mart.inventory_state`` 的 ``MAX(row_seen_at)``。

- 用**我方采集时钟**（``row_seen_at``）而不是妙手的「更新时间」：
  妙手时间戳会被一次 bulk UPDATE 批量戳穿（实测 file 2764 有 535 行 / 43.7%
  被写成同一时刻），拿它当水位线会**跳过整段真实变更**。
- 不另建表的另一个好处：水位线**随状态层 upsert 天然推进**，不需要额外的写路径。

重叠余量（``overlap_days``）
---------------------------
窗口起点比水位线往前挪 ``overlap_days`` 天，吸收两侧时钟偏差。
重复采到的行由落盘层的 upsert 幂等吃掉——**多采是安全的，漏采不是**。

本模块是**纯函数 + 薄取数**：窗口计算不碰 DB，可写无 DB 单测。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# 窗口起点比水位线往前挪的天数（吸收时钟偏差；重复采到由 upsert 幂等吃掉）
DEFAULT_OVERLAP_DAYS: int = 1
# 水位线距今超过这个天数 = 断档，触发长窗口补采
DEFAULT_GAP_THRESHOLD_DAYS: int = 3
# 断档时向前拉长的窗口天数
DEFAULT_BACKFILL_WINDOW_DAYS: int = 7

# 窗口成因
REASON_CUSTOM = "custom"
REASON_FIRST_RUN = "first_run"
REASON_WATERMARK = "watermark"
REASON_GAP_BACKFILL = "gap_backfill"
REASON_FAILED_BACKFILL = "failed_backfill"


@dataclass(frozen=True)
class CollectionWindow:
    """一次增量采集要覆盖的时间窗。"""

    start: datetime
    end: datetime
    reason: str
    reasons: tuple[str, ...] = field(default_factory=tuple)
    gap_days: int = 0

    @property
    def is_custom(self) -> bool:
        return self.reason == REASON_CUSTOM


def _shift(moment: datetime, days: int) -> datetime:
    return moment - timedelta(days=days)


def _as_aware(moment: Optional[datetime]) -> Optional[datetime]:
    """统一时区：naive 当 UTC 处理。

    水位线来自 DB、``now`` 来自应用时钟，两边的 tzinfo 未必一致；
    直接相减会抛 ``can't subtract offset-naive and offset-aware datetimes``。
    """
    if moment is None:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def _compute_auto_window(
    *,
    now: datetime,
    watermark: Optional[datetime],
    last_failed_start: Optional[datetime],
    overlap_days: int,
    gap_threshold_days: int,
    backfill_window_days: int,
) -> tuple[datetime, list[str], int]:
    """自动推进：水位线 → 断档补采 → 失败期覆盖。

    返回 ``(起点, 成因列表, 断档天数)``。
    """
    reasons: list[str] = []
    gap_days = 0
    now = _as_aware(now)
    watermark = _as_aware(watermark)
    last_failed_start = _as_aware(last_failed_start)

    if watermark is None:
        # 从没采过 → 没有水位线可接，先采一段长窗口把基线铺出来
        start = _shift(now, backfill_window_days)
        reasons.append(REASON_FIRST_RUN)
    else:
        start = _shift(watermark, overlap_days)
        reasons.append(REASON_WATERMARK)
        gap_days = max((now - watermark).days, 0)
        if gap_days > gap_threshold_days:
            backfill_start = _shift(now, backfill_window_days)
            if backfill_start < start:
                start = backfill_start
                reasons.append(REASON_GAP_BACKFILL)

    # 上一批失败 → 窗口必须覆盖失败期，否则那一段永远补不回来
    if last_failed_start is not None and last_failed_start < start:
        start = _shift(last_failed_start, overlap_days)
        reasons.append(REASON_FAILED_BACKFILL)

    return start, reasons, gap_days


def compute_collection_window(
    *,
    now: datetime,
    watermark: Optional[datetime] = None,
    requested_start: Optional[datetime] = None,
    requested_end: Optional[datetime] = None,
    last_failed_start: Optional[datetime] = None,
    overlap_days: int = DEFAULT_OVERLAP_DAYS,
    gap_threshold_days: int = DEFAULT_GAP_THRESHOLD_DAYS,
    backfill_window_days: int = DEFAULT_BACKFILL_WINDOW_DAYS,
) -> CollectionWindow:
    """算一次增量采集的窗口（纯函数）。

    ``requested_start`` 非空 = 用户显式配置了区间 → 原样返回，不裁剪、不回填。
    否则走自动推进：水位线 → 断档补采 → 失败期覆盖。
    """
    if requested_start is not None:
        return CollectionWindow(
            start=requested_start,
            end=requested_end or now,
            reason=REASON_CUSTOM,
            reasons=(REASON_CUSTOM,),
            gap_days=0,
        )

    start, reasons, gap_days = _compute_auto_window(
        now=now,
        watermark=watermark,
        last_failed_start=last_failed_start,
        overlap_days=overlap_days,
        gap_threshold_days=gap_threshold_days,
        backfill_window_days=backfill_window_days,
    )
    return CollectionWindow(
        start=start,
        end=requested_end or now,
        reason=reasons[-1],
        reasons=tuple(reasons),
        gap_days=gap_days,
    )


async def load_collection_watermark(
    db: AsyncSession, platform_code: str
) -> Optional[datetime]:
    """水位线 = 该平台状态层 ``MAX(row_seen_at)``（我方采集时钟）。

    容错纪律照 ``inventory_restock_query_service``：
    ``to_regclass`` 探测表是否存在（不存在就**根本不发出会失败的查询**），
    万一仍失败就用 SAVEPOINT 包住，**必须留日志**。
    """
    if db is None:
        return None

    try:
        async with db.begin_nested():
            exists = (
                await db.execute(text("SELECT to_regclass('mart.inventory_state')"))
            ).scalar()
            if not exists:
                return None
            value = (
                await db.execute(
                    text(
                        """
                        SELECT MAX(row_seen_at)
                        FROM mart.inventory_state
                        WHERE platform_code = :platform_code
                        """
                    ),
                    {"platform_code": platform_code},
                )
            ).scalar()
    except Exception as exc:  # noqa: BLE001
        from modules.core.logger import get_logger

        get_logger(__name__).warning(
            "inventory collection watermark lookup failed, falling back to a full window: %s",
            exc,
        )
        return None

    return value if isinstance(value, datetime) else None


async def resolve_incremental_range(
    db: AsyncSession,
    *,
    platform_code: str,
    custom_range: Optional[dict[str, Any]] = None,
    config_id: Optional[int] = None,
    now: Optional[datetime] = None,
) -> Optional[dict[str, Any]]:
    """决定库存增量采集这一次按哪个区间筛。

    规则（2026-10-25 定案，运营零操作）：
    1. **运营显式指定了区间** → 用它（一次性补数 / 指定窗口都走这条）
    2. **没有水位线**（状态层还没有这个平台）→ 返回 None = **不设筛选，导全量建基线**
       （与今天的全量行为一致，不会因为接了增量就丢掉基线）
    3. 否则 → 水位线窗口（+ 断档补采 + 失败期覆盖）

    返回 None = 不设筛选；否则返回
    ``{"start": "YYYY-MM-DD HH:MM:SS", "end": ..., "reason": ..., "gap_days": ...}``
    """
    if custom_range:
        start = str(custom_range.get("start") or "").strip()
        end = str(custom_range.get("end") or "").strip()
        if start and end:
            return {"start": start, "end": end, "reason": "custom", "gap_days": 0}

    watermark = await load_collection_watermark(db, platform_code)
    if watermark is None:
        return None

    last_failed_start = None
    if config_id is not None:
        last_failed_start = await load_last_failed_run_start(db, config_id)

    window = compute_collection_window(
        now=now or datetime.now(timezone.utc),
        watermark=watermark,
        last_failed_start=last_failed_start,
    )
    return {
        "start": window.start.strftime("%Y-%m-%d %H:%M:%S"),
        "end": window.end.strftime("%Y-%m-%d %H:%M:%S"),
        "reason": window.reason,
        "gap_days": window.gap_days,
    }


async def load_last_failed_run_start(
    db: AsyncSession, config_id: int
) -> Optional[datetime]:
    """最近一次**失败**运行的开始时间（用来把窗口拉长覆盖失败期）。

    复用既有 ``core.collection_config_runs``（有 ``status`` / ``started_at``），
    **不需要新建水位线表**。
    """
    if db is None:
        return None

    try:
        async with db.begin_nested():
            value = (
                await db.execute(
                    text(
                        """
                        SELECT started_at
                        FROM core.collection_config_runs
                        WHERE config_id = :config_id
                          AND status IN ('failed', 'partial_success')
                          AND started_at IS NOT NULL
                        ORDER BY started_at DESC
                        LIMIT 1
                        """
                    ),
                    {"config_id": config_id},
                )
            ).scalar()
    except Exception as exc:  # noqa: BLE001
        from modules.core.logger import get_logger

        get_logger(__name__).warning(
            "inventory collection failed-run lookup failed: %s",
            exc,
        )
        return None

    return value if isinstance(value, datetime) else None
