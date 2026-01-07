"""
代理IP提供者接口 - Proxy Provider Interface

提供代理IP获取和管理的抽象接口
支持多种代理服务商的集成

使用示例:
    # 使用空代理（开发环境）
    provider = NoProxyProvider()
    proxy = await provider.get_proxy()
    
    # 使用静态代理
    provider = StaticProxyProvider("http://proxy.example.com:8080")
    proxy = await provider.get_proxy()
    
    # 使用代理池
    provider = PoolProxyProvider(api_url="https://api.proxy.com/get")
    proxy = await provider.get_proxy(country="SG")
"""

import os
import random
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime, timedelta

from modules.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ProxyInfo:
    """
    代理信息
    
    Attributes:
        host: 代理主机地址
        port: 代理端口
        username: 认证用户名（可选）
        password: 认证密码（可选）
        protocol: 协议类型（http/https/socks5）
        country: 国家代码（可选）
        city: 城市（可选）
        expires_at: 过期时间（可选）
    """
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    protocol: str = "http"
    country: Optional[str] = None
    city: Optional[str] = None
    expires_at: Optional[datetime] = None
    
    @property
    def url(self) -> str:
        """获取代理URL"""
        if self.username and self.password:
            return f"{self.protocol}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.protocol}://{self.host}:{self.port}"
    
    @property
    def playwright_proxy(self) -> Dict[str, Any]:
        """获取Playwright代理配置"""
        proxy_config = {
            "server": f"{self.protocol}://{self.host}:{self.port}"
        }
        if self.username and self.password:
            proxy_config["username"] = self.username
            proxy_config["password"] = self.password
        return proxy_config
    
    @property
    def is_expired(self) -> bool:
        """检查代理是否过期"""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at


class ProxyProvider(ABC):
    """
    代理提供者抽象基类
    
    所有代理提供者实现必须继承此类
    """
    
    @abstractmethod
    async def get_proxy(
        self,
        country: Optional[str] = None,
        city: Optional[str] = None,
        **kwargs
    ) -> Optional[ProxyInfo]:
        """
        获取代理
        
        Args:
            country: 目标国家代码（如 SG, MY, TH）
            city: 目标城市
            **kwargs: 其他参数
            
        Returns:
            ProxyInfo: 代理信息，如果无可用代理返回 None
        """
        pass
    
    @abstractmethod
    async def report_failure(
        self,
        proxy: ProxyInfo,
        error: str,
        **kwargs
    ) -> None:
        """
        报告代理失败
        
        Args:
            proxy: 失败的代理
            error: 错误信息
            **kwargs: 其他参数
        """
        pass
    
    async def report_success(
        self,
        proxy: ProxyInfo,
        **kwargs
    ) -> None:
        """
        报告代理成功（可选实现）
        
        Args:
            proxy: 成功的代理
            **kwargs: 其他参数
        """
        pass


class NoProxyProvider(ProxyProvider):
    """
    空代理提供者
    
    不使用代理的默认实现，用于本地开发环境
    """
    
    async def get_proxy(
        self,
        country: Optional[str] = None,
        city: Optional[str] = None,
        **kwargs
    ) -> Optional[ProxyInfo]:
        """
        获取代理（始终返回 None）
        """
        logger.debug("NoProxyProvider: No proxy configured")
        return None
    
    async def report_failure(
        self,
        proxy: ProxyInfo,
        error: str,
        **kwargs
    ) -> None:
        """
        报告代理失败（空实现）
        """
        pass


