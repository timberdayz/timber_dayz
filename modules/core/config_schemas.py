#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
配置Schema验证

使用Pydantic定义和验证YAML配置文件的结构，确保配置的正确性和一致性。
支持的配置文件：
- accounts_config.yaml
- proxy_config.yaml
- collection_config.yaml
- multi_region_routing.yaml
"""

from typing import Dict, List, Optional, Union, Any
from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import datetime

from .logger import get_logger

logger = get_logger(__name__)


class PlatformType(str, Enum):
    """支持的平台类型"""
    MIAOSHOU_ERP = "妙手ERP"
    SHOPEE = "Shopee"
    AMAZON = "Amazon"
    LAZADA = "Lazada"
    TIKTOK = "TikTok"


class RegionType(str, Enum):
    """支持的地区类型"""
    CN = "CN"
    SG = "SG"
    MY = "MY"
    TH = "TH"
    VN = "VN"
    TW = "TW"
    US = "US"
    UK = "UK"
    DE = "DE"
    FR = "FR"


class CurrencyType(str, Enum):
    """支持的货币类型"""
    CNY = "CNY"
    SGD = "SGD"
    MYR = "MYR"
    THB = "THB"
    VND = "VND"
    TWD = "TWD"
    USD = "USD"
    GBP = "GBP"
    EUR = "EUR"


class ProxyType(str, Enum):
    """代理类型"""
    DIRECT = "direct"
    SYSTEM = "system"
    CUSTOM = "custom"


class AccountConfig(BaseModel):
    """单个账号配置"""
    account_id: str = Field(..., description="账号唯一标识")
    platform: PlatformType = Field(..., description="平台类型")
    store_name: str = Field(..., description="店铺名称")
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")
    region: RegionType = Field(..., description="地区")
    currency: CurrencyType = Field(..., description="货币")
    enabled: bool = Field(True, description="是否启用")
    proxy_required: bool = Field(False, description="是否需要代理")
    proxy_region: Optional[str] = Field(None, description="代理地区")
    login_url: Optional[str] = Field(None, description="登录URL")
    notes: Optional[str] = Field(None, description="备注")

    @field_validator('account_id')
    @classmethod
    def validate_account_id(cls, v):
        if not v or len(v) < 3:
            raise ValueError('账号ID长度至少3个字符')
        return v

    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError('密码长度至少6个字符')
        return v

    @model_validator(mode='after')
    def validate_proxy_settings(self):
        if self.proxy_required and not self.proxy_region:
            raise ValueError('需要代理时必须指定代理地区')
        return self


class PlatformConfig(BaseModel):
    """平台配置"""
    base_url: Optional[str] = Field(None, description="基础URL")
    base_urls: Optional[Dict[str, str]] = Field(None, description="多地区URL")
    login_path: str = Field(..., description="登录路径")
    data_paths: Dict[str, str] = Field(..., description="数据路径")
    proxy_required: bool = Field(False, description="是否需要代理")

    @model_validator(mode='after')
    def validate_urls(self):
        if not self.base_url and not self.base_urls:
            raise ValueError('必须提供base_url或base_urls')
        return self


class RetryConfig(BaseModel):
    """重试配置"""
    max_attempts: int = Field(3, ge=1, le=10, description="最大重试次数")
    delay_between_retries: int = Field(10, ge=1, le=300, description="重试间隔(秒)")


class BrowserConfig(BaseModel):
    """浏览器配置"""
    headless: bool = Field(False, description="是否无头模式")
    window_size: str = Field("1920,1080", description="窗口大小")
    user_agent: str = Field(..., description="用户代理")

    @field_validator('window_size')
    @classmethod
    def validate_window_size(cls, v):
        try:
            width, height = v.split(',')
            width, height = int(width), int(height)
            if width < 800 or height < 600:
                raise ValueError('窗口尺寸过小')
        except ValueError:
            raise ValueError('窗口大小格式错误，应为"宽度,高度"')
        return v


class CollectionSettings(BaseModel):
    """数据采集配置"""
    interval_between_accounts: int = Field(5, ge=1, le=60, description="账号间隔(秒)")
    page_load_timeout: int = Field(30, ge=10, le=120, description="页面加载超时(秒)")
    element_wait_timeout: int = Field(20, ge=5, le=60, description="元素等待超时(秒)")
    retry: RetryConfig = Field(..., description="重试配置")
    browser: BrowserConfig = Field(..., description="浏览器配置")


class EncryptionConfig(BaseModel):
    """加密配置"""
    algorithm: str = Field("AES-256", description="加密算法")
    key_rotation_days: int = Field(30, ge=1, le=365, description="密钥轮换天数")


class AccessControlConfig(BaseModel):
    """访问控制配置"""
    max_login_attempts: int = Field(3, ge=1, le=10, description="最大登录尝试次数")
    lockout_duration: int = Field(300, ge=60, le=3600, description="锁定时长(秒)")


class LoggingConfig(BaseModel):
    """日志配置"""
    mask_passwords: bool = Field(True, description="是否脱敏密码")
    mask_usernames: bool = Field(False, description="是否脱敏用户名")
    log_level: str = Field("INFO", description="日志级别")

    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'日志级别必须是: {valid_levels}')
        return v.upper()


class SecurityConfig(BaseModel):
    """安全配置"""
    encryption: EncryptionConfig = Field(..., description="加密配置")
    access_control: AccessControlConfig = Field(..., description="访问控制")
    logging: LoggingConfig = Field(..., description="日志配置")


class ExportSettings(BaseModel):
    """导出配置"""
    default_format: str = Field("excel", description="默认导出格式")
    supported_formats: List[str] = Field(..., description="支持的格式")
    output_directory: str = Field("data/exports", description="输出目录")
    filename_pattern: str = Field(..., description="文件名模式")

    @model_validator(mode='after')
    def validate_default_format(self):
        if self.supported_formats and self.default_format not in self.supported_formats:
            raise ValueError(f'默认格式必须在支持的格式中: {self.supported_formats}')
        return self


class AccountsConfigSchema(BaseModel):
    """账号配置文件Schema"""
    accounts: Dict[str, List[AccountConfig]] = Field(..., description="账号组")
    platform_configs: Dict[str, PlatformConfig] = Field(..., description="平台配置")
    collection_settings: CollectionSettings = Field(..., description="采集配置")
    security: SecurityConfig = Field(..., description="安全配置")
    export_settings: ExportSettings = Field(..., description="导出配置")

    @field_validator('accounts')
    @classmethod
    def validate_accounts(cls, v):
        if not v:
            raise ValueError('至少需要配置一个账号组')

        # 检查账号ID唯一性
        all_account_ids = []
        for group_name, accounts in v.items():
            for account in accounts:
                if account.account_id in all_account_ids:
                    raise ValueError(f'账号ID重复: {account.account_id}')
                all_account_ids.append(account.account_id)

        return v


class ProxySettings(BaseModel):
    """代理设置"""
    type: ProxyType = Field(..., description="代理类型")
    server: Optional[str] = Field(None, description="代理服务器")
    username: Optional[str] = Field(None, description="用户名")
    password: Optional[str] = Field(None, description="密码")
    description: str = Field(..., description="描述")

    @model_validator(mode='after')
    def validate_custom_proxy(self):
        if self.type == ProxyType.CUSTOM and not self.server:
            raise ValueError('自定义代理必须提供服务器地址')
        return self


class SpecialRule(BaseModel):
    """特殊规则"""
    proxy_type: ProxyType = Field(..., description="代理类型")
    browser_args: Optional[List[str]] = Field(None, description="浏览器参数")
    description: str = Field(..., description="描述")


class ProxyConfigSchema(BaseModel):
    """代理配置文件Schema"""
    version: str = Field(..., description="配置版本")
    description: str = Field(..., description="配置描述")
    direct_domains: List[str] = Field(..., description="直连域名")
    vpn_domains: List[str] = Field(..., description="VPN域名")
    proxy_settings: Dict[str, ProxySettings] = Field(..., description="代理设置")
    special_rules: Optional[Dict[str, SpecialRule]] = Field(None, description="特殊规则")

    @field_validator('direct_domains', 'vpn_domains')
    @classmethod
    def validate_domains(cls, v):
        if not v:
            raise ValueError('域名列表不能为空')

        for domain in v:
            if not domain or '.' not in domain:
                raise ValueError(f'无效的域名: {domain}')

        return v
