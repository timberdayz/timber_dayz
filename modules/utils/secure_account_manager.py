#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
安全账号管理器
读取本地账号配置文件并加密存储，确保账号信息安全
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from cryptography.fernet import Fernet
import base64
from modules.utils.logger import Logger

logger = Logger(__name__)


class SecureAccountManager:
    """安全账号管理器"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化安全账号管理器
        
        Args:
            config_path: 配置文件路径，默认为项目根目录下的secure_accounts.enc
        """
        self.config_path = config_path or "secure_accounts.enc"
        self.key_path = "secure_account_key.key"
        self.logger = Logger(__name__)
        
    def _get_encryption_key(self) -> bytes:
        """获取或生成加密密钥"""
        if os.path.exists(self.key_path):
            with open(self.key_path, 'rb') as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_path, 'wb') as f:
                f.write(key)
            return key
    
    def _encrypt_data(self, data: str) -> bytes:
        """加密数据"""
        key = self._get_encryption_key()
        f = Fernet(key)
        return f.encrypt(data.encode())
    
    def _decrypt_data(self, encrypted_data: bytes) -> str:
        """解密数据"""
        key = self._get_encryption_key()
        f = Fernet(key)
        return f.decrypt(encrypted_data).decode()
    
    def load_local_accounts(self) -> Dict[str, Any]:
        """从本地配置文件加载账号"""
        try:
            # 尝试导入本地账号配置
            from local_accounts import get_local_accounts, get_local_settings
            
            local_accounts = get_local_accounts()
            local_settings = get_local_settings()
            
            # 转换为标准格式
            accounts_list = []
            for platform_group, accounts in local_accounts.items():
                for account in accounts:
                    # 转换格式
                    standard_account = {
                        "platform": account.get('platform', platform_group),
                        "username": account.get('username', ''),
                        "password": account.get('password', ''),
                        "region": account.get('region', 'default'),
                        "notes": account.get('notes', ''),
                        "status": "active" if account.get('enabled', True) else "inactive",
                        "account_id": account.get('account_id', ''),
                        "store_name": account.get('store_name', ''),
                        "currency": account.get('currency', 'CNY'),
                        "timezone": account.get('timezone', 'Asia/Shanghai'),
                        "proxy_required": account.get('proxy_required', False),
                        "created_at": self._get_timestamp()
                    }
                    accounts_list.append(standard_account)
            
            # 创建配置
            config = {
                "accounts": accounts_list,
                "settings": local_settings
            }
            
            self.logger.info(f"成功从本地配置加载 {len(accounts_list)} 个账号")
            return config
            
        except ImportError:
            self.logger.warning("本地账号配置文件不存在，使用默认配置")
            return self._create_default_config()
        except Exception as e:
            self.logger.error(f"加载本地账号配置失败: {e}")
            return self._create_default_config()
    
    def _create_default_config(self) -> Dict[str, Any]:
        """创建默认配置"""
        return {
            "accounts": [],
            "settings": {
                "auto_sync": True,
                "encryption_enabled": True,
                "backup_enabled": True,
                "source": "default"
            }
        }
    
    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def load_accounts(self) -> Dict[str, Any]:
        """加载账号配置（从本地配置文件）"""
        try:
            # 优先尝试加载加密文件
            if os.path.exists(self.config_path):
                with open(self.config_path, 'rb') as f:
                    encrypted_data = f.read()
                decrypted_data = self._decrypt_data(encrypted_data)
                accounts = json.loads(decrypted_data)
                self.logger.info(f"成功加载加密账号配置: {len(accounts.get('accounts', []))} 个账号")
                return accounts
            
            # 如果没有加密文件，从本地配置文件加载
            else:
                return self.load_local_accounts()
                
        except Exception as e:
            self.logger.error(f"加载账号配置失败: {e}")
            return self._create_default_config()
    
    def save_accounts(self, accounts: Dict[str, Any], encrypt: bool = True) -> bool:
        """保存账号配置"""
        try:
            if encrypt:
                # 加密保存
                data_str = json.dumps(accounts, ensure_ascii=False, indent=2)
                encrypted_data = self._encrypt_data(data_str)
                with open(self.config_path, 'wb') as f:
                    f.write(encrypted_data)
                self.logger.info(f"成功保存加密账号配置: {len(accounts.get('accounts', []))} 个账号")
            else:
                # 普通保存
                with open(self.config_path.replace('.enc', '.json'), 'w', encoding='utf-8') as f:
                    json.dump(accounts, f, ensure_ascii=False, indent=2)
                self.logger.info(f"成功保存账号配置: {len(accounts.get('accounts', []))} 个账号")
            
            return True
            
        except Exception as e:
            self.logger.error(f"保存账号配置失败: {e}")
            return False
    
    def sync_from_local(self) -> bool:
        """从本地配置文件同步账号"""
        try:
            local_config = self.load_local_accounts()
            success = self.save_accounts(local_config, encrypt=True)
            
            if success:
                self.logger.info("成功从本地配置文件同步账号")
            else:
                self.logger.error("从本地配置文件同步账号失败")
            
            return success
            
        except Exception as e:
            self.logger.error(f"同步本地账号配置失败: {e}")
            return False
    
    def get_all_accounts(self) -> List[Dict[str, Any]]:
        """获取所有账号"""
        accounts = self.load_accounts()
        return accounts.get('accounts', [])
    
    def get_enabled_accounts(self) -> List[Dict[str, Any]]:
        """获取启用的账号"""
        all_accounts = self.get_all_accounts()
        return [acc for acc in all_accounts if acc.get('status') == 'active']
    
    def get_accounts_by_platform(self, platform: str) -> List[Dict[str, Any]]:
        """根据平台获取账号"""
        all_accounts = self.get_all_accounts()
        return [acc for acc in all_accounts if acc.get('platform') == platform]
    
    def add_account(self, platform: str, username: str, password: str, 
                   region: str = "default", notes: str = "") -> bool:
        """添加账号"""
        try:
            accounts = self.load_accounts()
            
            new_account = {
                "platform": platform,
                "username": username,
                "password": password,
                "region": region,
                "notes": notes,
                "status": "active",
                "created_at": self._get_timestamp()
            }
            
            accounts["accounts"].append(new_account)
            
            success = self.save_accounts(accounts)
            if success:
                self.logger.info(f"成功添加账号: {platform} - {username}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"添加账号失败: {e}")
            return False
    
    def update_account(self, platform: str, username: str, 
                      updates: Dict[str, Any]) -> bool:
        """更新账号信息"""
        try:
            accounts = self.load_accounts()
            
            # 查找并更新账号
            for account in accounts["accounts"]:
                if account["platform"] == platform and account["username"] == username:
                    account.update(updates)
                    account["updated_at"] = self._get_timestamp()
                    
                    success = self.save_accounts(accounts)
                    if success:
                        self.logger.info(f"成功更新账号: {platform} - {username}")
                    return success
            
            self.logger.warning(f"未找到要更新的账号: {platform} - {username}")
            return False
            
        except Exception as e:
            self.logger.error(f"更新账号失败: {e}")
            return False
    
    def remove_account(self, platform: str, username: str) -> bool:
        """删除账号"""
        try:
            accounts = self.load_accounts()
            
            # 查找并删除账号
            original_count = len(accounts["accounts"])
            accounts["accounts"] = [
                acc for acc in accounts["accounts"]
                if not (acc["platform"] == platform and acc["username"] == username)
            ]
            
            if len(accounts["accounts"]) < original_count:
                success = self.save_accounts(accounts)
                if success:
                    self.logger.info(f"成功删除账号: {platform} - {username}")
                return success
            else:
                self.logger.warning(f"未找到要删除的账号: {platform} - {username}")
                return False
                
        except Exception as e:
            self.logger.error(f"删除账号失败: {e}")
            return False
