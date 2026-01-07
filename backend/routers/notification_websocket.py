"""
通知 WebSocket 路由 (v4.19.0)

提供实时通知推送功能，支持JWT认证、连接管理、心跳机制等
"""

import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Set, Optional, List, Tuple
from collections import defaultdict, OrderedDict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.auth_service import auth_service
from backend.models.database import get_async_db
from backend.routers.auth import get_current_user
from backend.routers.users import require_admin
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/notifications", tags=["通知WebSocket"])

# WebSocket Close Codes（注意：与 HTTP 错误码不同）
WS_CLOSE_TOKEN_EXPIRED = 4005  # Token 过期
WS_CLOSE_CONNECTION_LIMIT = 4006  # 连接数超限
WS_CLOSE_RATE_LIMIT = 4007  # 速率限制
WS_CLOSE_INVALID_ORIGIN = 4008  # Origin 验证失败

# WebSocket 错误码（用于消息格式）
WS_ERROR_INVALID_TOKEN = 4001
WS_ERROR_TOKEN_EXPIRED = 4002
WS_ERROR_INVALID_MESSAGE = 4003
WS_ERROR_RATE_LIMIT = 4004

# 配置常量
HEARTBEAT_INTERVAL = 30  # 心跳间隔（秒）
HEARTBEAT_TIMEOUT = 120  # 心跳超时（秒）
CONNECTION_TIMEOUT = 3600  # 连接超时（1小时）
MAX_CONNECTIONS_PER_USER = 3  # 每个用户最多连接数
MAX_TOTAL_CONNECTIONS = 1000  # 系统最多总连接数
RATE_LIMIT_CONNECTIONS_PER_MINUTE = 10  # 每个IP每分钟最多连接数


class WebSocketMessage(BaseModel):
    """WebSocket 消息格式"""
    type: str = Field(..., description="消息类型")
    data: Optional[Dict] = Field(None, description="消息数据")
    
    @validator('type')
    def validate_type(cls, v):
        allowed_types = ['ping', 'pong', 'notification']
        if v not in allowed_types:
            raise ValueError(f"Invalid message type: {v}. Allowed: {allowed_types}")
        return v


class NotificationMessage(BaseModel):
    """通知消息格式"""
    notification_id: int
    recipient_id: int
    notification_type: str
    title: str = Field(..., max_length=200)
    content: str = Field(..., max_length=1000)
    extra_data: Optional[Dict] = None
    related_user_id: Optional[int] = None
    created_at: str


class ConnectionInfo:
    """连接信息"""
    def __init__(self, websocket: WebSocket, user_id: int, ip_address: str, connected_at: datetime):
        self.websocket = websocket
        self.user_id = user_id
        self.ip_address = ip_address
        self.connected_at = connected_at
        self.last_heartbeat = datetime.utcnow()
        self.expires_at = connected_at + timedelta(seconds=CONNECTION_TIMEOUT)


