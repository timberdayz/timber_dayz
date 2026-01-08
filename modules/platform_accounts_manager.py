#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
平台账号管理器
专家级跨境电商ERP系统 - 多平台账号统一管理
"""

import os
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
import pandas as pd

from utils.logger import get_logger
from utils.encryption import EncryptionManager

logger = get_logger(__name__)

@dataclass
class PlatformAccount:
    """平台账号数据结构"""
    account_id: str
    platform: str
    account_name: str
    login_url: str
    username: str
    password: str = ""  # 加密存储
    region: str = "global"
    status: str = "active"  # active, inactive, suspended
    last_login: Optional[datetime] = None
    login_success_rate: float = 0.0
    total_orders: int = 0
    monthly_revenue: float = 0.0
    health_score: float = 0.0
    risk_level: str = "low"  # low, medium, high
    notes: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class PlatformAccountsManager:
    """
    平台账号管理器
    专家级多平台账号统一管理和监控
    """

    def __init__(self):
        """初始化平台账号管理器"""
        self.logger = logger
        self.encryption_manager = EncryptionManager()
        
        # 配置路径
        self.config_dir = Path("config")
        self.config_dir.mkdir(exist_ok=True)
        
        # 本地账号配置文件路径
        self.local_accounts_file = Path("local_accounts.py")
        self.encrypted_accounts_file = self.config_dir / "encrypted_accounts.json"
        
        # 内存中的账号数据
        self.accounts: Dict[str, PlatformAccount] = {}
        
        # 平台配置
        self.platform_configs = {
            'shopee': {
                'name': 'Shopee',
                'default_regions': ['global', 'sg', 'my', 'th', 'vn', 'ph', 'id', 'br', 'mx', 'co', 'cl'],
                'health_indicators': ['login_success_rate', 'order_volume', 'account_status']
            },
            'lazada': {
                'name': 'Lazada',
                'default_regions': ['global', 'sg', 'my', 'th', 'vn', 'ph', 'id'],
                'health_indicators': ['login_success_rate', 'order_volume', 'account_status']
            },
            'amazon': {
                'name': 'Amazon',
                'default_regions': ['us', 'uk', 'de', 'fr', 'it', 'es', 'ca', 'jp', 'au'],
                'health_indicators': ['login_success_rate', 'order_volume', 'account_health']
            },
            'miaoshou': {
                'name': '妙手ERP',
                'default_regions': ['cn'],
                'health_indicators': ['login_success_rate', 'sync_status', 'api_health']
            }
        }
        
        # 加载账号数据
        self._load_accounts()
        
        logger.info(f"[OK] 平台账号管理器初始化完成，已加载 {len(self.accounts)} 个账号")

    def _load_accounts(self) -> None:
        """加载账号数据"""
        try:
            # 首先尝试从本地配置加载
            if self.local_accounts_file.exists():
                self._load_from_local_config()
            
            # 然后尝试从加密配置加载
            if self.encrypted_accounts_file.exists():
                self._load_from_encrypted_config()
                
            logger.info(f"[OK] 成功加载 {len(self.accounts)} 个账号配置")
            
        except Exception as e:
            logger.error(f"[FAIL] 加载账号配置失败: {e}")
            self.accounts = {}

    def _load_from_local_config(self) -> None:
        """从本地配置文件加载账号"""
        try:
            # 动态导入local_accounts.py
            import sys
            if str(Path.cwd()) not in sys.path:
                sys.path.insert(0, str(Path.cwd()))
            
            import local_accounts
            
            for account_data in local_accounts.ACCOUNTS:
                account = PlatformAccount(
                    account_id=account_data.get('account_id', ''),
                    platform=account_data.get('platform', ''),
                    account_name=account_data.get('account_name', ''),
                    login_url=account_data.get('login_url', ''),
                    username=account_data.get('username', ''),
                    password=account_data.get('password', ''),
                    region=account_data.get('region', 'global'),
                    status=account_data.get('status', 'active'),
                    notes=account_data.get('notes', ''),
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                
                # 计算健康分数
                account.health_score = self._calculate_health_score(account)
                account.risk_level = self._assess_risk_level(account)
                
                self.accounts[account.account_id] = account
                
            logger.info(f"[OK] 从local_accounts.py加载了 {len(local_accounts.ACCOUNTS)} 个账号")
            
        except ImportError:
            logger.warning("[WARN] local_accounts.py文件不存在或导入失败")
        except Exception as e:
            logger.error(f"[FAIL] 从本地配置加载账号失败: {e}")

    def _load_from_encrypted_config(self) -> None:
        """从加密配置文件加载账号"""
        try:
            with open(self.encrypted_accounts_file, 'r', encoding='utf-8') as f:
                encrypted_data = json.load(f)
            
            # 解密数据
            decrypted_data = self.encryption_manager.decrypt_data(encrypted_data)
            
            for account_data in decrypted_data.get('accounts', []):
                account = PlatformAccount(**account_data)
                # 更新时间戳
                if isinstance(account.last_login, str):
                    account.last_login = datetime.fromisoformat(account.last_login) if account.last_login else None
                if isinstance(account.created_at, str):
                    account.created_at = datetime.fromisoformat(account.created_at)
                if isinstance(account.updated_at, str):
                    account.updated_at = datetime.fromisoformat(account.updated_at)
                    
                self.accounts[account.account_id] = account
                
            logger.info(f"[OK] 从加密配置加载了 {len(decrypted_data.get('accounts', []))} 个账号")
            
        except Exception as e:
            logger.error(f"[FAIL] 从加密配置加载账号失败: {e}")

    def get_all_accounts(self) -> List[PlatformAccount]:
        """获取所有账号"""
        return list(self.accounts.values())

    def get_accounts_by_platform(self, platform: str) -> List[PlatformAccount]:
        """根据平台获取账号"""
        return [acc for acc in self.accounts.values() if acc.platform.lower() == platform.lower()]

    def get_active_accounts(self) -> List[PlatformAccount]:
        """获取活跃账号"""
        return [acc for acc in self.accounts.values() if acc.status == 'active']

    def get_account_by_id(self, account_id: str) -> Optional[PlatformAccount]:
        """根据ID获取账号"""
        return self.accounts.get(account_id)

    def get_platform_summary(self) -> Dict[str, Dict[str, int]]:
        """获取平台汇总信息"""
        summary = {}
        
        for platform_key, platform_config in self.platform_configs.items():
            platform_accounts = self.get_accounts_by_platform(platform_key)
            active_accounts = [acc for acc in platform_accounts if acc.status == 'active']
            
            summary[platform_config['name']] = {
                'total': len(platform_accounts),
                'active': len(active_accounts),
                'inactive': len(platform_accounts) - len(active_accounts)
            }
        
        return summary

    def _calculate_health_score(self, account: PlatformAccount) -> float:
        """计算账号健康分数"""
        score = 0.0
        
        # 登录成功率权重 40%
        score += account.login_success_rate * 0.4
        
        # 账号状态权重 30%
        status_scores = {'active': 1.0, 'inactive': 0.5, 'suspended': 0.0}
        score += status_scores.get(account.status, 0.0) * 0.3
        
        # 最近登录权重 20%
        if account.last_login:
            days_since_login = (datetime.now() - account.last_login).days
            if days_since_login <= 1:
                score += 1.0 * 0.2
            elif days_since_login <= 7:
                score += 0.8 * 0.2
            elif days_since_login <= 30:
                score += 0.5 * 0.2
            else:
                score += 0.2 * 0.2
        
        # 订单量权重 10%
        if account.total_orders > 100:
            score += 1.0 * 0.1
        elif account.total_orders > 50:
            score += 0.7 * 0.1
        elif account.total_orders > 10:
            score += 0.4 * 0.1
        
        return min(score, 1.0)  # 确保不超过1.0

    def _assess_risk_level(self, account: PlatformAccount) -> str:
        """评估风险等级"""
        risk_score = 0
        
        # 登录成功率低
        if account.login_success_rate < 0.5:
            risk_score += 3
        elif account.login_success_rate < 0.8:
            risk_score += 1
        
        # 账号状态异常
        if account.status == 'suspended':
            risk_score += 5
        elif account.status == 'inactive':
            risk_score += 2
        
        # 长时间未登录
        if account.last_login:
            days_since_login = (datetime.now() - account.last_login).days
            if days_since_login > 30:
                risk_score += 3
            elif days_since_login > 7:
                risk_score += 1
        else:
            risk_score += 2
        
        # 确定风险等级
        if risk_score >= 5:
            return 'high'
        elif risk_score >= 2:
            return 'medium'
        else:
            return 'low'

    def update_account_stats(self, account_id: str, 
                           login_success: Optional[bool] = None,
                           total_orders: Optional[int] = None,
                           monthly_revenue: Optional[float] = None) -> bool:
        """更新账号统计信息"""
        try:
            account = self.accounts.get(account_id)
            if not account:
                logger.warning(f"[WARN] 账号 {account_id} 不存在")
                return False
            
            # 更新登录统计
            if login_success is not None:
                if login_success:
                    account.last_login = datetime.now()
                    # 简化的成功率计算，实际应该维护历史记录
                    account.login_success_rate = min(account.login_success_rate + 0.1, 1.0)
                else:
                    account.login_success_rate = max(account.login_success_rate - 0.1, 0.0)
            
            # 更新业务统计
            if total_orders is not None:
                account.total_orders = total_orders
            
            if monthly_revenue is not None:
                account.monthly_revenue = monthly_revenue
            
            # 重新计算健康分数和风险等级
            account.health_score = self._calculate_health_score(account)
            account.risk_level = self._assess_risk_level(account)
            account.updated_at = datetime.now()
            
            logger.info(f"[OK] 更新账号 {account_id} 统计信息成功")
            return True
            
        except Exception as e:
            logger.error(f"[FAIL] 更新账号统计信息失败: {e}")
            return False

    def export_accounts_summary(self) -> pd.DataFrame:
        """导出账号汇总表"""
        try:
            data = []
            for account in self.accounts.values():
                data.append({
                    '账号ID': account.account_id,
                    '平台': account.platform,
                    '账号名称': account.account_name,
                    '状态': account.status,
                    '地区': account.region,
                    '健康分数': f"{account.health_score:.2f}",
                    '风险等级': account.risk_level,
                    '登录成功率': f"{account.login_success_rate:.2%}",
                    '总订单数': account.total_orders,
                    '月收入': f"${account.monthly_revenue:.2f}",
                    '最后登录': account.last_login.strftime('%Y-%m-%d %H:%M') if account.last_login else '从未登录',
                    '备注': account.notes
                })
            
            df = pd.DataFrame(data)
            logger.info(f"[OK] 导出账号汇总表成功，共 {len(data)} 个账号")
            return df
            
        except Exception as e:
            logger.error(f"[FAIL] 导出账号汇总表失败: {e}")
            return pd.DataFrame()

    def get_dashboard_data(self) -> Dict[str, Any]:
        """获取仪表板数据"""
        try:
            all_accounts = self.get_all_accounts()
            active_accounts = self.get_active_accounts()
            
            # 基础统计
            total_accounts = len(all_accounts)
            active_count = len(active_accounts)
            
            # 平台分布
            platform_distribution = {}
            for account in all_accounts:
                platform = account.platform
                if platform not in platform_distribution:
                    platform_distribution[platform] = {'total': 0, 'active': 0}
                platform_distribution[platform]['total'] += 1
                if account.status == 'active':
                    platform_distribution[platform]['active'] += 1
            
            # 健康分数分布
            health_scores = [acc.health_score for acc in all_accounts]
            avg_health_score = sum(health_scores) / len(health_scores) if health_scores else 0
            
            # 风险等级分布
            risk_distribution = {'low': 0, 'medium': 0, 'high': 0}
            for account in all_accounts:
                risk_distribution[account.risk_level] += 1
            
            # 登录统计
            login_stats = {
                'never_logged_in': len([acc for acc in all_accounts if acc.last_login is None]),
                'logged_in_today': len([acc for acc in all_accounts 
                                      if acc.last_login and (datetime.now() - acc.last_login).days == 0]),
                'logged_in_week': len([acc for acc in all_accounts 
                                     if acc.last_login and (datetime.now() - acc.last_login).days <= 7])
            }
            
            return {
                'total_accounts': total_accounts,
                'active_accounts': active_count,
                'platform_distribution': platform_distribution,
                'avg_health_score': avg_health_score,
                'risk_distribution': risk_distribution,
                'login_stats': login_stats,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"[FAIL] 获取仪表板数据失败: {e}")
            return {}

# 全局实例
platform_accounts_manager = PlatformAccountsManager() 