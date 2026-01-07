"""
用户任务配额服务

⭐ Phase 4.2: 用户隔离功能
- 跟踪每个用户正在运行的任务数量
- 实现用户级别的任务配额限制
- 防止单个用户提交过多任务影响其他用户

使用 Redis 存储用户任务计数（轻量级，高性能）
"""

from typing import Optional
from modules.core.logger import get_logger

logger = get_logger(__name__)

# 默认配额配置
DEFAULT_MAX_CONCURRENT_TASKS_PER_USER = 10  # 每个用户最多同时运行 10 个任务


class UserTaskQuotaService:
    """用户任务配额服务"""
    
    def __init__(self, redis_client=None):
        """
        初始化用户任务配额服务
        
        Args:
            redis_client: Redis 客户端（可选，如果为 None 则从 cache_service 获取）
        """
        self.redis_client = redis_client
        self.max_concurrent_tasks = DEFAULT_MAX_CONCURRENT_TASKS_PER_USER
    
    def _get_redis_client(self):
        """获取 Redis 客户端"""
        if self.redis_client:
            return self.redis_client
        
        try:
            from backend.services.cache_service import get_cache_service
            cache_service = get_cache_service()
            if cache_service and cache_service.redis_client:
                return cache_service.redis_client
        except Exception as e:
            logger.debug(f"[UserTaskQuota] 无法获取 Redis 客户端: {e}")
        
        return None
    
    def _get_user_task_count_key(self, user_id: int) -> str:
        """获取用户任务计数键"""
        return f"xihong_erp:user_task_count:{user_id}"
    
    async def get_user_task_count(self, user_id: int) -> int:
        """
        获取用户当前正在运行的任务数量
        
        Args:
            user_id: 用户ID
            
        Returns:
            int: 任务数量（如果 Redis 不可用，返回 0）
        """
        redis_client = self._get_redis_client()
        if not redis_client:
            # ⭐ v4.19.5 优化：降低日志级别（WARNING → DEBUG），减少日志噪音
            logger.debug(f"[UserTaskQuota] Redis 不可用，返回默认任务数量 0")
            return 0
        
        try:
            key = self._get_user_task_count_key(user_id)
            count = await redis_client.get(key)
            return int(count) if count else 0
        except Exception as e:
            # ⭐ v4.19.5 优化：区分不同类型的错误
            error_msg = str(e).lower()
            if "authentication" in error_msg or "auth" in error_msg:
                logger.debug(f"[UserTaskQuota] Redis 认证失败，返回默认任务数量 0（降级处理）")
            else:
                logger.debug(f"[UserTaskQuota] 查询用户 {user_id} 任务数量失败: {e}")
            return 0
    
    async def increment_user_task_count(self, user_id: int) -> bool:
        """
        增加用户任务计数（任务提交时调用）
        
        Args:
            user_id: 用户ID
            
        Returns:
            bool: 是否成功增加（如果超过配额，返回 False）
        """
        redis_client = self._get_redis_client()
        if not redis_client:
            # ⭐ v4.19.5 优化：降低日志级别
            logger.debug(f"[UserTaskQuota] Redis 不可用，允许提交任务（降级策略）")
            # Redis 不可用时，允许提交（降级策略）
            return True
        
        try:
            key = self._get_user_task_count_key(user_id)
            
            # 使用 Redis INCR 原子操作
            current_count = await redis_client.incr(key)
            
            # 设置过期时间（1小时，防止键永久存在）
            await redis_client.expire(key, 3600)
            
            # 检查是否超过配额
            if current_count > self.max_concurrent_tasks:
                # 超过配额，回滚计数
                await redis_client.decr(key)
                logger.warning(
                    f"[UserTaskQuota] 用户 {user_id} 任务数量超过配额: "
                    f"当前 {current_count} > 最大 {self.max_concurrent_tasks}"
                )
                return False
            
            logger.debug(f"[UserTaskQuota] 用户 {user_id} 任务计数增加: {current_count}/{self.max_concurrent_tasks}")
            return True
        except Exception as e:
            logger.error(f"[UserTaskQuota] 增加用户 {user_id} 任务计数失败: {e}")
            return False
    
    async def decrement_user_task_count(self, user_id: int) -> None:
        """
        减少用户任务计数（任务完成或失败时调用）
        
        Args:
            user_id: 用户ID
        """
        redis_client = self._get_redis_client()
        if not redis_client:
            # ⭐ v4.19.5 优化：降低日志级别
            logger.debug(f"[UserTaskQuota] Redis 不可用，跳过减少任务计数")
            return
        
        try:
            key = self._get_user_task_count_key(user_id)
            
            # 使用 Redis DECR 原子操作（不会小于 0）
            current_count = await redis_client.decr(key)
            
            # 如果计数为 0 或负数，删除键
            if current_count <= 0:
                await redis_client.delete(key)
            
            logger.debug(f"[UserTaskQuota] 用户 {user_id} 任务计数减少: {current_count if current_count > 0 else 0}/{self.max_concurrent_tasks}")
        except Exception as e:
            # ⭐ v4.19.5 优化：区分不同类型的错误，静默处理认证错误
            error_msg = str(e).lower()
            if "authentication" in error_msg or "auth" in error_msg:
                logger.debug(f"[UserTaskQuota] Redis 认证失败，跳过任务计数操作（降级处理）")
            else:
                logger.warning(f"[UserTaskQuota] 减少用户 {user_id} 任务计数失败: {e}")
    
    async def can_submit_task(self, user_id: int) -> tuple[bool, Optional[str]]:
        """
        检查用户是否可以提交新任务
        
        Args:
            user_id: 用户ID
            
        Returns:
            tuple[bool, Optional[str]]: (是否可以提交, 错误消息)
        """
        current_count = await self.get_user_task_count(user_id)
        
        if current_count >= self.max_concurrent_tasks:
            return (
                False,
                f"任务数量超过限制：当前 {current_count} 个任务，最多允许 {self.max_concurrent_tasks} 个并发任务"
            )
        
        return (True, None)
    
    async def reset_user_task_count(self, user_id: int) -> None:
        """
        重置用户任务计数（用于清理或调试）
        
        Args:
            user_id: 用户ID
        """
        redis_client = self._get_redis_client()
        if not redis_client:
            return
        
        try:
            key = self._get_user_task_count_key(user_id)
            await redis_client.delete(key)
            logger.info(f"[UserTaskQuota] 已重置用户 {user_id} 的任务计数")
        except Exception as e:
            logger.error(f"[UserTaskQuota] 重置用户 {user_id} 任务计数失败: {e}")


# 全局服务实例
_user_task_quota_service: Optional[UserTaskQuotaService] = None


def get_user_task_quota_service(redis_client=None) -> UserTaskQuotaService:
    """
    获取用户任务配额服务实例（单例模式）
    
    Args:
        redis_client: Redis 客户端（可选）
        
    Returns:
        UserTaskQuotaService: 服务实例
    """
    global _user_task_quota_service
    
    if _user_task_quota_service is None:
        _user_task_quota_service = UserTaskQuotaService(redis_client=redis_client)
    
    return _user_task_quota_service

