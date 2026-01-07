#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
安全秘密管理器

提供统一的秘密管理功能：
- 环境变量读取
- 密钥生成和验证
- 安全存储和检索
- 开发/生产环境隔离
"""

import os
import secrets
from pathlib import Path
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
import base64
import hashlib

from .logger import get_logger
from .exceptions import ERPException

logger = get_logger(__name__)


class SecretsManager:
    """安全秘密管理器"""
    
    def __init__(self):
        """初始化秘密管理器"""
        self._load_env_file()
        self._validate_environment()
        
    def _load_env_file(self):
        """加载环境变量文件"""
        env_files = ['.env', '.env.local']
        
        for env_file in env_files:
            env_path = Path(env_file)
            if env_path.exists():
                try:
                    with open(env_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#') and '=' in line:
                                key, value = line.split('=', 1)
                                # 只设置未设置的环境变量
                                if key.strip() not in os.environ:
                                    os.environ[key.strip()] = value.strip()
                    
                    logger.debug(f"加载环境变量文件: {env_file}")
                    break
                    
                except Exception as e:
                    logger.warning(f"加载环境变量文件失败 {env_file}: {e}")
    
    def _validate_environment(self):
        """验证环境配置"""
        required_vars = ['DATABASE_NAME', 'DATA_DIR']
        missing_vars = []
        
        for var in required_vars:
            if not os.getenv(var):
                missing_vars.append(var)
        
        if missing_vars:
            logger.warning(f"缺少环境变量: {missing_vars}")
            logger.info("请创建 .env 文件或设置相应的环境变量")
    
    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        获取秘密值
        
        Args:
            key: 秘密键名
            default: 默认值
            
        Returns:
            Optional[str]: 秘密值
        """
        # 优先从环境变量获取
        value = os.getenv(key, default)
        
        if value is None:
            logger.warning(f"未找到秘密值: {key}")
        
        return value
    
    def get_database_path(self) -> Path:
        """获取数据库路径"""
        data_dir = self.get_secret('DATA_DIR', 'data')
        db_name = self.get_secret('DATABASE_NAME', 'sales_analytics.db')
        return Path(data_dir) / db_name
    
    def get_unified_database_path(self) -> Path:
        """获取统一数据库路径"""
        unified_path = self.get_secret('UNIFIED_DATABASE_PATH', 'data/unified_erp_system.db')
        # 确保使用绝对路径，避免相对路径问题
        if not Path(unified_path).is_absolute():
            # 从项目根目录开始计算路径（使用统一路径管理器）
            from .path_manager import get_project_root
            project_root = get_project_root()
            full_path = project_root / unified_path
            # 如果路径不存在，尝试从当前工作目录开始
            if not full_path.exists():
                current_dir = Path.cwd()
                full_path = current_dir / unified_path
            return full_path
        return Path(unified_path)
    
    def get_encryption_key(self, key_name: str = 'ACCOUNT_ENCRYPTION_KEY') -> bytes:
        """
        获取加密密钥
        
        Args:
            key_name: 密钥环境变量名
            
        Returns:
            bytes: 加密密钥
            
        Raises:
            ERPException: 密钥不存在或无效
        """
        key_hex = self.get_secret(key_name)
        
        if not key_hex:
            # 生成新密钥并提示用户保存
            new_key = secrets.token_hex(32)
            logger.error(f"未找到加密密钥 {key_name}")
            logger.info(f"请在 .env 文件中设置: {key_name}={new_key}")
            raise ERPException(f"缺少加密密钥: {key_name}")
        
        try:
            return bytes.fromhex(key_hex)
        except ValueError:
            raise ERPException(f"无效的加密密钥格式: {key_name}")
    
    def get_fernet_cipher(self, key_name: str = 'ACCOUNT_ENCRYPTION_KEY') -> Fernet:
        """
        获取Fernet加密器
        
        Args:
            key_name: 密钥环境变量名
            
        Returns:
            Fernet: 加密器实例
        """
        key_bytes = self.get_encryption_key(key_name)
        # Fernet需要32字节的base64编码密钥
        fernet_key = base64.urlsafe_b64encode(key_bytes)
        return Fernet(fernet_key)
    
    def encrypt_data(self, data: str, key_name: str = 'ACCOUNT_ENCRYPTION_KEY') -> str:
        """
        加密数据
        
        Args:
            data: 要加密的数据
            key_name: 密钥名称
            
        Returns:
            str: 加密后的数据（base64编码）
        """
        cipher = self.get_fernet_cipher(key_name)
        encrypted_data = cipher.encrypt(data.encode('utf-8'))
        return base64.urlsafe_b64encode(encrypted_data).decode('utf-8')
    
    def decrypt_data(self, encrypted_data: str, key_name: str = 'ACCOUNT_ENCRYPTION_KEY') -> str:
        """
        解密数据
        
        Args:
            encrypted_data: 加密的数据（base64编码）
            key_name: 密钥名称
            
        Returns:
            str: 解密后的数据
        """
        cipher = self.get_fernet_cipher(key_name)
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode('utf-8'))
        decrypted_data = cipher.decrypt(encrypted_bytes)
        return decrypted_data.decode('utf-8')
    
    def get_config_value(self, key: str, default: Any = None, value_type: type = str) -> Any:
        """
        获取配置值并转换类型
        
        Args:
            key: 配置键
            default: 默认值
            value_type: 值类型
            
        Returns:
            Any: 转换后的配置值
        """
        value = self.get_secret(key)
        
        if value is None:
            return default
        
        try:
            if value_type == bool:
                return value.lower() in ('true', '1', 'yes', 'on')
            elif value_type == int:
                return int(value)
            elif value_type == float:
                return float(value)
            else:
                return value_type(value)
        except (ValueError, TypeError):
            logger.warning(f"配置值类型转换失败 {key}={value}, 使用默认值: {default}")
            return default
    
    def is_development_mode(self) -> bool:
        """检查是否为开发模式"""
        return self.get_config_value('DEVELOPMENT_MODE', False, bool)
    
    def is_debug_mode(self) -> bool:
        """检查是否为调试模式"""
        return self.get_config_value('DEBUG', False, bool)
    
    def get_log_level(self) -> str:
        """获取日志级别"""
        return self.get_secret('LOG_LEVEL', 'INFO').upper()
    
    def generate_new_key(self) -> str:
        """生成新的32字节密钥"""
        return secrets.token_hex(32)
    
    def validate_key_format(self, key_hex: str) -> bool:
        """验证密钥格式"""
        try:
            key_bytes = bytes.fromhex(key_hex)
            return len(key_bytes) == 32
        except ValueError:
            return False


# 全局秘密管理器实例
_secrets_manager = None


def get_secrets_manager() -> SecretsManager:
    """获取全局秘密管理器实例"""
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = SecretsManager()
    return _secrets_manager


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """获取秘密值的便捷函数"""
    return get_secrets_manager().get_secret(key, default)


def get_database_path() -> Path:
    """获取数据库路径的便捷函数"""
    return get_secrets_manager().get_database_path()


def get_encryption_key(key_name: str = 'ACCOUNT_ENCRYPTION_KEY') -> bytes:
    """获取加密密钥的便捷函数"""
    return get_secrets_manager().get_encryption_key(key_name)
