#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
账号信息加密服务 (v4.7.0)

功能：
- 使用 Fernet 对称加密算法加密/解密密码
- 密钥从环境变量读取
- 首次启动时自动生成密钥
"""

import os
import base64
from cryptography.fernet import Fernet, InvalidToken
from modules.core.logger import get_logger

logger = get_logger(__name__)


class AccountEncryptionService:
    """
    账号信息加密服务
    
    使用Fernet对称加密算法，密钥存储在环境变量ACCOUNT_ENCRYPTION_KEY中
    """
    
    def __init__(self):
        """初始化加密服务"""
        encryption_key = os.getenv('ACCOUNT_ENCRYPTION_KEY')
        
        if not encryption_key:
            # 首次启动，生成密钥
            encryption_key = Fernet.generate_key().decode()
            logger.warning("="*60)
            logger.warning("[WARN]  首次启动检测：未找到加密密钥")
            logger.warning("="*60)
            logger.warning(f"请将以下密钥添加到 .env 文件:")
            logger.warning(f"ACCOUNT_ENCRYPTION_KEY={encryption_key}")
            logger.warning("="*60)
            logger.warning("安全提示:")
            logger.warning("1. 此密钥用于加密账号密码，请妥善保管")
            logger.warning("2. 密钥泄露将导致所有账号密码可被解密")
            logger.warning("3. 密钥丢失将导致无法解密已有账号密码")
            logger.warning("="*60)
            
            # 使用临时生成的密钥（仅本次运行有效）
            logger.info("使用临时密钥（仅本次运行有效，重启后失效）")
        
        try:
            self.cipher = Fernet(encryption_key.encode())
            logger.info("加密服务初始化成功")
        except Exception as e:
            logger.error(f"加密服务初始化失败: {e}")
            raise ValueError(f"加密密钥无效: {e}")
    
    def encrypt_password(self, plain_password: str) -> str:
        """
        加密密码
        
        Args:
            plain_password: 明文密码
            
        Returns:
            str: Base64编码的加密密码
        """
        if not plain_password:
            return ""
        
        try:
            encrypted = self.cipher.encrypt(plain_password.encode())
            encrypted_b64 = base64.b64encode(encrypted).decode()
            logger.debug("密码加密成功")
            return encrypted_b64
        except Exception as e:
            logger.error(f"密码加密失败: {e}")
            raise ValueError(f"密码加密失败: {e}")
    
    def decrypt_password(self, encrypted_password: str) -> str:
        """
        解密密码
        
        Args:
            encrypted_password: Base64编码的加密密码
            
        Returns:
            str: 明文密码
        """
        if not encrypted_password:
            return ""
        
        try:
            encrypted = base64.b64decode(encrypted_password.encode())
            decrypted = self.cipher.decrypt(encrypted)
            logger.debug("密码解密成功")
            return decrypted.decode()
        except InvalidToken:
            logger.error("密码解密失败: 无效的密钥或数据已损坏")
            raise ValueError("密码解密失败: 无效的密钥或数据已损坏")
        except Exception as e:
            logger.error(f"密码解密失败: {e}")
            raise ValueError(f"密码解密失败: {e}")
    
    def verify_encryption(self, plain_password: str, encrypted_password: str) -> bool:
        """
        验证加密密码是否正确
        
        Args:
            plain_password: 明文密码
            encrypted_password: 加密密码
            
        Returns:
            bool: 是否匹配
        """
        try:
            decrypted = self.decrypt_password(encrypted_password)
            return decrypted == plain_password
        except Exception:
            return False


# 全局单例（延迟初始化）
_encryption_service = None


def get_encryption_service() -> AccountEncryptionService:
    """
    获取加密服务单例
    
    Returns:
        AccountEncryptionService: 加密服务实例
    """
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = AccountEncryptionService()
    return _encryption_service

