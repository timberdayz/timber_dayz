from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from backend.celery_app import celery_app
from backend.models.database import (
    AsyncSessionLocal,
)
from backend.utils.async_task_runner import run_async_task
from backend.services.data_pipeline.inventory_age_refresh_service import (
    InventoryAgeRefreshService,
)
from backend.services.data_pipeline.inventory_state_refresh_service import (
    InventoryStateRefreshService,
)
from backend.services.cache_service import get_cache_service
from backend.services.data_pipeline.dashboard_bootstrap import (
    DASHBOARD_MODULE_TARGETS,
    bootstrap_dashboard_assets_if_needed,
    inspect_dashboard_assets,
)
from backend.services.data_pipeline.refresh_queue_service import RefreshQueueService
from backend.services.data_pipeline.refresh_validation import (
    RefreshValidationReport,
    validate_refresh_result,
)
from backend.services.product_center_service import sync_inventory_skus
from backend.services.data_pipeline.refresh_runner import (
    execute_refresh_plan,
    extract_failed_targets,
    extract_refresh_status,
    extract_run_id,
    extract_sqlstate,
)
from modules.core.logger import get_logger

logger = get_logger(__name__)

#: 「running 多久算死了」的阈值（秒）。
#:
#: 必须**大于** Celery 的硬超时（``time_limit=1800``）。
#: 旧阈值是 600 秒 —— 比软超时（1500 秒）还小 ⇒ 任务还在正常跑，
#: 就被另一个 worker 判成死的并重排队 ⇒ 同一条刷新被跑第二遍，还可能并发。
#: 40 分钟 = 硬超时 30 分钟 + 10 分钟余量。
REFRESH_QUEUE_RUNNING_TIMEOUT_SECONDS = 40 * 60

#: 安全网**熔断阈值**：同一模块连续这么多次修复任务失败 ⇒ 暂停自动重试。
#:
#: 没有熔断 ⇒ 「修不好」的状态会被每 5 分钟重试一次，永不停歇。
#: 2026-11-07 实测：``dashboard_safety_net_repair`` 攒出 **859 次 failed**
#: （+193 次 skipped）—— 每一次都真的重跑了整条刷新计划（物化视图全量重算），
#: 纯属浪费机器，而且把「到底哪一步失败」淹在噪声里。
SAFETY_NET_CIRCUIT_BREAK_THRESHOLD = 3

#: 熔断后的**冷却时间**（分钟）—— 过了这个时间放一次「半开」尝试，
#: 避免「一次偶发失败就永久停摆」。
SAFETY_NET_CIRCUIT_COOLDOWN_MINUTES = 30

#: ``ops.pipeline_run_log`` 里一行 run 超过这么久还是 ``running`` ⇒ 判定为僵尸。
#:
#: 为什么要回收：``_load_active_dashboard_refresh_runs`` 只要看到 ``running``
#: 的看板刷新 run，就把对应模块判成 ``refreshing``。进程被 kill / OOM /
#: 机器重启 ⇒ run 永远停在 ``running`` ⇒ 模块永远「正在刷新」⇒ 页面永远挂提示。
#: 2026-11-07 实测：``ops.pipeline_run_log`` 里有 3 行永久 ``running`` 的
#: ``dashboard_safety_net_repair``，最老的停了 19 小时。
#:
#: 阈值必须**大于**刷新队列任务的硬超时（``time_limit=1800`` 秒 = 30 分钟）
#: —— 否则还在正常跑的长任务会被误判成僵尸。
STALE_DASHBOARD_REFRESH_RUN_MINUTES = 45

#: 可以**自动重排队**的 SQLSTATE（环境类故障：重跑可能就好了）。
#:
#: - ``40001`` 序列化失败、``40P01`` 死锁、``55P03`` 锁不可用
#: - ``57014`` 查询被取消（含语句超时）
#: - ``53200`` 内存不足、``53300`` 连接数超限
#: - ``08006`` / ``08003`` / ``08001`` 连接类故障
#: - ``57P01`` / ``57P02`` / ``57P03`` 服务端关停 / 重启
#:
#: 不在表里的（``22P02`` 类型转换错、``42P01`` 表不存在、``42703`` 列不存在 等）
#: 一律**不重试**：重跑一百遍还是错，重排队只会把队列堵死。
RETRYABLE_SQLSTATES = frozenset(
    {
        "40001",
        "40P01",
        "55P03",
        "57014",
        "53200",
        "53300",
        "08006",
        "08003",
        "08001",
        "57P01",
        "57P02",
        "57P03",
    }
)


