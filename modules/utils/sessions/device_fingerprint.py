#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
设备指纹管理器

为每个账号生成和维护稳定的设备指纹，包括：
- 用户代理 (User Agent)
- 浏览器视口 (Viewport)
- 时区和语言设置
- 其他浏览器特征
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, List
from loguru import logger


class DeviceFingerprintManager:
    """设备指纹管理器"""
    
    # 扩展的用户代理列表（20+ 不同 UA - v4.7.0 扩展）
    STABLE_USER_AGENTS = [
        # Chrome Windows (最新版本)
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
        # Chrome macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        # Edge Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
        # Firefox Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
        # Firefox macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.0; rv:120.0) Gecko/20100101 Firefox/120.0",
        # Safari macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        # Chrome Linux
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        # Windows 11
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Windows/11",
        # Opera
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 OPR/105.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 OPR/105.0.0.0",
        # Brave
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Brave/120",
    ]
    
    # 扩展的视口尺寸列表（10+ 常用分辨率 - v4.7.0 扩展）
    COMMON_VIEWPORTS = [
        # 桌面显示器
        {"width": 1920, "height": 1080},  # Full HD (最常见)
        {"width": 2560, "height": 1440},  # 2K / QHD
        {"width": 3840, "height": 2160},  # 4K / UHD
        {"width": 1366, "height": 768},   # 笔记本 (常见)
        {"width": 1536, "height": 864},   # 笔记本
        {"width": 1440, "height": 900},   # MacBook
        {"width": 1680, "height": 1050},  # WSXGA+
        {"width": 1280, "height": 720},   # HD
        {"width": 1600, "height": 900},   # HD+
        {"width": 1280, "height": 800},   # WXGA
        {"width": 1920, "height": 1200},  # WUXGA
        {"width": 2560, "height": 1600},  # MacBook Pro 16"
        {"width": 2880, "height": 1800},  # MacBook Pro Retina
    ]
    
    # 地区指纹模板（v4.7.0 新增 - 东南亚6国）
    REGION_TEMPLATES = {
        # 中国大陆
        "CN": {
            "locale": "zh-CN",
            "timezone": "Asia/Shanghai",
            "accept_language": "zh-CN,zh;q=0.9,en;q=0.8",
            "currency": "CNY",
        },
        # 新加坡
        "SG": {
            "locale": "en-SG",
            "timezone": "Asia/Singapore",
            "accept_language": "en-SG,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            "currency": "SGD",
        },
        # 马来西亚
        "MY": {
            "locale": "ms-MY",
            "timezone": "Asia/Kuala_Lumpur",
            "accept_language": "ms-MY,ms;q=0.9,en;q=0.8,zh-CN;q=0.7",
            "currency": "MYR",
        },
        # 泰国
        "TH": {
            "locale": "th-TH",
            "timezone": "Asia/Bangkok",
            "accept_language": "th-TH,th;q=0.9,en;q=0.8",
            "currency": "THB",
        },
        # 越南
        "VN": {
            "locale": "vi-VN",
            "timezone": "Asia/Ho_Chi_Minh",
            "accept_language": "vi-VN,vi;q=0.9,en;q=0.8",
            "currency": "VND",
        },
        # 菲律宾
        "PH": {
            "locale": "en-PH",
            "timezone": "Asia/Manila",
            "accept_language": "en-PH,en;q=0.9,fil;q=0.8",
            "currency": "PHP",
        },
        # 印度尼西亚
        "ID": {
            "locale": "id-ID",
            "timezone": "Asia/Jakarta",
            "accept_language": "id-ID,id;q=0.9,en;q=0.8",
            "currency": "IDR",
        },
        # 台湾
        "TW": {
            "locale": "zh-TW",
            "timezone": "Asia/Taipei",
            "accept_language": "zh-TW,zh;q=0.9,en;q=0.8",
            "currency": "TWD",
        },
        # 香港
        "HK": {
            "locale": "zh-HK",
            "timezone": "Asia/Hong_Kong",
            "accept_language": "zh-HK,zh;q=0.9,en;q=0.8",
            "currency": "HKD",
        },
        # 日本
        "JP": {
            "locale": "ja-JP",
            "timezone": "Asia/Tokyo",
            "accept_language": "ja-JP,ja;q=0.9,en;q=0.8",
            "currency": "JPY",
        },
        # 韩国
        "KR": {
            "locale": "ko-KR",
            "timezone": "Asia/Seoul",
            "accept_language": "ko-KR,ko;q=0.9,en;q=0.8",
            "currency": "KRW",
        },
        # 美国
        "US": {
            "locale": "en-US",
            "timezone": "America/New_York",
            "accept_language": "en-US,en;q=0.9",
            "currency": "USD",
        },
        # 巴西
        "BR": {
            "locale": "pt-BR",
            "timezone": "America/Sao_Paulo",
            "accept_language": "pt-BR,pt;q=0.9,en;q=0.8",
            "currency": "BRL",
        },
        # 墨西哥
        "MX": {
            "locale": "es-MX",
            "timezone": "America/Mexico_City",
            "accept_language": "es-MX,es;q=0.9,en;q=0.8",
            "currency": "MXN",
        },
        # 英国
        "GB": {
            "locale": "en-GB",
            "timezone": "Europe/London",
            "accept_language": "en-GB,en;q=0.9",
            "currency": "GBP",
        },
        # 德国
        "DE": {
            "locale": "de-DE",
            "timezone": "Europe/Berlin",
            "accept_language": "de-DE,de;q=0.9,en;q=0.8",
            "currency": "EUR",
        },
    }
    
    def __init__(self, base_path: Path = Path("data/device_fingerprints")):
        """
        初始化设备指纹管理器
        
        Args:
            base_path: 指纹存储基础路径
        """
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"初始化设备指纹管理器: {self.base_path}")
    
    def get_fingerprint_file(self, platform: str, account_id: str) -> Path:
        """
        获取指纹文件路径
        
        Args:
            platform: 平台名称
            account_id: 账号ID
            
        Returns:
            指纹文件路径
        """
        platform_path = self.base_path / platform.lower()
        platform_path.mkdir(parents=True, exist_ok=True)
        
        # 使用账号ID的哈希值作为文件名（避免文件名过长或包含特殊字符）
        account_hash = hashlib.md5(account_id.encode('utf-8')).hexdigest()[:16]
        return platform_path / f"fingerprint_{account_hash}.json"
    
    def get_or_create_fingerprint(
        self, 
        platform: str, 
        account_id: str, 
        account_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        获取或创建设备指纹
        
        Args:
            platform: 平台名称
            account_id: 账号ID
            account_config: 账号配置（可选，用于生成指纹）
            
        Returns:
            设备指纹字典
        """
        fingerprint_file = self.get_fingerprint_file(platform, account_id)
        
        # 尝试加载现有指纹
        if fingerprint_file.exists():
            try:
                with open(fingerprint_file, 'r', encoding='utf-8') as f:
                    fingerprint = json.load(f)
                
                logger.debug(f"加载现有设备指纹: {platform}/{account_id}")
                return fingerprint
                
            except Exception as e:
                logger.warning(f"加载设备指纹失败，将重新生成: {e}")
        
        # 生成新指纹
        fingerprint = self._generate_fingerprint(platform, account_id, account_config)
        
        # 保存指纹
        try:
            with open(fingerprint_file, 'w', encoding='utf-8') as f:
                json.dump(fingerprint, f, indent=2, ensure_ascii=False)
            
            logger.info(f"生成并保存新设备指纹: {platform}/{account_id}")
            
        except Exception as e:
            logger.error(f"保存设备指纹失败: {e}")
        
        return fingerprint
    
    def _generate_fingerprint(
        self, 
        platform: str, 
        account_id: str, 
        account_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        生成设备指纹
        
        Args:
            platform: 平台名称
            account_id: 账号ID
            account_config: 账号配置
            
        Returns:
            设备指纹字典
        """
        # 使用账号ID和平台生成稳定的随机种子
        seed = hashlib.md5(f"{platform}_{account_id}".encode('utf-8')).hexdigest()
        seed_int = int(seed[:8], 16)
        
        # 基于种子选择稳定的配置
        ua_index = seed_int % len(self.STABLE_USER_AGENTS)
        viewport_index = seed_int % len(self.COMMON_VIEWPORTS)
        
        user_agent = self.STABLE_USER_AGENTS[ua_index]
        viewport = self.COMMON_VIEWPORTS[viewport_index].copy()
        
        # 从账号配置中获取地区信息，使用地区模板（v4.7.0 扩展）
        region = "CN"
        if account_config:
            region = account_config.get("region", "CN").upper()
        
        # 获取地区模板配置
        region_template = self.REGION_TEMPLATES.get(region, self.REGION_TEMPLATES["CN"])
        
        locale = region_template["locale"]
        timezone = region_template["timezone"]
        accept_language = region_template["accept_language"]
        currency = region_template.get("currency", "CNY")
        
        # 允许账号配置覆盖默认值
        if account_config:
            timezone = account_config.get("timezone", timezone)
            locale = account_config.get("locale", locale)
        
        # 生成设备指纹
        fingerprint = {
            "platform": platform,
            "account_id": account_id,
            "region": region,
            "user_agent": user_agent,
            "viewport": viewport,
            "locale": locale,
            "timezone": timezone,
            "currency": currency,
            "device_scale_factor": 1.0,
            "is_mobile": False,
            "has_touch": False,
            "color_scheme": "light",
            "reduced_motion": "no-preference",
            "forced_colors": "none",
            "extra_http_headers": {
                "Accept-Language": accept_language,
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                "Cache-Control": "max-age=0",
                "Upgrade-Insecure-Requests": "1",
            },
            "permissions": {
                "geolocation": "denied",
                "notifications": "denied",
                "camera": "denied",
                "microphone": "denied",
            },
            "created_at": __import__("time").time(),
            "version": "2.0"  # v4.7.0 升级版本号
        }
        
        return fingerprint
    
    def get_playwright_context_options(
        self, 
        platform: str, 
        account_id: str, 
        account_config: Optional[Dict[str, Any]] = None,
        proxy: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        获取 Playwright 上下文选项
        
        Args:
            platform: 平台名称
            account_id: 账号ID
            account_config: 账号配置
            proxy: 代理配置
            
        Returns:
            Playwright 上下文选项字典
        """
        fingerprint = self.get_or_create_fingerprint(platform, account_id, account_config)
        
        # 构建上下文选项
        context_options = {
            "user_agent": fingerprint["user_agent"],
            "viewport": fingerprint["viewport"],
            "locale": fingerprint["locale"],
            "timezone_id": fingerprint["timezone"],
            "device_scale_factor": fingerprint["device_scale_factor"],
            "is_mobile": fingerprint["is_mobile"],
            "has_touch": fingerprint["has_touch"],
            "color_scheme": fingerprint["color_scheme"],
            "reduced_motion": fingerprint["reduced_motion"],
            "forced_colors": fingerprint["forced_colors"],
            "extra_http_headers": fingerprint["extra_http_headers"],
            "permissions": list(fingerprint["permissions"].keys()),
            "ignore_https_errors": True,  # 忽略HTTPS错误
            "java_script_enabled": True,
        }
        
        # 添加代理配置
        if proxy and account_config and account_config.get("proxy_required", False):
            context_options["proxy"] = proxy
        
        logger.debug(f"生成上下文选项: {platform}/{account_id}")
        return context_options
    
    def update_fingerprint(
        self, 
        platform: str, 
        account_id: str, 
        updates: Dict[str, Any]
    ) -> bool:
        """
        更新设备指纹
        
        Args:
            platform: 平台名称
            account_id: 账号ID
            updates: 更新的字段
            
        Returns:
            更新是否成功
        """
        try:
            fingerprint_file = self.get_fingerprint_file(platform, account_id)
            
            if fingerprint_file.exists():
                with open(fingerprint_file, 'r', encoding='utf-8') as f:
                    fingerprint = json.load(f)
            else:
                fingerprint = self._generate_fingerprint(platform, account_id)
            
            # 应用更新
            fingerprint.update(updates)
            fingerprint["updated_at"] = __import__("time").time()
            
            # 保存更新后的指纹
            with open(fingerprint_file, 'w', encoding='utf-8') as f:
                json.dump(fingerprint, f, indent=2, ensure_ascii=False)
            
            logger.info(f"设备指纹已更新: {platform}/{account_id}")
            return True
            
        except Exception as e:
            logger.error(f"更新设备指纹失败: {e}")
            return False
    
    def delete_fingerprint(self, platform: str, account_id: str) -> bool:
        """
        删除设备指纹
        
        Args:
            platform: 平台名称
            account_id: 账号ID
            
        Returns:
            删除是否成功
        """
        try:
            fingerprint_file = self.get_fingerprint_file(platform, account_id)
            
            if fingerprint_file.exists():
                fingerprint_file.unlink()
                logger.info(f"设备指纹已删除: {platform}/{account_id}")
            else:
                logger.debug(f"设备指纹文件不存在: {platform}/{account_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"删除设备指纹失败: {e}")
            return False
    
    def list_fingerprints(self, platform: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        列出所有设备指纹
        
        Args:
            platform: 可选的平台过滤
            
        Returns:
            设备指纹信息列表
        """
        fingerprints = []
        
        try:
            if platform:
                platform_path = self.base_path / platform.lower()
                if platform_path.exists():
                    platforms_to_scan = [platform_path]
                else:
                    platforms_to_scan = []
            else:
                platforms_to_scan = [p for p in self.base_path.iterdir() if p.is_dir()]
            
            for platform_path in platforms_to_scan:
                platform_name = platform_path.name
                
                for fingerprint_file in platform_path.glob("fingerprint_*.json"):
                    try:
                        with open(fingerprint_file, 'r', encoding='utf-8') as f:
                            fingerprint = json.load(f)
                        
                        # 添加文件信息
                        fingerprint["file_path"] = str(fingerprint_file)
                        fingerprints.append(fingerprint)
                        
                    except Exception as e:
                        logger.warning(f"读取指纹文件失败: {fingerprint_file}, {e}")
            
        except Exception as e:
            logger.error(f"列出设备指纹时出错: {e}")
        
        return fingerprints
