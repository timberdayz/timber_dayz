"""
WebSocket服务 - 采集任务实时状态推送

提供采集任务执行过程中的实时状态推送功能
"""

from typing import Optional
from modules.core.logger import get_logger
from backend.routers.collection_websocket import connection_manager

logger = get_logger(__name__)


class WebSocketService:
    """
    WebSocket服务
    
    封装WebSocket连接管理器，提供采集任务状态推送功能
    """
    
    def __init__(self):
        self.manager = connection_manager
    
    async def send_progress(
        self,
        task_id: str,
        progress: int,
        message: str,
        current_domain: Optional[str] = None,
        status: str = "running"
    ):
        """
        发送进度更新
        
        Args:
            task_id: 任务ID
            progress: 进度百分比 (0-100)
            message: 进度消息
            current_domain: 当前采集的数据域（v4.7.0）
            status: 任务状态
        """
        try:
            await self.manager.send_progress(
                task_id=task_id,
                progress=progress,
                current_step=message,
                status=status
            )
            
            # v4.7.0: 如果提供了current_domain，发送额外的域级别更新
            if current_domain:
                await self.manager.broadcast_to_task(task_id, {
                    "type": "domain_progress",
                    "task_id": task_id,
                    "current_domain": current_domain,
                    "progress": progress,
                    "message": message
                })
        
        except Exception as e:
            logger.error(f"Failed to send progress via WebSocket: {e}")
    
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
            level: 日志级别 (info/warning/error/debug)
            message: 日志消息
        """
        try:
            await self.manager.send_log(
                task_id=task_id,
                level=level,
                message=message
            )
        except Exception as e:
            logger.error(f"Failed to send log via WebSocket: {e}")
    
    async def send_complete(
        self,
        task_id: str,
        status: str,
        files_collected: int = 0,
        error_message: Optional[str] = None,
        completed_domains: list = None,
        failed_domains: list = None
    ):
        """
        发送任务完成通知
        
        Args:
            task_id: 任务ID
            status: 最终状态 (completed/partial_success/failed/cancelled)
            files_collected: 采集文件数
            error_message: 错误信息（如果有）
            completed_domains: 成功的数据域列表（v4.7.0）
            failed_domains: 失败的数据域列表（v4.7.0）
        """
        try:
            # 发送基础完成消息
            await self.manager.send_complete(
                task_id=task_id,
                status=status,
                files_collected=files_collected,
                error_message=error_message
            )
            
            # v4.7.0: 发送域级别统计
            if completed_domains or failed_domains:
                await self.manager.broadcast_to_task(task_id, {
                    "type": "domain_summary",
                    "task_id": task_id,
                    "completed_domains": completed_domains or [],
                    "failed_domains": failed_domains or [],
                    "total_domains": (len(completed_domains or []) + len(failed_domains or []))
                })
        
        except Exception as e:
            logger.error(f"Failed to send complete via WebSocket: {e}")
    
    async def send_verification_required(
        self,
        task_id: str,
        verification_type: str,
        screenshot_path: Optional[str] = None
    ):
        """
        发送验证码请求
        
        Args:
            task_id: 任务ID
            verification_type: 验证码类型 (captcha/sms/email)
            screenshot_path: 验证码截图路径
        """
        try:
            await self.manager.send_verification_required(
                task_id=task_id,
                verification_type=verification_type,
                screenshot_path=screenshot_path
            )
        except Exception as e:
            logger.error(f"Failed to send verification request via WebSocket: {e}")
    
    def get_connection_count(self, task_id: Optional[str] = None) -> int:
        """
        获取WebSocket连接数
        
        Args:
            task_id: 任务ID（可选）
        
        Returns:
            int: 连接数
        """
        return self.manager.get_connection_count(task_id)
    
    def get_active_tasks(self) -> list:
        """
        获取有活跃WebSocket连接的任务ID列表
        
        Returns:
            list: 任务ID列表
        """
        return self.manager.get_active_task_ids()


# 全局WebSocket服务实例
websocket_service = WebSocketService()

