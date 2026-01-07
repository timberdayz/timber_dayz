"""
资源监控服务

v4.19.0新增：执行器统一管理和资源优化
- 定期检查资源使用率
- 告警阈值检查
- 警告日志记录

注意：轻量级监控，避免性能开销
"""

import asyncio
import psutil
import threading
from typing import Optional
from modules.core.logger import get_logger

logger = get_logger(__name__)


class ResourceMonitor:
    """
    资源监控服务
    
    功能：
    - 定期检查CPU和内存使用率
    - 当资源使用率超过阈值时记录警告日志
    - 可选：发送告警通知（邮件/短信/Webhook）
    """
    
    def __init__(
        self,
        cpu_threshold: float = 80.0,
        memory_threshold: float = 85.0,
        check_interval: int = 60,  # 检查间隔（秒）
        enabled: bool = True
    ):
        """
        初始化资源监控服务
        
        Args:
            cpu_threshold: CPU使用率告警阈值（%），默认80%
            memory_threshold: 内存使用率告警阈值（%），默认85%
            check_interval: 检查间隔（秒），默认60秒
            enabled: 是否启用监控，默认True
        """
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold
        self.check_interval = check_interval
        self.enabled = enabled
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._lock = threading.Lock()
    
    async def start(self):
        """启动资源监控服务"""
        with self._lock:
            if self._running:
                logger.warning("[ResourceMonitor] 监控服务已在运行")
                return
            
            if not self.enabled:
                logger.info("[ResourceMonitor] 监控服务已禁用")
                return
            
            self._running = True
            self._task = asyncio.create_task(self._monitor_loop())
            logger.info(
                f"[ResourceMonitor] 监控服务已启动 - "
                f"CPU阈值: {self.cpu_threshold}%, "
                f"内存阈值: {self.memory_threshold}%, "
                f"检查间隔: {self.check_interval}秒"
            )
    
    async def stop(self):
        """停止资源监控服务"""
        with self._lock:
            if not self._running:
                return
            
            self._running = False
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            logger.info("[ResourceMonitor] 监控服务已停止")
    
    async def _monitor_loop(self):
        """监控循环"""
        while self._running:
            try:
                await self._check_resources()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                logger.info("[ResourceMonitor] 监控循环已取消")
                break
            except Exception as e:
                logger.error(f"[ResourceMonitor] 监控检查失败: {e}", exc_info=True)
                # 即使出错也继续监控
                await asyncio.sleep(self.check_interval)
    
    async def _check_resources(self):
        """检查资源使用情况"""
        # ⭐ 使用 run_in_executor 包装 psutil 调用，避免阻塞事件循环
        loop = asyncio.get_running_loop()
        
        # CPU使用率（需要间隔时间，使用0.1秒）
        cpu_usage = await loop.run_in_executor(
            None,
            lambda: psutil.cpu_percent(interval=0.1)
        )
        
        # 内存使用率
        memory_info = await loop.run_in_executor(
            None,
            psutil.virtual_memory
        )
        memory_usage = memory_info.percent
        
        # 检查阈值
        if cpu_usage >= self.cpu_threshold:
            logger.warning(
                f"[ResourceMonitor] ⚠️ CPU使用率过高: {cpu_usage:.1f}% "
                f"(阈值: {self.cpu_threshold}%)"
            )
        
        if memory_usage >= self.memory_threshold:
            logger.warning(
                f"[ResourceMonitor] ⚠️ 内存使用率过高: {memory_usage:.1f}% "
                f"(阈值: {self.memory_threshold}%)"
            )
        
        # 可选：同时触发告警时记录更详细的日志
        if cpu_usage >= self.cpu_threshold and memory_usage >= self.memory_threshold:
            logger.error(
                f"[ResourceMonitor] 🚨 资源使用率严重超标 - "
                f"CPU: {cpu_usage:.1f}%, 内存: {memory_usage:.1f}%"
            )


# 全局资源监控服务实例
_resource_monitor: Optional[ResourceMonitor] = None


def get_resource_monitor(
    cpu_threshold: Optional[float] = None,
    memory_threshold: Optional[float] = None,
    check_interval: Optional[int] = None,
    enabled: Optional[bool] = None
) -> ResourceMonitor:
    """
    获取资源监控服务实例（单例模式）
    
    Args:
        cpu_threshold: CPU使用率告警阈值（%），默认80%
        memory_threshold: 内存使用率告警阈值（%），默认85%
        check_interval: 检查间隔（秒），默认60秒
        enabled: 是否启用监控，默认True
    
    Returns:
        ResourceMonitor: 资源监控服务实例
    """
    global _resource_monitor
    
    if _resource_monitor is None:
        import os
        # 从环境变量读取配置
        cpu_threshold = float(os.getenv("RESOURCE_MONITOR_CPU_THRESHOLD", "80.0")) if cpu_threshold is None else cpu_threshold
        memory_threshold = float(os.getenv("RESOURCE_MONITOR_MEMORY_THRESHOLD", "85.0")) if memory_threshold is None else memory_threshold
        check_interval = int(os.getenv("RESOURCE_MONITOR_CHECK_INTERVAL", "60")) if check_interval is None else check_interval
        enabled = os.getenv("RESOURCE_MONITOR_ENABLED", "true").lower() == "true" if enabled is None else enabled
        
        _resource_monitor = ResourceMonitor(
            cpu_threshold=cpu_threshold,
            memory_threshold=memory_threshold,
            check_interval=check_interval,
            enabled=enabled
        )
    
    return _resource_monitor

