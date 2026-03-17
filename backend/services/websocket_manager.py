"""
WebSocket 连接管理器 (Connection Manager)

从 backend/routers/collection_websocket.py 提取的共享组件，
供 router 和 service 层使用，避免 service -> router 的反向依赖。

用法:
    from backend.services.websocket_manager import connection_manager
"""

from datetime import datetime, timezone
from typing import Dict, Set

from fastapi import WebSocket

from modules.core.logger import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """WebSocket 连接管理器，管理所有活跃的 WebSocket 连接。"""

    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, task_id: str) -> bool:
        """建立连接并将其加入任务订阅组。"""
        await websocket.accept()

        if task_id not in self.active_connections:
            self.active_connections[task_id] = set()

        self.active_connections[task_id].add(websocket)
        logger.debug(f"WebSocket connected: task_id={task_id}")
        return True

    def disconnect(self, websocket: WebSocket, task_id: str):
        """断开连接并从任务订阅组移除。"""
        if task_id in self.active_connections:
            self.active_connections[task_id].discard(websocket)

            if not self.active_connections[task_id]:
                del self.active_connections[task_id]

        logger.debug(f"WebSocket disconnected: task_id={task_id}")

    async def broadcast_to_task(self, task_id: str, message: dict):
        """向任务的所有订阅者广播消息。"""
        if task_id not in self.active_connections:
            return

        disconnected = set()

        for websocket in self.active_connections[task_id]:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send message to WebSocket: {e}")
                disconnected.add(websocket)

        for ws in disconnected:
            self.disconnect(ws, task_id)

    async def send_progress(
        self,
        task_id: str,
        progress: int,
        current_step: str,
        status: str = "running",
    ):
        """发送进度更新。"""
        conn_count = len(self.active_connections.get(task_id, set()))
        logger.info(
            f"[WS] send_progress: task_id={task_id}, progress={progress}, connections={conn_count}"
        )

        if conn_count == 0:
            logger.warning(f"[WS] No active connections for task {task_id}")

        await self.broadcast_to_task(task_id, {
            "type": "progress",
            "task_id": task_id,
            "progress": progress,
            "current_step": current_step,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def send_log(self, task_id: str, level: str, message: str):
        """发送日志消息。"""
        await self.broadcast_to_task(task_id, {
            "type": "log",
            "task_id": task_id,
            "level": level,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def send_complete(
        self,
        task_id: str,
        status: str,
        files_collected: int = 0,
        error_message: str = None,
    ):
        """发送完成通知。"""
        await self.broadcast_to_task(task_id, {
            "type": "complete",
            "task_id": task_id,
            "status": status,
            "files_collected": files_collected,
            "error_message": error_message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def send_verification_required(
        self,
        task_id: str,
        verification_type: str,
        screenshot_path: str = None,
    ):
        """发送验证码请求。"""
        await self.broadcast_to_task(task_id, {
            "type": "verification_required",
            "task_id": task_id,
            "verification_type": verification_type,
            "screenshot_path": screenshot_path,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def get_connection_count(self, task_id: str = None) -> int:
        """获取连接数量（可按任务过滤）。"""
        if task_id:
            return len(self.active_connections.get(task_id, set()))
        return sum(len(conns) for conns in self.active_connections.values())

    def get_active_task_ids(self) -> list:
        """获取有活跃连接的任务 ID 列表。"""
        return list(self.active_connections.keys())


# 全局单例
connection_manager = ConnectionManager()
