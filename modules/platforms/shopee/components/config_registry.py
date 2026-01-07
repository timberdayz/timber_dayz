"""
Shopee 组件配置注册中心

统一管理各数据域的配置文件与组件映射，实现智能配置编辑。

使用方式：
- get_config_path("analytics") → analytics_config.py 路径
- get_export_component("orders") → OrdersExport 组件类
- get_navigation_target("products") → TargetPage.PRODUCTS_PERFORMANCE
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Type, Any, Optional
from enum import Enum


class DataDomain(Enum):
    """数据域枚举"""
    ANALYTICS = "analytics"      # 客流/流量表现
    PRODUCTS = "products"        # 商品表现
    ORDERS = "orders"           # 订单表现（兼容保留，将迁移至 services）
    FINANCE = "finance"         # 财务表现/结算
    SERVICES = "services"       # 服务表现/客服


@dataclass(frozen=True)
class DomainConfig:
    """数据域配置信息"""
    domain: DataDomain
    config_file: str                    # 配置文件名
    export_component: str               # 导出组件类名
    navigation_target: str              # 导航目标枚举值
    menu_display_name: str              # 菜单显示名称
    data_type_dir: str                  # 输出目录名


# 数据域配置映射表
DOMAIN_CONFIGS: Dict[DataDomain, DomainConfig] = {
    DataDomain.ANALYTICS: DomainConfig(
        domain=DataDomain.ANALYTICS,
        config_file="analytics_config.py",
        export_component="ShopeeAnalyticsExport",
        navigation_target="TRAFFIC_OVERVIEW",
        menu_display_name="流量表现数据导出",
        data_type_dir="analytics"  # v4.10.0更新：统一使用analytics域，traffic域已废弃
    ),
    DataDomain.PRODUCTS: DomainConfig(
        domain=DataDomain.PRODUCTS,
        config_file="products_config.py",
        export_component="ShopeeProductsExport",
        navigation_target="PRODUCTS_PERFORMANCE",
        menu_display_name="商品表现数据导出",
        data_type_dir="products"
    ),
    DataDomain.ORDERS: DomainConfig(
        domain=DataDomain.ORDERS,
        config_file="orders_config.py",
        export_component="ShopeeOrdersExport",
        navigation_target="ORDERS_PERFORMANCE",
        menu_display_name="订单表现数据导出",
        data_type_dir="orders"
    ),
    DataDomain.FINANCE: DomainConfig(
        domain=DataDomain.FINANCE,
        config_file="finance_config.py",
        export_component="ShopeeFinanceExport",
        navigation_target="FINANCE_OVERVIEW",
        menu_display_name="财务表现数据导出",
        data_type_dir="finance"
    ),
    DataDomain.SERVICES: DomainConfig(
        domain=DataDomain.SERVICES,
        config_file="services_config.py",
        export_component="ShopeeServicesExport",
        navigation_target="SERVICES",  # handled inside component
        menu_display_name="服务表现数据导出",
        data_type_dir="services"
    ),
}


class ConfigRegistry:
    """配置注册中心"""
    
    @staticmethod
    def get_config_path(domain: str | DataDomain) -> Path:
        """获取数据域对应的配置文件路径"""
        if isinstance(domain, str):
            domain = DataDomain(domain)
        
        config = DOMAIN_CONFIGS.get(domain)
        if not config:
            raise ValueError(f"未知数据域: {domain}")
        
        return Path("modules/platforms/shopee/components") / config.config_file
    
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
    def get_export_component_class(domain: str | DataDomain) -> Type[Any]:
        """动态获取导出组件类"""
        config = ConfigRegistry.get_domain_config(domain)
        
        # 动态导入组件类
        if domain == DataDomain.ANALYTICS:
            from modules.platforms.shopee.components.analytics_export import ShopeeAnalyticsExport
            return ShopeeAnalyticsExport
        elif domain == DataDomain.PRODUCTS:
            from modules.platforms.shopee.components.products_export import ShopeeProductsExport
            return ShopeeProductsExport
        elif domain == DataDomain.ORDERS:
            from modules.platforms.shopee.components.orders_export import ShopeeOrdersExport
            return ShopeeOrdersExport
        elif domain == DataDomain.FINANCE:
            from modules.platforms.shopee.components.finance_export import ShopeeFinanceExport
            return ShopeeFinanceExport
        elif domain == DataDomain.SERVICES:
            from modules.platforms.shopee.components.services_export import ShopeeServicesExport
            return ShopeeServicesExport
        else:
            raise ValueError(f"未实现的导出组件: {config.export_component}")

    @staticmethod
    def get_config_class(domain: str | DataDomain) -> Type[Any]:
        """动态获取配置类"""
        if isinstance(domain, str):
            domain = DataDomain(domain)
        
        # 动态导入配置类
        if domain == DataDomain.ANALYTICS:
            from modules.platforms.shopee.components.analytics_config import AnalyticsSelectors
            return AnalyticsSelectors
        elif domain == DataDomain.PRODUCTS:
            from modules.platforms.shopee.components.products_config import ProductsSelectors
            return ProductsSelectors
        elif domain == DataDomain.ORDERS:
            from modules.platforms.shopee.components.orders_config import OrdersSelectors
            return OrdersSelectors
        elif domain == DataDomain.FINANCE:
            from modules.platforms.shopee.components.finance_config import FinanceSelectors
            return FinanceSelectors
        elif domain == DataDomain.SERVICES:
            from modules.platforms.shopee.components.services_config import ServicesSelectors
            return ServicesSelectors
        else:
            raise ValueError(f"未实现的配置类: {domain}")

    @staticmethod
    def get_navigation_target(domain: str | DataDomain) -> str:
        """获取导航目标枚举值"""
        config = ConfigRegistry.get_domain_config(domain)
        return config.navigation_target
    
    @staticmethod
    def list_all_domains() -> Dict[DataDomain, DomainConfig]:
        """列出所有数据域配置"""
        return DOMAIN_CONFIGS.copy()
    
    @staticmethod
    def open_config_file(domain: str | DataDomain) -> bool:
        """智能打开配置文件进行编辑"""
        import os
        import subprocess
        
        try:
            config_path = ConfigRegistry.get_config_path(domain)
            config = ConfigRegistry.get_domain_config(domain)
            
            print(f"\n[EDIT] 快速修改 {config.menu_display_name} 组件配置")
            print("=" * 50)
            print(f"📁 配置文件: {config_path}")
            print(f"[DOMAIN] 数据域: {config.domain.value}")
            print(f"[DATA] 输出目录: temp/outputs/shopee/<账号>/<店铺>/{config.data_type_dir}/")
            print("\n💡 提示：修改以下配置项即可适配不同页面：")
            print("   - BASE_URL: 基础域名")
            print("   - *_PATH: 目标页面路径")
            print("   - EXPORT_BUTTON_SELECTORS: 导出按钮选择器")
            print("   - DOWNLOAD_BUTTON_SELECTORS: 下载按钮选择器")
            print("   - DATA_READY_PROBES: 页面加载完成探针")
            
            choice = input("\n是否打开配置文件进行编辑? (y/n): ").strip().lower()
            if choice in ['y', 'yes', '是']:
                # 尝试用系统默认编辑器打开
                if os.name == 'nt':  # Windows
                    os.startfile(str(config_path))
                else:  # Unix/Linux/Mac
                    subprocess.run(['open', str(config_path)], check=True)
                print("[OK] 已打开配置文件，请在编辑器中修改后保存")
                return True
            return False
            
        except Exception as e:
            print(f"[FAIL] 无法打开配置文件: {e}")
            config_path = ConfigRegistry.get_config_path(domain)
            print(f"📝 请手动打开文件: {config_path.absolute()}")
            return False


# 便捷函数
def get_config_path(domain: str | DataDomain) -> Path:
    """便捷函数：获取配置文件路径"""
    return ConfigRegistry.get_config_path(domain)


def open_config_file(domain: str | DataDomain) -> bool:
    """便捷函数：打开配置文件"""
    return ConfigRegistry.open_config_file(domain)


def get_domain_config(domain: str | DataDomain) -> DomainConfig:
    """便捷函数：获取数据域配置"""
    return ConfigRegistry.get_domain_config(domain)