class StaticProxyProvider(ProxyProvider):
    """
    静态代理提供者
    
    使用固定的代理地址，适合自建代理服务器
    """
    
    def __init__(
        self,
        proxy_url: str = None,
        host: str = None,
        port: int = None,
        username: str = None,
        password: str = None,
        protocol: str = "http"
    ):
        """
        初始化静态代理
        
        Args:
            proxy_url: 完整代理URL（如 http://user:pass@host:port）
            host: 代理主机
            port: 代理端口
            username: 认证用户名
            password: 认证密码
            protocol: 协议类型
        """
        if proxy_url:
            self._parse_proxy_url(proxy_url)
        else:
            self.host = host or os.getenv("PROXY_HOST")
            self.port = int(port or os.getenv("PROXY_PORT", 8080))
            self.username = username or os.getenv("PROXY_USERNAME")
            self.password = password or os.getenv("PROXY_PASSWORD")
            self.protocol = protocol or os.getenv("PROXY_PROTOCOL", "http")
    
    def _parse_proxy_url(self, url: str) -> None:
        """解析代理URL"""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        
        self.protocol = parsed.scheme or "http"
        self.host = parsed.hostname
        self.port = parsed.port or 8080
        self.username = parsed.username
        self.password = parsed.password
    
    async def get_proxy(
        self,
        country: Optional[str] = None,
        city: Optional[str] = None,
        **kwargs
    ) -> Optional[ProxyInfo]:
        """
        获取静态代理
        """
        if not self.host:
            logger.warning("StaticProxyProvider: No proxy configured")
            return None
        
        return ProxyInfo(
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            protocol=self.protocol,
            country=country
        )
    
    async def report_failure(
        self,
        proxy: ProxyInfo,
        error: str,
        **kwargs
    ) -> None:
        """
        报告代理失败（记录日志）
        """
        logger.warning(f"Static proxy failed: {proxy.host}:{proxy.port} - {error}")


class PoolProxyProvider(ProxyProvider):
    """
    代理池提供者
    
    从代理池API获取代理，支持代理轮换
    适用于：快代理、芝麻代理、讯代理等服务商
    """
    
    def __init__(
        self,
        api_url: str = None,
        api_key: str = None,
        pool_size: int = 10,
        retry_count: int = 3
    ):
        """
        初始化代理池
        
        Args:
            api_url: 代理池API地址
            api_key: API密钥
            pool_size: 本地代理池大小
            retry_count: 获取代理重试次数
        """
        self.api_url = api_url or os.getenv("PROXY_POOL_API")
        self.api_key = api_key or os.getenv("PROXY_POOL_KEY")
        self.pool_size = pool_size
        self.retry_count = retry_count
        
        # 本地代理池
        self._pool: List[ProxyInfo] = []
        self._blacklist: Dict[str, datetime] = {}
        self._blacklist_duration = timedelta(minutes=10)
    
    async def get_proxy(
        self,
        country: Optional[str] = None,
        city: Optional[str] = None,
        **kwargs
    ) -> Optional[ProxyInfo]:
        """
        从代理池获取代理
        """
        # 清理过期黑名单
        self._cleanup_blacklist()
        
        # 先从本地池获取
        for proxy in self._pool:
            proxy_key = f"{proxy.host}:{proxy.port}"
            if proxy_key not in self._blacklist and not proxy.is_expired:
                if country is None or proxy.country == country:
                    return proxy
        
        # 本地池无可用代理，从API获取
        if self.api_url:
            for _ in range(self.retry_count):
                proxy = await self._fetch_from_api(country, city)
                if proxy:
                    self._pool.append(proxy)
                    return proxy
        
        logger.warning("PoolProxyProvider: No available proxy")
        return None
    
    async def _fetch_from_api(
        self,
        country: Optional[str] = None,
        city: Optional[str] = None
    ) -> Optional[ProxyInfo]:
        """
        从API获取代理
        
        注意：这是示例实现，实际使用需根据代理服务商API调整
        """
        try:
            import aiohttp
            
            params = {}
            if self.api_key:
                params["key"] = self.api_key
            if country:
                params["country"] = country
            if city:
                params["city"] = city
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.api_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        # 示例响应格式，需根据实际API调整
                        return ProxyInfo(
                            host=data.get("ip"),
                            port=int(data.get("port", 8080)),
                            protocol=data.get("protocol", "http"),
                            country=data.get("country"),
                            city=data.get("city"),
                            expires_at=datetime.utcnow() + timedelta(minutes=data.get("ttl", 5))
                        )
        except Exception as e:
            logger.error(f"Failed to fetch proxy from API: {e}")
        
        return None
    
    async def report_failure(
        self,
        proxy: ProxyInfo,
        error: str,
        **kwargs
    ) -> None:
        """
        报告代理失败（加入黑名单）
        """
        proxy_key = f"{proxy.host}:{proxy.port}"
        self._blacklist[proxy_key] = datetime.utcnow()
        logger.warning(f"Proxy blacklisted: {proxy_key} - {error}")
        
        # 从本地池移除
        self._pool = [p for p in self._pool if f"{p.host}:{p.port}" != proxy_key]
    
    def _cleanup_blacklist(self) -> None:
        """清理过期黑名单"""
        now = datetime.utcnow()
        expired = [
            key for key, time in self._blacklist.items()
            if now - time > self._blacklist_duration
        ]
        for key in expired:
            del self._blacklist[key]


