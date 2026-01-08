"""
采集器健康检查集成模块
====================

为所有平台采集器提供统一的账号健康检查和异常处理机制

功能特性：
- [SEARCH] 统一的健康检查接口
- [ALERT] 自动异常账号处理
- [DATA] 健康状态统计和报告
- [RETRY] 多平台支持（Shopee、Amazon、妙手ERP等）
- [SAVE] 健康状态持久化存储

版本：v1.0.0
作者：跨境电商ERP系统
更新：2025-08-29
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from playwright.sync_api import Page

from modules.utils.account_health_checker import AccountHealthChecker, AccountStatus
from modules.utils.logger import get_logger

logger = get_logger(__name__)


class CollectorHealthIntegration:
    """采集器健康检查集成器"""
    
    def __init__(self, platform: str, data_dir: str = "data"):
        """
        初始化健康检查集成器
        
        Args:
            platform: 平台名称
            data_dir: 数据存储目录
        """
        self.platform = platform.lower()
        self.data_dir = Path(data_dir)
        self.health_checker = AccountHealthChecker(platform)
        self.health_log_file = self.data_dir / "account_health_logs.json"
        self.disabled_accounts_file = self.data_dir / "disabled_accounts.json"
        
        # 确保数据目录存在
        self.data_dir.mkdir(exist_ok=True)
        
        # 加载已禁用账号列表
        self.disabled_accounts = self._load_disabled_accounts()
        
    def check_and_handle_account(self, page: Page, account: Dict, operation_name: str = "数据采集") -> bool:
        """
        检查账号健康状态并处理异常
        
        Args:
            page: Playwright页面对象
            account: 账号配置信息
            operation_name: 操作名称（用于日志记录）
            
        Returns:
            bool: 是否可以继续操作
        """
        account_id = account.get('username', 'Unknown')
        
        try:
            # 1. 检查账号是否已被标记为禁用
            if self._is_account_disabled(account_id):
                logger.warning(f"[NO] 账号 {account_id} 已被标记为禁用，跳过操作")
                return False
            
            # 2. 执行健康检查
            logger.info(f"[SEARCH] 开始健康检查 - 账号: {account_id}, 操作: {operation_name}")
            status, message, extra_data = self.health_checker.check_account_health(page, account)
            
            # 3. 记录健康检查日志
            self._log_health_check(account_id, status, message, extra_data, operation_name)
            
            # 4. 处理检查结果
            should_continue = self.health_checker.handle_unhealthy_account(status, message, account, page)
            
            # 5. 如果账号异常，更新禁用列表
            if not should_continue and status in [
                AccountStatus.ACCOUNT_SUSPENDED, 
                AccountStatus.ACCOUNT_LOCKED,
                AccountStatus.PERMISSION_DENIED
            ]:
                self._add_to_disabled_accounts(account_id, status, message)
            
            return should_continue
            
        except Exception as e:
            logger.error(f"[FAIL] 健康检查过程异常 - 账号: {account_id}, 错误: {e}")
            return False
    
    def batch_check_accounts(self, accounts: List[Dict], operation_name: str = "批量检查") -> Dict[str, bool]:
        """
        批量检查多个账号的健康状态
        
        Args:
            accounts: 账号列表
            operation_name: 操作名称
            
        Returns:
            Dict[str, bool]: 账号ID -> 是否健康的映射
        """
        results = {}
        healthy_count = 0
        total_count = len(accounts)
        
        logger.info(f"[SEARCH] 开始批量健康检查 - 总计 {total_count} 个账号")
        
        for i, account in enumerate(accounts, 1):
            account_id = account.get('username', f'Account_{i}')
            
            try:
                # 这里需要实际的页面对象，在实际使用中需要传入
                # 暂时返回基于禁用列表的检查结果
                is_healthy = not self._is_account_disabled(account_id)
                results[account_id] = is_healthy
                
                if is_healthy:
                    healthy_count += 1
                    logger.info(f"[OK] [{i}/{total_count}] {account_id} - 健康")
                else:
                    logger.warning(f"[FAIL] [{i}/{total_count}] {account_id} - 已禁用")
                    
            except Exception as e:
                logger.error(f"[FAIL] [{i}/{total_count}] {account_id} - 检查失败: {e}")
                results[account_id] = False
        
        logger.info(f"[DATA] 批量检查完成 - 健康: {healthy_count}/{total_count}")
        return results
    
    def get_health_statistics(self, days: int = 7) -> Dict[str, Any]:
        """
        获取健康状态统计信息
        
        Args:
            days: 统计天数
            
        Returns:
            Dict: 统计信息
        """
        try:
            logs = self._load_health_logs()
            cutoff_time = time.time() - (days * 24 * 60 * 60)
            
            # 过滤指定天数内的日志
            recent_logs = [log for log in logs if log.get('timestamp', 0) > cutoff_time]
            
            # 统计各种状态
            status_counts = {}
            account_status = {}
            
            for log in recent_logs:
                status = log.get('status', 'unknown')
                account_id = log.get('account_id', 'unknown')
                
                # 统计状态分布
                status_counts[status] = status_counts.get(status, 0) + 1
                
                # 记录每个账号的最新状态
                if account_id not in account_status or log.get('timestamp', 0) > account_status[account_id].get('timestamp', 0):
                    account_status[account_id] = log
            
            # 计算健康率
            total_checks = len(recent_logs)
            healthy_checks = status_counts.get('healthy', 0)
            health_rate = (healthy_checks / total_checks * 100) if total_checks > 0 else 0
            
            return {
                'period_days': days,
                'total_checks': total_checks,
                'healthy_checks': healthy_checks,
                'health_rate': round(health_rate, 2),
                'status_distribution': status_counts,
                'unique_accounts': len(account_status),
                'disabled_accounts_count': len(self.disabled_accounts),
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"[FAIL] 获取健康统计失败: {e}")
            return {}
    
    def _is_account_disabled(self, account_id: str) -> bool:
        """检查账号是否已被禁用"""
        return account_id in self.disabled_accounts
    
    def _add_to_disabled_accounts(self, account_id: str, status: AccountStatus, reason: str):
        """添加账号到禁用列表"""
        try:
            self.disabled_accounts[account_id] = {
                'status': status.value,
                'reason': reason,
                'disabled_at': datetime.now().isoformat(),
                'platform': self.platform
            }
            
            self._save_disabled_accounts()
            logger.warning(f"[NO] 账号 {account_id} 已添加到禁用列表")
            
        except Exception as e:
            logger.error(f"[FAIL] 添加禁用账号失败: {e}")
    
    def _load_disabled_accounts(self) -> Dict[str, Any]:
        """加载已禁用账号列表"""
        try:
            if self.disabled_accounts_file.exists():
                with open(self.disabled_accounts_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"[FAIL] 加载禁用账号列表失败: {e}")
            return {}
    
    def _save_disabled_accounts(self):
        """保存禁用账号列表"""
        try:
            with open(self.disabled_accounts_file, 'w', encoding='utf-8') as f:
                json.dump(self.disabled_accounts, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[FAIL] 保存禁用账号列表失败: {e}")
    
    def _log_health_check(self, account_id: str, status: AccountStatus, message: str, extra_data: Dict, operation: str):
        """记录健康检查日志"""
        try:
            log_entry = {
                'timestamp': time.time(),
                'datetime': datetime.now().isoformat(),
                'account_id': account_id,
                'platform': self.platform,
                'status': status.value,
                'message': message,
                'operation': operation,
                'extra_data': extra_data
            }
            
            # 加载现有日志
            logs = self._load_health_logs()
            logs.append(log_entry)
            
            # 保持最近1000条日志
            if len(logs) > 1000:
                logs = logs[-1000:]
            
            # 保存日志
            with open(self.health_log_file, 'w', encoding='utf-8') as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"[FAIL] 记录健康检查日志失败: {e}")
    
    def _load_health_logs(self) -> List[Dict]:
        """加载健康检查日志"""
        try:
            if self.health_log_file.exists():
                with open(self.health_log_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return []
        except Exception as e:
            logger.error(f"[FAIL] 加载健康检查日志失败: {e}")
            return []
    
    def enable_account(self, account_id: str) -> bool:
        """重新启用账号"""
        try:
            if account_id in self.disabled_accounts:
                del self.disabled_accounts[account_id]
                self._save_disabled_accounts()
                logger.info(f"[OK] 账号 {account_id} 已重新启用")
                return True
            else:
                logger.warning(f"[WARN] 账号 {account_id} 不在禁用列表中")
                return False
        except Exception as e:
            logger.error(f"[FAIL] 启用账号失败: {e}")
            return False
    
    def get_disabled_accounts(self) -> Dict[str, Any]:
        """获取所有禁用账号信息"""
        return self.disabled_accounts.copy()


# 便捷函数
def create_health_integration(platform: str) -> CollectorHealthIntegration:
    """
    创建健康检查集成器实例
    
    Args:
        platform: 平台名称
        
    Returns:
        CollectorHealthIntegration: 集成器实例
    """
    return CollectorHealthIntegration(platform)


def quick_health_check(page: Page, account: Dict, platform: str, operation: str = "数据采集") -> bool:
    """
    快速健康检查（便捷函数）
    
    Args:
        page: 页面对象
        account: 账号配置
        platform: 平台名称
        operation: 操作名称
        
    Returns:
        bool: 是否可以继续操作
    """
    integration = create_health_integration(platform)
    return integration.check_and_handle_account(page, account, operation)
