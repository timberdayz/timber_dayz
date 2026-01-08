from __future__ import annotations

"""
TikTok 组件配置注册中心

统一管理各数据域的配置文件与组件映射，实现智能配置编辑。

- get_config_path("analytics") -> analytics_config.py 路径
- get_config_class("products") -> ProductsSelectors 配置类
- get_navigation_target("products") -> TargetPage.PRODUCTS_PERFORMANCE

注意：仅定义映射与便捷函数；禁止在导入阶段做任何 I/O 或实例化。
"""
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Type


class DataDomain(Enum):
    ANALYTICS = "analytics"  # 客流/流量表现
    PRODUCTS = "products"  # 商品表现
    ORDERS = "orders"      # 订单
    FINANCE = "finance"    # 财务
    SERVICES = "services"  # 服务


@dataclass(frozen=True)
class DomainConfig:
    """数据域配置信息"""

    domain: DataDomain
    config_file: str  # 配置文件名
    navigation_target: str  # 导航目标枚举值（TargetPage.*）
    menu_display_name: str  # 菜单显示名称
    data_type_dir: str  # 输出目录名


DOMAIN_CONFIGS: Dict[DataDomain, DomainConfig] = {
    DataDomain.ANALYTICS: DomainConfig(
        domain=DataDomain.ANALYTICS,
        config_file="analytics_config.py",
        navigation_target="TRAFFIC_OVERVIEW",
        menu_display_name="流量表现数据导出",
        data_type_dir="analytics",  # v4.10.0更新：统一使用analytics域，traffic域已废弃
    ),
    DataDomain.PRODUCTS: DomainConfig(
        domain=DataDomain.PRODUCTS,
        config_file="products_config.py",
        navigation_target="PRODUCTS_PERFORMANCE",
        menu_display_name="商品表现数据导出",
        data_type_dir="products",
    ),
    DataDomain.ORDERS: DomainConfig(
        domain=DataDomain.ORDERS,
        config_file="orders_config.py",
        navigation_target="ORDERS",
        menu_display_name="订单数据导出",
        data_type_dir="orders",
    ),
    DataDomain.FINANCE: DomainConfig(
        domain=DataDomain.FINANCE,
        config_file="finance_config.py",
        navigation_target="FINANCE",
        menu_display_name="财务数据导出",
        data_type_dir="finance",
    ),
    DataDomain.SERVICES: DomainConfig(
        domain=DataDomain.SERVICES,
        config_file="service_config.py",
        navigation_target="SERVICE_ANALYTICS",
        menu_display_name="服务数据导出",
        data_type_dir="services",
    ),
}


class ConfigRegistry:
    """配置注册中心（无导入副作用）"""

    @staticmethod
    def get_config_path(domain: str | DataDomain) -> Path:
        """获取数据域对应的配置文件路径"""
        if isinstance(domain, str):
            domain = DataDomain(domain)
        config = DOMAIN_CONFIGS.get(domain)
        if not config:
            raise ValueError(f"未知数据域: {domain}")
        return Path("modules/platforms/tiktok/components") / config.config_file

    @staticmethod
    def get_domain_config(domain: str | DataDomain) -> DomainConfig:
        """获取数据域完整配置"""
        if isinstance(domain, str):
            domain = DataDomain(domain)
        config = DOMAIN_CONFIGS.get(domain)
        if not config:
            raise ValueError(f"未知数据域: {domain}")
        return config

    @staticmethod
    def get_config_class(domain: str | DataDomain) -> Type[Any]:
        """动态获取配置类（延迟导入）"""
        if isinstance(domain, str):
            domain = DataDomain(domain)
        if domain == DataDomain.ANALYTICS:
            from modules.platforms.tiktok.components.analytics_config import AnalyticsSelectors
            return AnalyticsSelectors
        elif domain == DataDomain.PRODUCTS:
            from modules.platforms.tiktok.components.products_config import ProductsSelectors
            return ProductsSelectors
        elif domain == DataDomain.ORDERS:
            from modules.platforms.tiktok.components.orders_config import OrdersSelectors
            return OrdersSelectors
        elif domain == DataDomain.FINANCE:
            from modules.platforms.tiktok.components.finance_config import FinanceSelectors
            return FinanceSelectors
        elif domain == DataDomain.SERVICES:
            from modules.platforms.tiktok.components.service_config import ServiceSelectors
            return ServiceSelectors
        raise ValueError(f"未实现的配置类: {domain}")

    @staticmethod
    def get_navigation_target(domain: str | DataDomain) -> str:
        """获取导航目标枚举值（TargetPage.*）"""
        config = ConfigRegistry.get_domain_config(domain)
        return config.navigation_target

    @staticmethod
    def list_all_domains() -> Dict[DataDomain, DomainConfig]:
        """列出所有数据域配置（拷贝）"""
        return DOMAIN_CONFIGS.copy()


# 便捷函数

def get_config_path(domain: str | DataDomain) -> Path:
    return ConfigRegistry.get_config_path(domain)


def get_domain_config(domain: str | DataDomain) -> DomainConfig:
    return ConfigRegistry.get_domain_config(domain)


def get_navigation_target(domain: str | DataDomain) -> str:
    return ConfigRegistry.get_navigation_target(domain)

