"""最低售价变更检测与通知（每日任务）。

流程（两段，刻意分成两个事务）：

1. **检测**：全量重算所有 active SKU 的最低售价 → 与基线比对 → 产出变更集
   → 静默推进基线（首次建基线 / 下架造成的跳高）→ 为需要通知的变更创建 outbox 任务
   → **提交**
2. **投递**：把 outbox 任务批量新增到飞书「调价记录表」→ 投递成功后回写基线 → 提交

为什么分成两段：飞书写入是外部 IO，放在长事务里既慢又危险；
而且投递失败时任务必须**留在 outbox 里**等重试，不能连同检测结果一起回滚。

**基线推进的顺序不能反**——见 `price_adjust_notify_service` 的模块说明。
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from backend.celery_app import celery_app
from backend.models.database import (
    AsyncSessionLocal,
    reset_async_engine_pool_for_new_loop,
)
from backend.services.feishu_projection_service import FeishuProjectionService
from backend.services.price_adjust_notify_service import PriceAdjustNotifyService
from modules.core.db import FeishuProjectionTask
from modules.core.logger import get_logger

logger = get_logger(__name__)


async def _existing_price_adjust_sku_ids(db, sku_ids: list[int]) -> set[int]:
    """这些 SKU 是否已经有在途的价格调整任务。

    同一次变化如果上一轮投递失败，基线不会推进，下一轮又会检测到差异。
    若不加这道闸，会为同一次变化反复建任务 → payload 哈希相同撞唯一约束，
    或者产生重复通知行。
    """
    if not sku_ids:
        return set()
    rows = (
        await db.execute(
            select(
                FeishuProjectionTask.business_key,
                FeishuProjectionTask.status,
            ).where(
                FeishuProjectionTask.entity_type == "price_adjust",
                FeishuProjectionTask.business_key.in_([str(s) for s in sku_ids]),
                FeishuProjectionTask.status.in_(
                    ("pending", "running", "failed", "completed")
                ),
            )
        )
    ).all()
    return {int(row.business_key) for row in rows if str(row.business_key).isdigit()}


def _build_payload(change: dict) -> dict:
    """组装 outbox payload。

    ⚠️ **不含任何时间戳**：payload 的哈希是去重依据，
    带时间戳会让同一次变化重跑时哈希不同、去重失效。
    「变动时间」由投递时取 outbox 任务的 created_at 补上。
    """
    return {
        "sku_id": change["sku_id"],
        "sku_key": change["sku_key"],
        "spu": change["spu"],
        "sku_name": change["sku_name"],
        "specification": change["specification"],
        "old_min_selling_price": change["old_min_selling_price"],
        "new_min_selling_price": change["new_min_selling_price"],
        "change_rate": change["change_rate"],
        "direction": change["direction"],
        "reason": change["reason"],
        "pricing_tier_label": change["pricing_tier_label"],
        "age_days": change["age_days"],
        "current_qty": change["current_qty"],
        "inventory_value": change["inventory_value"],
        # 归因上下文快照：投递成功后用它回写基线
        "context": change["context"],
    }


async def _async_detect_and_enqueue_price_adjustments() -> dict:
    # ---------- 第一段：检测 + 建任务 ----------
    async with AsyncSessionLocal() as db:
        service = PriceAdjustNotifyService(db)
        notify, silent = await service.detect_changes()

        advanced = await service.advance_baselines(silent)

        enqueued = 0
        skipped = 0
        if notify:
            projection = FeishuProjectionService(db)
            existing = await _existing_price_adjust_sku_ids(
                db, [change["sku_id"] for change in notify]
            )
            for change in notify:
                if change["sku_id"] in existing:
                    skipped += 1
                    continue
                await projection.enqueue(
                    "price_adjust",
                    str(change["sku_id"]),
                    _build_payload(change),
                )
                enqueued += 1
        await db.commit()

    logger.info(
        "[PriceAdjustNotify] detection done: changed=%s notified=%s "
        "baseline_advanced=%s skipped_inflight=%s",
        len(notify),
        enqueued,
        advanced,
        skipped,
    )

    # ---------- 第二段：投递 ----------
    delivered = 0
    delivery_error = None
    async with AsyncSessionLocal() as db:
        try:
            delivered = await FeishuProjectionService(db).process_pending()
            await db.commit()
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            delivery_error = str(exc)[:500]
            logger.warning(
                "[PriceAdjustNotify] delivery failed, tasks stay in outbox for retry: %s",
                exc,
            )

    return {
        "changed": len(notify),
        "baseline_advanced": advanced,
        "enqueued": enqueued,
        "skipped_inflight": skipped,
        "delivered": delivered,
        "delivery_error": delivery_error,
    }


@celery_app.task(
    name="backend.tasks.price_adjust_notify_tasks.detect_and_notify_price_adjustments",
    bind=True,
    queue="scheduled",
    priority=5,
    time_limit=1800,
    soft_time_limit=1500,
)
def detect_and_notify_price_adjustments(self):  # noqa: ANN201
    reset_async_engine_pool_for_new_loop()
    return asyncio.run(_async_detect_and_enqueue_price_adjustments())
