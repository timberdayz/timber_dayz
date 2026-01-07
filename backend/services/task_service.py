"""
任务服务 - Task Service

提供任务状态管理、乐观锁、队列管理等功能
"""

import os
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable, Awaitable
from sqlalchemy.orm import Session
from sqlalchemy import and_, update

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
    
    功能：
    1. 乐观锁状态更新
    2. 任务队列管理
    3. 任务状态转换
    4. 账号能力过滤（v4.7.0 Phase 2.5.1）
    """
    
    # 最大并发任务数
    MAX_CONCURRENT_TASKS = int(os.getenv('MAX_COLLECTION_TASKS', 3))
    
    # 有效的状态转换
    VALID_STATUS_TRANSITIONS = {
        'pending': ['queued', 'running', 'cancelled'],
        'queued': ['running', 'cancelled'],
        'running': ['completed', 'failed', 'paused', 'cancelled', 'interrupted'],
        'paused': ['running', 'cancelled'],
        'completed': [],
        'failed': [],
        'cancelled': [],
        'interrupted': [],
    }
    
    def __init__(self, db: Session):
        """
        初始化任务服务
        
        Args:
            db: 数据库会话
        """
        self.db = db
    
    def filter_domains_by_account_capability(
        self,
        account_info: Dict[str, Any],
        requested_domains: List[str]
    ) -> tuple[List[str], List[str]]:
        """
        根据账号能力过滤数据域（Phase 2.5.1）
        
        Args:
            account_info: 账号信息字典
            requested_domains: 请求的数据域列表
            
        Returns:
            tuple: (支持的数据域列表, 不支持的数据域列表)
            
        Example:
            >>> account = {"capabilities": {"orders": True, "services": False}}
            >>> supported, unsupported = service.filter_domains_by_account_capability(
            ...     account, ["orders", "services", "products"]
            ... )
            >>> supported
            ['orders', 'products']  # products默认为True
            >>> unsupported
            ['services']
        """
        account_id = account_info.get('account_id', 'unknown')
        
        # 获取账号能力配置
        capabilities = account_info.get('capabilities')
        
        # 如果没有配置capabilities或为空，默认所有域都支持
        if not capabilities:
            logger.warning(f"Account {account_id} missing capabilities, assuming all supported")
            return requested_domains, []
        
        supported_domains = []
        unsupported_domains = []
        
        for domain in requested_domains:
            # 检查该域是否被支持（默认为True）
            is_supported = capabilities.get(domain, True)
            
            if is_supported:
                supported_domains.append(domain)
            else:
                unsupported_domains.append(domain)
                logger.info(
                    f"Domain '{domain}' filtered out for account {account_id} (not in capabilities)"
                )
        
        if unsupported_domains:
            logger.info(
                f"Capability filter for {account_id}: "
                f"requested={len(requested_domains)}, "
                f"supported={len(supported_domains)}, "
                f"filtered={len(unsupported_domains)} ({', '.join(unsupported_domains)})"
            )
        
        return supported_domains, unsupported_domains
    
    def update_task_status(
        self,
        task_id: int,
        new_status: str,
        expected_version: int = None,
        expected_status: str = None,
        progress: int = None,
        current_step: str = None,
        error_message: str = None,
        files_collected: int = None,
        duration_seconds: int = None,
        verification_type: str = None,
    ) -> bool:
        """
        使用乐观锁更新任务状态
        
        Args:
            task_id: 任务数据库ID
            new_status: 新状态
            expected_version: 期望的版本号（乐观锁）
            expected_status: 期望的当前状态
            progress: 进度百分比
            current_step: 当前步骤
            error_message: 错误信息
            files_collected: 采集文件数
            duration_seconds: 执行时长
            verification_type: 验证码类型
            
        Returns:
            bool: 是否更新成功
            
        Raises:
            OptimisticLockError: 乐观锁冲突
            TaskServiceError: 其他错误
        """
        # 构建更新条件
        conditions = [CollectionTask.id == task_id]
        
        if expected_version is not None:
            conditions.append(CollectionTask.version == expected_version)
        
        if expected_status is not None:
            conditions.append(CollectionTask.status == expected_status)
        
        # 构建更新值
        update_values = {
            'status': new_status,
            'version': CollectionTask.version + 1,
            'updated_at': datetime.utcnow(),
        }
        
        if progress is not None:
            update_values['progress'] = progress
        
        if current_step is not None:
            update_values['current_step'] = current_step
        
        if error_message is not None:
            update_values['error_message'] = error_message
        
        if files_collected is not None:
            update_values['files_collected'] = files_collected
        
        if duration_seconds is not None:
            update_values['duration_seconds'] = duration_seconds
        
        if verification_type is not None:
            update_values['verification_type'] = verification_type
        
        # 执行更新
        result = self.db.execute(
            update(CollectionTask)
            .where(and_(*conditions))
            .values(**update_values)
        )
        
        self.db.commit()
        
        # 检查是否更新成功
        if result.rowcount == 0:
            # 查询当前状态以确定失败原因
            task = self.db.query(CollectionTask).filter(CollectionTask.id == task_id).first()
            
            if task is None:
                raise TaskServiceError(f"Task not found: {task_id}")
            
            if expected_version is not None and task.version != expected_version:
                raise OptimisticLockError(
                    f"Version conflict: expected {expected_version}, actual {task.version}"
                )
            
            if expected_status is not None and task.status != expected_status:
                raise TaskServiceError(
                    f"Status conflict: expected {expected_status}, actual {task.status}"
                )
            
            raise TaskServiceError("Update failed for unknown reason")
        
        logger.debug(f"Updated task {task_id} status to {new_status}")
        return True
    
    def add_task_log(
        self,
        task_id: int,
        level: str,
        message: str,
        details: Dict[str, Any] = None
    ) -> CollectionTaskLog:
        """
        添加任务日志
        
        Args:
            task_id: 任务数据库ID
            level: 日志级别（info/warning/error）
            message: 日志消息
            details: 额外详情
            
        Returns:
            CollectionTaskLog: 日志记录
        """
        log = CollectionTaskLog(
            task_id=task_id,
            level=level,
            message=message,
            details=details
        )
        
        self.db.add(log)
        self.db.commit()
        
        return log
    
    def get_running_count(self) -> int:
        """
        获取当前运行中的任务数量
        
        Returns:
            int: 运行中任务数
        """
        return self.db.query(CollectionTask).filter(
            CollectionTask.status == 'running'
        ).count()
    
    def get_queued_tasks(self, limit: int = 10) -> List[CollectionTask]:
        """
        获取排队中的任务（按创建时间排序）
        
        Args:
            limit: 最大返回数量
            
        Returns:
            List[CollectionTask]: 排队中的任务列表
        """
        return self.db.query(CollectionTask).filter(
            CollectionTask.status == 'queued'
        ).order_by(CollectionTask.created_at).limit(limit).all()
    
    def can_start_new_task(self) -> bool:
        """
        检查是否可以启动新任务（基于并发限制）
        
        Returns:
            bool: 是否可以启动
        """
        running_count = self.get_running_count()
        return running_count < self.MAX_CONCURRENT_TASKS
    
    def try_start_next_queued_task(self) -> Optional[CollectionTask]:
        """
        尝试启动下一个排队任务
        
        使用乐观锁确保只有一个任务被启动
        
        Returns:
            Optional[CollectionTask]: 启动的任务，如果没有则返回None
        """
        if not self.can_start_new_task():
            logger.debug("Cannot start new task: max concurrent tasks reached")
            return None
        
        # 获取排队任务
        queued_tasks = self.get_queued_tasks(limit=5)
        
        for task in queued_tasks:
            try:
                # 使用乐观锁更新状态
                self.update_task_status(
                    task_id=task.id,
                    new_status='running',
                    expected_status='queued',
                    expected_version=task.version,
                    progress=0,
                    current_step='准备开始...'
                )
                
                logger.info(f"Started queued task: {task.task_id}")
                
                # 刷新任务对象
                self.db.refresh(task)
                return task
            
            except OptimisticLockError:
                # 其他进程已经启动了这个任务，尝试下一个
                logger.debug(f"Task {task.task_id} already claimed, trying next")
                continue
            
            except TaskServiceError as e:
                logger.warning(f"Failed to start task {task.task_id}: {e}")
                continue
        
        return None
    
    def mark_interrupted_tasks(self) -> int:
        """
        标记中断的任务（服务重启时调用）
        
        将所有running状态的任务标记为interrupted
        
        Returns:
            int: 标记的任务数量
        """
        result = self.db.execute(
            update(CollectionTask)
            .where(CollectionTask.status == 'running')
            .values(
                status='interrupted',
                error_message='服务重启导致任务中断',
                updated_at=datetime.utcnow()
            )
        )
        
        self.db.commit()
        
        count = result.rowcount
        if count > 0:
            logger.warning(f"Marked {count} tasks as interrupted due to service restart")
        
        return count
    
    def check_account_conflict(self, account: str, platform: str) -> bool:
        """
        检查账号是否有正在运行的任务
        
        Args:
            account: 账号ID
            platform: 平台
            
        Returns:
            bool: 是否有冲突
        """
        count = self.db.query(CollectionTask).filter(
            CollectionTask.account == account,
            CollectionTask.platform == platform,
            CollectionTask.status.in_(['running', 'paused'])
        ).count()
        
        return count > 0
    
    def get_task_by_uuid(self, task_uuid: str) -> Optional[CollectionTask]:
        """
        通过UUID获取任务
        
        Args:
            task_uuid: 任务UUID
            
        Returns:
            Optional[CollectionTask]: 任务对象
        """
        return self.db.query(CollectionTask).filter(
            CollectionTask.task_id == task_uuid
        ).first()
    
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
        self,
        account_info: Dict[str, Any],
        data_domains: List[str]
    ) -> tuple[List[str], List[str]]:
        """
        根据账号能力过滤数据域（v4.7.0新增）
        
        Args:
            account_info: 账号信息字典
            data_domains: 请求的数据域列表
            
        Returns:
            tuple[List[str], List[str]]: (支持的数据域, 不支持的数据域)
        """
        capabilities = account_info.get('capabilities', {})
        
        # 如果没有capabilities字段，默认全部支持
        if not capabilities:
            logger.warning(f"Account {account_info.get('account_id')} missing capabilities, assuming all supported")
            return data_domains, []
        
        supported = []
        unsupported = []
        
        for domain in data_domains:
            if capabilities.get(domain, True):  # 默认True，向后兼容
                supported.append(domain)
            else:
                unsupported.append(domain)
                logger.info(f"Domain '{domain}' filtered out for account {account_info.get('account_id')} (not in capabilities)")
        
        return supported, unsupported


class TaskQueueService:
    """
    任务队列服务
    
    管理任务的排队和自动启动
    """
    
    def __init__(self, db: Session, on_task_ready: Callable[[CollectionTask], Awaitable[None]] = None):
        """
        初始化任务队列服务
        
        Args:
            db: 数据库会话
            on_task_ready: 任务就绪回调（用于触发执行）
        """
        self.task_service = TaskService(db)
        self.on_task_ready = on_task_ready
    
    async def enqueue_task(self, task: CollectionTask) -> str:
        """
        将任务加入队列
        
        根据并发限制决定任务状态（queued或running）
        
        Args:
            task: 任务对象
            
        Returns:
            str: 任务的新状态
        """
        # 检查账号冲突
        if self.task_service.check_account_conflict(task.account, task.platform):
            self.task_service.update_task_status(
                task_id=task.id,
                new_status='queued',
                progress=0,
                current_step='等待同账号任务完成...'
            )
            return 'queued'
        
        # 检查并发限制
        if self.task_service.can_start_new_task():
            self.task_service.update_task_status(
                task_id=task.id,
                new_status='running',
                progress=0,
                current_step='准备开始...'
            )
            
            # 触发执行回调
            if self.on_task_ready:
                await self.on_task_ready(task)
            
            return 'running'
        else:
            self.task_service.update_task_status(
                task_id=task.id,
                new_status='queued',
                progress=0,
                current_step='等待执行槽位...'
            )
            return 'queued'
    
    async def on_task_complete(self, task_id: int) -> Optional[CollectionTask]:
        """
        任务完成回调
        
        尝试启动下一个排队任务
        
        Args:
            task_id: 完成的任务ID
            
        Returns:
            Optional[CollectionTask]: 新启动的任务
        """
        next_task = self.task_service.try_start_next_queued_task()
        
        if next_task and self.on_task_ready:
            await self.on_task_ready(next_task)
        
        return next_task