def is_retryable_failure(errors: dict[str, dict[str, str]] | None) -> bool:
    """这些失败该不该自动重排队。

    保守原则：**全部**失败都是可重试的环境类故障，才重排队。
    混着「口径写错」「对象缺失」就不重排队 —— 那种重跑也没用。
    """
    if not errors:
        return False
    for detail in errors.values():
        sqlstate = str((detail or {}).get("sqlstate") or "")
        if sqlstate not in RETRYABLE_SQLSTATES:
            return False
    return True


def is_retryable_exception(exc: BaseException) -> bool:
    """单个异常该不该自动重排队（按 SQLSTATE 判）。"""
    return extract_sqlstate(exc) in RETRYABLE_SQLSTATES


#: 库存事实来源资产 —— 「本次刷新重建了它」就意味着状态层必须跟着重算。
#:
#: 为什么判据从「事件带 data_domain=inventory」换成「刷新目标里含库存事实」
#: （2026-10-31 第 11 轮，详见 docs/architecture/SYNC_MODULE_REFACTOR_PLAN.md §3.9.11）：
#: 旧判据**只有 A 类文件上传会带**（`data_ingestion_service` → `DATA_INGESTED`），
#: 云同步 / 手工触发 / 安全网自愈都不带 ⇒ 生产上状态层**从来没有被刷新过**
#: （`mart.inventory_state` 是空表 → 滞销榜恒 0 行）。
#:
#: 新判据看的是「这次刷新到底动了哪些资产」，**与谁触发的无关**：
#: 只要刷新计划重建了库存事实，状态层就必须跟着重算，否则两者会脱节。
INVENTORY_FACT_TARGET = "semantic.fact_inventory_snapshot"


def _should_refresh_inventory_layers(
    targets: list[str], context: dict[str, Any] | None
) -> bool:
    """本次刷新要不要顺带刷新库存状态层 + 库龄层。

    判据是「库存事实有没有被重建」，不是「事件有没有声明 domain」：
    orders 域的刷新闭包里同样含库存事实
    （`api.business_overview_inventory_backlog_module` → `mart.inventory_backlog_base`
    → `mart.inventory_state` → `semantic.fact_inventory_snapshot`），
    所以订单采集也会顺带把状态层刷对 —— 这正是生产需要的自愈能力。
    """
    if (context or {}).get("data_domain") == "inventory":
        return True
    return INVENTORY_FACT_TARGET in (targets or [])


def _modules_for_targets(targets: list[str]) -> list[str]:
    matched: list[str] = []
    target_set = set(targets)
    for module_name, module_targets in DASHBOARD_MODULE_TARGETS.items():
        module_target_set = set(module_targets.get("core_targets", [])) | set(
            module_targets.get("refresh_targets", [])
        )
        if target_set & module_target_set:
            matched.append(module_name)
    return matched


async def _repair_dashboard_assets_if_needed(db, targets: list[str]) -> None:
    modules = _modules_for_targets(targets)
    if not modules:
        return
    try:
        report = await inspect_dashboard_assets(db)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[RefreshQueue] dashboard asset readiness inspection skipped before refresh: %s",
            exc,
            exc_info=True,
        )
        return
    module_reports = report.get("modules") if isinstance(report, dict) else None
    if not isinstance(module_reports, dict):
        return
    for module_name in modules:
        module_report = module_reports.get(module_name)
        if not isinstance(module_report, dict):
            continue
        if module_report.get("status") != "drift":
            continue
        try:
            await bootstrap_dashboard_assets_if_needed(
                db,
                wait_for_lock=True,
                module=module_name,
            )
            if hasattr(db, "commit"):
                await db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[RefreshQueue] dashboard asset repair failed before refresh: module=%s error=%s",
                module_name,
                exc,
                exc_info=True,
            )


async def _invalidate_refresh_target_caches(targets: list[str]) -> None:
    modules = set(_modules_for_targets(targets))
    if not modules:
        return
    try:
        cache_service = get_cache_service()
        if "business_overview" in modules:
            await cache_service.invalidate_dashboard_business_overview()
        if "inventory_backlog" in modules:
            # 业务概览的「库存积压」四张卡读的是 api.business_overview_inventory_backlog_module，
            # 它的缓存键是 dashboard_inventory_backlog（TTL 300s）。
            # 积压资产组归到 inventory_backlog 模块后，inventory 域刷新不再命中
            # business_overview → invalidate_dashboard_business_overview() 不会被调用 →
            # 这张卡会吃到上一轮采集的旧数据。显式补一次失效。
            await cache_service.invalidate("dashboard_inventory_backlog")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[RefreshQueue] cache invalidation failed after refresh: %s",
            exc,
            exc_info=True,
        )


