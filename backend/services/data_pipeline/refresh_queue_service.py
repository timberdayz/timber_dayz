from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Select, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import RefreshQueueTask
from modules.core.data_domains import normalize_data_domain


#: 有刷新目标图的业务域（与 ``refresh_registry._REFRESHABLE_DOMAINS`` 保持一致）。
#: 这五个域各自一条道；其余（finance / purchase / 手工触发 / 安全网）走共享道。
REFRESH_LANES = frozenset({"orders", "analytics", "products", "inventory", "services"})

#: 共享道：没有明确业务域的任务都进这里（生产实测 614 条里只有 7 条）。
DEFAULT_LANE = "default"

#: 同时最多跑几道刷新。
#:
#: 为什么是 2：生产 PG 容器内存实限 **1.5GiB**，``work_mem=8MB × max_connections=80``
#: 理论峰值 640MB；两条道并发会叠加。相比单通道（今天的形态），
#: 2 道能让「慢域」不再堵住「快域」，又不至于把内存打爆。
REFRESH_QUEUE_MAX_CONCURRENT = 2

#: 领取任务的**全局互斥键**。
#:
#: 为什么需要：两个 Celery worker 可能同时来领任务。如果都走「先查在跑的域 →
#: 再挑一条 pending」，两个事务会挑到**同一条**任务（重复跑），或者挑到
#: **同一个域**的两条任务（违反「同域串行」）。
#:
#: 用一把 PostgreSQL 事务级 advisory lock 把「挑选 + 标记为 running」这个
#: 短临界区串起来 —— 它在 commit 时自动释放，进程挂了也会随事务回滚释放。
REFRESH_QUEUE_CLAIM_LOCK_KEY = int(
    hashlib.blake2b(b"xihong.refresh_queue.claim", digest_size=8).hexdigest(),
    16,
) - (1 << 63)

#: 失败后**自动**重排队的最大次数。
#:
#: ``attempt_count`` 只增不减 ⇒ 同一条任务最多自动重试这么多次；
#: 人工点重试（``retry_failed_task``）才把计数归零。
#: 归零 = 无限重排队 —— 生产失败率 23%，不设上界会变成重试风暴。
MAX_AUTO_RETRY_ATTEMPTS = 3

#: 退避基数（秒）与上限（秒）。
#:
#: 60s → 120s → 240s，封顶 30 分钟。第一次重试等 1 分钟：
#: 采集入库后 1 分钟内刷新本来就该完成，等 1 分钟不算拖延。
RETRY_BACKOFF_BASE_SECONDS = 60
RETRY_BACKOFF_MAX_SECONDS = 30 * 60


def resolve_refresh_lane(context: dict[str, Any] | None) -> str:
    """把任务的上下文解析成它该走哪条道。

    判据是 ``context["data_domain"]``（生产覆盖 607/614 = 99%，精确）。

    **不从 targets 反推**：targets 里含已退役的目标
    （``api.store_analysis_*`` / ``mart.shop_hour_traffic_kpi`` /
    ``api.annual_summary_*`` / ``api.clearance_ranking_module``），
    反推必然歧义 —— 同一个目标集合可能同时属于多个域。
    """
    normalized = normalize_data_domain((context or {}).get("data_domain"))
    if normalized in REFRESH_LANES:
        return normalized
    return DEFAULT_LANE


def retry_backoff_seconds(attempt_count: int) -> int:
    """第 ``attempt_count`` 次失败后，等多久再重试（指数退避，封顶 30 分钟）。"""
    exponent = max(0, int(attempt_count or 0) - 1)
    delay = RETRY_BACKOFF_BASE_SECONDS * (2**exponent)
    return min(delay, RETRY_BACKOFF_MAX_SECONDS)


