"""
代理配置管理器

自动读取proxy_config.py配置，为不同账号分配合适的代理
支持代理轮换、健康检查、使用监控等功能
"""

import json
import time
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ProxyInfo:
    """代理信息数据类"""
    ip: str
    port: int
    protocol: str = "http"
    username: str = ""
    password: str = ""
    region: str = ""
    provider: str = ""
    expires_at: Optional[datetime] = None
    created_at: datetime = None
    last_used: Optional[datetime] = None
    success_count: int = 0
    failure_count: int = 0
    is_active: bool = True
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        total = self.success_count + self.failure_count
        if total == 0:
            return 1.0
        return self.success_count / total
    
    @property
    def is_expired(self) -> bool:
        """是否已过期"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at
    
    def to_playwright_format(self) -> Dict[str, str]:
        """转换为Playwright代理格式"""
        proxy_config = {
            "server": f"{self.protocol}://{self.ip}:{self.port}"
        }
        
        if self.username and self.password:
            proxy_config.update({
                "username": self.username,
                "password": self.password
            })
        
        return proxy_config


class ProxyConfigManager:
    """代理配置管理器"""
    
    def __init__(self, config_file: str = "config/proxy_config.py"):
        """
        初始化代理配置管理器
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = Path(config_file)
        self.proxy_cache: Dict[str, List[ProxyInfo]] = {}  # 按地区缓存代理
        self.account_proxy_assignments: Dict[str, ProxyInfo] = {}  # 账号代理分配
        self.proxy_config = {}
        self.account_mapping = {}
        self.strategy_config = {}
        
        # 加载配置
        self._load_config()
        
        logger.info(f"代理配置管理器初始化完成: {self.config_file}")
    
    def _load_config(self) -> None:
        """加载代理配置"""
        try:
            # 动态导入配置模块
            import sys
            import importlib.util
            
            spec = importlib.util.spec_from_file_location("proxy_config", str(self.config_file))
            if spec and spec.loader:
                proxy_config_module = importlib.util.module_from_spec(spec)
                sys.modules["proxy_config"] = proxy_config_module
                spec.loader.exec_module(proxy_config_module)
                
                # 读取配置
                self.proxy_config = getattr(proxy_config_module, "PROXY_CONFIG", {})
                self.account_mapping = getattr(proxy_config_module, "ACCOUNT_PROXY_MAPPING", {})
                self.strategy_config = getattr(proxy_config_module, "PROXY_STRATEGY", {})
                
                logger.info(f"✅ 加载代理配置: {len(self.proxy_config)} 个地区")
                
        except Exception as e:
            logger.error(f"❌ 加载代理配置失败: {e}")
            # 使用默认配置
            self.proxy_config = {}
            self.account_mapping = {}
            self.strategy_config = {"global": {"fallback_to_direct": True}}
    
    def get_account_proxy_region(self, account_info: Dict[str, Any]) -> str:
        """
        获取账号应该使用的代理地区
        
        Args:
            account_info: 账号信息
            
        Returns:
            代理地区代码
        """
        platform = account_info.get("platform", "")
        account_region = account_info.get("region", "CN")
        account_type = account_info.get("account_type", "seller")
        
        platform_mapping = self.account_mapping.get(platform, {})
        
        # 优先检查账号类型映射
        if "account_type_mapping" in platform_mapping:
            type_mapping = platform_mapping["account_type_mapping"].get(account_type, {})
            if account_region in type_mapping:
                return type_mapping[account_region]
            if "default" in type_mapping:
                return type_mapping["default"]
        
        # 检查地区映射
        region_mapping = platform_mapping.get("region_mapping", {})
        if account_region in region_mapping:
            return region_mapping[account_region]
        
        # 返回默认地区
        if "default" in region_mapping:
            return region_mapping["default"]
        
        return "china"  # 最后的默认值
    
    def _get_api_proxy(self, provider_config: Dict[str, Any]) -> Optional[ProxyInfo]:
        """
        从API获取代理
        
        Args:
            provider_config: 代理提供商配置
            
        Returns:
            代理信息或None
        """
        try:
            api_config = provider_config.get("api_config", {})
            api_url = api_config.get("api_url")
            
            if not api_url:
                return None
            
            # 构建请求参数
            params = api_config.get("params", {}).copy()
            
            # 添加认证参数
            if "secret" in api_config:
                params["secret"] = api_config["secret"]
            if "sign" in api_config:
                params["sign"] = api_config["sign"]
            if "api_key" in api_config:
                params["api_key"] = api_config["api_key"]
            
            # 发送请求
            response = requests.get(api_url, params=params, timeout=10)
            response.raise_for_status()
            
            # 解析响应
            if api_config.get("params", {}).get("type") == "json":
                data = response.json()
                
                # 天启IP API响应格式
                if "code" in data and data["code"] == 200 and "data" in data:
                    proxy_data = data["data"][0]  # 取第一个代理
                    
                    # 计算过期时间
                    duration = api_config.get("params", {}).get("time", 60) * 60  # 转换为秒
                    expires_at = datetime.now() + timedelta(seconds=duration)
                    
                    proxy_info = ProxyInfo(
                        ip=proxy_data["ip"],
                        port=int(proxy_data["port"]),
                        protocol="http",
                        region=provider_config.get("region", "unknown"),
                        provider=provider_config.get("provider_name", "unknown"),
                        expires_at=expires_at
                    )
                    
                    logger.info(f"✅ 获取API代理成功: {proxy_info.ip}:{proxy_info.port}")
                    return proxy_info
                
            else:
                # 处理其他格式的响应
                logger.warning(f"⚠️ 未知的API响应格式: {response.text[:200]}")
                
        except Exception as e:
            logger.error(f"❌ 获取API代理失败: {e}")
        
        return None
    
    def _get_static_proxy(self, provider_config: Dict[str, Any]) -> Optional[ProxyInfo]:
        """
        获取静态代理
        
        Args:
            provider_config: 代理提供商配置
            
        Returns:
            代理信息或None
        """
        # 支持新的static_config配置格式
        static_config = provider_config.get("static_config", {})
        static_proxies = static_config.get("proxy_list", [])
        
        # 兼容旧格式
        if not static_proxies:
            static_proxies = provider_config.get("static_proxies", [])
        
        if not static_proxies:
            logger.warning(f"⚠️ 静态代理配置为空: {provider_config.get('provider_name')}")
            return None
        
        # 选择有效的代理
        valid_proxies = []
        for proxy_data in static_proxies:
            # 检查代理是否过期
            valid_until = proxy_data.get("valid_until")
            if valid_until:
                try:
                    from datetime import datetime
                    if isinstance(valid_until, str):
                        valid_until = datetime.fromisoformat(valid_until)
                    if datetime.now() > valid_until:
                        logger.debug(f"跳过过期代理: {proxy_data.get('host')}:{proxy_data.get('port')}")
                        continue
                except Exception as e:
                    logger.warning(f"解析代理过期时间失败: {e}")
            
            valid_proxies.append(proxy_data)
        
        if not valid_proxies:
            logger.warning(f"⚠️ 没有有效的静态代理")
            return None
        
        # 简单轮询选择
        import random
        proxy_data = random.choice(valid_proxies)
        
        # 支持新的配置格式 (host/port) 和旧格式 (ip/port)
        host = proxy_data.get("host") or proxy_data.get("ip")
        port = proxy_data.get("port")
        
        proxy_info = ProxyInfo(
            ip=host,
            port=int(port),
            protocol=proxy_data.get("protocol", "http"),
            username=proxy_data.get("username", ""),
            password=proxy_data.get("password", ""),
            region=provider_config.get("region", "unknown"),
            provider=provider_config.get("provider_name", "unknown")
        )
        
        logger.info(f"✅ 获取静态代理: {proxy_info.ip}:{proxy_info.port}")
        return proxy_info
    
    def get_proxy_for_account(self, account_info: Dict[str, Any]) -> Optional[ProxyInfo]:
        """
        为账号获取合适的代理
        
        Args:
            account_info: 账号信息
            
        Returns:
            代理信息或None
        """
        account_id = account_info.get("account_id", "")
        
        # 检查是否已分配代理且仍有效
        if account_id in self.account_proxy_assignments:
            existing_proxy = self.account_proxy_assignments[account_id]
            if existing_proxy.is_active and not existing_proxy.is_expired:
                logger.info(f"🔄 使用已分配的代理: {account_id} -> {existing_proxy.ip}:{existing_proxy.port}")
                return existing_proxy
            else:
                # 清理过期代理
                del self.account_proxy_assignments[account_id]
        
        # 获取账号应该使用的代理地区
        proxy_region = self.get_account_proxy_region(account_info)
        
        # 获取该地区的代理提供商
        region_config = self.proxy_config.get(proxy_region, {})
        providers = region_config.get("providers", [])
        
        # 按优先级排序，只考虑启用的提供商
        enabled_providers = [p for p in providers if p.get("enabled", False)]
        enabled_providers.sort(key=lambda x: x.get("priority", 999))
        
        # 尝试从提供商获取代理
        for provider in enabled_providers:
            provider_type = provider.get("provider_type", "api")
            
            try:
                proxy_info = None
                
                if provider_type == "api":
                    proxy_info = self._get_api_proxy(provider)
                elif provider_type == "static":
                    proxy_info = self._get_static_proxy(provider)
                
                if proxy_info:
                    # 分配给账号
                    self.account_proxy_assignments[account_id] = proxy_info
                    logger.info(f"🎯 为账号分配代理: {account_id} -> {proxy_info.ip}:{proxy_info.port}")
                    return proxy_info
                    
            except Exception as e:
                logger.error(f"❌ 从提供商获取代理失败 {provider.get('provider_name')}: {e}")
                continue
        
        logger.warning(f"⚠️ 无法为账号获取代理: {account_id} (地区: {proxy_region})")
        return None
    
    def test_proxy(self, proxy_info: ProxyInfo, test_url: str = "https://httpbin.org/ip") -> bool:
        """
        测试代理连接
        
        Args:
            proxy_info: 代理信息
            test_url: 测试URL
            
        Returns:
            测试是否成功
        """
        try:
            proxy_config = {
                "http": f"{proxy_info.protocol}://{proxy_info.ip}:{proxy_info.port}",
                "https": f"{proxy_info.protocol}://{proxy_info.ip}:{proxy_info.port}"
            }
            
            if proxy_info.username and proxy_info.password:
                proxy_config = {
                    "http": f"{proxy_info.protocol}://{proxy_info.username}:{proxy_info.password}@{proxy_info.ip}:{proxy_info.port}",
                    "https": f"{proxy_info.protocol}://{proxy_info.username}:{proxy_info.password}@{proxy_info.ip}:{proxy_info.port}"
                }
            
            response = requests.get(test_url, proxies=proxy_config, timeout=10)
            response.raise_for_status()
            
            proxy_info.success_count += 1
            proxy_info.last_used = datetime.now()
            
            logger.info(f"✅ 代理测试成功: {proxy_info.ip}:{proxy_info.port}")
            return True
            
        except Exception as e:
            proxy_info.failure_count += 1
            logger.error(f"❌ 代理测试失败 {proxy_info.ip}:{proxy_info.port}: {e}")
            return False
    
    def get_proxy_stats(self) -> Dict[str, Any]:
        """获取代理使用统计"""
        stats = {
            "total_assignments": len(self.account_proxy_assignments),
            "active_proxies": len([p for p in self.account_proxy_assignments.values() if p.is_active]),
            "expired_proxies": len([p for p in self.account_proxy_assignments.values() if p.is_expired]),
            "regions": {}
        }
        
        # 按地区统计
        for proxy in self.account_proxy_assignments.values():
            region = proxy.region
            if region not in stats["regions"]:
                stats["regions"][region] = {
                    "count": 0,
                    "active": 0,
                    "expired": 0,
                    "avg_success_rate": 0.0
                }
            
            stats["regions"][region]["count"] += 1
            if proxy.is_active:
                stats["regions"][region]["active"] += 1
            if proxy.is_expired:
                stats["regions"][region]["expired"] += 1
        
        return stats
    
    def cleanup_expired_proxies(self) -> int:
        """清理过期代理"""
        expired_count = 0
        expired_accounts = []
        
        for account_id, proxy in self.account_proxy_assignments.items():
            if proxy.is_expired:
                expired_accounts.append(account_id)
                expired_count += 1
        
        for account_id in expired_accounts:
            del self.account_proxy_assignments[account_id]
            logger.info(f"🧹 清理过期代理: {account_id}")
        
        return expired_count
    
    def should_use_proxy(self, account_info: Dict[str, Any]) -> bool:
        """
        判断账号是否应该使用代理
        
        Args:
            account_info: 账号信息
            
        Returns:
            是否应该使用代理
        """
        # 检查账号配置
        if account_info.get("proxy_required", False):
            return True
        
        # 检查平台策略
        platform = account_info.get("platform", "")
        platform_strategy = self.strategy_config.get("platform_specific", {}).get(platform, {})
        
        if platform_strategy.get("force_proxy", False):
            return True
        
        # 智能检测逻辑可以在这里实现
        # 例如检查当前网络环境、访问成功率等
        
        return False
    
    def get_playwright_proxy_config(self, account_info: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """
        获取Playwright代理配置
        
        Args:
            account_info: 账号信息
            
        Returns:
            Playwright代理配置或None
        """
        if not self.should_use_proxy(account_info):
            return None
        
        proxy_info = self.get_proxy_for_account(account_info)
        if proxy_info:
            return proxy_info.to_playwright_format()
        
        return None


# 全局实例
proxy_config_manager = ProxyConfigManager()


def get_account_proxy(account_info: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    为账号获取代理配置（简化接口）
    
    Args:
        account_info: 账号信息
        
    Returns:
        Playwright代理配置或None
    """
    return proxy_config_manager.get_playwright_proxy_config(account_info)


if __name__ == "__main__":
    # 测试代理配置管理器
    print("🧪 测试代理配置管理器")
    
    # 模拟账号信息
    test_account = {
        "account_id": "test_shopee_cn_001",
        "platform": "Shopee",
        "region": "CN",
        "account_type": "seller"
    }
    
    # 测试代理分配
    proxy_config = get_account_proxy(test_account)
    if proxy_config:
        print(f"✅ 获取代理配置: {proxy_config}")
    else:
        print("ℹ️ 当前环境不需要使用代理")
    
    # 显示统计信息
    stats = proxy_config_manager.get_proxy_stats()
    print(f"📊 代理使用统计: {stats}") 