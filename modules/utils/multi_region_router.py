#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
多国IP路由管理器
解决跨境电商多国同步采集的IP路由挑战

核心功能：
1. 按平台自动分配国家IP
2. 支持代理池管理
3. 智能路由切换
4. 并发采集支持
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import requests
from loguru import logger


@dataclass
class RegionConfig:
    """地区配置"""
    country_code: str  # SG, ID, VN, CN
    country_name: str  # 新加坡, 印尼, 越南, 中国
    proxy_config: Optional[Dict[str, Any]] = None
    test_url: str = "https://httpbin.org/ip"
    priority: int = 1  # 优先级，1最高


@dataclass
class PlatformRouting:
    """平台路由配置"""
    platform: str
    required_region: str
    domains: List[str]
    test_endpoints: List[str] = None
    bypass_vpn: bool = False
    description: str = ""


class MultiRegionRouter:
    """多国IP路由管理器"""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path("config/multi_region_routing.yaml")
        self.regions: Dict[str, RegionConfig] = {}
        self.platform_routing: Dict[str, PlatformRouting] = {}
        self.current_ip_cache: Dict[str, str] = {}
        self.executor = ThreadPoolExecutor(max_workers=10)
        
        # 初始化默认配置
        self._init_default_configs()
        self._load_config()
    
    def _init_default_configs(self):
        """初始化默认配置"""
        # 地区配置
        self.regions = {
            "SG": RegionConfig(
                country_code="SG",
                country_name="新加坡",
                test_url="https://httpbin.org/ip",
                priority=1
            ),
            "ID": RegionConfig(
                country_code="ID", 
                country_name="印尼",
                test_url="https://httpbin.org/ip",
                priority=2
            ),
            "VN": RegionConfig(
                country_code="VN",
                country_name="越南", 
                test_url="https://httpbin.org/ip",
                priority=3
            ),
            "CN": RegionConfig(
                country_code="CN",
                country_name="中国",
                test_url="https://www.baidu.com",
                priority=4
            )
        }
        
        # 平台路由配置
        self.platform_routing = {
            "shopee_sg": PlatformRouting(
                platform="shopee_sg",
                required_region="SG",
                domains=["seller.shopee.sg", "shopee.sg"],
                test_endpoints=["https://seller.shopee.sg/portal/product/list"]
            ),
            "shopee_id": PlatformRouting(
                platform="shopee_id", 
                required_region="ID",
                domains=["seller.shopee.co.id", "shopee.co.id"],
                test_endpoints=["https://seller.shopee.co.id/portal/product/list"]
            ),
            "shopee_vn": PlatformRouting(
                platform="shopee_vn",
                required_region="VN", 
                domains=["seller.shopee.vn", "shopee.vn"],
                test_endpoints=["https://seller.shopee.vn/portal/product/list"]
            ),
            "miaoshou_erp": PlatformRouting(
                platform="miaoshou_erp",
                required_region="CN",
                domains=["erp.91miaoshou.com", "91miaoshou.com"],
                test_endpoints=["https://erp.91miaoshou.com/login"]
            )
        }
    
    def configure_region_proxy(self, region_code: str, proxy_config: Dict[str, Any]):
        """配置地区代理"""
        if region_code in self.regions:
            self.regions[region_code].proxy_config = proxy_config
            logger.info(f"[OK] 已配置{self.regions[region_code].country_name}代理")
        else:
            logger.error(f"[FAIL] 未知地区代码: {region_code}")
    
    def get_platform_routing(self, platform: str) -> Optional[PlatformRouting]:
        """获取平台路由配置"""
        return self.platform_routing.get(platform)
    
    def get_region_proxy(self, region_code: str) -> Optional[Dict[str, Any]]:
        """获取地区代理配置"""
        region = self.regions.get(region_code)
        return region.proxy_config if region else None
    
    def test_region_connectivity(self, region_code: str) -> Dict[str, Any]:
        """测试地区连通性"""
        region = self.regions.get(region_code)
        if not region:
            return {"success": False, "error": f"未知地区: {region_code}"}
        
        try:
            start_time = time.time()
            
            # 构建请求参数
            kwargs = {
                "url": region.test_url,
                "timeout": 10,
                "headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
            }
            
            # 如果有代理配置，添加代理
            if region.proxy_config:
                proxy_url = f"{region.proxy_config['type']}://"
                if region.proxy_config.get('username'):
                    proxy_url += f"{region.proxy_config['username']}:{region.proxy_config['password']}@"
                proxy_url += f"{region.proxy_config['host']}:{region.proxy_config['port']}"
                kwargs["proxies"] = {"http": proxy_url, "https": proxy_url}
            
            response = requests.get(**kwargs)
            duration = time.time() - start_time
            
            if response.status_code == 200:
                # 尝试解析IP信息
                try:
                    ip_info = response.json()
                    current_ip = ip_info.get("origin", "unknown")
                except:
                    current_ip = "unknown"
                
                return {
                    "success": True,
                    "region": region.country_name,
                    "ip": current_ip,
                    "response_time": round(duration, 3),
                    "proxy_used": region.proxy_config is not None
                }
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}",
                    "response_time": round(duration, 3)
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "response_time": 0
            }
    
    def test_all_regions(self) -> Dict[str, Dict[str, Any]]:
        """测试所有地区连通性"""
        results = {}
        
        logger.info("[TEST] 开始测试所有地区连通性...")
        
        # 并发测试所有地区
        future_to_region = {}
        for region_code in self.regions.keys():
            future = self.executor.submit(self.test_region_connectivity, region_code)
            future_to_region[future] = region_code
        
        # 收集结果
        for future in future_to_region:
            region_code = future_to_region[future]
            try:
                result = future.result(timeout=15)
                results[region_code] = result
                
                if result["success"]:
                    logger.success(f"[OK] {self.regions[region_code].country_name}: {result['ip']} ({result['response_time']}秒)")
                else:
                    logger.error(f"[FAIL] {self.regions[region_code].country_name}: {result['error']}")
                    
            except Exception as e:
                results[region_code] = {
                    "success": False,
                    "error": f"测试超时: {e}",
                    "response_time": 0
                }
                logger.error(f"[FAIL] {self.regions[region_code].country_name}: 测试超时")
        
        return results
    
    def get_playwright_proxy_config(self, platform: str) -> Optional[Dict[str, Any]]:
        """获取Playwright代理配置"""
        routing = self.get_platform_routing(platform)
        if not routing:
            return None
        
        proxy_config = self.get_region_proxy(routing.required_region)
        if not proxy_config:
            return None
        
        # 转换为Playwright格式
        playwright_proxy = {
            "server": f"{proxy_config['type']}://{proxy_config['host']}:{proxy_config['port']}"
        }
        
        if proxy_config.get('username'):
            playwright_proxy["username"] = proxy_config["username"]
            playwright_proxy["password"] = proxy_config["password"]
        
        return playwright_proxy
    
    def create_platform_session(self, platform: str) -> Tuple[bool, Dict[str, Any]]:
        """为平台创建网络会话"""
        routing = self.get_platform_routing(platform)
        if not routing:
            return False, {"error": f"未配置平台路由: {platform}"}
        
        region = self.regions.get(routing.required_region)
        if not region:
            return False, {"error": f"未配置地区: {routing.required_region}"}
        
        # 测试连通性
        connectivity = self.test_region_connectivity(routing.required_region)
        if not connectivity["success"]:
            return False, {"error": f"地区{region.country_name}连接失败: {connectivity['error']}"}
        
        # 返回会话配置
        session_config = {
            "platform": platform,
            "region": routing.required_region,
            "region_name": region.country_name,
            "proxy_config": region.proxy_config,
            "playwright_proxy": self.get_playwright_proxy_config(platform),
            "current_ip": connectivity.get("ip"),
            "response_time": connectivity.get("response_time"),
            "test_endpoints": routing.test_endpoints
        }
        
        return True, session_config
    
    def batch_create_sessions(self, platforms: List[str]) -> Dict[str, Dict[str, Any]]:
        """批量创建平台会话"""
        sessions = {}
        
        logger.info(f"[START] 批量创建 {len(platforms)} 个平台会话...")
        
        # 并发创建会话
        future_to_platform = {}
        for platform in platforms:
            future = self.executor.submit(self.create_platform_session, platform)
            future_to_platform[future] = platform
        
        # 收集结果
        for future in future_to_platform:
            platform = future_to_platform[future]
            try:
                success, config = future.result(timeout=15)
                if success:
                    sessions[platform] = config
                    region_name = config["region_name"]
                    current_ip = config.get("current_ip", "unknown")
                    logger.success(f"[OK] {platform} -> {region_name} ({current_ip})")
                else:
                    logger.error(f"[FAIL] {platform}: {config['error']}")
                    
            except Exception as e:
                logger.error(f"[FAIL] {platform}: 会话创建超时 {e}")
        
        return sessions
    
    def save_config(self):
        """保存配置到文件"""
        try:
            config_data = {
                "regions": {},
                "platform_routing": {}
            }
            
            # 序列化地区配置
            for code, region in self.regions.items():
                config_data["regions"][code] = {
                    "country_code": region.country_code,
                    "country_name": region.country_name,
                    "proxy_config": region.proxy_config,
                    "test_url": region.test_url,
                    "priority": region.priority
                }
            
            # 序列化平台路由
            for platform, routing in self.platform_routing.items():
                config_data["platform_routing"][platform] = {
                    "platform": routing.platform,
                    "required_region": routing.required_region,
                    "domains": routing.domains,
                    "test_endpoints": routing.test_endpoints
                }
            
            # 确保目录存在
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 保存配置
            import yaml
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
            
            logger.success(f"[OK] 配置已保存: {self.config_path}")
            
        except Exception as e:
            logger.error(f"[FAIL] 保存配置失败: {e}")
    
    def _load_config(self):
        """从文件加载配置"""
        if not self.config_path.exists():
            logger.info("配置文件不存在，使用默认配置")
            return
        
        try:
            import yaml
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            # 加载地区配置
            if "regions" in config_data:
                for code, region_data in config_data["regions"].items():
                    # 确保包含必需的country_code字段
                    if isinstance(region_data, dict):
                        region_data = region_data.copy()  # 避免修改原始数据
                        region_data["country_code"] = code
                        self.regions[code] = RegionConfig(**region_data)
                    else:
                        logger.warning(f"[WARN] 跳过无效地区配置: {code}")
            
            # 加载平台路由
            if "platform_routing" in config_data:
                for platform, routing_data in config_data["platform_routing"].items():
                    # 确保包含platform字段
                    if isinstance(routing_data, dict):
                        routing_data = routing_data.copy()
                        routing_data["platform"] = platform
                        # 设置默认值
                        if "test_endpoints" not in routing_data:
                            routing_data["test_endpoints"] = []
                        self.platform_routing[platform] = PlatformRouting(**routing_data)
                    else:
                        logger.warning(f"[WARN] 跳过无效平台配置: {platform}")
            
            logger.success(f"[OK] 配置已加载: {self.config_path}")
            
        except Exception as e:
            logger.error(f"[FAIL] 加载配置失败: {e}")

    def get_playwright_proxy_config(self, platform: str) -> Optional[Dict[str, Any]]:
        """获取指定平台的Playwright代理配置"""
        # 找到平台对应的地区
        platform_routing = self.platform_routing.get(platform)
        if not platform_routing:
            logger.warning(f"[WARN] 未找到平台 {platform} 的路由配置")
            return None
        
        region_code = platform_routing.required_region
        region = self.regions.get(region_code)
        if not region or not region.proxy_config:
            logger.warning(f"[WARN] 地区 {region_code} 无代理配置")
            return None
        
        proxy_config = region.proxy_config
        proxy_type = proxy_config.get("type")
        
        # 处理中国代理模式（新策略：使用代理而非VPN绕过）
        if region_code == "CN":
            logger.info(f"[CN] 使用中国代理模式访问 {platform}")
            # 中国地区也使用标准的HTTP/SOCKS5代理处理逻辑
        
        # 处理HTTP/SOCKS5代理（包括中国地区）
        if proxy_type in ["http", "socks5"]:
            host = proxy_config.get("host")
            port = proxy_config.get("port")
            username = proxy_config.get("username")
            password = proxy_config.get("password")
            
            if not host or not port:
                logger.warning(f"[WARN] 代理配置不完整: {region_code}")
                return None
            
            playwright_proxy = {
                "server": f"{proxy_type}://{host}:{port}"
            }
            
            if username and password:
                playwright_proxy["username"] = username
                playwright_proxy["password"] = password
            
            logger.success(f"[OK] 已配置 {proxy_type.upper()} 代理: {host}:{port}")
            return playwright_proxy
        
        # 直连模式
        elif proxy_type == "direct":
            logger.info(f"[SIGNAL] 使用直连模式访问 {platform}")
            return None
        
        else:
            logger.warning(f"[WARN] 不支持的代理类型: {proxy_type}")
            return None


