"""
账号管理处理器

处理账号管理的具体业务逻辑。
"""

from pathlib import Path
from typing import List, Dict, Any
from modules.core.logger import get_logger
from modules.core.exceptions import DataProcessingError
import json

logger = get_logger(__name__)


class AccountHandler:
    """账号处理器"""
    
    def __init__(self):
        """初始化账号处理器 - 无副作用版本"""
        self.config_file = Path("local_accounts.json")
        self.backup_dir = Path("temp/backups")
        self._initialized = False

        logger.debug("账号处理器初始化完成")

    def _ensure_initialized(self):
        """确保处理器已初始化（惰性初始化）"""
        if not self._initialized:
            # 创建必要的目录
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            self._initialized = True
            logger.debug("账号处理器惰性初始化完成")

    def health_check(self) -> bool:
        """处理器健康检查"""
        try:
            self._ensure_initialized()

            # 检查配置文件目录权限
            if not self.config_file.parent.exists():
                return False

            # 检查备份目录
            if not self.backup_dir.exists():
                return False

            return True
        except Exception as e:
            logger.error(f"账号处理器健康检查失败: {e}")
            return False
    
    def check_config_files(self) -> bool:
        """检查配置文件"""
        try:
            if self.config_file.exists():
                # 尝试读取配置文件验证格式
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    json.load(f)
                return True
            else:
                logger.warning(f"配置文件不存在: {self.config_file}")
                return True  # 文件不存在不算错误
        except Exception as e:
            logger.error(f"配置文件检查失败: {e}")
            return False
    
    def get_all_accounts(self) -> List[Dict[str, Any]]:
        """获取所有账号"""
        try:
            self._ensure_initialized()

            if not self.config_file.exists():
                logger.info("配置文件不存在，返回空列表")
                return []
            
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            accounts = config.get('accounts', [])
            logger.info(f"获取到 {len(accounts)} 个账号")
            return accounts
        
        except Exception as e:
            logger.error(f"获取账号列表失败: {e}")
            raise DataProcessingError(f"获取账号列表失败: {e}")
    
    def add_account(self, account_data: Dict[str, Any]) -> bool:
        """添加账号"""
        try:
            # 备份现有配置
            self._backup_config()
            
            # 读取现有配置
            config = self._load_config()
            
            # 检查账号是否已存在
            existing_accounts = config.get('accounts', [])
            for existing in existing_accounts:
                if (existing.get('platform') == account_data.get('platform') and 
                    existing.get('username') == account_data.get('username')):
                    logger.warning(f"账号已存在: {account_data['platform']} - {account_data['username']}")
                    return False
            
            # 添加新账号
            existing_accounts.append(account_data)
            config['accounts'] = existing_accounts
            
            # 保存配置
            self._save_config(config)
            
            logger.info(f"添加账号成功: {account_data['platform']} - {account_data['username']}")
            return True
        
        except Exception as e:
            logger.error(f"添加账号失败: {e}")
            return False
    
    def verify_all_accounts(self) -> Dict[str, Dict[str, Any]]:
        """验证所有账号状态"""
        try:
            accounts = self.get_all_accounts()
            results = {}
            
            for account in accounts:
                platform = account.get('platform', 'unknown')
                username = account.get('username', 'unknown')
                
                # 这里应该实现真实的账号验证逻辑
                # 目前返回模拟结果
                results[f"{platform}-{username}"] = {
                    "success": True,
                    "message": "验证通过"
                }
            
            logger.info(f"验证了 {len(results)} 个账号")
            return results
        
        except Exception as e:
            logger.error(f"验证账号失败: {e}")
            return {}
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取账号统计信息"""
        try:
            accounts = self.get_all_accounts()
            
            stats = {
                "total": len(accounts),
                "active": 0,
                "error": 0,
                "pending": 0,
                "platforms": {}
            }
            
            for account in accounts:
                status = account.get('status', 'unknown')
                platform = account.get('platform', 'unknown')
                
                # 统计状态
                if status == 'active':
                    stats['active'] += 1
                elif status == 'error':
                    stats['error'] += 1
                elif status == 'pending':
                    stats['pending'] += 1
                
                # 统计平台
                if platform in stats['platforms']:
                    stats['platforms'][platform] += 1
                else:
                    stats['platforms'][platform] = 1
            
            logger.info(f"生成账号统计: 总数 {stats['total']}")
            return stats
        
        except Exception as e:
            logger.error(f"获取统计失败: {e}")
            return {
                "total": 0,
                "active": 0,
                "error": 0,
                "pending": 0,
                "platforms": {}
            }
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            return {"accounts": []}
    
    def _save_config(self, config: Dict[str, Any]):
        """保存配置文件"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    
    def _backup_config(self):
        """备份配置文件"""
        if self.config_file.exists():
            import time
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            backup_file = self.backup_dir / f"local_accounts_{timestamp}.json"
            
            import shutil
            shutil.copy2(self.config_file, backup_file)
            logger.debug(f"配置文件已备份: {backup_file}") 