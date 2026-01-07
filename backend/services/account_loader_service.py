#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
账号加载服务 (v4.7.0)
从数据库加载账号信息，用于数据采集模块

替代 local_accounts.py，统一账号数据源（SSOT原则）
"""

from typing import Dict, List, Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from modules.core.db import PlatformAccount
from backend.services.encryption_service import get_encryption_service
from modules.core.logger import get_logger

logger = get_logger(__name__)


class AccountLoaderService:
    """账号加载服务（数据库优先，支持同步/异步）"""
    
    def __init__(self):
        self.encryption_service = get_encryption_service()
    
    async def load_account_async(self, account_id: str, db: AsyncSession) -> Optional[Dict]:
        """
        从数据库加载账号信息（异步版本）
        
        Args:
            account_id: 账号ID
            db: 异步数据库会话
            
        Returns:
            账号字典（格式兼容采集模块），如果不存在或未启用返回None
        """
        result = await db.execute(
            select(PlatformAccount).where(
                PlatformAccount.account_id == account_id,
                PlatformAccount.enabled == True  # 只加载启用的账号
            )
        )
        account = result.scalar_one_or_none()
        
        if not account:
            logger.warning(f"账号 {account_id} 未找到或未启用")
            return None
        
        # 解密密码
        try:
            password = self.encryption_service.decrypt_password(account.password_encrypted)
        except Exception as e:
            logger.error(f"解密账号 {account_id} 密码失败: {e}")
            return None
        
        # 转换为采集模块需要的格式（兼容旧格式）
        account_dict = {
            # 核心字段
            'account_id': account.account_id,
            'platform': account.platform.lower(),  # 统一小写
            'store_name': account.store_name,
            'username': account.username,
            'password': password,
            'login_url': account.login_url or '',
            
            # 联系信息
            'email': account.email or '',
            'phone': account.phone or '',
            'region': account.region or 'CN',
            'currency': account.currency or 'CNY',
            
            # 店铺信息
            'shop_type': account.shop_type or '',
            'shop_region': account.shop_region or '',
            'parent_account': account.parent_account or '',
            
            # 状态和配置
            'enabled': account.enabled,
            'proxy_required': account.proxy_required,
            'notes': account.notes or '',
            
            # 能力配置（用于过滤不支持的数据域）
            'capabilities': account.capabilities or {},
            
            # 账号别名（用于账号对齐）
            'another_name': account.account_alias or '',
            'account_alias': account.account_alias or '',
            
            # 兼容旧字段（某些Handler可能需要）
            'E-mail': account.email or '',
            'Email account': account.email or '',
            'Email password': '',  # 数据库中没有存储邮箱密码
            'Email address': '',
            'login_flags': account.extra_config.get('login_flags', {}) if account.extra_config else {},
        }
        
        logger.debug(f"从数据库加载账号: {account_id} ({account.store_name})")
        return account_dict
    
    def load_account(self, account_id: str, db: Union[Session, AsyncSession]) -> Optional[Dict]:
        """
        从数据库加载账号信息（同步版本，兼容异步）
        
        Args:
            account_id: 账号ID
            db: 数据库会话（同步或异步）
            
        Returns:
            账号字典（格式兼容采集模块），如果不存在或未启用返回None
        """
        if isinstance(db, AsyncSession):
            # 异步模式：需要 await，但这是同步方法，应该使用 load_account_async
            raise ValueError("异步 Session 请使用 load_account_async() 方法")
        
        account = db.query(PlatformAccount).filter(
            PlatformAccount.account_id == account_id,
            PlatformAccount.enabled == True  # 只加载启用的账号
        ).first()
        
        if not account:
            logger.warning(f"账号 {account_id} 未找到或未启用")
            return None
        
        # 解密密码
        try:
            password = self.encryption_service.decrypt_password(account.password_encrypted)
        except Exception as e:
            logger.error(f"解密账号 {account_id} 密码失败: {e}")
            return None
        
        # 转换为采集模块需要的格式（兼容旧格式）
        account_dict = {
            # 核心字段
            'account_id': account.account_id,
            'platform': account.platform.lower(),  # 统一小写
            'store_name': account.store_name,
            'username': account.username,
            'password': password,
            'login_url': account.login_url or '',
            
            # 联系信息
            'email': account.email or '',
            'phone': account.phone or '',
            'region': account.region or 'CN',
            'currency': account.currency or 'CNY',
            
            # 店铺信息
            'shop_type': account.shop_type or '',
            'shop_region': account.shop_region or '',
            'parent_account': account.parent_account or '',
            
            # 状态和配置
            'enabled': account.enabled,
            'proxy_required': account.proxy_required,
            'notes': account.notes or '',
            
            # 能力配置（用于过滤不支持的数据域）
            'capabilities': account.capabilities or {},
            
            # 账号别名（用于账号对齐）
            'another_name': account.account_alias or '',
            'account_alias': account.account_alias or '',
            
            # 兼容旧字段（某些Handler可能需要）
            'E-mail': account.email or '',
            'Email account': account.email or '',
            'Email password': '',  # 数据库中没有存储邮箱密码
            'Email address': '',
            'login_flags': account.extra_config.get('login_flags', {}) if account.extra_config else {},
        }
        
        logger.debug(f"从数据库加载账号: {account_id} ({account.store_name})")
        return account_dict
    
    def load_all_accounts(self, db: Session, platform: Optional[str] = None) -> List[Dict]:
        """
        从数据库加载所有账号
        
        Args:
            db: 数据库会话
            platform: 平台筛选（可选）
            
        Returns:
            账号列表
        """
        query = db.query(PlatformAccount).filter(PlatformAccount.enabled == True)
        
        if platform:
            # 支持大小写不敏感匹配
            query = query.filter(PlatformAccount.platform.ilike(platform))
        
        accounts = query.order_by(PlatformAccount.platform, PlatformAccount.store_name).all()
        
        result = []
        for account in accounts:
            account_dict = self.load_account(account.account_id, db)
            if account_dict:
                result.append(account_dict)
        
        logger.info(f"从数据库加载了 {len(result)} 个活跃账号{f'（平台: {platform}）' if platform else ''}")
        return result
    
    def get_accounts_by_capability(
        self, 
        db: Session, 
        platform: str, 
        data_domain: str
    ) -> List[Dict]:
        """
        根据能力配置筛选账号
        
        Args:
            db: 数据库会话
            platform: 平台代码
            data_domain: 数据域（orders/products/services等）
            
        Returns:
            支持该数据域的账号列表
        """
        accounts = self.load_all_accounts(db, platform=platform)
        
        # 筛选支持该数据域的账号
        filtered = [
            acc for acc in accounts 
            if acc.get('capabilities', {}).get(data_domain, False)
        ]
        
        logger.info(f"平台 {platform} 支持 {data_domain} 的账号数: {len(filtered)}/{len(accounts)}")
        return filtered


# 全局单例
_account_loader_service = None


def get_account_loader_service() -> AccountLoaderService:
    """获取账号加载服务单例"""
    global _account_loader_service
    if _account_loader_service is None:
        _account_loader_service = AccountLoaderService()
    return _account_loader_service

