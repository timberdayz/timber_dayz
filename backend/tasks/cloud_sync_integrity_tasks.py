"""云端同步链路完整性巡检的定时任务。

作用: 定时巡检**云端**那一侧的三件事, 把结论写进 ``ops.pipeline_run_log`` /
``ops.pipeline_step_log``(既有监控台账, **不需要新增表、不需要迁移**):

1. **云端数据还新鲜吗** —— 用 ``max(ingest_timestamp)`` 判定, 同步链断一天就能发现;
2. **行内身份还能不能认出来** —— 算「能唯一归属到主数据账号」的收敛率;
3. **候选池有没有缺平台** —— 缺平台 ⇒ 那条链的身份从一开始就解析不出来。

为什么必须是**云端**连接
----------------------
采集机本地跑的是「采集链」新鲜度(:mod:`source_freshness_service`),
它回答的是「我采到的数据有多旧」。它**回答不了**「云端还有没有在收数据」——
2026-11-07 事故里, 采集机一切正常, 是云端停在 11-06 再也没动过。

所以这个任务用 ``CLOUD_DATABASE_URL`` 连云端。
没配这个环境变量时**跳过**(不报错)—— 云端不可达不该把定时任务打挂。
"""

import logging
import os
from typing import Any, Dict

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.celery_app import celery_app
from backend.models.database import get_async_database_url
from backend.services.data_pipeline.cloud_sync_integrity_service import (
    run_cloud_sync_integrity_check,
)
from backend.utils.async_task_runner import run_async_task

logger = logging.getLogger(__name__)


async def _run_check() -> Dict[str, Any]:
    cloud_database_url = (os.getenv("CLOUD_DATABASE_URL") or "").strip()
    if not cloud_database_url:
        return {
            "status": "skipped",
            "reason": "CLOUD_DATABASE_URL is not configured",
        }

    engine = create_async_engine(get_async_database_url(cloud_database_url))
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    db = session_factory()
    try:
        report = await run_cloud_sync_integrity_check(db, trigger_source="scheduler")
        summary = report.to_summary()
        summary["status"] = "success" if report.is_success else "partial_failed"
        summary["error_message"] = report.to_error_message()
        return summary
    finally:
        await db.close()
        await engine.dispose()


@celery_app.task(
    name="backend.tasks.cloud_sync_integrity_tasks.check_cloud_sync_integrity"
)
def check_cloud_sync_integrity() -> Dict[str, Any]:
    """巡检云端同步链路的完整性(陈旧 / 收敛率 / 候选池平台)。"""
    try:
        # 用全仓唯一的异步出口: 它保证在本事件循环**存活期间**真正关闭连接池。
        # 直接 asyncio.run(...) 会让 asyncpg 的连接绑定到一个随即死掉的循环上,
        # 之后连 close 都关不掉 —— 生产实测 80/80 连接槽位就是这样被打满的。
        summary = run_async_task(_run_check)
    except Exception as exc:  # noqa: BLE001
        logger.error("[CloudSyncIntegrity] 巡检执行失败: %s", exc, exc_info=True)
        raise

    if summary.get("status") == "skipped":
        logger.info("[CloudSyncIntegrity] 未配置云端连接, 跳过巡检")
        return summary

    if summary.get("status") == "partial_failed":
        logger.warning(
            "[CloudSyncIntegrity] 云端同步链路异常: 陈旧链 %s 条, 收敛率异常 %s 条, "
            "候选池缺平台 %s 个",
            summary.get("stale_chains"),
            summary.get("low_convergence_chains"),
            summary.get("missing_candidate_platforms"),
        )
    else:
        logger.info(
            "[CloudSyncIntegrity] 巡检通过: %s 条链全部新鲜, 收敛率正常, 候选池平台齐全",
            summary.get("checked_chains"),
        )
    return summary