async def _bootstrap_modules_for_validation_report(
    db, report: RefreshValidationReport
) -> None:
    for module_name in report.modules:
        await bootstrap_dashboard_assets_if_needed(
            db,
            wait_for_lock=True,
            module=module_name,
        )
        if hasattr(db, "commit"):
            await db.commit()


async def _validate_refresh_with_repair(
    db,
    *,
    targets: list[str],
    context: dict,
    modules: list[str],
    pipeline_name: str,
    trigger_source: str,
) -> tuple[RefreshValidationReport, dict | None]:
    report = await validate_refresh_result(
        db,
        targets=targets,
        context=context,
        modules=modules,
    )
    if report.is_success():
        return report, None

    retry_result = await execute_refresh_plan(
        db,
        targets=targets,
        pipeline_name=pipeline_name,
        trigger_source=trigger_source,
        context={**context, "repair_stage": "post_refresh_retry"},
        continue_on_error=True,
        max_attempts=2,
        retry_backoff_seconds=0.1,
    )
    retry_status = extract_refresh_status(retry_result)
    if retry_status == "success" and hasattr(db, "commit"):
        await db.commit()
    retry_report = await validate_refresh_result(
        db,
        targets=targets,
        context=context,
        modules=modules,
        repair_attempted=True,
    )
    if retry_report.is_success():
        return retry_report, retry_result

    await _bootstrap_modules_for_validation_report(db, retry_report)
    final_report = await validate_refresh_result(
        db,
        targets=targets,
        context=context,
        modules=modules,
        repair_attempted=True,
    )
    return final_report, retry_result


# PostgreSQL 死锁（40P01）/ 序列化失败（40001）→ 值得重试
_RETRYABLE_LOCK_SQLSTATES = {"40P01", "40001"}
_RETRYABLE_LOCK_ERROR_NAMES = {"DeadlockDetectedError", "SerializationError"}
# 锁冲突重试：死锁是**事务级**失败，回滚整个事务后重开
LOCK_RETRY_ATTEMPTS = 3
LOCK_RETRY_BACKOFF_SECONDS = 2.0


def _is_retryable_lock_error(exc: BaseException) -> bool:
    """是不是「值得重试」的锁冲突（死锁 / 序列化失败）。

    为什么要在**整个刷新计划的外层**重试
    ----------------------------------
    死锁是**事务级**失败：PostgreSQL 把整个事务标记为 aborted 后，
    SAVEPOINT（``db.begin_nested()``）回滚无效 —— 必须回滚**整个事务**再重开。
    所以语句级的重试救不回来，必须把整个计划重跑一遍。
    """
    for candidate in (exc, getattr(exc, "orig", None)):
        if candidate is None:
            continue
        sqlstate = getattr(candidate, "sqlstate", None) or getattr(
            candidate, "pgcode", None
        )
        if sqlstate in _RETRYABLE_LOCK_SQLSTATES:
            return True
        if type(candidate).__name__ in _RETRYABLE_LOCK_ERROR_NAMES:
            return True
    return False


async def _run_plan_with_lock_retry(
    db: Any,
    task: Any,
    targets: list[str],
    context: dict[str, Any],
) -> Any:
    """跑刷新计划；遇到死锁就**回滚整个事务**后退避重试。

    没有它，一次死锁就把刷新任务打成 failed（2026-10-26 线上事故）。
    """
    last_exc: BaseException | None = None
    for attempt in range(1, LOCK_RETRY_ATTEMPTS + 1):
        try:
            return await execute_refresh_plan(
                db,
                targets=targets,
                pipeline_name=task.pipeline_name,
                trigger_source=getattr(task, "trigger_type", "data_ingested"),
                context=context,
                continue_on_error=True,
                max_attempts=2,
                retry_backoff_seconds=0.1,
            )
        except Exception as exc:  # noqa: BLE001
            if not _is_retryable_lock_error(exc) or attempt >= LOCK_RETRY_ATTEMPTS:
                raise
            last_exc = exc
            logger.warning(
                "[RefreshQueue] 遇到锁冲突（死锁/序列化失败），第 %s/%s 次重试：%s",
                attempt,
                LOCK_RETRY_ATTEMPTS,
                exc,
            )
            # 关键：死锁是事务级失败 → 必须回滚整个事务，SAVEPOINT 无效
            if hasattr(db, "rollback"):
                await db.rollback()
            await asyncio.sleep(LOCK_RETRY_BACKOFF_SECONDS * attempt)
    assert last_exc is not None
    raise last_exc


