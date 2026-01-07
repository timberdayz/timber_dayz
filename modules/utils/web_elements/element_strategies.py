#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
元素查找策略

定义不同网站和平台的特定元素查找策略
"""

from typing import Dict, List, Optional
from .element_types import ElementType, ElementSelectorGroup


class ElementStrategy:
    """元素查找策略基类"""
    
    def __init__(self, platform_name: str):
        self.platform_name = platform_name
        self.custom_selectors: Dict[ElementType, ElementSelectorGroup] = {}
    
    def add_custom_selector(self, element_type: ElementType, selector_group: ElementSelectorGroup):
        """添加平台特定的选择器"""
        self.custom_selectors[element_type] = selector_group
    
    def get_selectors(self, element_type: ElementType) -> Optional[ElementSelectorGroup]:
        """获取元素类型的选择器组"""
        return self.custom_selectors.get(element_type)


class MiaoshouERPStrategy(ElementStrategy):
    """妙手ERP平台策略"""
    
    def __init__(self):
        super().__init__("妙手ERP")
        self._setup_miaoshou_selectors()
    
    def _setup_miaoshou_selectors(self):
        """设置妙手ERP特定的选择器"""
        
        # 妙手ERP登录页面元素
        self.add_custom_selector(
            ElementType.USERNAME_INPUT,
            ElementSelectorGroup(ElementType.USERNAME_INPUT)
                .add_selector('input[name="phone"]')
                .add_selector('input[placeholder*="手机号"]')
                .add_selector('input.ant-input')
                .add_selector('.ant-form-item input[type="text"]')
        )
        
        self.add_custom_selector(
            ElementType.PASSWORD_INPUT,
            ElementSelectorGroup(ElementType.PASSWORD_INPUT)
                .add_selector('input[name="password"]')
                .add_selector('input[type="password"]')
                .add_selector('input[placeholder*="密码"]')
                .add_selector('.ant-form-item input[type="password"]')
        )
        
        self.add_custom_selector(
            ElementType.CAPTCHA_INPUT,
            ElementSelectorGroup(ElementType.CAPTCHA_INPUT)
                .add_selector('input[name="verifyCode"]')
                .add_selector('input[placeholder*="验证码"]')
                .add_selector('input[placeholder*="短信验证码"]')
                .add_selector('.ant-form-item input[name*="code"]')
        )
        
        self.add_custom_selector(
            ElementType.LOGIN_BUTTON,
            ElementSelectorGroup(ElementType.LOGIN_BUTTON)
                .add_selector('button[type="submit"]')
                .add_selector('button.ant-btn-primary')
                .add_selector('button:has-text("登录")')
                .add_selector('.ant-btn-primary')
        )


class ShopeeStrategy(ElementStrategy):
    """Shopee平台策略"""
    
    def __init__(self):
        super().__init__("Shopee")
        self._setup_shopee_selectors()
    
    def _setup_shopee_selectors(self):
        """设置Shopee特定的选择器"""
        
        self.add_custom_selector(
            ElementType.USERNAME_INPUT,
            ElementSelectorGroup(ElementType.USERNAME_INPUT)
                .add_selector('input[name="loginKey"]')
                .add_selector('input[name="username"]')
                .add_selector('input[placeholder*="Email"]')
                .add_selector('input[placeholder*="Phone"]')
        )
        
        self.add_custom_selector(
            ElementType.PASSWORD_INPUT,
            ElementSelectorGroup(ElementType.PASSWORD_INPUT)
                .add_selector('input[name="password"]')
                .add_selector('input[type="password"]')
        )
        
        self.add_custom_selector(
            ElementType.CAPTCHA_INPUT,
            ElementSelectorGroup(ElementType.CAPTCHA_INPUT)
                .add_selector('input[name="captcha"]')
                .add_selector('input[placeholder*="验证码"]')
                .add_selector('input[placeholder*="Verification"]')
        )
        
        self.add_custom_selector(
            ElementType.LOGIN_BUTTON,
            ElementSelectorGroup(ElementType.LOGIN_BUTTON)
                .add_selector('button[type="submit"]')
                .add_selector('button:has-text("Log In")')
                .add_selector('button:has-text("登录")')
        )


class Email163Strategy(ElementStrategy):
    """163邮箱策略"""
    
    def __init__(self):
        super().__init__("163邮箱")
        self._setup_163_selectors()
    
    def _setup_163_selectors(self):
        """设置163邮箱特定的选择器（用于iframe中的登录）"""
        
        self.add_custom_selector(
            ElementType.USERNAME_INPUT,
            ElementSelectorGroup(ElementType.USERNAME_INPUT)
                .add_selector('input[name="email"]')
                .add_selector('input[type="text"]')
                .add_selector('input.j-inputtext.dlemail')
                .add_selector('input[placeholder*="邮箱账号"]')
        )
        
        self.add_custom_selector(
            ElementType.PASSWORD_INPUT,
            ElementSelectorGroup(ElementType.PASSWORD_INPUT)
                .add_selector('input[type="password"][name="password"]')
                .add_selector('input.j-inputtext.dlpwd')
                .add_selector('input[placeholder*="输入密码"]')
        )
        
        self.add_custom_selector(
            ElementType.LOGIN_BUTTON,
            ElementSelectorGroup(ElementType.LOGIN_BUTTON)
                .add_selector('a:has-text("登录")')
                .add_selector('a:has-text("登 录")')
                .add_selector('a:has-text("登  录")')  # 163特有的两个空格
        )


# 策略工厂
PLATFORM_STRATEGIES = {
    "miaoshou_erp": MiaoshouERPStrategy,
    "妙手ERP": MiaoshouERPStrategy,
    "shopee": ShopeeStrategy,
    "Shopee": ShopeeStrategy,
    "163邮箱": Email163Strategy,
    "email_163": Email163Strategy,
}


def get_strategy(platform_name: str) -> Optional[ElementStrategy]:
    """
    获取平台策略
    
    Args:
        platform_name: 平台名称
        
    Returns:
        对应的策略实例
    """
    strategy_class = PLATFORM_STRATEGIES.get(platform_name)
    if strategy_class:
        return strategy_class()
    return None


def create_custom_strategy(
    platform_name: str,
    selectors_config: Dict[ElementType, Dict[str, List[str]]]
) -> ElementStrategy:
    """
    创建自定义策略
    
    Args:
        platform_name: 平台名称
        selectors_config: 选择器配置
            格式: {
                ElementType.USERNAME_INPUT: {
                    "selectors": ["input[name='username']", ...],
                    "keywords": ["用户名", "账号", ...]
                },
                ...
            }
    
    Returns:
        自定义策略实例
    """
    strategy = ElementStrategy(platform_name)
    
    for element_type, config in selectors_config.items():
        selector_group = ElementSelectorGroup(element_type)
        
        # 添加CSS选择器
        for selector in config.get("selectors", []):
            selector_group.add_selector(selector)
        
        # 添加关键词
        for keyword in config.get("keywords", []):
            selector_group.add_keyword(keyword)
        
        # 添加属性
        for attr_name, attr_value in config.get("attributes", {}).items():
            selector_group.add_attribute(attr_name, attr_value)
        
        strategy.add_custom_selector(element_type, selector_group)
    
    return strategy
