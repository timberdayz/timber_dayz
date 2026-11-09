"""源数据新鲜度巡检的定时任务。

作用：定时巡检 ``b_class.fact_*`` 业务事实表，
把「哪条业务链多久没有新数据」写进 ``ops.pipeline_run_log`` /
``ops.pipeline_step_log``——这两张表是既有的监控台账，**不需要新增表、不需要迁移**。

断流时该次巡检的 run 状态为 ``partial_failed``，
在数据平台的运行列表里直接可见，不再出现「刷新全绿但业务数据早已过期」的情况。
"""

import logging
from typing import Any, Dict

from backend.celery_app import celery_app
from backend.models.database import AsyncSessionLocal
from backend.services.data_pipeline.source_freshness_service import (
    run_source_freshness_check,
)
from backend.utils.async_task_runner import run_async_task

logger = logging.getLogger(__name__)


async def _run_check() -> Dict[str, Any]:
    db = AsyncSessionLocal()
    try:
        report = await run_source_freshness_check(db, trigger_source="scheduler")
        return report.to_summary()
    finally:
        await db.close()


@celery_app.task(
    name="backend.tasks.source_freshness_tasks.check_source_data_freshness"
)
def check_source_data_freshness() -> Dict[str, Any]:
    """巡检源数据新鲜度。

    返回摘要：巡检了多少条链、多少条新鲜、多少条断流、断流的是哪些链。
    """
    try:
        summary = run_async_task(_run_check)
    except Exception as exc:  # noqa: BLE001
        logger.error("[SourceFreshness] 巡检执行失败: %s", exc, exc_info=True)
        raise

    stale_labels = summary.get("stale_chain_labels") or []
    if stale_labels:
        logger.warning(
            "[SourceFreshness] 检测到 %s 条断流数据链: %s",
            summary.get("stale_chains"),
            ", ".join(stale_labels),
        )
    else:
        logger.info(
            "[SourceFreshness] 巡检通过：%s 条链全部在新鲜期内（空表 %s 条）",
            summary.get("checked_chains"),
            summary.get("empty_chains"),
        )
    return summary
