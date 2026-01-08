"""
安全配置服务
提供密码策略、登录限制、会话配置等安全配置的读取和管理

v4.20.0: 系统管理模块API实现
"""

from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from modules.core.db import SecurityConfig
from modules.core.logger import get_logger

logger = get_logger(__name__)


class SecurityConfigService:
    """安全配置服务类"""
    
    def __init__(self, db: AsyncSession):
        """初始化服务（仅支持异步）"""
        self.db = db
    
    async def get_config(self, config_key: str) -> Optional[SecurityConfig]:
        """获取配置"""
        try:
            result = await self.db.execute(
                select(SecurityConfig).where(SecurityConfig.config_key == config_key)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"获取安全配置失败 {config_key}: {e}", exc_info=True)
            return None
    
    async def set_config(
        self,
        config_key: str,
        config_value: Dict[str, Any],
        description: Optional[str] = None,
        updated_by: Optional[int] = None
    ) -> SecurityConfig:
        """设置配置（如果不存在则创建，存在则更新）"""
        config = await self.get_config(config_key)
        
        if config:
            # 更新现有配置
            config.config_value = config_value
            if description is not None:
                config.description = description
            if updated_by is not None:
                config.updated_by = updated_by
        else:
            # 创建新配置
            config = SecurityConfig(
                config_key=config_key,
                config_value=config_value,
                description=description,
                updated_by=updated_by
            )
            self.db.add(config)
        
        await self.db.commit()
        await self.db.refresh(config)
        return config
    
    # ==================== 密码策略 ====================
    
    async def get_password_policy(self) -> Dict[str, Any]:
        """
        获取密码策略（带默认值回退）
        
        默认值：
        - min_length: 8
        - require_uppercase: True
        - require_lowercase: True
        - require_digits: True
        - require_special_chars: False
        - max_age_days: 90
        - prevent_reuse_count: 5
        """
        config = await self.get_config("password_policy")
        
        if config and isinstance(config.config_value, dict):
            return config.config_value
        
        # 返回默认值
        return {
            "min_length": 8,
            "require_uppercase": True,
            "require_lowercase": True,
            "require_digits": True,
            "require_special_chars": False,
            "max_age_days": 90,
            "prevent_reuse_count": 5
        }
    
    async def set_password_policy(
        self,
        policy: Dict[str, Any],
        updated_by: Optional[int] = None
    ) -> SecurityConfig:
        """设置密码策略"""
        return await self.set_config(
            config_key="password_policy",
            config_value=policy,
            description="密码策略配置",
            updated_by=updated_by
        )
    
    def validate_password(self, password: str, policy: Optional[Dict[str, Any]] = None) -> tuple[bool, Optional[str]]:
        """
        验证密码是否符合策略
        
        Returns:
            (is_valid, error_message)
        """
        if policy is None:
            # 同步调用需要传入policy，异步调用应该先获取policy
            return False, "密码策略未提供"
        
        min_length = policy.get("min_length", 8)
        if len(password) < min_length:
            return False, f"密码长度至少{min_length}位"
        
        if policy.get("require_uppercase", True):
            if not any(c.isupper() for c in password):
                return False, "密码必须包含大写字母"
        
        if policy.get("require_lowercase", True):
            if not any(c.islower() for c in password):
                return False, "密码必须包含小写字母"
        
        if policy.get("require_digits", True):
            if not any(c.isdigit() for c in password):
                return False, "密码必须包含数字"
        
        if policy.get("require_special_chars", False):
            special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
            if not any(c in special_chars for c in password):
                return False, "密码必须包含特殊字符"
        
        return True, None
    
    # ==================== 登录限制 ====================
    
    async def get_login_restrictions(self) -> Dict[str, Any]:
        """
        获取登录限制配置（带默认值回退）
        
        默认值：
        - max_failed_attempts: 5
        - lockout_duration_minutes: 30
        - enable_ip_whitelist: False
        """
        config = await self.get_config("login_restrictions")
        
        if config and isinstance(config.config_value, dict):
            return config.config_value
        
        # 返回默认值
        return {
            "max_failed_attempts": 5,
            "lockout_duration_minutes": 30,
            "enable_ip_whitelist": False
        }
    
    async def set_login_restrictions(
        self,
        restrictions: Dict[str, Any],
        updated_by: Optional[int] = None
    ) -> SecurityConfig:
        """设置登录限制配置"""
        return await self.set_config(
            config_key="login_restrictions",
            config_value=restrictions,
            description="登录限制配置",
            updated_by=updated_by
        )
    
    async def get_ip_whitelist(self) -> List[str]:
        """
        获取IP白名单（带默认值回退）
        
        默认值：空列表
        """
        config = await self.get_config("ip_whitelist")
        
        if config and isinstance(config.config_value, list):
            return config.config_value
        
        return []
    
    async def set_ip_whitelist(
        self,
        ip_addresses: List[str],
        updated_by: Optional[int] = None
    ) -> SecurityConfig:
        """设置IP白名单"""
        return await self.set_config(
            config_key="ip_whitelist",
            config_value=ip_addresses,
            description="IP白名单配置",
            updated_by=updated_by
        )
    
    # ==================== 会话管理 ====================
    
    async def get_session_config(self) -> Dict[str, Any]:
        """
        获取会话配置（带默认值回退）
        
        默认值：
        - timeout_minutes: 15
        - max_concurrent_sessions: 5
        - enable_session_limit: True
        """
        config = await self.get_config("session_config")
        
        if config and isinstance(config.config_value, dict):
            return config.config_value
        
        # 返回默认值
        return {
            "timeout_minutes": 15,
            "max_concurrent_sessions": 5,
            "enable_session_limit": True
        }
    
    async def set_session_config(
        self,
        session_config: Dict[str, Any],
        updated_by: Optional[int] = None
    ) -> SecurityConfig:
        """设置会话配置"""
        return await self.set_config(
            config_key="session_config",
            config_value=session_config,
            description="会话管理配置",
            updated_by=updated_by
        )


def get_security_config_service(db: AsyncSession) -> SecurityConfigService:
    """获取安全配置服务实例"""
    return SecurityConfigService(db)
