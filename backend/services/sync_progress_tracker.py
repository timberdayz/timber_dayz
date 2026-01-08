#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据同步进度跟踪服务（Sync Progress Tracker）

v4.12.0新增：
- 使用数据库存储的进度跟踪器（持久化）
- 替代内存存储的ProgressTracker（用于数据同步场景）
- 支持服务重启后恢复进度

v4.18.2更新：
- 支持异步数据库操作（AsyncSession）
- 移除阻塞的 time.sleep()，改用 asyncio.sleep()
- 所有方法改为 async def

职责：
- 创建、更新、查询同步任务进度
- 持久化存储，支持历史查询
- 与现有ProgressTracker并行运行（不同场景）
"""

from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
import asyncio

from modules.core.db import SyncProgressTask
from modules.core.logger import get_logger
from backend.utils.data_formatter import format_datetime

logger = get_logger(__name__)


class SyncProgressTracker:
    """
    数据同步进度跟踪器（数据库存储，支持异步）
    
    v4.18.2更新：支持 AsyncSession，所有方法改为 async def
    
    职责：
    - 创建、更新、查询同步任务进度
    - 持久化存储，支持历史查询
    - 与现有ProgressTracker并行运行（不同场景）
    """
    
    def __init__(self, db: AsyncSession):
        """
        [*] v4.18.2更新：完全过渡到异步架构，只接受AsyncSession
        """
        self.db = db
    
    async def create_task(
        self,
        task_id: str,
        total_files: int,
        task_type: str = "bulk_ingest"
    ) -> Dict[str, Any]:
        """
        创建进度跟踪任务
        
        Args:
            task_id: 任务ID
            total_files: 总文件数
            task_type: 任务类型（bulk_ingest/single_file）
            
        Returns:
            任务信息字典
        """
        try:
            # 检查任务是否已存在
            result = await self.db.execute(
                select(SyncProgressTask).where(SyncProgressTask.task_id == task_id)
            )
            existing_task = result.scalar_one_or_none()
            
            if existing_task:
                logger.warning(f"[SyncProgress] Task {task_id} already exists, updating instead")
                return self._task_to_dict(existing_task)
            
            # 创建新任务
            task = SyncProgressTask(
                task_id=task_id,
                task_type=task_type,
                total_files=total_files,
                processed_files=0,
                current_file="",
                status="pending",
                total_rows=0,
                processed_rows=0,
                valid_rows=0,
                error_rows=0,
                quarantined_rows=0,
                file_progress=0.0,
                row_progress=0.0,
                start_time=datetime.utcnow(),
                errors=[],
                warnings=[],
                task_details={}
            )
            
            self.db.add(task)
            await self.db.commit()
            
            logger.info(f"[SyncProgress] Created task {task_id}: {total_files} files")
            return self._task_to_dict(task)
            
        except Exception as e:
            logger.error(f"[SyncProgress] Failed to create task {task_id}: {e}", exc_info=True)
            await self.db.rollback()
            raise
    
    async def update_task(
        self,
        task_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        更新任务进度
        
        Args:
            task_id: 任务ID
            updates: 更新字段字典
            
        Returns:
            更新后的任务信息字典
        """
        try:
            result = await self.db.execute(
                select(SyncProgressTask).where(SyncProgressTask.task_id == task_id)
            )
            task = result.scalar_one_or_none()
            
            if not task:
                raise ValueError(f"Task {task_id} not found")
            
            # [*] v4.17.1修复：合并task_details而不是覆盖
            if "task_details" in updates:
                current_details = task.task_details or {}
                new_details = updates["task_details"]
                # 合并字典（新值覆盖旧值）
                if isinstance(current_details, dict) and isinstance(new_details, dict):
                    merged_details = {**current_details, **new_details}
                    updates["task_details"] = merged_details
                # 如果不是字典，直接使用新值
            
            # 更新字段
            for key, value in updates.items():
                if hasattr(task, key):
                    setattr(task, key, value)
            
            # 自动计算进度百分比
            if task.total_files > 0:
                task.file_progress = round(
                    task.processed_files / task.total_files * 100, 2
                )
            
            if task.total_rows > 0:
                task.row_progress = round(
                    task.processed_rows / task.total_rows * 100, 2
                )
            
            # 更新时间戳
            task.updated_at = datetime.utcnow()
            
            await self.db.commit()
            
            return self._task_to_dict(task)
            
        except Exception as e:
            logger.error(f"[SyncProgress] Failed to update task {task_id}: {e}", exc_info=True)
            await self.db.rollback()
            raise
    
    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务进度
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务信息字典，如果不存在则返回None
        """
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # [*] 修复：每次查询前先回滚，确保使用干净的事务
                try:
                    await self.db.rollback()
                except:
                    pass  # 如果回滚失败（可能没有活动事务），忽略
                
                # 尝试查询
                result = await self.db.execute(
                    select(SyncProgressTask).where(SyncProgressTask.task_id == task_id)
                )
                task = result.scalar_one_or_none()
                
                if not task:
                    return None
                
                return self._task_to_dict(task)
                
            except Exception as query_error:
                error_str = str(query_error)
                # 检查是否是事务错误
                is_transaction_error = (
                    'InFailedSqlTransaction' in error_str or 
                    'current transaction is aborted' in error_str.lower() or
                    'transaction' in error_str.lower()
                )
                
                if is_transaction_error and retry_count < max_retries - 1:
                    retry_count += 1
                    logger.warning(f"[SyncProgress] Transaction error detected (retry {retry_count}/{max_retries}), rolling back: {query_error}")
                    try:
                        await self.db.rollback()
                    except:
                        pass
                    # [*] v4.18.2修复：使用 asyncio.sleep 替代 time.sleep
                    await asyncio.sleep(0.1 * retry_count)
                    continue
                else:
                    # 其他错误或重试次数用完，记录并返回None
                    logger.error(f"[SyncProgress] Failed to get task {task_id} (retry {retry_count}/{max_retries}): {query_error}", exc_info=True)
                    try:
                        await self.db.rollback()
                    except:
                        pass
                    return None
        
        return None
    
    async def complete_task(
        self,
        task_id: str,
        success: bool = True,
        error: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        完成任务
        
        Args:
            task_id: 任务ID
            success: 是否成功
            error: 错误信息（可选）
            
        Returns:
            任务信息字典
        """
        try:
            result = await self.db.execute(
                select(SyncProgressTask).where(SyncProgressTask.task_id == task_id)
            )
            task = result.scalar_one_or_none()
            
            if not task:
                raise ValueError(f"Task {task_id} not found")
            
            task.status = "completed" if success else "failed"
            task.end_time = datetime.utcnow()
            task.updated_at = datetime.utcnow()
            
            if error:
                errors = task.errors or []
                errors.append({
                    "time": datetime.utcnow().isoformat(),
                    "message": error
                })
                task.errors = errors
            
            await self.db.commit()
            
            logger.info(f"[SyncProgress] Completed task {task_id}: {'success' if success else 'failed'}")
            return self._task_to_dict(task)
            
        except Exception as e:
            logger.error(f"[SyncProgress] Failed to complete task {task_id}: {e}", exc_info=True)
            await self.db.rollback()
            raise
    
    async def add_error(self, task_id: str, error: str) -> None:
        """
        添加错误信息
        
        Args:
            task_id: 任务ID
            error: 错误信息
        """
        try:
            result = await self.db.execute(
                select(SyncProgressTask).where(SyncProgressTask.task_id == task_id)
            )
            task = result.scalar_one_or_none()
            
            if task:
                errors = task.errors or []
                errors.append({
                    "time": datetime.utcnow().isoformat(),
                    "message": error
                })
                task.errors = errors
                task.updated_at = datetime.utcnow()
                await self.db.commit()
                
        except Exception as e:
            logger.error(f"[SyncProgress] Failed to add error to task {task_id}: {e}", exc_info=True)
            await self.db.rollback()
    
    async def add_warning(self, task_id: str, warning: str) -> None:
        """
        添加警告信息
        
        Args:
            task_id: 任务ID
            warning: 警告信息
        """
        try:
            result = await self.db.execute(
                select(SyncProgressTask).where(SyncProgressTask.task_id == task_id)
            )
            task = result.scalar_one_or_none()
            
            if task:
                warnings = task.warnings or []
                warnings.append({
                    "time": datetime.utcnow().isoformat(),
                    "message": warning
                })
                task.warnings = warnings
                task.updated_at = datetime.utcnow()
                await self.db.commit()
                
        except Exception as e:
            logger.error(f"[SyncProgress] Failed to add warning to task {task_id}: {e}", exc_info=True)
            await self.db.rollback()
    
    async def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        列出所有任务
        
        Args:
            status: 状态筛选（可选）
            limit: 返回数量限制
            
        Returns:
            任务列表
        """
        try:
            stmt = select(SyncProgressTask)
            if status:
                stmt = stmt.where(SyncProgressTask.status == status)
            stmt = stmt.order_by(SyncProgressTask.start_time.desc()).limit(limit)
            result = await self.db.execute(stmt)
            tasks = result.scalars().all()
            
            return [self._task_to_dict(task) for task in tasks]
            
        except Exception as e:
            logger.error(f"[SyncProgress] Failed to list tasks: {e}", exc_info=True)
            return []
    
    async def delete_task(self, task_id: str) -> bool:
        """
        删除任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否删除成功
        """
        try:
            result = await self.db.execute(
                select(SyncProgressTask).where(SyncProgressTask.task_id == task_id)
            )
            task = result.scalar_one_or_none()
            
            if task:
                await self.db.delete(task)
                await self.db.commit()
                logger.info(f"[SyncProgress] Deleted task {task_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"[SyncProgress] Failed to delete task {task_id}: {e}", exc_info=True)
            await self.db.rollback()
            return False
    
    def _task_to_dict(self, task: SyncProgressTask) -> Dict[str, Any]:
        """
        将任务对象转换为字典
        
        Args:
            task: 任务对象
            
        Returns:
            任务信息字典
        """
        task_details = task.task_details or {}
        return {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "total_files": task.total_files,
            "processed_files": task.processed_files,
            "current_file": task.current_file,
            "status": task.status,
            "total_rows": task.total_rows,
            "processed_rows": task.processed_rows,
            "valid_rows": task.valid_rows,
            "error_rows": task.error_rows,
            "quarantined_rows": task.quarantined_rows,
            "file_progress": task.file_progress,
            "row_progress": task.row_progress,
            # [*] 修复：使用format_datetime确保返回带Z标识符的UTC时间
            "start_time": format_datetime(task.start_time),
            "end_time": format_datetime(task.end_time),
            "updated_at": format_datetime(task.updated_at),
            "errors": task.errors or [],
            # [*] v4.15.0修复：从errors中提取最后一条错误消息作为message
            "message": self._extract_message_from_errors(task.errors) if task.errors else None,
            "warnings": task.warnings or [],
            "task_details": task_details,
            # [*] 新增：从task_details中提取文件统计信息（用于前端显示）
            "success_files": task_details.get("success_files", 0),
            "failed_files": task_details.get("failed_files", 0),
            "skipped_files": task_details.get("skipped_files", 0),
        }
    
    def _extract_message_from_errors(self, errors: List[Dict[str, Any]]) -> Optional[str]:
        """
        从错误列表中提取最后一条错误消息
        
        Args:
            errors: 错误列表
            
        Returns:
            最后一条错误消息，如果没有则返回None
        """
        if not errors or len(errors) == 0:
            return None
        
        # 获取最后一条错误消息
        last_error = errors[-1]
        if isinstance(last_error, dict):
            return last_error.get("message")
        elif isinstance(last_error, str):
            return last_error
        else:
            return str(last_error)