def demo_multi_region_setup():
    """演示多地区配置"""
    router = MultiRegionRouter()
    
    print("[WEB] 多国IP路由管理器演示")
    print("=" * 50)
    
    # 示例：配置新加坡代理
    sg_proxy = {
        "type": "http",
        "host": "sg-proxy.example.com", 
        "port": 8080,
        "username": "user",
        "password": "pass"
    }
    router.configure_region_proxy("SG", sg_proxy)
    
    # 示例：配置印尼代理
    id_proxy = {
        "type": "socks5",
        "host": "id-proxy.example.com",
        "port": 1080
    }
    router.configure_region_proxy("ID", id_proxy)
    
    # 测试所有地区
    results = router.test_all_regions()
    
    print(f"\n[DATA] 测试结果:")
    for region_code, result in results.items():
        status = "[OK]" if result["success"] else "[FAIL]"
        print(f"{status} {router.regions[region_code].country_name}: {result}")
    
    # 批量创建会话
    platforms = ["shopee_sg", "shopee_id", "miaoshou_erp"]
    sessions = router.batch_create_sessions(platforms)
    
    print(f"\n[LINK] 平台会话:")
    for platform, config in sessions.items():
        print(f"[PHONE] {platform} -> {config['region_name']} ({config.get('current_ip')})")
    
    # 保存配置
    router.save_config()
    
    return router


if __name__ == "__main__":
    demo_multi_region_setup() 