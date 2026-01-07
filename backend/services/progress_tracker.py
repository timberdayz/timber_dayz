"""
批量入库进度跟踪服务
"""

from typing import Dict, Any
from datetime import datetime
import asyncio
import json


class ProgressTracker:
    """进度跟踪器（内存存储，支持并发）"""
    
    def __init__(self):
        self._progress_store: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
    
    async def create_task(self, task_id: str, total_files: int, task_type: str = "bulk_ingest") -> Dict[str, Any]:
        """创建进度跟踪任务"""
        async with self._lock:
            task_info = {
                "task_id": task_id,
                "task_type": task_type,
                "total_files": total_files,
                "processed_files": 0,
                "current_file": "",
                "status": "pending",  # pending, processing, completed, failed
                "total_rows": 0,
                "processed_rows": 0,
                "valid_rows": 0,
                "error_rows": 0,
                "quarantined_rows": 0,
                "start_time": datetime.now().isoformat(),
                "end_time": None,
                "errors": [],
                "warnings": []
            }
            self._progress_store[task_id] = task_info
            return task_info
    
    async def update_task(self, task_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """更新任务进度"""
        async with self._lock:
            if task_id not in self._progress_store:
                raise ValueError(f"Task {task_id} not found")
            
            task_info = self._progress_store[task_id]
            task_info.update(updates)
            
            # 自动计算进度百分比
            if task_info["total_files"] > 0:
                task_info["file_progress"] = round(
                    task_info["processed_files"] / task_info["total_files"] * 100, 2
                )
            
            if task_info["total_rows"] > 0:
                task_info["row_progress"] = round(
                    task_info["processed_rows"] / task_info["total_rows"] * 100, 2
                )
            
            return task_info
    
    async def get_task(self, task_id: str) -> Dict[str, Any]:
        """获取任务进度"""
        async with self._lock:
            if task_id not in self._progress_store:
                return None
            return self._progress_store[task_id].copy()
    
    async def complete_task(self, task_id: str, success: bool = True, error: str = None) -> Dict[str, Any]:
        """完成任务"""
        async with self._lock:
            if task_id not in self._progress_store:
                raise ValueError(f"Task {task_id} not found")
            
            task_info = self._progress_store[task_id]
            task_info["status"] = "completed" if success else "failed"
            task_info["end_time"] = datetime.now().isoformat()
            
            if error:
                task_info["errors"].append({
                    "time": datetime.now().isoformat(),
                    "message": error
                })
            
            return task_info
    
    async def add_error(self, task_id: str, error: str) -> None:
        """添加错误信息"""
        async with self._lock:
            if task_id in self._progress_store:
                self._progress_store[task_id]["errors"].append({
                    "time": datetime.now().isoformat(),
                    "message": error
                })
    
    async def add_warning(self, task_id: str, warning: str) -> None:
        """添加警告信息"""
        async with self._lock:
            if task_id in self._progress_store:
                self._progress_store[task_id]["warnings"].append({
                    "time": datetime.now().isoformat(),
                    "message": warning
                })
    
    async def delete_task(self, task_id: str) -> bool:
        """删除任务（清理内存）"""
        async with self._lock:
            if task_id in self._progress_store:
                del self._progress_store[task_id]
                return True
            return False
    
    async def list_tasks(self, status: str = None) -> list:
        """列出所有任务"""
        async with self._lock:
            tasks = list(self._progress_store.values())
            if status:
                tasks = [t for t in tasks if t["status"] == status]
            return tasks


# 全局进度跟踪器实例
progress_tracker = ProgressTracker()

