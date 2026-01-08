"""
系统维护服务
提供缓存清理、数据清理、系统升级等功能

v4.20.0: 系统管理模块API实现
"""

import os
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, and_
from modules.core.db import SystemLog, BackupRecord
from modules.core.logger import get_logger
from backend.utils.config import get_settings

logger = get_logger(__name__)


class MaintenanceService:
    """系统维护服务类"""
    
    def __init__(self, db: AsyncSession):
        """初始化服务（仅支持异步）"""
        self.db = db
        self.settings = get_settings()
        
        # Docker环境路径配置（容器内路径）
        self.temp_dir = Path("/app/temp")
        self.data_dir = Path("/app/data")
        self.logs_dir = Path("/app/logs")
    
    # ==================== 缓存清理 ====================
    
    async def get_cache_status(self) -> Dict[str, Any]:
        """获取缓存状态"""
        status = {
            "redis_connected": False,
            "redis_memory_used": None,
            "redis_keys_count": None,
            "app_cache_size": None
        }
        
        try:
            # 尝试连接Redis
            import redis
            
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
            # 如果REDIS_URL中没有密码，尝试从REDIS_PASSWORD读取
            if "@" not in redis_url.split("://")[1] and os.getenv("REDIS_PASSWORD"):
                from urllib.parse import urlparse
                parsed = urlparse(redis_url)
                password = os.getenv("REDIS_PASSWORD")
                if parsed.port:
                    redis_url = f"redis://:{password}@{parsed.hostname}:{parsed.port}{parsed.path}"
                else:
                    redis_url = f"redis://:{password}@{parsed.hostname}:6379{parsed.path}"
            
            # Docker环境：使用redis服务名连接
            r = redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
            r.ping()
            
            status["redis_connected"] = True
            
            # 获取Redis信息
            info = r.info("memory")
            status["redis_memory_used"] = info.get("used_memory", 0)
            
            # 获取键数量
            status["redis_keys_count"] = r.dbsize()
            
            r.close()
            
        except ImportError:
            logger.warning("redis库未安装，无法获取Redis状态")
        except Exception as e:
            logger.warning(f"获取Redis状态失败: {e}")
        
        # 应用缓存大小（简化实现，实际可以统计应用内缓存对象）
        status["app_cache_size"] = 0  # TODO: 实现应用缓存统计
        
        return status
    
    async def clear_cache(
        self,
        cache_type: str = "all",
        pattern: Optional[str] = None
    ) -> Tuple[int, Optional[int]]:
        """
        清理缓存
        
        Returns:
            (cleared_keys, freed_memory_bytes)
        """
        cleared_keys = 0
        freed_memory = None
        
        try:
            import redis
            
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
            # 如果REDIS_URL中没有密码，尝试从REDIS_PASSWORD读取
            if "@" not in redis_url.split("://")[1] and os.getenv("REDIS_PASSWORD"):
                from urllib.parse import urlparse
                parsed = urlparse(redis_url)
                password = os.getenv("REDIS_PASSWORD")
                if parsed.port:
                    redis_url = f"redis://:{password}@{parsed.hostname}:{parsed.port}{parsed.path}"
                else:
                    redis_url = f"redis://:{password}@{parsed.hostname}:6379{parsed.path}"
            
            r = redis.from_url(redis_url, socket_connect_timeout=5, socket_timeout=5)
            
            if cache_type in ["all", "redis"]:
                if pattern:
                    # 按模式清理
                    keys = r.keys(pattern)
                    if keys:
                        cleared_keys = r.delete(*keys)
                else:
                    # 清理所有缓存
                    cleared_keys = r.dbsize()
                    r.flushdb()
                    freed_memory = r.info("memory").get("used_memory", 0)
            
            r.close()
            
            # 应用缓存清理（TODO: 实现应用内缓存清理）
            if cache_type in ["all", "app"]:
                # 这里可以清理应用内的缓存对象
                pass
            
            return cleared_keys, freed_memory
            
        except ImportError:
            logger.warning("redis库未安装，无法清理Redis缓存")
            return 0, None
        except Exception as e:
            logger.error(f"清理缓存失败: {e}", exc_info=True)
            raise
    
    # ==================== 数据清理 ====================
    
    async def get_data_status(self) -> Dict[str, Any]:
        """获取数据状态"""
        status = {
            "system_logs_count": 0,
            "system_logs_size": None,
            "task_logs_count": 0,
            "task_logs_size": None,
            "temp_files_count": 0,
            "temp_files_size": 0,
            "staging_data_count": 0,
            "staging_data_size": None
        }
        
        try:
            # 系统日志统计
            result = await self.db.execute(select(func.count(SystemLog.id)))
            status["system_logs_count"] = result.scalar() or 0
            
            # 任务日志统计（TODO: 如果有任务日志表）
            # result = await self.db.execute(select(func.count(CollectionTaskLog.id)))
            # status["task_logs_count"] = result.scalar() or 0
            
            # 临时文件统计
            if self.temp_dir.exists():
                temp_files = list(self.temp_dir.rglob("*"))
                status["temp_files_count"] = len([f for f in temp_files if f.is_file()])
                status["temp_files_size"] = sum(f.stat().st_size for f in temp_files if f.is_file())
            
            # 临时表数据统计（TODO: 如果有staging表）
            # status["staging_data_count"] = ...
            
        except Exception as e:
            logger.error(f"获取数据状态失败: {e}", exc_info=True)
        
        return status
    
    async def clean_data(
        self,
        clean_type: str,
        retention_days: int,
        user_id: Optional[int] = None
    ) -> Tuple[int, Optional[int]]:
        """
        清理数据
        
        Returns:
            (deleted_count, freed_space_bytes)
        """
        deleted_count = 0
        freed_space = 0
        
        try:
            if clean_type == "system_logs":
                # 清理系统日志（保留最近N天）
                cutoff_time = datetime.utcnow() - timedelta(days=retention_days)
                
                # 查询要删除的记录数
                count_result = await self.db.execute(
                    select(func.count(SystemLog.id)).where(
                        SystemLog.created_at < cutoff_time
                    )
                )
                deleted_count = count_result.scalar() or 0
                
                # 执行删除
                if deleted_count > 0:
                    delete_stmt = delete(SystemLog).where(
                        SystemLog.created_at < cutoff_time
                    )
                    await self.db.execute(delete_stmt)
                    await self.db.commit()
                
                logger.info(f"清理系统日志: 删除 {deleted_count} 条记录（保留最近{retention_days}天）")
                
            elif clean_type == "temp_files":
                # 清理临时文件（保留最近N天）
                cutoff_time = datetime.utcnow() - timedelta(days=retention_days)
                
                if self.temp_dir.exists():
                    for file_path in self.temp_dir.rglob("*"):
                        if file_path.is_file():
                            file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                            if file_mtime < cutoff_time:
                                file_size = file_path.stat().st_size
                                file_path.unlink()
                                deleted_count += 1
                                freed_space += file_size
                
                logger.info(f"清理临时文件: 删除 {deleted_count} 个文件，释放 {freed_space} 字节")
                
            elif clean_type == "task_logs":
                # 清理任务日志（TODO: 如果有任务日志表）
                logger.warning("任务日志清理功能待实现")
                
            elif clean_type == "staging_data":
                # 清理临时表数据（TODO: 如果有staging表）
                logger.warning("临时表数据清理功能待实现")
            
            # 记录审计日志
            from backend.services.audit_service import audit_service
            await audit_service.log_action(
                user_id=user_id,
                action="data_cleanup",
                resource="maintenance",
                resource_id=clean_type,
                details={
                    "clean_type": clean_type,
                    "retention_days": retention_days,
                    "deleted_count": deleted_count,
                    "freed_space": freed_space
                },
                is_success=True
            )
            
            return deleted_count, freed_space
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"清理数据失败: {e}", exc_info=True)
            raise
    
    # ==================== 系统升级（P3 - 可选） ====================
    
    async def check_upgrade(self) -> Dict[str, Any]:
        """
        检查系统升级
        
        返回当前版本和最新版本信息
        """
        # 获取当前版本（从环境变量或配置文件）
        current_version = os.getenv("APP_VERSION", "v4.20.0")
        
        # TODO: 从GitHub/GitLab API获取最新版本
        # 这里只是占位实现
        latest_version = None
        upgrade_available = False
        release_notes = None
        
        return {
            "current_version": current_version,
            "latest_version": latest_version,
            "upgrade_available": upgrade_available,
            "release_notes": release_notes,
            "check_time": datetime.utcnow()
        }


def get_maintenance_service(db: AsyncSession) -> MaintenanceService:
    """获取维护服务实例"""
    return MaintenanceService(db)
