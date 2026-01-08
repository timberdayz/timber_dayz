"""
系统配置服务
提供系统基础配置和数据库配置管理功能

v4.20.0: 系统管理模块API实现
"""

import os
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from modules.core.db import SystemConfig
from modules.core.logger import get_logger
from backend.utils.config import get_settings
from backend.services.encryption_service import get_encryption_service

logger = get_logger(__name__)


class SystemConfigService:
    """系统配置服务类"""
    
    def __init__(self, db: AsyncSession):
        """初始化服务（仅支持异步）"""
        self.db = db
        self.settings = get_settings()
        self.encryption_service = get_encryption_service()
    
    # ==================== 系统基础配置 ====================
    
    async def get_system_config(self) -> Dict[str, Any]:
        """获取系统基础配置"""
        config = {
            "system_name": "西虹ERP系统",
            "version": "v4.20.0",
            "timezone": "Asia/Shanghai",
            "language": "zh-CN",
            "currency": "CNY",
            "updated_at": None,
            "updated_by": None
        }
        
        try:
            # 从数据库读取配置
            config_keys = ["system_name", "version", "timezone", "language", "currency"]
            for key in config_keys:
                result = await self.db.execute(
                    select(SystemConfig).where(SystemConfig.config_key == key)
                )
                config_record = result.scalar_one_or_none()
                if config_record:
                    config[key] = config_record.config_value
                    if key == config_keys[0]:  # 使用第一个配置的更新时间
                        config["updated_at"] = config_record.updated_at
                        config["updated_by"] = config_record.updated_by
        except Exception as e:
            logger.warning(f"读取系统配置失败，使用默认值: {e}")
        
        return config
    
    async def update_system_config(
        self,
        config_update: Dict[str, Any],
        updated_by_user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """更新系统基础配置"""
        try:
            config_keys = ["system_name", "version", "timezone", "language", "currency"]
            
            for key, value in config_update.items():
                if key not in config_keys or value is None:
                    continue
                
                # 查找或创建配置记录
                result = await self.db.execute(
                    select(SystemConfig).where(SystemConfig.config_key == key)
                )
                config_record = result.scalar_one_or_none()
                
                if config_record:
                    # 更新现有配置
                    config_record.config_value = str(value)
                    config_record.updated_at = datetime.utcnow()
                    config_record.updated_by = updated_by_user_id
                else:
                    # 创建新配置
                    config_record = SystemConfig(
                        config_key=key,
                        config_value=str(value),
                        description=f"{key} configuration",
                        updated_by=updated_by_user_id
                    )
                    self.db.add(config_record)
            
            await self.db.commit()
            
            # 返回更新后的配置
            return await self.get_system_config()
        except Exception as e:
            await self.db.rollback()
            logger.error(f"更新系统配置失败: {e}", exc_info=True)
            raise
    
    # ==================== 数据库配置 ====================
    
    async def get_database_config(self) -> Dict[str, Any]:
        """获取数据库配置（从环境变量读取，敏感字段加密）"""
        try:
            # 从环境变量或settings读取
            database_url = self.settings.DATABASE_URL
            
            # 解析数据库URL
            from urllib.parse import urlparse
            parsed = urlparse(database_url)
            
            host = parsed.hostname or self.settings.POSTGRES_HOST
            port = parsed.port or self.settings.POSTGRES_PORT
            database = parsed.path.lstrip('/') if parsed.path else self.settings.POSTGRES_DB
            username = parsed.username or self.settings.POSTGRES_USER
            password = parsed.password or self.settings.POSTGRES_PASSWORD
            
            # 构建隐藏密码的连接URL
            safe_url = f"{parsed.scheme}://{username}:***@{host}:{port}/{database}"
            
            # 检查是否有pending状态的配置
            result = await self.db.execute(
                select(SystemConfig).where(
                    SystemConfig.config_key == "database_config_pending"
                )
            )
            pending_config = result.scalar_one_or_none()
            
            updated_at = None
            updated_by = None
            if pending_config:
                updated_at = pending_config.updated_at
                updated_by = pending_config.updated_by
            
            return {
                "host": host,
                "port": port,
                "database": database,
                "username": username,
                "password": "***",  # 密码已隐藏
                "connection_url": safe_url,
                "updated_at": updated_at,
                "updated_by": updated_by
            }
        except Exception as e:
            logger.error(f"获取数据库配置失败: {e}", exc_info=True)
            raise
    
    async def test_database_connection(
        self,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str
    ) -> tuple[bool, Optional[str], Optional[int]]:
        """
        测试数据库连接
        
        Returns:
            (is_success, error_message, response_time_ms)
        """
        import time
        from sqlalchemy import create_engine, text
        
        try:
            # 构建连接URL
            connection_url = f"postgresql://{username}:{password}@{host}:{port}/{database}"
            
            # 测试连接
            start_time = time.time()
            engine = create_engine(connection_url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
            
            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                result.scalar()
            
            response_time_ms = int((time.time() - start_time) * 1000)
            engine.dispose()
            
            return True, None, response_time_ms
        except Exception as e:
            logger.error(f"数据库连接测试失败: {e}", exc_info=True)
            return False, str(e), None
    
    async def update_database_config(
        self,
        config_update: Dict[str, Any],
        updated_by_user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        更新数据库配置（保存为pending状态）
        
        注意：在Docker环境中，配置需要手动应用到docker-compose.yml或通过动态配置应用
        """
        try:
            # 先测试新配置的连接性
            if "host" in config_update and "port" in config_update and "database" in config_update and "username" in config_update and "password" in config_update:
                is_success, error_message, _ = await self.test_database_connection(
                    host=config_update["host"],
                    port=config_update["port"],
                    database=config_update["database"],
                    username=config_update["username"],
                    password=config_update["password"]
                )
                
                if not is_success:
                    raise ValueError(f"数据库连接测试失败: {error_message}")
            
            # 加密密码
            if "password" in config_update:
                plain_password = config_update.pop("password")
                config_update["password_encrypted"] = self.encryption_service.encrypt_password(plain_password)
            
            # 保存配置到SystemConfig表（标记为pending）
            config_json = {
                "host": config_update.get("host"),
                "port": config_update.get("port"),
                "database": config_update.get("database"),
                "username": config_update.get("username"),
                "password_encrypted": config_update.get("password_encrypted")
            }
            
            # 查找或创建配置记录
            result = await self.db.execute(
                select(SystemConfig).where(
                    SystemConfig.config_key == "database_config_pending"
                )
            )
            config_record = result.scalar_one_or_none()
            
            if config_record:
                # 更新现有配置
                import json
                config_record.config_value = json.dumps(config_json)
                config_record.updated_at = datetime.utcnow()
                config_record.updated_by = updated_by_user_id
            else:
                # 创建新配置
                import json
                config_record = SystemConfig(
                    config_key="database_config_pending",
                    config_value=json.dumps(config_json),
                    description="数据库配置（pending状态，需要手动应用）",
                    updated_by=updated_by_user_id
                )
                self.db.add(config_record)
            
            await self.db.commit()
            
            # 返回更新后的配置（隐藏密码）
            return await self.get_database_config()
        except Exception as e:
            await self.db.rollback()
            logger.error(f"更新数据库配置失败: {e}", exc_info=True)
            raise


def get_system_config_service(db: AsyncSession) -> SystemConfigService:
    """获取系统配置服务实例"""
    return SystemConfigService(db)