class RefreshQueueService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def build_dedupe_key(pipeline_name: str, targets: list[str]) -> str:
        normalized_targets = sorted(
            str(target).strip() for target in targets if str(target).strip()
        )
        payload = json.dumps(
            {
                "pipeline_name": str(pipeline_name or "").strip(),
                "targets": normalized_targets,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _merge_context(
        existing: dict[str, Any], incoming: dict[str, Any]
    ) -> dict[str, Any]:
        merged = dict(existing or {})
        for key, value in (incoming or {}).items():
            if isinstance(value, list) and isinstance(merged.get(key), list):
                merged[key] = list(dict.fromkeys([*merged[key], *value]))
            elif isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
        return merged

    async def enqueue_refresh(
        self,
        *,
        trigger_type: str,
        pipeline_name: str,
        targets: list[str],
        context: dict[str, Any] | None = None,
    ) -> RefreshQueueTask:
        dedupe_key = self.build_dedupe_key(pipeline_name, targets)
        existing = await self._get_pending_by_dedupe_key(dedupe_key)
        if existing:
            existing.context_json = self._merge_context(
                existing.context_json or {}, context or {}
            )
            # 域跟着上下文走：合并进来的事件可能带了更明确的 data_domain。
            existing.domain = resolve_refresh_lane(existing.context_json or {})
            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        task = RefreshQueueTask(
            job_id=f"refresh-{uuid.uuid4().hex}",
            trigger_type=trigger_type,
            pipeline_name=pipeline_name,
            dedupe_key=dedupe_key,
            targets_json=sorted(
                str(target).strip() for target in targets if str(target).strip()
            ),
            context_json=context or {},
            status="pending",
            attempt_count=0,
            domain=resolve_refresh_lane(context or {}),
            next_retry_at=None,
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def _acquire_claim_lock(self) -> None:
        """拿领取临界区的互斥锁（仅 PostgreSQL）。

        为什么按方言降级
        --------------
        单元测试跑在 SQLite 上（``backend/tests/data_pipeline/test_refresh_queue_service.py``），
        SQLite 没有 advisory lock。降级后逻辑不变（分道、并发上限、退避都还在），
        只是少了跨进程互斥 —— 单进程测试里本来就不需要。
        """
        try:
            bind = self.db.get_bind()
            dialect_name = str(getattr(getattr(bind, "dialect", None), "name", ""))
        except Exception:  # noqa: BLE001
            dialect_name = ""
        if dialect_name != "postgresql":
            return
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": REFRESH_QUEUE_CLAIM_LOCK_KEY},
        )

    async def claim_next_refresh_task(
        self, *, max_concurrent: int = REFRESH_QUEUE_MAX_CONCURRENT
    ) -> RefreshQueueTask | None:
        """领一条「本域没在跑、且到点该重试」的任务。

        并发上限是**库里的事实**，不是调用方的自觉
        ------------------------------------------
        无论 Celery 派了多少条消息进来，库里同时在跑的任务数都不会超过
        ``max_concurrent``。这样「最多 2 道」是硬保证，不依赖编排配置正确。

        同域串行
        --------
        已经在跑的任务所占的域会被排除 ⇒ 同一个域不会同时跑两条。

        临界区用事务级 advisory lock 保护
        --------------------------------
        两个 worker 同时来领时，「查在跑的域 → 挑一条 → 标记 running」
        必须是一个不可分割的动作，否则会领到同一条任务。
        """
        await self._acquire_claim_lock()

        running_result = await self.db.execute(
            select(RefreshQueueTask.id, RefreshQueueTask.domain).where(
                RefreshQueueTask.status == "running"
            )
        )
        running_rows = running_result.all()
        if len(running_rows) >= max_concurrent:
            # 位置已满 → 释放 advisory lock（commit 会释放）并空手而归。
            await self.db.commit()
            return None

        busy_domains = {str(row[1] or DEFAULT_LANE) for row in running_rows}
        now = datetime.now(timezone.utc)

        stmt: Select[tuple[RefreshQueueTask]] = (
            select(RefreshQueueTask)
            .where(
                RefreshQueueTask.status == "pending",
                or_(
                    RefreshQueueTask.next_retry_at.is_(None),
                    RefreshQueueTask.next_retry_at <= now,
                ),
            )
            .order_by(RefreshQueueTask.created_at.asc(), RefreshQueueTask.id.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if busy_domains:
            stmt = stmt.where(RefreshQueueTask.domain.notin_(sorted(busy_domains)))

        result = await self.db.execute(stmt)
        task = result.scalar_one_or_none()
        if task is None:
            await self.db.commit()
            return None

        task.status = "running"
        task.attempt_count = (task.attempt_count or 0) + 1
        task.started_at = now
        task.last_error = None
        task.next_retry_at = None
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def recover_stale_running_tasks(self, *, timeout_seconds: int) -> int:
        """把「跑太久没回来的」任务收回队列。

        为什么收回而不是判死
        ------------------
        ``running`` 超时只说明**执行它的 worker 没了**（被 OOM kill、容器重启、
        机器断电），不代表这件事做不了 ⇒ 收回队列重排才是对的。
        以前这里是直接判 ``failed`` ⇒ 这条刷新永远不再自动执行
        （生产 144 条失败里就有一批是这样丢掉的）。

        次数有上界：``attempt_count`` 只增不减，超过 ``MAX_AUTO_RETRY_ATTEMPTS``
        就转 ``failed``，不再自动重排队。

        超时阈值必须**大于** Celery 的硬超时（1800 秒），否则会把「还在跑的
        任务」误判成死的，然后重排队 → 同一条刷新被跑第二遍（还可能并发）。
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=timeout_seconds)
        result = await self.db.execute(
            select(RefreshQueueTask).where(
                RefreshQueueTask.status == "running",
                RefreshQueueTask.started_at.is_not(None),
                RefreshQueueTask.started_at < cutoff,
            )
        )
        rows = result.scalars().all()
        requeued = 0
        for task in rows:
            task.last_error = "refresh queue task timed out while running"
            attempts = task.attempt_count or 0
            if attempts < MAX_AUTO_RETRY_ATTEMPTS:
                task.status = "pending"
                task.next_retry_at = now + timedelta(
                    seconds=retry_backoff_seconds(attempts)
                )
                task.started_at = None
                task.finished_at = None
                requeued += 1
            else:
                task.status = "failed"
                task.next_retry_at = None
                task.finished_at = now
        if rows:
            await self.db.commit()
        return len(rows)

    async def mark_completed(self, task_id: int) -> RefreshQueueTask:
        task = await self.db.get(RefreshQueueTask, task_id)
        if task is None:
            raise ValueError(f"refresh queue task {task_id} not found")
        task.status = "completed"
        task.next_retry_at = None
        task.finished_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def mark_failed(
        self,
        task_id: int,
        error_message: str,
        *,
        retryable: bool = False,
        max_attempts: int = MAX_AUTO_RETRY_ATTEMPTS,
    ) -> RefreshQueueTask:
        """标记失败；**可重试**的错误会自动带退避重排队。

        为什么要区分「可重试」和「不可重试」
        ----------------------------------
        生产失败率 23%。如果把「数据口径错」「对象缺失」这类**再跑一百遍
        也还是错**的错误也自动重排队，就会变成重试风暴，把队列堵死。

        可重试（环境类，重跑可能就好了）：

        - ``40001`` 序列化失败、``40P01`` 死锁、``55P03`` 锁不可用
        - ``57014`` 查询被取消（含语句超时）
        - ``53200`` 内存不足、``53300`` 连接数超限
        - ``08006`` / ``08003`` / ``08001`` 连接类故障
        - ``57P01`` / ``57P02`` / ``57P03`` 服务端关停/重启

        不可重试（数据/口径/对象缺失类）：``22P02``、``42P01``、``42703`` 等，
        以及校验阶段报出的 ``missing_objects``。

        ``attempt_count`` 不归零
        ----------------------
        归零 = 无限重排队。自动重排队只增不减，人工重试才归零。
        """
        task = await self.db.get(RefreshQueueTask, task_id)
        if task is None:
            raise ValueError(f"refresh queue task {task_id} not found")
        now = datetime.now(timezone.utc)
        attempts = task.attempt_count or 0
        task.last_error = error_message
        if retryable and attempts < max_attempts:
            task.status = "pending"
            task.next_retry_at = now + timedelta(
                seconds=retry_backoff_seconds(attempts)
            )
            task.started_at = None
            task.finished_at = None
        else:
            task.status = "failed"
            task.next_retry_at = None
            task.finished_at = now
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def list_tasks(
        self, *, status: str | None = None, limit: int = 100
    ) -> list[RefreshQueueTask]:
        stmt: Select[tuple[RefreshQueueTask]] = select(RefreshQueueTask).order_by(
            RefreshQueueTask.created_at.desc(),
            RefreshQueueTask.id.desc(),
        )
        if status:
            stmt = stmt.where(RefreshQueueTask.status == status)
        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def retry_failed_task(self, task_id: int) -> RefreshQueueTask:
        """人工重试：把次数归零，重新排队。

        人工介入 = 承认「之前失败的原因已经被处理掉了」⇒ 计数归零是安全的。
        """
        task = await self.db.get(RefreshQueueTask, task_id)
        if task is None:
            raise ValueError(f"refresh queue task {task_id} not found")
        if task.status != "failed":
            raise ValueError(f"refresh queue task {task_id} is not failed")

        task.status = "pending"
        task.attempt_count = 0
        task.last_error = None
        task.started_at = None
        task.finished_at = None
        task.next_retry_at = None
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def _get_pending_by_dedupe_key(
        self, dedupe_key: str
    ) -> RefreshQueueTask | None:
        result = await self.db.execute(
            select(RefreshQueueTask)
            .where(
                RefreshQueueTask.dedupe_key == dedupe_key,
                RefreshQueueTask.status == "pending",
            )
            .order_by(RefreshQueueTask.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()
