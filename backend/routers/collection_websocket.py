"""
数据采集 WebSocket 路由

提供任务状态实时推送功能，支持JWT认证
"""

import os
import jwt
from datetime import datetime
from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel

from modules.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["采集WebSocket"])


# JWT配置
JWT_SECRET = os.getenv('JWT_SECRET', 'xihong-erp-secret-key-change-in-production')
JWT_ALGORITHM = os.getenv('JWT_ALGORITHM', 'HS256')

# WebSocket错误码
WS_ERROR_INVALID_TOKEN = 4001
WS_ERROR_TOKEN_EXPIRED = 4002
WS_ERROR_INVALID_TASK = 4003


class WebSocketMessage(BaseModel):
    """WebSocket消息格式"""
    type: str  # progress/log/error/complete
    task_id: str
    data: Dict


class ConnectionManager:
    """
    WebSocket连接管理器
    
    管理所有活跃的WebSocket连接
    """
    
    def __init__(self):
        # task_id -> Set[WebSocket]
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, task_id: str) -> bool:
        """
        建立连接
        
        Args:
            websocket: WebSocket连接
            task_id: 任务ID
            
        Returns:
            bool: 是否成功
        """
        await websocket.accept()
        
        if task_id not in self.active_connections:
            self.active_connections[task_id] = set()
        
        self.active_connections[task_id].add(websocket)
        logger.debug(f"WebSocket connected: task_id={task_id}")
        return True
    
    def disconnect(self, websocket: WebSocket, task_id: str):
        """
        断开连接
        
        Args:
            websocket: WebSocket连接
            task_id: 任务ID
        """
        if task_id in self.active_connections:
            self.active_connections[task_id].discard(websocket)
            
            # 如果没有连接了，删除任务条目
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]
        
        logger.debug(f"WebSocket disconnected: task_id={task_id}")
    
    async def broadcast_to_task(self, task_id: str, message: dict):
        """
        向任务的所有订阅者广播消息
        
        Args:
            task_id: 任务ID
            message: 消息内容
        """
        if task_id not in self.active_connections:
            return
        
        disconnected = set()
        
        for websocket in self.active_connections[task_id]:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send message to WebSocket: {e}")
                disconnected.add(websocket)
        
        # 移除断开的连接
        for ws in disconnected:
            self.disconnect(ws, task_id)
    
    async def send_progress(
        self, 
        task_id: str, 
        progress: int, 
        current_step: str, 
        status: str = "running"
    ):
        """
        发送进度更新
        
        Args:
            task_id: 任务ID
            progress: 进度百分比
            current_step: 当前步骤
            status: 任务状态
        """
        # [*] v4.7.4: 检查是否有活跃连接
        conn_count = len(self.active_connections.get(task_id, set()))
        logger.info(f"[WS] send_progress: task_id={task_id}, progress={progress}, connections={conn_count}")
        
        if conn_count == 0:
            logger.warning(f"[WS] No active connections for task {task_id}")
        
        await self.broadcast_to_task(task_id, {
            "type": "progress",
            "task_id": task_id,
            "progress": progress,
            "current_step": current_step,
            "status": status,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    async def send_log(
        self, 
        task_id: str, 
        level: str, 
        message: str
    ):
        """
        发送日志消息
        
        Args:
            task_id: 任务ID
            level: 日志级别
            message: 日志消息
        """
        await self.broadcast_to_task(task_id, {
            "type": "log",
            "task_id": task_id,
            "level": level,
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    async def send_complete(
        self, 
        task_id: str, 
        status: str, 
        files_collected: int = 0,
        error_message: str = None
    ):
        """
        发送完成通知
        
        Args:
            task_id: 任务ID
            status: 最终状态
            files_collected: 采集文件数
            error_message: 错误信息
        """
        await self.broadcast_to_task(task_id, {
            "type": "complete",
            "task_id": task_id,
            "status": status,
            "files_collected": files_collected,
            "error_message": error_message,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    async def send_verification_required(
        self,
        task_id: str,
        verification_type: str,
        screenshot_path: str = None
    ):
        """
        发送验证码请求
        
        Args:
            task_id: 任务ID
            verification_type: 验证码类型
            screenshot_path: 截图路径
        """
        await self.broadcast_to_task(task_id, {
            "type": "verification_required",
            "task_id": task_id,
            "verification_type": verification_type,
            "screenshot_path": screenshot_path,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    def get_connection_count(self, task_id: str = None) -> int:
        """
        获取连接数量
        
        Args:
            task_id: 任务ID（可选，不传则返回总数）
            
        Returns:
            int: 连接数量
        """
        if task_id:
            return len(self.active_connections.get(task_id, set()))
        
        return sum(len(conns) for conns in self.active_connections.values())
    
    def get_active_task_ids(self) -> list:
        """
        获取有活跃连接的任务ID列表
        
        Returns:
            list: 任务ID列表
        """
        return list(self.active_connections.keys())


# 全局连接管理器
connection_manager = ConnectionManager()


def validate_jwt_token(token: str) -> Dict:
    """
    验证JWT Token
    
    Args:
        token: JWT Token字符串
        
    Returns:
        Dict: Token payload
        
    Raises:
        Exception: Token无效或过期
    """
    if not token:
        raise ValueError("Token is required")
    
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid token: {e}")


@router.websocket("/ws/collection/{task_id}")
async def websocket_task_status(
    websocket: WebSocket,
    task_id: str,
    token: str = Query(None, description="JWT认证Token")
):
    """
    任务状态WebSocket端点
    
    连接时需要通过query参数传递JWT token进行认证：
    ws://host/ws/collection/{task_id}?token=xxx
    
    消息格式：
    - 进度更新: {"type": "progress", "task_id": "...", "progress": 50, ...}
    - 日志消息: {"type": "log", "task_id": "...", "level": "info", ...}
    - 完成通知: {"type": "complete", "task_id": "...", "status": "completed", ...}
    - 验证码请求: {"type": "verification_required", "task_id": "...", ...}
    """
    # 验证JWT Token
    try:
        if os.getenv('WEBSOCKET_AUTH_ENABLED', 'true').lower() == 'true':
            if not token:
                await websocket.close(code=WS_ERROR_INVALID_TOKEN, reason="Token required")
                return
            
            validate_jwt_token(token)
    
    except ValueError as e:
        logger.warning(f"WebSocket auth failed: {e}")
        
        if "expired" in str(e).lower():
            await websocket.close(code=WS_ERROR_TOKEN_EXPIRED, reason="Token expired")
        else:
            await websocket.close(code=WS_ERROR_INVALID_TOKEN, reason="Invalid token")
        return
    
    # 建立连接
    await connection_manager.connect(websocket, task_id)
    
    try:
        # 发送连接确认
        await websocket.send_json({
            "type": "connected",
            "task_id": task_id,
            "message": "Successfully connected to task status stream",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # 保持连接，等待客户端断开
        while True:
            try:
                # 接收客户端消息（心跳等）
                data = await websocket.receive_text()
                
                # 处理心跳
                if data == "ping":
                    await websocket.send_text("pong")
            
            except WebSocketDisconnect:
                break
    
    finally:
        connection_manager.disconnect(websocket, task_id)


@router.get("/ws/collection/stats")
async def websocket_stats():
    """
    获取WebSocket连接统计
    
    用于监控和调试
    """
    return {
        "total_connections": connection_manager.get_connection_count(),
        "active_tasks": connection_manager.get_active_task_ids(),
        "task_connections": {
            task_id: connection_manager.get_connection_count(task_id)
            for task_id in connection_manager.get_active_task_ids()
        }
    }

