#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
增强版安全账号管理器
提供多层加密保护和脱敏处理功能
"""

import os
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import getpass
from datetime import datetime
from loguru import logger


class SecureAccountManagerEnhanced:
    """增强版安全账号管理器"""
    
    def __init__(self):
        self.config_dir = Path("config")
        self.config_dir.mkdir(exist_ok=True)
        
        # 加密存储文件
        self.encrypted_file = self.config_dir / "secure_accounts.enc"
        self.key_file = self.config_dir / "account_key.key"
        self.hash_file = self.config_dir / "account_hash.dat"
        
        # 运行时密钥（内存中）
        self._runtime_key = None
        self._cached_accounts = None
        
        # 敏感字段列表
        self.sensitive_fields = [
            "password", "Email password", "Email License", 
            "phone", "username", "E-mail"
        ]
    
    def _generate_key_from_password(self, password: str, salt: bytes = None) -> bytes:
        """从密码生成加密密钥"""
        if salt is None:
            salt = os.urandom(16)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key, salt
    
    def _get_or_create_master_key(self) -> bytes:
        """获取或创建主密钥"""
        if self._runtime_key:
            return self._runtime_key
        
        if self.key_file.exists():
            try:
                # 尝试从文件加载密钥
                with open(self.key_file, 'rb') as f:
                    encrypted_key_data = f.read()
                
                # 提示用户输入密码解密密钥
                password = getpass.getpass("请输入主密码解锁账号信息: ")
                
                # 解密密钥
                salt = encrypted_key_data[:16]
                encrypted_key = encrypted_key_data[16:]
                
                key, _ = self._generate_key_from_password(password, salt)
                fernet = Fernet(key)
                
                master_key = fernet.decrypt(encrypted_key)
                self._runtime_key = master_key
                
                logger.success("✅ 主密钥解锁成功")
                return master_key
                
            except Exception as e:
                logger.error(f"密钥解锁失败: {e}")
                return None
        else:
            # 创建新的主密钥
            logger.info("首次使用，创建新的主密钥...")
            password = getpass.getpass("请设置主密码（用于保护账号信息）: ")
            confirm_password = getpass.getpass("请确认主密码: ")
            
            if password != confirm_password:
                logger.error("密码不匹配")
                return None
            
            # 生成主密钥
            master_key = Fernet.generate_key()
            
            # 用密码加密主密钥
            key, salt = self._generate_key_from_password(password)
            fernet = Fernet(key)
            encrypted_master_key = fernet.encrypt(master_key)
            
            # 保存加密的主密钥
            with open(self.key_file, 'wb') as f:
                f.write(salt + encrypted_master_key)
            
            self._runtime_key = master_key
            logger.success("✅ 主密钥创建成功")
            return master_key
    
    def _encrypt_accounts(self, accounts_data: Dict) -> bool:
        """加密账号数据"""
        try:
            master_key = self._get_or_create_master_key()
            if not master_key:
                return False
            
            fernet = Fernet(master_key)
            
            # 序列化并加密数据
            json_data = json.dumps(accounts_data, ensure_ascii=False, indent=2)
            encrypted_data = fernet.encrypt(json_data.encode('utf-8'))
            
            # 保存到文件
            with open(self.encrypted_file, 'wb') as f:
                f.write(encrypted_data)
            
            # 生成数据哈希用于完整性验证
            data_hash = hashlib.sha256(json_data.encode('utf-8')).hexdigest()
            with open(self.hash_file, 'w') as f:
                f.write(data_hash)
            
            logger.success("✅ 账号数据加密保存成功")
            return True
            
        except Exception as e:
            logger.error(f"账号数据加密失败: {e}")
            return False
    
    def _decrypt_accounts(self) -> Optional[Dict]:
        """解密账号数据"""
        try:
            if not self.encrypted_file.exists():
                return None
            
            master_key = self._get_or_create_master_key()
            if not master_key:
                return None
            
            fernet = Fernet(master_key)
            
            # 读取并解密数据
            with open(self.encrypted_file, 'rb') as f:
                encrypted_data = f.read()
            
            decrypted_data = fernet.decrypt(encrypted_data)
            json_data = decrypted_data.decode('utf-8')
            
            # 验证数据完整性
            if self.hash_file.exists():
                with open(self.hash_file, 'r') as f:
                    stored_hash = f.read().strip()
                
                current_hash = hashlib.sha256(json_data.encode('utf-8')).hexdigest()
                if stored_hash != current_hash:
                    logger.warning("⚠️  数据完整性验证失败")
            
            accounts_data = json.loads(json_data)
            logger.success("✅ 账号数据解密成功")
            return accounts_data
            
        except Exception as e:
            logger.error(f"账号数据解密失败: {e}")
            return None
    
    def import_from_local_accounts(self) -> bool:
        """从local_accounts.py导入账号信息并加密存储"""
        try:
            # 尝试导入local_accounts.py
            import importlib.util
            import sys
            
            local_accounts_path = Path("local_accounts.py")
            if not local_accounts_path.exists():
                logger.error("local_accounts.py文件不存在")
                return False
            
            spec = importlib.util.spec_from_file_location("local_accounts", str(local_accounts_path))
            local_accounts = importlib.util.module_from_spec(spec)
            sys.modules["local_accounts"] = local_accounts
            spec.loader.exec_module(local_accounts)
            
            local_data = getattr(local_accounts, "LOCAL_ACCOUNTS", {})
            
            # 转换为标准格式
            all_accounts = []
            for group, accounts_list in local_data.items():
                for account in accounts_list:
                    account["source_group"] = group
                    all_accounts.append(account)
            
            accounts_data = {
                "version": "2.0",
                "encryption": "enhanced",
                "accounts": all_accounts,
                "metadata": {
                    "imported_from": "local_accounts.py",
                    "import_time": str(datetime.now()),
                    "total_accounts": len(all_accounts)
                }
            }
            
            # 加密存储
            if self._encrypt_accounts(accounts_data):
                logger.success(f"✅ 成功导入并加密 {len(all_accounts)} 个账号")
                
                # 清空运行时缓存，强制重新加载
                self._cached_accounts = None
                
                return True
            else:
                logger.error("账号数据加密失败")
                return False
                
        except Exception as e:
            logger.error(f"导入账号失败: {e}")
            return False
    
    def get_all_accounts(self, decrypt_sensitive: bool = True) -> List[Dict]:
        """获取所有账号信息"""
        try:
            if self._cached_accounts is None:
                accounts_data = self._decrypt_accounts()
                if not accounts_data:
                    return []
                self._cached_accounts = accounts_data.get("accounts", [])
            
            accounts = self._cached_accounts.copy()
            
            if not decrypt_sensitive:
                # 脱敏处理
                accounts = self._mask_sensitive_data(accounts)
            
            return accounts
            
        except Exception as e:
            logger.error(f"获取账号列表失败: {e}")
            return []
    
    def get_accounts_by_platform(self, platform: str, decrypt_sensitive: bool = True) -> List[Dict]:
        """根据平台获取账号"""
        all_accounts = self.get_all_accounts(decrypt_sensitive)
        return [acc for acc in all_accounts if acc.get("platform", "").lower() == platform.lower()]
    
    def get_enabled_accounts(self, decrypt_sensitive: bool = True) -> List[Dict]:
        """获取启用的账号"""
        all_accounts = self.get_all_accounts(decrypt_sensitive)
        return [acc for acc in all_accounts if acc.get("enabled", True)]
    
    def _mask_sensitive_data(self, accounts: List[Dict]) -> List[Dict]:
        """脱敏处理敏感数据"""
        masked_accounts = []
        
        for account in accounts:
            masked_account = account.copy()
            
            for field in self.sensitive_fields:
                if field in masked_account:
                    value = str(masked_account[field])
                    if value and len(value) > 0:
                        if field == "password" or "password" in field.lower():
                            # 密码完全隐藏
                            masked_account[field] = "******"
                        elif field == "phone":
                            # 手机号脱敏：138****5678
                            if len(value) >= 8:
                                masked_account[field] = value[:3] + "****" + value[-4:]
                            else:
                                masked_account[field] = "****"
                        elif "@" in value:
                            # 邮箱脱敏：tes***@example.com
                            parts = value.split("@")
                            if len(parts) == 2:
                                username = parts[0]
                                domain = parts[1]
                                if len(username) > 3:
                                    masked_username = username[:3] + "***"
                                else:
                                    masked_username = "***"
                                masked_account[field] = f"{masked_username}@{domain}"
                            else:
                                masked_account[field] = "***@***"
                        else:
                            # 其他敏感信息部分隐藏
                            if len(value) > 6:
                                masked_account[field] = value[:2] + "***" + value[-2:]
                            else:
                                masked_account[field] = "***"
            
            masked_accounts.append(masked_account)
        
        return masked_accounts
    
    def add_account(self, account_data: Dict) -> bool:
        """添加新账号"""
        try:
            accounts_data = self._decrypt_accounts() or {"version": "2.0", "accounts": []}
            accounts_data["accounts"].append(account_data)
            
            if self._encrypt_accounts(accounts_data):
                self._cached_accounts = None  # 清空缓存
                logger.success("✅ 账号添加成功")
                return True
            else:
                logger.error("账号保存失败")
                return False
                
        except Exception as e:
            logger.error(f"添加账号失败: {e}")
            return False
    
    def update_account(self, account_id: str, updated_data: Dict) -> bool:
        """更新账号信息"""
        try:
            accounts_data = self._decrypt_accounts()
            if not accounts_data:
                return False
            
            accounts = accounts_data["accounts"]
            for i, account in enumerate(accounts):
                if account.get("account_id") == account_id:
                    accounts[i].update(updated_data)
                    break
            else:
                logger.error(f"未找到账号: {account_id}")
                return False
            
            if self._encrypt_accounts(accounts_data):
                self._cached_accounts = None  # 清空缓存
                logger.success("✅ 账号更新成功")
                return True
            else:
                logger.error("账号保存失败")
                return False
                
        except Exception as e:
            logger.error(f"更新账号失败: {e}")
            return False
    
    def delete_account(self, account_id: str) -> bool:
        """删除账号"""
        try:
            accounts_data = self._decrypt_accounts()
            if not accounts_data:
                return False
            
            accounts = accounts_data["accounts"]
            original_count = len(accounts)
            accounts_data["accounts"] = [acc for acc in accounts if acc.get("account_id") != account_id]
            
            if len(accounts_data["accounts"]) == original_count:
                logger.error(f"未找到账号: {account_id}")
                return False
            
            if self._encrypt_accounts(accounts_data):
                self._cached_accounts = None  # 清空缓存
                logger.success("✅ 账号删除成功")
                return True
            else:
                logger.error("账号保存失败")
                return False
                
        except Exception as e:
            logger.error(f"删除账号失败: {e}")
            return False
    
    def backup_accounts(self, backup_path: Optional[str] = None) -> str:
        """备份账号数据"""
        try:
            from datetime import datetime
            
            if backup_path is None:
                backup_dir = Path("backups/accounts")
                backup_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = backup_dir / f"accounts_backup_{timestamp}.enc"
            
            backup_path = Path(backup_path)
            
            # 复制加密文件
            if self.encrypted_file.exists():
                import shutil
                shutil.copy2(self.encrypted_file, backup_path)
                
                # 也备份哈希文件
                hash_backup = backup_path.with_suffix('.hash')
                if self.hash_file.exists():
                    shutil.copy2(self.hash_file, hash_backup)
                
                logger.success(f"✅ 账号备份成功: {backup_path}")
                return str(backup_path)
            else:
                logger.error("没有找到加密账号文件")
                return ""
                
        except Exception as e:
            logger.error(f"账号备份失败: {e}")
            return ""
    
    def restore_accounts(self, backup_path: str) -> bool:
        """从备份恢复账号数据"""
        try:
            backup_path = Path(backup_path)
            if not backup_path.exists():
                logger.error(f"备份文件不存在: {backup_path}")
                return False
            
            # 备份当前数据
            current_backup = self.backup_accounts()
            if current_backup:
                logger.info(f"当前数据已备份到: {current_backup}")
            
            # 恢复数据
            import shutil
            shutil.copy2(backup_path, self.encrypted_file)
            
            # 恢复哈希文件
            hash_backup = backup_path.with_suffix('.hash')
            if hash_backup.exists():
                shutil.copy2(hash_backup, self.hash_file)
            
            # 清空缓存
            self._cached_accounts = None
            
            logger.success("✅ 账号恢复成功")
            return True
            
        except Exception as e:
            logger.error(f"账号恢复失败: {e}")
            return False
    
    def get_security_status(self) -> Dict:
        """获取安全状态"""
        try:
            status = {
                "encrypted_file_exists": self.encrypted_file.exists(),
                "key_file_exists": self.key_file.exists(),
                "hash_file_exists": self.hash_file.exists(),
                "total_accounts": 0,
                "enabled_accounts": 0,
                "encryption_status": "unknown",
                "last_backup": None
            }
            
            if status["encrypted_file_exists"]:
                accounts = self.get_all_accounts(decrypt_sensitive=False)
                status["total_accounts"] = len(accounts)
                status["enabled_accounts"] = len([acc for acc in accounts if acc.get("enabled", True)])
                status["encryption_status"] = "encrypted"
            
            # 检查最近备份
            backup_dir = Path("backups/accounts")
            if backup_dir.exists():
                backup_files = list(backup_dir.glob("accounts_backup_*.enc"))
                if backup_files:
                    latest_backup = max(backup_files, key=lambda x: x.stat().st_mtime)
                    status["last_backup"] = latest_backup.name
            
            return status
            
        except Exception as e:
            logger.error(f"获取安全状态失败: {e}")
            return {}
    
    def clear_runtime_cache(self):
        """清空运行时缓存"""
        self._runtime_key = None
        self._cached_accounts = None
        logger.info("运行时缓存已清空")


# 全局实例
secure_account_manager = SecureAccountManagerEnhanced()

def get_secure_accounts(platform: str = None, enabled_only: bool = True, decrypt_sensitive: bool = True) -> List[Dict]:
    """便捷函数：获取安全账号信息"""
    if platform:
        accounts = secure_account_manager.get_accounts_by_platform(platform, decrypt_sensitive)
    else:
        accounts = secure_account_manager.get_all_accounts(decrypt_sensitive)
    
    if enabled_only:
        accounts = [acc for acc in accounts if acc.get("enabled", True)]
    
    return accounts 