async def _async_process_refresh_queue_task() -> dict:
    db = AsyncSessionLocal()
    try:
        queue_service = RefreshQueueService(db)
        recovered_count = await queue_service.recover_stale_running_tasks(
            timeout_seconds=REFRESH_QUEUE_RUNNING_TIMEOUT_SECONDS
        )
        if recovered_count:
            logger.warning(
                "[RefreshQueue] recovered %s stale running refresh tasks",
                recovered_count,
            )
        task = await queue_service.claim_next_refresh_task()
        if task is None:
            return {"status": "skipped", "reason": "no_pending_refresh_queue_task"}
        lane = getattr(task, "domain", None) or "default"

        try:
            targets = list(task.targets_json or [])
            context = dict(task.context_json or {})
            modules = _modules_for_targets(targets)
            await _repair_dashboard_assets_if_needed(db, targets)
            refresh_result = await _run_plan_with_lock_retry(db, task, targets, context)
            run_id = extract_run_id(refresh_result)
            refresh_status = extract_refresh_status(refresh_result)
            failed_targets = extract_failed_targets(refresh_result)
            if _should_refresh_inventory_layers(targets, context):
                # 先同步 SKU 身份(miaoshou 别名桥),后面的刷新才拿得到 sku_id 映射
                await sync_inventory_skus(db, source_file_id=context.get("file_id"))
                # 状态层先 upsert：「距上次进货天数」的来源就是它。
                # 不跑这一步 → 状态层不动 → 天数不推进 → 增量窗口永远是同一个。
                await InventoryStateRefreshService(db).refresh(force_full=False)
                await InventoryAgeRefreshService(db).refresh(force_full=False)
            if hasattr(db, "commit"):
                await db.commit()
            if refresh_status != "success":
                error_message = (
                    f"refresh pipeline {refresh_status}: "
                    f"{', '.join(str(target) for target in failed_targets) or 'unknown target'}"
                )
                # 只有「环境类故障」（锁冲突 / 超时 / 连接断了）才自动重排队。
                # 口径错、对象缺失这类重跑也没用 ⇒ 直接判失败，留给人工看。
                failure_details = (
                    refresh_result.get("failed_target_errors")
                    if isinstance(refresh_result, dict)
                    else None
                )
                retryable = is_retryable_failure(failure_details)
                await queue_service.mark_failed(
                    task.id, error_message, retryable=retryable
                )
                return {
                    "status": "failed",
                    "job_id": task.job_id,
                    "run_id": run_id,
                    "domain": lane,
                    "error": error_message,
                    "retryable": retryable,
                }
            validation_report, repair_result = await _validate_refresh_with_repair(
                db,
                targets=targets,
                context=context,
                modules=modules,
                pipeline_name=task.pipeline_name,
                trigger_source=getattr(task, "trigger_type", "data_ingested"),
            )
            if repair_result is not None:
                run_id = extract_run_id(repair_result) or run_id
            if not validation_report.is_success():
                error_message = validation_report.to_error_message()
                # 校验失败 = 数据/口径不对（缺对象、口径漂移）⇒ 不自动重试。
                await queue_service.mark_failed(task.id, error_message)
                return {
                    "status": "failed",
                    "job_id": task.job_id,
                    "run_id": run_id,
                    "domain": lane,
                    "error": error_message,
                    "missing_objects": validation_report.missing_objects,
                    "stale_targets": validation_report.stale_targets,
                }
            await _invalidate_refresh_target_caches(targets)
            await queue_service.mark_completed(task.id)
            return {
                "status": "success",
                "job_id": task.job_id,
                "run_id": run_id,
                "domain": lane,
            }
        except Exception as exc:  # noqa: BLE001
            if hasattr(db, "rollback"):
                await db.rollback()
            retryable = is_retryable_exception(exc)
            await queue_service.mark_failed(task.id, str(exc), retryable=retryable)
            logger.warning(
                "[RefreshQueue] queue task failed: job_id=%s domain=%s retryable=%s error=%s",
                task.job_id,
                lane,
                retryable,
                exc,
                exc_info=True,
            )
            return {
                "status": "failed",
                "job_id": task.job_id,
                "domain": lane,
                "error": str(exc),
                "retryable": retryable,
            }
    finally:
        await db.close()


