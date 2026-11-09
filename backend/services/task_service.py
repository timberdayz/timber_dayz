"""
任务服务 - Task Service

提供任务状态管理、乐观锁、队列管理等功能
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Callable, Awaitable
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, update

from modules.core.db import CollectionTask, CollectionTaskLog
from modules.core.logger import get_logger

logger = get_logger(__name__)


class TaskServiceError(Exception):
    """任务服务错误"""

    pass


class OptimisticLockError(TaskServiceError):
    """乐观锁冲突错误"""

    pass


class TaskService:
    """
    任务服务

    功能:
    1. 乐观锁状态更新
    2. 任务队列管理
    3. 任务状态转换
    4. 账号能力过滤(v4.7.0 Phase 2.5.1)
    """

    # 最大并发任务数
    MAX_CONCURRENT_TASKS = int(os.getenv("MAX_COLLECTION_TASKS", 3))

    # pending/queued 任务的陈旧阈值（秒）：超过这个时间没有任何动静，
    # 就认为它是上次进程没收拾干净的僵尸任务（见 mark_interrupted_tasks）。
    STALE_PENDING_RECLAIM_SECONDS = int(
        os.getenv("COLLECTION_STALE_PENDING_RECLAIM_SECONDS", "60")
    )

    # 有效的状态转换
    VALID_STATUS_TRANSITIONS = {
        "pending": ["queued", "running", "cancelled"],
        "queued": ["running", "cancelled"],
        "running": ["completed", "failed", "paused", "cancelled", "interrupted"],
        "paused": ["running", "cancelled"],
        "completed": [],
        "failed": [],
        "cancelled": [],
        "interrupted": [],
    }

    def __init__(self, db: Session):
        """
        初始化任务服务

        Args:
            db: 数据库会话
        """
        self.db = db

    def mark_interrupted_tasks(self, stale_after_seconds: Optional[int] = None) -> int:
        """
        标记服务重启前遗留的任务为中断(interrupted)

        [*] 为什么要连 pending/queued 一起回收：
            采集任务是在接口里落库(status=pending)后，用 `asyncio.create_task`
            在**本进程内**起后台协程执行的；排队(queued)的任务也只靠**进程内**
            的"上一个任务结束 -> 拉起下一个"回调推进。进程一挂，这些任务没人再管，
            会永远停在 pending/queued（僵尸任务），页面上看着像"还在跑"。

        回收口径：
        - running：一律回收（进程重启后不可能还在跑）
        - pending/queued：只回收**陈旧**的（默认超过阈值没动静），
          避免多 worker 部署时把别的 worker 刚创建的任务误判成僵尸

        Args:
            stale_after_seconds: pending/queued 的陈旧阈值（秒）。None 表示用默认值。

        Returns:
            int: 标记的任务数量
        """
        now = datetime.now(timezone.utc)
        threshold = (
            self.STALE_PENDING_RECLAIM_SECONDS
            if stale_after_seconds is None
            else stale_after_seconds
        )
        cutoff = now - timedelta(seconds=max(0, threshold))

        running_result = self.db.execute(
            update(CollectionTask)
            .where(CollectionTask.status == "running")
            .values(
                status="interrupted",
                error_message="服务重启导致任务中断",
                updated_at=now,
            )
        )

        stale_result = self.db.execute(
            update(CollectionTask)
            .where(CollectionTask.status.in_(["pending", "queued"]))
            .where(
                or_(
                    CollectionTask.updated_at <= cutoff,
                    CollectionTask.created_at <= cutoff,
                )
            )
            .values(
                status="interrupted",
                error_message="服务重启导致任务中断（尚未开始执行）",
                updated_at=now,
            )
        )

        self.db.commit()

        count = (running_result.rowcount or 0) + (stale_result.rowcount or 0)
        if count > 0:
            logger.warning(
                f"Marked {count} tasks as interrupted due to service restart"
            )

        return count

    def validate_status_transition(self, current_status: str, new_status: str) -> bool:
        """
        验证状态转换是否有效

        Args:
            current_status: 当前状态
            new_status: 新状态

        Returns:
            bool: 是否有效
        """
        valid_transitions = self.VALID_STATUS_TRANSITIONS.get(current_status, [])
        return new_status in valid_transitions

    def filter_domains_by_account_capability(
        self, account_info: Dict[str, Any], data_domains: List[str]
    ) -> tuple[List[str], List[str]]:
        """
        根据账号能力过滤数据域(v4.7.0新增)

        Args:
            account_info: 账号信息字典
            data_domains: 请求的数据域列表

        Returns:
            tuple[List[str], List[str]]: (支持的数据域, 不支持的数据域)
        """
        capabilities = account_info.get("capabilities", {})

        # 如果没有capabilities字段,默认全部支持
        if not capabilities:
            logger.warning(
                f"Account {account_info.get('account_id')} missing capabilities, assuming all supported"
            )
            return data_domains, []

        supported = []
        unsupported = []

        for domain in data_domains:
            if capabilities.get(domain, True):  # 默认True,向后兼容
                supported.append(domain)
            else:
                unsupported.append(domain)
                logger.info(
                    f"Domain '{domain}' filtered out for account {account_info.get('account_id')} (not in capabilities)"
                )

        return supported, unsupported