class NotificationConnectionManager:
    """
    通知 WebSocket 连接管理器
    
    管理所有活跃的 WebSocket 连接（基于 user_id）
    """
    
    def __init__(self):
        # user_id -> Set[ConnectionInfo]
        self.active_connections: Dict[int, Set[ConnectionInfo]] = defaultdict(set)
        # IP -> List[datetime] (用于速率限制)
        self.connection_attempts: Dict[str, List[datetime]] = defaultdict(list)
        # LRU 缓存（用于内存存储速率限制记录）
        self._lru_cache: OrderedDict = OrderedDict()
        self._max_cache_size = 10000
    
    def _cleanup_expired_attempts(self):
        """清理过期的连接频率记录（1小时）"""
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=1)
        
        for ip in list(self.connection_attempts.keys()):
            self.connection_attempts[ip] = [
                dt for dt in self.connection_attempts[ip] if dt > cutoff
            ]
            if not self.connection_attempts[ip]:
                del self.connection_attempts[ip]
    
    def _check_rate_limit(self, ip_address: str) -> bool:
        """
        检查连接速率限制
        
        Args:
            ip_address: 客户端IP地址
            
        Returns:
            bool: 是否超过限制
        """
        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=1)
        
        # 清理过期记录
        self.connection_attempts[ip_address] = [
            dt for dt in self.connection_attempts[ip_address] if dt > cutoff
        ]
        
        # 检查是否超过限制
        if len(self.connection_attempts[ip_address]) >= RATE_LIMIT_CONNECTIONS_PER_MINUTE:
            return False
        
        # 记录本次连接尝试
        self.connection_attempts[ip_address].append(now)
        return True
    
    def _check_connection_limits(self, user_id: int) -> Tuple[bool, Optional[str]]:
        """
        检查连接数限制
        
        Args:
            user_id: 用户ID
            
        Returns:
            tuple: (是否允许, 错误消息)
        """
        # 检查用户连接数
        user_connections = len(self.active_connections.get(user_id, set()))
        if user_connections >= MAX_CONNECTIONS_PER_USER:
            return False, f"User connection limit exceeded (max {MAX_CONNECTIONS_PER_USER})"
        
        # 检查系统总连接数
        total_connections = sum(len(conns) for conns in self.active_connections.values())
        if total_connections >= MAX_TOTAL_CONNECTIONS:
            return False, f"System connection limit exceeded (max {MAX_TOTAL_CONNECTIONS})"
        
        return True, None
    
    async def connect(self, websocket: WebSocket, user_id: int, ip_address: str) -> Tuple[bool, Optional[str]]:
        """
        建立连接
        
        Args:
            websocket: WebSocket 连接
            user_id: 用户ID
            ip_address: 客户端IP地址
            
        Returns:
            tuple: (是否成功, 错误消息)
        """
        # 检查连接数限制
        allowed, error_msg = self._check_connection_limits(user_id)
        if not allowed:
            return False, error_msg
        
        # 检查速率限制
        if not self._check_rate_limit(ip_address):
            return False, "Rate limit exceeded"
        
        # 接受连接
        await websocket.accept()
        
        # 创建连接信息
        conn_info = ConnectionInfo(
            websocket=websocket,
            user_id=user_id,
            ip_address=ip_address,
            connected_at=datetime.utcnow()
        )
        
        # 添加到活跃连接
        self.active_connections[user_id].add(conn_info)
        
        logger.info(f"[WS] Notification connection established: user_id={user_id}, ip={ip_address}")
        return True, None
    
    def disconnect(self, websocket: WebSocket, user_id: int):
        """
        断开连接
        
        Args:
            websocket: WebSocket 连接
            user_id: 用户ID
        """
        if user_id in self.active_connections:
            # 找到并移除对应的连接
            conns_to_remove = [
                conn for conn in self.active_connections[user_id]
                if conn.websocket == websocket
            ]
            for conn in conns_to_remove:
                self.active_connections[user_id].discard(conn)
            
            # 如果没有连接了，删除用户条目
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        
        logger.debug(f"[WS] Notification connection disconnected: user_id={user_id}")
    
    async def send_notification(self, user_id: int, notification: NotificationMessage) -> bool:
        """
        向用户发送通知
        
        Args:
            user_id: 用户ID
            notification: 通知消息
            
        Returns:
            bool: 是否成功发送
        """
        # v4.19.0 P0安全要求：验证 recipient_id 与连接用户 ID 匹配
        if notification.recipient_id != user_id:
            logger.error(f"[WS] Security violation: notification recipient_id={notification.recipient_id} != user_id={user_id}")
            return False
        
        if user_id not in self.active_connections:
            return False
        
        disconnected = set()
        success_count = 0
        
        for conn_info in self.active_connections[user_id]:
            try:
                message = {
                    "type": "notification",
                    "data": notification.dict()
                }
                await conn_info.websocket.send_json(message)
                success_count += 1
            except Exception as e:
                logger.warning(f"[WS] Failed to send notification to user {user_id}: {e}")
                disconnected.add(conn_info)
        
        # 移除断开的连接
        for conn_info in disconnected:
            self.disconnect(conn_info.websocket, user_id)
        
        if success_count > 0:
            logger.info(f"[WS] Sent notification to {success_count} connections for user {user_id}")
        
        return success_count > 0
    
    async def broadcast_to_admins(self, notification: NotificationMessage, admin_ids: List[int]) -> Dict[str, int]:
        """
        向多个管理员批量推送通知
        
        Args:
            notification: 通知消息
            admin_ids: 管理员ID列表
            
        Returns:
            Dict: {"success": 成功数量, "failed": 失败数量}
        """
        success_count = 0
        failed_count = 0
        
        # v4.19.0 P1性能要求：批量数量限制策略
        if len(admin_ids) <= 50:
            # 直接批量推送
            tasks = [
                self.send_notification(admin_id, notification)
                for admin_id in admin_ids
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success_count = sum(1 for r in results if r is True)
            failed_count = len(admin_ids) - success_count
        else:
            # 分批推送（每批50个）
            batch_size = 50
            for i in range(0, len(admin_ids), batch_size):
                batch = admin_ids[i:i + batch_size]
                tasks = [
                    asyncio.create_task(self.send_notification(admin_id, notification))
                    for admin_id in batch
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                batch_success = sum(1 for r in results if r is True)
                success_count += batch_success
                failed_count += len(batch) - batch_success
        
        logger.info(f"[WS] Broadcast notification to admins: success={success_count}, failed={failed_count}")
        return {"success": success_count, "failed": failed_count}
    
    def update_heartbeat(self, websocket: WebSocket, user_id: int):
        """更新心跳时间"""
        if user_id in self.active_connections:
            for conn_info in self.active_connections[user_id]:
                if conn_info.websocket == websocket:
                    conn_info.last_heartbeat = datetime.utcnow()
                    break
    
    async def cleanup_dead_connections(self):
        """清理死连接和超时连接"""
        now = datetime.utcnow()
        dead_connections = []
        
        for user_id, conns in list(self.active_connections.items()):
            for conn_info in list(conns):
                # 检查心跳超时
                if (now - conn_info.last_heartbeat).total_seconds() > HEARTBEAT_TIMEOUT:
                    dead_connections.append((conn_info, user_id))
                    continue
                
                # 检查连接超时
                if now > conn_info.expires_at:
                    dead_connections.append((conn_info, user_id))
                    continue
        
        # 断开死连接
        for conn_info, user_id in dead_connections:
            try:
                await conn_info.websocket.close(code=1000, reason="Connection timeout")
            except:
                pass
            self.disconnect(conn_info.websocket, user_id)
        
        if dead_connections:
            logger.info(f"[WS] Cleaned up {len(dead_connections)} dead connections")
    
    def get_connection_count(self, user_id: Optional[int] = None) -> int:
        """获取连接数量"""
        if user_id:
            return len(self.active_connections.get(user_id, set()))
        return sum(len(conns) for conns in self.active_connections.values())
    
    def get_stats(self) -> Dict:
        """获取连接统计信息"""
        return {
            "total_connections": self.get_connection_count(),
            "active_users": len(self.active_connections),
            "connections_per_user": {
                user_id: len(conns)
                for user_id, conns in self.active_connections.items()
            },
            "timestamp": datetime.utcnow().isoformat()
        }


# 全局连接管理器
connection_manager = NotificationConnectionManager()


def validate_origin(origin: Optional[str]) -> bool:
    """
    验证 WebSocket Origin
    
    Args:
        origin: Origin 头值
        
    Returns:
        bool: 是否允许
    """
    if not origin:
        return False
    
    # 从环境变量读取允许的 Origin 列表
    allowed_origins = os.getenv("ALLOWED_ORIGINS", "").split(",")
    allowed_origins = [o.strip() for o in allowed_origins if o.strip()]
    
    # 如果没有配置，允许所有（仅开发环境）
    if not allowed_origins:
        is_production = os.getenv("ENVIRONMENT", "development") == "production"
        if is_production:
            logger.warning("[WS] No ALLOWED_ORIGINS configured in production!")
            return False
        return True
    
    return origin in allowed_origins


def require_wss(websocket: WebSocket) -> bool:
    """
    检查是否要求 WSS（生产环境）
    
    Args:
        websocket: WebSocket 连接
        
    Returns:
        bool: 是否允许连接
    """
    is_production = os.getenv("ENVIRONMENT", "development") == "production"
    if not is_production:
        return True
    
    # 检查是否是 WSS
    is_secure = websocket.url.scheme == "wss"
    if not is_secure:
        logger.warning(f"[WS] Non-WSS connection rejected in production: {websocket.url}")
        return False
    
    return True


async def verify_websocket_token(websocket: WebSocket, token: Optional[str]) -> Tuple[Optional[int], Optional[str]]:
    """
    验证 WebSocket JWT Token
    
    Args:
        websocket: WebSocket 连接
        token: JWT Token
        
    Returns:
        tuple: (user_id, error_message)
    """
    if not token:
        return None, "Token required"
    
    try:
        payload = auth_service.verify_token(token)
        user_id = payload.get("user_id")
        
        if not user_id:
            return None, "Invalid token: missing user_id"
        
        return user_id, None
    
    except Exception as e:
        error_msg = str(e)
        if "expired" in error_msg.lower():
            return None, "Token expired"
        return None, f"Invalid token: {error_msg}"


@router.websocket("/ws")
async def websocket_notifications(
    websocket: WebSocket,
    token: str = Query(..., description="JWT认证Token")
):
    """
    通知 WebSocket 端点
    
    连接时需要通过query参数传递JWT token进行认证：
    ws://host/api/notifications/ws?token=xxx
    
    消息格式：
    - 心跳: "ping" (文本)
    - 心跳响应: "pong" (文本)
    - 通知推送: {"type": "notification", "data": {...}} (JSON)
    """
    # v4.19.0 P0安全要求：Origin 验证
    origin = websocket.headers.get("origin")
    if not validate_origin(origin):
        logger.warning(f"[WS] Invalid origin rejected: {origin}")
        await websocket.close(code=WS_CLOSE_INVALID_ORIGIN, reason="Invalid origin")
        return
    
    # v4.19.0 P0安全要求：WSS 强制要求（生产环境）
    if not require_wss(websocket):
        await websocket.close(code=1008, reason="WSS required in production")
        return
    
    # v4.19.0 P0安全要求：JWT 认证
    user_id, error_msg = await verify_websocket_token(websocket, token)
    if not user_id:
        close_code = WS_CLOSE_TOKEN_EXPIRED if "expired" in error_msg.lower() else WS_ERROR_INVALID_TOKEN
        await websocket.close(code=close_code, reason=error_msg)
        return
    
    # 获取客户端IP
    ip_address = websocket.client.host if websocket.client else "unknown"
    
    # 建立连接
    success, error_msg = await connection_manager.connect(websocket, user_id, ip_address)
    if not success:
        close_code = WS_CLOSE_RATE_LIMIT if "Rate limit" in error_msg else WS_CLOSE_CONNECTION_LIMIT
        await websocket.close(code=close_code, reason=error_msg)
        return
    
    try:
        # 发送连接确认
        await websocket.send_json({
            "type": "connected",
            "user_id": user_id,
            "message": "Successfully connected to notification stream",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # v4.19.0 P0安全要求：心跳机制
        last_heartbeat = datetime.utcnow()
        
        # 保持连接，等待客户端断开
        while True:
            try:
                # 接收客户端消息（心跳等）
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=HEARTBEAT_INTERVAL
                )
                
                # 处理心跳
                if data == "ping":
                    await websocket.send_text("pong")
                    connection_manager.update_heartbeat(websocket, user_id)
                    last_heartbeat = datetime.utcnow()
                else:
                    # 尝试解析为JSON消息
                    try:
                        import json
                        message_data = json.loads(data)
                        message = WebSocketMessage(**message_data)
                        
                        if message.type == "ping":
                            await websocket.send_json({"type": "pong"})
                            connection_manager.update_heartbeat(websocket, user_id)
                            last_heartbeat = datetime.utcnow()
                    except:
                        logger.warning(f"[WS] Invalid message format from user {user_id}: {data}")
            
            except asyncio.TimeoutError:
                # 检查心跳超时
                if (datetime.utcnow() - last_heartbeat).total_seconds() > HEARTBEAT_TIMEOUT:
                    logger.warning(f"[WS] Heartbeat timeout for user {user_id}")
                    await websocket.close(code=1000, reason="Heartbeat timeout")
                    break
                
                # 发送心跳
                await websocket.send_text("ping")
            
            except WebSocketDisconnect:
                break
    
    finally:
        connection_manager.disconnect(websocket, user_id)


# ⭐ v4.19.4更新：使用基于角色的动态限流（替换硬编码限流）
try:
    from backend.middleware.rate_limiter import role_based_rate_limit
except ImportError:
    role_based_rate_limit = None

@router.get("/ws/stats")
@role_based_rate_limit(endpoint_type="default")  # ⭐ v4.19.4: 基于角色的动态限流
async def websocket_stats(
    current_user = Depends(require_admin),
    request: Request = None
):
    """
    获取 WebSocket 连接统计
    
    v4.19.0 P1运维要求：仅管理员可访问
    """
    stats = connection_manager.get_stats()
    
    # v4.19.0 P2性能要求：限制返回的连接数（最多100个用户）
    if "connections_per_user" in stats:
        connections_per_user = stats["connections_per_user"]
        if len(connections_per_user) > 100:
            # 仅返回连接数最多的前100个用户
            sorted_users = sorted(
                connections_per_user.items(),
                key=lambda x: x[1],
                reverse=True
            )[:100]
            stats["connections_per_user"] = dict(sorted_users)
            stats["total_users"] = len(connections_per_user)
            stats["returned_users"] = 100
    
    return success_response(
        data=stats,
        message="WebSocket statistics retrieved"
    )


# v4.19.0: 定期清理死连接的后台任务
_cleanup_task = None

async def start_cleanup_task():
    """
    启动清理任务
    
    Returns:
        asyncio.Task: 清理任务（用于在应用关闭时取消）
    """
    global _cleanup_task
    if _cleanup_task is not None and not _cleanup_task.done():
        return _cleanup_task  # 已经启动
    
    async def _cleanup_loop():
        """清理循环"""
        while True:
            try:
                await asyncio.sleep(60)  # 每分钟清理一次
                await connection_manager.cleanup_dead_connections()
                connection_manager._cleanup_expired_attempts()
            except asyncio.CancelledError:
                logger.info("[WS] Cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"[WS] Cleanup task error: {e}")
    
    _cleanup_task = asyncio.create_task(_cleanup_loop())
    logger.info("[WS] WebSocket cleanup task started")
    return _cleanup_task


def init_websocket_cleanup():
    """
    初始化 WebSocket 清理任务
    
    注意：应该在 FastAPI lifespan startup 中调用，而不是在模块导入时
    """
    # 这个函数保留用于向后兼容，但实际启动应该在 lifespan 中
    logger.debug("[WS] init_websocket_cleanup called (should be called from lifespan)")