@celery_app.task(
    name="backend.tasks.refresh_queue_tasks.process_refresh_queue_task",
    bind=True,
    # 独立队列：刷新任务单条最长 250 秒（生产实测），和「定时任务」挤在同一个
    # 队列里会被拖慢，也让「最多 2 道」的并发上限不好观察。
    queue="refresh_queue",
    priority=5,
    time_limit=1800,
    soft_time_limit=1500,
)
def process_refresh_queue_task(self):  # noqa: ANN201
    return run_async_task(_async_process_refresh_queue_task)


async def _reap_stale_dashboard_refresh_runs(
    db,
    *,
    stale_minutes: int = STALE_DASHBOARD_REFRESH_RUN_MINUTES,
) -> int:
    """把永久 ``running`` 的看板刷新 run 标记为 ``failed``（僵尸回收）。

    为什么必须回收
    --------------
    ``dashboard_bootstrap._load_active_dashboard_refresh_runs`` 只要看到
    ``status='running'`` 的看板刷新 run，就把对应模块判成 ``refreshing``。
    进程被 kill / OOM / 机器重启 ⇒ 那行 run 永远停在 ``running``
    ⇒ 模块永远「正在刷新」⇒ 页面永远挂提示 ⇒ 安全网还会一直往队列里排修复。

    2026-11-07 实测：``ops.pipeline_run_log`` 里 3 行永久 ``running`` 的
    ``dashboard_safety_net_repair``（最老的停了 19 小时）。

    匹配条件**包含** ``_load_active_dashboard_refresh_runs`` 的全部条件
    （那部分直接决定状态判定，必须清），并额外覆盖安全网 / bootstrap 两族
    （它们不影响状态判定，但会让监控表越积越多、盖住真正的失败）。
    """
    try:
        result = await db.execute(
            text(
                """
                UPDATE ops.pipeline_run_log
                SET status = 'failed',
                    completed_at = NOW(),
                    error_message = COALESCE(
                        error_message, 'stale_run_reaped_by_safety_net'
                    )
                WHERE status = 'running'
                  AND started_at < NOW()
                      - make_interval(mins => CAST(:stale_minutes AS integer))
                  AND (
                      pipeline_name LIKE 'dashboard_materialization_refresh.%'
                      OR pipeline_name LIKE 'dashboard_materialization_rebuild_core.%'
                      OR pipeline_name LIKE 'dashboard_safety_net_repair%'
                      OR pipeline_name LIKE 'bootstrap_postgresql_dashboard%'
                      OR (
                          trigger_source = 'materialization_refresh'
                          AND context ? 'module_name'
                      )
                  )
                RETURNING id
                """
            ),
            {"stale_minutes": int(stale_minutes)},
        )
        reaped = list(result.fetchall())
        if reaped:
            if hasattr(db, "commit"):
                await db.commit()
            logger.warning(
                "[RefreshQueue] reaped %s stale dashboard refresh run(s)",
                len(reaped),
            )
        return len(reaped)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[RefreshQueue] stale dashboard refresh run reaping skipped: %s",
            exc,
            exc_info=True,
        )
        return 0


async def _safety_net_consecutive_repair_failures(
    db,
    *,
    module_name: str,
    limit: int = 20,
) -> tuple[int, datetime | None]:
    """返回 ``(连续失败次数, 最近一次失败的时间)``。

    判据：把该模块的 ``dashboard_safety_net_repair`` 任务按时间倒序看，
    从最新一条开始数连续的 ``failed``；碰到第一条不是 failed 的就停。

    这样熔断是**自复位**的：一旦有一次成功（或被跳过），连续计数归零。
    """
    try:
        result = await db.execute(
            text(
                """
                SELECT status, created_at, last_error
                FROM core.refresh_queue_tasks
                WHERE pipeline_name = 'dashboard_safety_net_repair'
                  AND context_json->>'module_name' = :module_name
                ORDER BY id DESC
                LIMIT :limit
                """
            ),
            {"module_name": module_name, "limit": int(limit)},
        )
        rows = list(result.mappings())
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[RefreshQueue] safety net circuit inspection failed: module=%s error=%s",
            module_name,
            exc,
            exc_info=True,
        )
        return 0, None

    consecutive_failures = 0
    last_failure_at: datetime | None = None
    for row in rows:
        if str(row.get("status") or "") != "failed":
            break
        consecutive_failures += 1
        created_at = row.get("created_at")
        if isinstance(created_at, datetime) and last_failure_at is None:
            last_failure_at = created_at
    return consecutive_failures, last_failure_at


