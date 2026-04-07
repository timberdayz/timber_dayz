"""
数据采集 WebSocket 路由

提供任务状态实时推送功能,支持JWT认证
"""

import os
import jwt
from datetime import datetime, timezone
from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel

from backend.schemas.websocket import (
    CollectionWebSocketMessage as WebSocketMessage,
)
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


# SSOT: ConnectionManager 已迁移至 backend.services.websocket_manager，此处 re-export 保持向后兼容
from backend.services.websocket_manager import ConnectionManager, connection_manager  # noqa: F401


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
    
    连接时需要通过query参数传递JWT token进行认证:
    ws://host/ws/collection/{task_id}?token=xxx
    
    消息格式:
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
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        # 保持连接,等待客户端断开
        while True:
            try:
                # 接收客户端消息(心跳等)
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

