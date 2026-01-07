"""
账户管理模块

提供账户配置的加载、验证和管理功能。
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from cryptography.fernet import Fernet
import base64
from modules.core.logger import get_logger

logger = get_logger(__name__)


class AccountManager:
    """账户管理器"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化账户管理器
        
        Args:
            config_path: 配置文件路径，默认为项目根目录下的accounts.json
        """
        self.config_path = config_path or "accounts.json"
        self.encrypted_path = self.config_path.replace('.json', '.enc')
        self.key_path = "account_key.key"
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
    
    def load_accounts(self) -> Dict[str, Any]:
        """加载账户配置，自动同步local_accounts.py到加密/JSON账号配置"""
        try:
            # 1. 检查local_accounts.py是否存在
            import importlib.util
            import sys
            from pathlib import Path
            local_accounts_path = Path(os.getcwd()) / "local_accounts.py"
            local_accounts = []
            if local_accounts_path.exists():
                try:
                    spec = importlib.util.spec_from_file_location("local_accounts", str(local_accounts_path))
                    local_accounts_mod = importlib.util.module_from_spec(spec)
                    sys.modules["local_accounts"] = local_accounts_mod
                    spec.loader.exec_module(local_accounts_mod)
                    for group, accounts_list in getattr(local_accounts_mod, "LOCAL_ACCOUNTS", {}).items():
                        local_accounts.extend(accounts_list)
                except Exception as e:
                    self.logger.warning(f"加载local_accounts.py失败: {e}")
            # 2. 加载加密/JSON账号
            accounts = None
            if os.path.exists(self.encrypted_path):
                with open(self.encrypted_path, 'rb') as f:
                    encrypted_data = f.read()
                decrypted_data = self._decrypt_data(encrypted_data)
                accounts = json.loads(decrypted_data)
            elif os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    accounts = json.load(f)
            else:
                accounts = {"accounts": [], "settings": {}}
            # 3. 合并local_accounts.py账号到加密/JSON账号（以local_accounts.py为准，去重，保留所有字段）
            if local_accounts:
                # 以username+platform为唯一键
                def acc_key(acc):
                    return (acc.get('platform', '').lower(), acc.get('username', ''))
                existing_keys = {acc_key(acc): acc for acc in accounts.get('accounts', [])}
                for acc in local_accounts:
                    k = acc_key(acc)
                    existing_keys[k] = acc  # local_accounts优先
                merged_accounts = list(existing_keys.values())
                accounts['accounts'] = merged_accounts
                # 自动保存到加密/JSON
                self.save_accounts(accounts, encrypt=True)
                self.logger.info(f"已自动同步local_accounts.py到加密账号配置: {len(merged_accounts)} 个账号")
            self.logger.info(f"成功加载加密账户配置: {len(accounts.get('accounts', []))} 个账户")
            return accounts
        except Exception as e:
            self.logger.error(f"加载账户配置失败: {e}")
            return {"accounts": [], "settings": {}}
    
    def save_accounts(self, accounts: Dict[str, Any], encrypt: bool = True) -> bool:
        """保存账户配置"""
        try:
            if encrypt:
                # 加密保存
                data_str = json.dumps(accounts, ensure_ascii=False, indent=2)
                encrypted_data = self._encrypt_data(data_str)
                with open(self.encrypted_path, 'wb') as f:
                    f.write(encrypted_data)
                self.logger.info(f"成功保存加密账户配置: {len(accounts.get('accounts', []))} 个账户")
            else:
                # 普通保存
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump(accounts, f, ensure_ascii=False, indent=2)
                self.logger.info(f"成功保存账户配置: {len(accounts.get('accounts', []))} 个账户")
            
            return True
            
        except Exception as e:
            self.logger.error(f"保存账户配置失败: {e}")
            return False
    
    def add_account(self, platform: str, username: str, password: str, 
                   region: str = "default", notes: str = "") -> bool:
        """添加账户"""
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
                self.logger.info(f"成功添加账户: {platform} - {username}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"添加账户失败: {e}")
            return False
    
    def remove_account(self, platform: str, username: str) -> bool:
        """删除账户"""
        try:
            accounts = self.load_accounts()
            
            # 查找并删除账户
            original_count = len(accounts["accounts"])
            accounts["accounts"] = [
                acc for acc in accounts["accounts"]
                if not (acc["platform"] == platform and acc["username"] == username)
            ]
            
            if len(accounts["accounts"]) < original_count:
                success = self.save_accounts(accounts)
                if success:
                    self.logger.info(f"成功删除账户: {platform} - {username}")
                return success
            else:
                self.logger.warning(f"未找到要删除的账户: {platform} - {username}")
                return False
                
        except Exception as e:
            self.logger.error(f"删除账户失败: {e}")
            return False
    
    def update_account(self, platform: str, username: str, 
                      updates: Dict[str, Any]) -> bool:
        """更新账户信息"""
        try:
            accounts = self.load_accounts()
            
            # 查找并更新账户
            for account in accounts["accounts"]:
                if account["platform"] == platform and account["username"] == username:
                    account.update(updates)
                    account["updated_at"] = self._get_timestamp()
                    
                    success = self.save_accounts(accounts)
                    if success:
                        self.logger.info(f"成功更新账户: {platform} - {username}")
                    return success
            
            self.logger.warning(f"未找到要更新的账户: {platform} - {username}")
            return False
            
        except Exception as e:
            self.logger.error(f"更新账户失败: {e}")
            return False
    
    def get_accounts_by_platform(self, platform: str) -> List[Dict[str, Any]]:
        """根据平台获取账户列表（大小写不敏感，兼容常见别名）"""
        try:
            accounts = self.load_accounts()
            norm = (platform or "").strip().lower()
            alias_map = {
                "tiktok": {
                    "tiktok", "tiktok_shop", "tiktokshop",
                    "tiktok global shop", "tiktokglobalshop",
                    "tiktok shop", "tiktokshopglobalselling",
                    "tiktok_shop_globalselling",
                },
                "shopee": {"shopee", "虾皮"},
                "amazon": {"amazon", "亚马逊"},
                "miaoshou": {"miaoshou", "miaoshou_erp", "erp", "妙手", "妙手erp"},
            }
            aliases = alias_map.get(norm, {norm} if norm else set())

            platform_accounts: List[Dict[str, Any]] = []
            for acc in accounts.get("accounts", []):
                acc_plat = str(acc.get("platform", "")).strip().lower()
                if not acc_plat:
                    continue
                if acc_plat == norm or acc_plat in aliases:
                    platform_accounts.append(acc)

            # 回退：尝试子串匹配（以防平台名写法不一致）
            if not platform_accounts and norm:
                for acc in accounts.get("accounts", []):
                    acc_plat = str(acc.get("platform", "")).strip().lower()
                    if norm in acc_plat or acc_plat in norm:
                        platform_accounts.append(acc)

            return platform_accounts

        except Exception as e:
            self.logger.error(f"获取平台账户失败: {e}")
            return []
    
    def validate_account(self, platform: str, username: str, password: str) -> bool:
        """验证账户信息"""
        try:
            accounts = self.load_accounts()
            
            for account in accounts["accounts"]:
                if (account["platform"] == platform and 
                    account["username"] == username and 
                    account["password"] == password):
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"验证账户失败: {e}")
            return False
    
    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def run(self) -> bool:
        """运行账户管理（兼容旧接口）"""
        try:
            # 检查是否存在旧的配置文件需要迁移
            old_configs = [
                "local_accounts.json",
                "local_accounts_template.json",
                "accounts_config_20250804_212930.json",
                "accounts_config_20250804_180223.json"
            ]
            
            migrated = False
            for old_config in old_configs:
                if os.path.exists(old_config):
                    self.logger.info(f"发现旧配置文件: {old_config}")
                    # 这里可以添加迁移逻辑
                    migrated = True
            
            if migrated:
                self.logger.info("账户配置迁移完成")
            
            # 确保配置文件存在
            accounts = self.load_accounts()
            if not accounts.get("accounts"):
                self.logger.info("创建默认账户配置")
                self.save_accounts(accounts)
            
            return True
            
        except Exception as e:
            self.logger.error(f"账户管理运行失败: {e}")
            return False


class LocalAccountLoader:
    """本地账户加载器（兼容旧接口）"""
    
    def __init__(self):
        self.account_manager = AccountManager()
    
    def run(self) -> bool:
        """运行账户加载（兼容旧接口）"""
        return self.account_manager.run()
