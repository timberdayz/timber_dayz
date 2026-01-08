"""
Platform Adapters - 平台适配器
===============================

为不同电商平台提供统一的深链接构造、数据类型映射和导出接口适配

核心功能：
- [LINK] 深链接构造：登录后直达指定数据页面
- [DATA] 数据类型映射：统一的数据类型到平台特定URL的映射
- [RECV] 导出接口适配：标准化的数据导出流程
- [STORE] 店铺切换：基于shop_id的店铺数据访问

支持平台：
- Shopee 卖家端
- Amazon Seller Central（预留）
- 妙手ERP（预留）

版本：v1.0.0
作者：跨境电商ERP系统
更新：2025-08-29
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass

from modules.utils.recording_registry import RecordingType
from modules.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ExportConfig:
    """导出配置"""
    method: str  # GET/POST
    endpoint: str  # API端点
    params: Dict  # 请求参数
    headers: Dict  # 请求头
    file_extension: str  # 文件扩展名
    timeout: int = 30000  # 超时时间


class PlatformAdapter(ABC):
    """平台适配器基类"""
    
    def __init__(self, platform_name: str):
        self.platform_name = platform_name
        
    @abstractmethod
    def build_deep_link(self, data_type: RecordingType, shop_id: str, **kwargs) -> str:
        """构造深链接URL"""
        pass
    
    @abstractmethod
    def get_export_config(self, data_type: RecordingType, shop_id: str, **kwargs) -> ExportConfig:
        """获取导出配置"""
        pass
    
    @abstractmethod
    def get_page_selectors(self, data_type: RecordingType) -> Dict[str, str]:
        """获取页面关键选择器"""
        pass
    
    @abstractmethod
    def validate_shop_access(self, page, shop_id: str) -> Tuple[bool, str]:
        """验证店铺访问权限"""
        pass


class ShopeeAdapter(PlatformAdapter):
    """Shopee 卖家端适配器"""
    
    BASE_URL = "https://seller.shopee.cn"
    
    # 深链接路由映射
    DEEP_LINK_ROUTES = {
        RecordingType.PRODUCTS: "/datacenter/product/overview",
        RecordingType.ORDERS: "/portal/order/list",
        RecordingType.ANALYTICS: "/datacenter/traffic/overview", 
        RecordingType.FINANCE: "/portal/finance/revenue"
    }
    
    # 页面关键选择器
    PAGE_SELECTORS = {
        RecordingType.PRODUCTS: {
            "export_button": "text=导出数据",
            "data_table": "[data-testid='product-table']",
            "loading": ".loading, .spinner",
            "error": ".error-message, .no-permission"
        },
        RecordingType.ORDERS: {
            "export_button": "text=导出订单",
            "data_table": "[data-testid='order-table']", 
            "loading": ".loading, .spinner",
            "error": ".error-message, .no-permission"
        },
        RecordingType.ANALYTICS: {
            "export_button": "text=导出报告",
            "data_table": ".analytics-chart, .traffic-data",
            "loading": ".loading, .spinner", 
            "error": ".error-message, .no-permission"
        },
        RecordingType.FINANCE: {
            "export_button": "text=导出财务数据",
            "data_table": ".finance-table, .revenue-data",
            "loading": ".loading, .spinner",
            "error": ".error-message, .no-permission"
        }
    }
    
    def __init__(self):
        super().__init__("shopee")
        
    def build_deep_link(self, data_type: RecordingType, shop_id: str, **kwargs) -> str:
        """
        构造Shopee深链接
        
        Args:
            data_type: 数据类型
            shop_id: 店铺ID
            **kwargs: 额外参数（如日期范围等）
            
        Returns:
            str: 完整的深链接URL
        """
        if data_type not in self.DEEP_LINK_ROUTES:
            raise ValueError(f"不支持的数据类型: {data_type}")
            
        route = self.DEEP_LINK_ROUTES[data_type]
        url = f"{self.BASE_URL}{route}?cnsc_shop_id={shop_id}"
        
        # 添加额外参数
        if kwargs:
            params = []
            for key, value in kwargs.items():
                if value is not None:
                    params.append(f"{key}={value}")
            if params:
                url += "&" + "&".join(params)
                
        logger.info(f"[LINK] 构造深链接: {data_type.value} -> {url}")
        return url
    
    def get_export_config(self, data_type: RecordingType, shop_id: str, **kwargs) -> ExportConfig:
        """
        获取导出配置（需要通过录制确定具体接口）
        
        注意：这里提供的是模板配置，实际使用时需要通过录制确定真实的API端点
        """
        base_config = {
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
            },
            "timeout": 30000
        }
        
        if data_type == RecordingType.PRODUCTS:
            return ExportConfig(
                method="GET",
                endpoint=f"{self.BASE_URL}/api/datacenter/product/export",
                params={
                    "shop_id": shop_id,
                    "type": "overview",
                    "range": kwargs.get("date_range", "last_30_days")
                },
                headers=base_config["headers"],
                file_extension="csv",
                timeout=base_config["timeout"]
            )
        elif data_type == RecordingType.ORDERS:
            return ExportConfig(
                method="GET", 
                endpoint=f"{self.BASE_URL}/api/order/export",
                params={
                    "shop_id": shop_id,
                    "status": kwargs.get("status", "all"),
                    "range": kwargs.get("date_range", "last_30_days")
                },
                headers=base_config["headers"],
                file_extension="xlsx",
                timeout=base_config["timeout"]
            )
        elif data_type == RecordingType.ANALYTICS:
            return ExportConfig(
                method="GET",
                endpoint=f"{self.BASE_URL}/api/datacenter/traffic/export", 
                params={
                    "shop_id": shop_id,
                    "metrics": kwargs.get("metrics", "overview"),
                    "range": kwargs.get("date_range", "last_30_days")
                },
                headers=base_config["headers"],
                file_extension="csv",
                timeout=base_config["timeout"]
            )
        elif data_type == RecordingType.FINANCE:
            return ExportConfig(
                method="GET",
                endpoint=f"{self.BASE_URL}/api/finance/export",
                params={
                    "shop_id": shop_id,
                    "type": kwargs.get("finance_type", "revenue"),
                    "range": kwargs.get("date_range", "last_30_days")
                },
                headers=base_config["headers"],
                file_extension="xlsx", 
                timeout=base_config["timeout"]
            )
        else:
            raise ValueError(f"不支持的数据类型: {data_type}")
    
    def get_page_selectors(self, data_type: RecordingType) -> Dict[str, str]:
        """获取页面关键选择器"""
        if data_type not in self.PAGE_SELECTORS:
            raise ValueError(f"不支持的数据类型: {data_type}")
        return self.PAGE_SELECTORS[data_type]
    
    def validate_shop_access(self, page, shop_id: str) -> Tuple[bool, str]:
        """
        验证店铺访问权限
        
        Returns:
            Tuple[bool, str]: (是否有权限, 详细信息)
        """
        try:
            current_url = page.url
            
            # 检查URL中是否包含正确的shop_id
            if f"cnsc_shop_id={shop_id}" not in current_url:
                return False, f"URL中shop_id不匹配: 期望{shop_id}, 当前{current_url}"
            
            # 检查是否有权限错误页面
            error_indicators = [
                "您访问的店铺不在当前账号下",
                "您没有权限查看这个页面",
                "no-permission",
                "权限不足"
            ]
            
            page_content = page.text_content('body') or ""
            for indicator in error_indicators:
                if indicator in page_content:
                    return False, f"检测到权限错误: {indicator}"
            
            # 检查是否有正常的店铺数据
            normal_indicators = [
                "数据概览",
                "商品数据", 
                "订单数据",
                "流量数据",
                "财务数据",
                "店铺数据"
            ]
            
            has_normal_content = any(indicator in page_content for indicator in normal_indicators)
            if has_normal_content:
                return True, f"店铺 {shop_id} 访问正常"
            
            return False, "页面内容异常，无法确认店铺访问权限"
            
        except Exception as e:
            return False, f"验证店铺权限时发生异常: {e}"


class AmazonAdapter(PlatformAdapter):
    """Amazon Seller Central 适配器（预留）"""
    
    def __init__(self):
        super().__init__("amazon")
        
    def build_deep_link(self, data_type: RecordingType, shop_id: str, **kwargs) -> str:
        # TODO: 实现Amazon深链接构造
        raise NotImplementedError("Amazon适配器待实现")
    
    def get_export_config(self, data_type: RecordingType, shop_id: str, **kwargs) -> ExportConfig:
        # TODO: 实现Amazon导出配置
        raise NotImplementedError("Amazon适配器待实现")
    
    def get_page_selectors(self, data_type: RecordingType) -> Dict[str, str]:
        # TODO: 实现Amazon页面选择器
        raise NotImplementedError("Amazon适配器待实现")
    
    def validate_shop_access(self, page, shop_id: str) -> Tuple[bool, str]:
        # TODO: 实现Amazon店铺权限验证
        raise NotImplementedError("Amazon适配器待实现")


class MiaoshouAdapter(PlatformAdapter):
    """妙手ERP适配器（预留）"""
    
    def __init__(self):
        super().__init__("miaoshow")
        
    def build_deep_link(self, data_type: RecordingType, shop_id: str, **kwargs) -> str:
        # TODO: 实现妙手ERP深链接构造
        raise NotImplementedError("妙手ERP适配器待实现")
    
    def get_export_config(self, data_type: RecordingType, shop_id: str, **kwargs) -> ExportConfig:
        # TODO: 实现妙手ERP导出配置
        raise NotImplementedError("妙手ERP适配器待实现")
    
    def get_page_selectors(self, data_type: RecordingType) -> Dict[str, str]:
        # TODO: 实现妙手ERP页面选择器
        raise NotImplementedError("妙手ERP适配器待实现")
    
    def validate_shop_access(self, page, shop_id: str) -> Tuple[bool, str]:
        # TODO: 实现妙手ERP店铺权限验证
        raise NotImplementedError("妙手ERP适配器待实现")


# 适配器工厂
PLATFORM_ADAPTERS = {
    "shopee": ShopeeAdapter,
    "amazon": AmazonAdapter, 
    "miaoshow": MiaoshouAdapter
}


def get_platform_adapter(platform: str) -> PlatformAdapter:
    """
    获取平台适配器实例
    
    Args:
        platform: 平台名称
        
    Returns:
        PlatformAdapter: 适配器实例
    """
    platform = platform.lower()
    if platform not in PLATFORM_ADAPTERS:
        raise ValueError(f"不支持的平台: {platform}")
    
    return PLATFORM_ADAPTERS[platform]()


__all__ = [
    "PlatformAdapter",
    "ShopeeAdapter", 
    "AmazonAdapter",
    "MiaoshouAdapter",
    "ExportConfig",
    "get_platform_adapter"
]