class RotatingProxyProvider(ProxyProvider):
    """
    轮换代理提供者
    
    从多个静态代理中随机选择，适合有多个代理服务器的场景
    """
    
    def __init__(self, proxies: List[str] = None):
        """
        初始化轮换代理
        
        Args:
            proxies: 代理URL列表
        """
        self.proxies = proxies or []
        self._providers: List[StaticProxyProvider] = [
            StaticProxyProvider(proxy_url=url) for url in self.proxies
        ]
        self._blacklist: Dict[int, datetime] = {}
        self._blacklist_duration = timedelta(minutes=5)
    
    def add_proxy(self, proxy_url: str) -> None:
        """添加代理"""
        self.proxies.append(proxy_url)
        self._providers.append(StaticProxyProvider(proxy_url=proxy_url))
    
    async def get_proxy(
        self,
        country: Optional[str] = None,
        city: Optional[str] = None,
        **kwargs
    ) -> Optional[ProxyInfo]:
        """
        随机获取代理
        """
        if not self._providers:
            return None
        
        # 清理过期黑名单
        now = datetime.utcnow()
        expired = [i for i, t in self._blacklist.items() if now - t > self._blacklist_duration]
        for i in expired:
            del self._blacklist[i]
        
        # 获取可用代理索引
        available = [i for i in range(len(self._providers)) if i not in self._blacklist]
        
        if not available:
            logger.warning("RotatingProxyProvider: All proxies blacklisted")
            return None
        
        # 随机选择
        idx = random.choice(available)
        return await self._providers[idx].get_proxy(country=country, city=city)
    
    async def report_failure(
        self,
        proxy: ProxyInfo,
        error: str,
        **kwargs
    ) -> None:
        """
        报告代理失败
        """
        # 找到对应的代理索引
        for i, provider in enumerate(self._providers):
            if provider.host == proxy.host and provider.port == proxy.port:
                self._blacklist[i] = datetime.utcnow()
                logger.warning(f"Rotating proxy {i} blacklisted: {proxy.host}:{proxy.port}")
                break


def get_proxy_provider() -> ProxyProvider:
    """
    获取代理提供者工厂函数
    
    根据环境变量配置返回对应的代理提供者
    
    环境变量:
        PROXY_MODE: none/static/pool/rotating
        PROXY_HOST: 静态代理主机
        PROXY_PORT: 静态代理端口
        PROXY_POOL_API: 代理池API
        PROXY_LIST: 轮换代理列表（逗号分隔）
    
    Returns:
        ProxyProvider: 代理提供者实例
    """
    mode = os.getenv("PROXY_MODE", "none").lower()
    
    if mode == "none":
        return NoProxyProvider()
    
    elif mode == "static":
        return StaticProxyProvider()
    
    elif mode == "pool":
        return PoolProxyProvider()
    
    elif mode == "rotating":
        proxy_list = os.getenv("PROXY_LIST", "").split(",")
        proxy_list = [p.strip() for p in proxy_list if p.strip()]
        return RotatingProxyProvider(proxies=proxy_list)
    
    else:
        logger.warning(f"Unknown PROXY_MODE: {mode}, using NoProxyProvider")
        return NoProxyProvider()


# 导出
__all__ = [
    "ProxyInfo",
    "ProxyProvider",
    "NoProxyProvider",
    "StaticProxyProvider",
    "PoolProxyProvider",
    "RotatingProxyProvider",
    "get_proxy_provider",
]