async def _async_dashboard_refresh_safety_net() -> dict:
    db = AsyncSessionLocal()
    try:
        queue_service = RefreshQueueService(db)
        recovered_count = await queue_service.recover_stale_running_tasks(
            timeout_seconds=REFRESH_QUEUE_RUNNING_TIMEOUT_SECONDS
        )
        reaped_runs = await _reap_stale_dashboard_refresh_runs(db)
        report = await inspect_dashboard_assets(db)
        module_reports = report.get("modules") if isinstance(report, dict) else {}
        enqueued_repairs = 0
        circuit_open_modules: list[str] = []
        if isinstance(module_reports, dict):
            for module_name, module_report in module_reports.items():
                if not isinstance(module_report, dict):
                    continue
                status = str(module_report.get("status") or "")
                # 只有 ``drift`` 是**可自愈**的状态：对象缺失（普通视图 / 物化视图
                # 都没了）⇒ 修复任务跑起来会用资产文件把它们建回来
                # （「不存在则 CREATE」）。
                #
                # ``refreshing`` 说明**正有一趟刷新在跑** —— 再排一次只会并发；
                # 而「刷新资产的定义落后于文件」这种**没人能修**的状态
                # （资产文件对已存在的物化视图只做原地 REFRESH，从不重建定义）
                # 已经在状态机里不再作为判据（见 ``dashboard_bootstrap``），
                # 所以这里也**不需要**再排修复任务。
                if status != "drift":
                    continue
                module_targets = DASHBOARD_MODULE_TARGETS.get(module_name, {})
                targets = list(
                    dict.fromkeys(
                        [
                            *module_targets.get("refresh_targets", []),
                            *module_targets.get("core_targets", []),
                        ]
                    )
                )
                if not targets:
                    continue

                consecutive_failures, last_failure_at = (
                    await _safety_net_consecutive_repair_failures(
                        db, module_name=module_name
                    )
                )
                if consecutive_failures >= SAFETY_NET_CIRCUIT_BREAK_THRESHOLD:
                    cooldown_deadline = None
                    if last_failure_at is not None:
                        if last_failure_at.tzinfo is None:
                            last_failure_at = last_failure_at.replace(
                                tzinfo=timezone.utc
                            )
                        cooldown_deadline = last_failure_at + timedelta(
                            minutes=SAFETY_NET_CIRCUIT_COOLDOWN_MINUTES
                        )
                    now = datetime.now(timezone.utc)
                    # 拿不到失败时间（理论上不会发生，``created_at`` NOT NULL）
                    # ⇒ 保守按「仍在冷却」处理。
                    if cooldown_deadline is None or now < cooldown_deadline:
                        circuit_open_modules.append(module_name)
                        logger.error(
                            "[RefreshQueue] dashboard safety net circuit OPEN: "
                            "module=%s consecutive_failures=%s last_failure_at=%s "
                            "cooldown_until=%s —— 已暂停自动修复，需人工介入",
                            module_name,
                            consecutive_failures,
                            last_failure_at,
                            cooldown_deadline,
                        )
                        continue

                await queue_service.enqueue_refresh(
                    trigger_type="safety_net",
                    pipeline_name="dashboard_safety_net_repair",
                    targets=targets,
                    context={
                        "module_name": module_name,
                        "reason": "dashboard_asset_drift",
                        "dashboard_asset_status": module_report.get("status"),
                        "missing_objects": module_report.get("core_missing_objects", [])
                        or module_report.get("missing_objects", []),
                    },
                )
                enqueued_repairs += 1
        return {
            "status": "success",
            "recovered_stale_tasks": recovered_count,
            "reaped_stale_refresh_runs": reaped_runs,
            "enqueued_repairs": enqueued_repairs,
            "circuit_open_modules": circuit_open_modules,
        }
    finally:
        await db.close()


@celery_app.task(
    name="backend.tasks.refresh_queue_tasks.dashboard_refresh_safety_net",
    bind=True,
    queue="scheduled",
    priority=4,
    time_limit=900,
    soft_time_limit=780,
)
def dashboard_refresh_safety_net(self):  # noqa: ANN201
    return run_async_task(_async_dashboard_refresh_safety_net)
