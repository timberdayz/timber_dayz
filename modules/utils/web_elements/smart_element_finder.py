#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
智能网页元素查找器

基于Playwright的智能元素定位系统，支持多种查找策略和容错机制
"""

import asyncio
import re
from typing import Dict, List, Optional, Any, Union, Tuple
from playwright.async_api import Page, Frame, Locator, ElementHandle
from loguru import logger

from .element_types import ElementType, ElementAction, ELEMENT_SELECTORS
from ..logger import Logger

# 初始化日志  
logger_instance = Logger(__name__)


class SmartElementFinder:
    """智能元素查找器"""
    
    def __init__(self, page: Page, frame: Optional[Frame] = None):
        """
        初始化智能元素查找器
        
        Args:
            page: Playwright页面对象
            frame: 可选的iframe对象，如果在iframe中查找元素
        """
        self.page = page
        self.frame = frame or page
        self.found_elements_cache: Dict[str, Any] = {}
        
    async def find_element(
        self,
        element_type: ElementType,
        timeout: int = 30000,  # 增加默认超时时间，适应VPN环境
        custom_selectors: Optional[List[str]] = None,
        custom_keywords: Optional[List[str]] = None,
        must_be_visible: bool = True,
        must_be_enabled: bool = True
    ) -> Optional[ElementHandle]:
        """
        智能查找单个元素
        
        Args:
            element_type: 元素类型
            timeout: 超时时间（毫秒）
            custom_selectors: 自定义选择器列表
            custom_keywords: 自定义关键词列表
            must_be_visible: 必须可见
            must_be_enabled: 必须启用
            
        Returns:
            找到的元素，未找到返回None
        """
        cache_key = f"{element_type.value}_{must_be_visible}_{must_be_enabled}"
        
        # 检查缓存
        if cache_key in self.found_elements_cache:
            try:
                cached_element = self.found_elements_cache[cache_key]
                if await cached_element.is_visible() if must_be_visible else True:
                    logger.debug(f"使用缓存的{element_type.value}元素")
                    return cached_element
                else:
                    # 缓存的元素不再可见，清除缓存
                    del self.found_elements_cache[cache_key]
            except:
                # 缓存的元素无效，清除缓存
                del self.found_elements_cache[cache_key]
        
        logger.info(f"开始智能查找元素: {element_type.value}")
        
        # 获取预定义的选择器组
        selector_group = ELEMENT_SELECTORS.get(element_type)
        if not selector_group:
            logger.warning(f"未找到{element_type.value}的预定义选择器")
            return None
        
        # 合并自定义选择器和关键词
        all_selectors = (custom_selectors or []) + selector_group.selectors
        all_keywords = (custom_keywords or []) + selector_group.keywords
        
        # 策略1: 直接CSS选择器匹配
        element = await self._find_by_selectors(all_selectors, timeout, must_be_visible, must_be_enabled)
        if element:
            logger.success(f"通过CSS选择器找到{element_type.value}元素")
            self.found_elements_cache[cache_key] = element
            return element
        
        # 策略2: 关键词文本匹配
        element = await self._find_by_keywords(all_keywords, timeout, must_be_visible, must_be_enabled)
        if element:
            logger.success(f"通过关键词匹配找到{element_type.value}元素")
            self.found_elements_cache[cache_key] = element
            return element
        
        # 策略3: 属性模糊匹配
        element = await self._find_by_attributes(selector_group.attributes, timeout, must_be_visible, must_be_enabled)
        if element:
            logger.success(f"通过属性匹配找到{element_type.value}元素")
            self.found_elements_cache[cache_key] = element
            return element
        
        # 策略4: 智能推断（基于上下文和位置）
        element = await self._find_by_context(element_type, timeout, must_be_visible, must_be_enabled)
        if element:
            logger.success(f"通过上下文推断找到{element_type.value}元素")
            self.found_elements_cache[cache_key] = element
            return element
        
        logger.warning(f"未能找到{element_type.value}元素")
        return None
    
    async def find_elements(
        self,
        element_type: ElementType,
        timeout: int = 10000,
        custom_selectors: Optional[List[str]] = None,
        custom_keywords: Optional[List[str]] = None,
        must_be_visible: bool = True
    ) -> List[ElementHandle]:
        """
        智能查找多个元素
        
        Returns:
            找到的元素列表
        """
        logger.info(f"开始智能查找多个元素: {element_type.value}")
        
        selector_group = ELEMENT_SELECTORS.get(element_type)
        if not selector_group:
            logger.warning(f"未找到{element_type.value}的预定义选择器")
            return []
        
        all_selectors = (custom_selectors or []) + selector_group.selectors
        all_keywords = (custom_keywords or []) + selector_group.keywords
        
        elements = []
        
        # 通过选择器查找
        for selector in all_selectors:
            try:
                found_elements = await self.frame.query_selector_all(selector)
                for elem in found_elements:
                    if must_be_visible:
                        is_visible = await elem.is_visible()
                        if not is_visible:
                            continue
                    elements.append(elem)
            except Exception as e:
                logger.debug(f"选择器 {selector} 查找失败: {e}")
                continue
        
        # 通过关键词查找
        if all_keywords:
            keyword_elements = await self._find_multiple_by_keywords(all_keywords, must_be_visible)
            elements.extend(keyword_elements)
        
        # 去重
        unique_elements = []
        for elem in elements:
            if elem not in unique_elements:
                unique_elements.append(elem)
        
        logger.info(f"找到 {len(unique_elements)} 个{element_type.value}元素")
        return unique_elements
    
    async def _find_by_selectors(
        self,
        selectors: List[str],
        timeout: int,
        must_be_visible: bool,
        must_be_enabled: bool
    ) -> Optional[ElementHandle]:
        """通过CSS选择器查找元素"""
        for selector in selectors:
            try:
                element = await self.frame.wait_for_selector(selector, timeout=timeout)
                if element:
                    # 验证可见性和可用性
                    if must_be_visible and not await element.is_visible():
                        logger.debug(f"元素不可见，跳过: {selector}")
                        continue
                    if must_be_enabled and not await element.is_enabled():
                        logger.debug(f"元素不可用，跳过: {selector}")
                        continue
                    
                    logger.debug(f"通过选择器找到元素: {selector}")
                    return element
            except Exception as e:
                logger.debug(f"选择器 {selector} 查找失败: {e}")
                continue
        
        return None
    
    async def _find_by_keywords(
        self,
        keywords: List[str],
        timeout: int,
        must_be_visible: bool,
        must_be_enabled: bool
    ) -> Optional[ElementHandle]:
        """通过关键词文本匹配查找元素"""
        # 查找所有可能的可点击或可输入元素
        candidate_selectors = [
            'input', 'button', 'a', '[role="button"]', '[onclick]',
            'select', 'textarea', 'div[contenteditable]'
        ]
        
        for keyword in keywords:
            for selector in candidate_selectors:
                try:
                    elements = await self.frame.query_selector_all(selector)
                    
                    for element in elements:
                        # 检查元素文本
                        text = await element.inner_text() if element else ''
                        placeholder = await element.get_attribute('placeholder') if element else ''
                        value = await element.get_attribute('value') if element else ''
                        title = await element.get_attribute('title') if element else ''
                        
                        # 关键词匹配
                        search_text = f"{text} {placeholder} {value} {title}".lower()
                        if keyword.lower() in search_text:
                            # 验证可见性和可用性
                            if must_be_visible and not await element.is_visible():
                                continue
                            if must_be_enabled and not await element.is_enabled():
                                continue
                            
                            logger.debug(f"通过关键词 '{keyword}' 找到元素")
                            return element
                            
                except Exception as e:
                    logger.debug(f"关键词 {keyword} 查找失败: {e}")
                    continue
        
        return None
    
    async def _find_multiple_by_keywords(
        self,
        keywords: List[str],
        must_be_visible: bool
    ) -> List[ElementHandle]:
        """通过关键词查找多个元素"""
        elements = []
        
        candidate_selectors = [
            'input', 'button', 'a', '[role="button"]',
            'div', 'span', 'td', 'th', 'li'
        ]
        
        for keyword in keywords:
            for selector in candidate_selectors:
                try:
                    found_elements = await self.frame.query_selector_all(selector)
                    
                    for element in found_elements:
                        text = await element.inner_text() if element else ''
                        if keyword.lower() in text.lower():
                            if must_be_visible and not await element.is_visible():
                                continue
                            elements.append(element)
                            
                except Exception as e:
                    logger.debug(f"多元素关键词查找失败: {e}")
                    continue
        
        return elements
    
    async def _find_by_attributes(
        self,
        attributes: Dict[str, Any],
        timeout: int,
        must_be_visible: bool,
        must_be_enabled: bool
    ) -> Optional[ElementHandle]:
        """通过属性匹配查找元素"""
        if not attributes:
            return None
        
        # 构建属性选择器
        attr_selectors = []
        for attr_name, attr_value in attributes.items():
            if isinstance(attr_value, str):
                attr_selectors.append(f'[{attr_name}*="{attr_value}"]')
            else:
                attr_selectors.append(f'[{attr_name}="{attr_value}"]')
        
        # 尝试各种组合
        for selector in attr_selectors:
            try:
                element = await self.frame.wait_for_selector(selector, timeout=timeout)
                if element:
                    if must_be_visible and not await element.is_visible():
                        continue
                    if must_be_enabled and not await element.is_enabled():
                        continue
                    
                    logger.debug(f"通过属性找到元素: {selector}")
                    return element
            except:
                continue
        
        return None
    
    async def _find_by_context(
        self,
        element_type: ElementType,
        timeout: int,
        must_be_visible: bool,
        must_be_enabled: bool
    ) -> Optional[ElementHandle]:
        """通过上下文推断查找元素"""
        
        # 基于元素类型的智能推断
        if element_type == ElementType.PASSWORD_INPUT:
            # 密码框通常在用户名框后面
            username_elem = await self.find_element(ElementType.USERNAME_INPUT, timeout=2000, must_be_visible=False)
            if username_elem:
                try:
                    # 查找用户名框后面的密码输入框
                    next_inputs = await self.frame.evaluate("""
                        (usernameElem) => {
                            const inputs = Array.from(document.querySelectorAll('input[type="password"]'));
                            return inputs.filter(input => {
                                const rect1 = usernameElem.getBoundingClientRect();
                                const rect2 = input.getBoundingClientRect();
                                return rect2.top >= rect1.top;
                            });
                        }
                    """, username_elem)
                    
                    if next_inputs:
                        password_elem = await self.frame.query_selector(f'input[type="password"]')
                        if password_elem and await password_elem.is_visible():
                            return password_elem
                except:
                    pass
        
        elif element_type == ElementType.LOGIN_BUTTON:
            # 登录按钮通常在表单底部
            try:
                # 查找包含登录相关文本的所有可点击元素
                all_clickable = await self.frame.query_selector_all('a, button, input[type="button"], input[type="submit"], [role="button"], [onclick]')
                
                login_candidates = []
                for elem in all_clickable:
                    try:
                        text = await elem.inner_text() if elem else ''
                        value = await elem.get_attribute('value') if elem else ''
                        
                        # 登录相关的模糊匹配
                        login_patterns = [
                            r'登\s*录', r'登\s{1,3}录', r'sign\s*in', r'login',
                            r'提\s*交', r'确\s*定', r'进\s*入'
                        ]
                        
                        combined_text = f"{text} {value}".lower()
                        for pattern in login_patterns:
                            if re.search(pattern, combined_text, re.IGNORECASE):
                                if must_be_visible and not await elem.is_visible():
                                    continue
                                if must_be_enabled and not await elem.is_enabled():
                                    continue
                                login_candidates.append((elem, text, value))
                                break
                    except:
                        continue
                
                # 优先选择明确包含"登录"的按钮
                for elem, text, value in login_candidates:
                    if '登录' in text or '登录' in value:
                        return elem
                
                # 如果没有明确的登录按钮，选择第一个候选
                if login_candidates:
                    return login_candidates[0][0]
                    
            except Exception as e:
                logger.debug(f"上下文推断登录按钮失败: {e}")
        
        return None
    
    async def perform_action(
        self,
        element: ElementHandle,
        action: ElementAction,
        value: Optional[Any] = None,
        **kwargs
    ) -> bool:
        """
        对元素执行操作
        
        Args:
            element: 目标元素
            action: 操作类型
            value: 操作值（如输入的文本）
            **kwargs: 其他参数
            
        Returns:
            操作是否成功
        """
        try:
            if action == ElementAction.CLICK:
                await element.click()
                logger.debug("执行点击操作")
                
            elif action == ElementAction.FILL:
                if value is not None:
                    await element.fill(str(value))
                    logger.debug(f"执行填充操作: {str(value)[:20]}...")
                    
            elif action == ElementAction.SELECT:
                if value is not None:
                    await element.select_option(value)
                    logger.debug(f"执行选择操作: {value}")
                    
            elif action == ElementAction.CHECK:
                await element.check()
                logger.debug("执行勾选操作")
                
            elif action == ElementAction.UNCHECK:
                await element.uncheck()
                logger.debug("执行取消勾选操作")
                
            elif action == ElementAction.HOVER:
                await element.hover()
                logger.debug("执行悬停操作")
                
            elif action == ElementAction.GET_TEXT:
                text = await element.inner_text()
                logger.debug(f"获取文本: {text[:50]}...")
                return text
                
            elif action == ElementAction.GET_ATTRIBUTE:
                attr_name = kwargs.get('attribute', 'value')
                attr_value = await element.get_attribute(attr_name)
                logger.debug(f"获取属性 {attr_name}: {attr_value}")
                return attr_value
                
            elif action == ElementAction.SCREENSHOT:
                screenshot_path = kwargs.get('path', 'element_screenshot.png')
                await element.screenshot(path=screenshot_path)
                logger.debug(f"元素截图保存: {screenshot_path}")
                
            else:
                logger.warning(f"不支持的操作类型: {action}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"执行操作 {action} 失败: {e}")
            return False
    
    async def smart_login(
        self,
        username: str,
        password: str,
        captcha: Optional[str] = None,
        timeout: int = 30000
    ) -> bool:
        """
        智能登录功能
        
        自动查找用户名框、密码框、验证码框和登录按钮，并执行登录操作
        
        Args:
            username: 用户名
            password: 密码
            captcha: 验证码（可选）
            timeout: 超时时间
            
        Returns:
            登录是否成功
        """
        logger.info("开始智能登录流程")
        
        try:
            # 查找并填充用户名
            username_element = await self.find_element(ElementType.USERNAME_INPUT, timeout=timeout)
            if not username_element:
                logger.error("未找到用户名输入框")
                return False
            
            await self.perform_action(username_element, ElementAction.FILL, username)
            logger.success("用户名填充成功")
            
            # 等待页面可能的动态变化
            await asyncio.sleep(1)
            
            # 查找并填充密码
            password_element = await self.find_element(ElementType.PASSWORD_INPUT, timeout=timeout)
            if not password_element:
                logger.error("未找到密码输入框")
                return False
            
            await self.perform_action(password_element, ElementAction.FILL, password)
            logger.success("密码填充成功")
            
            # 如果提供了验证码，查找并填充验证码
            if captcha:
                captcha_element = await self.find_element(ElementType.CAPTCHA_INPUT, timeout=5000)
                if captcha_element:
                    await self.perform_action(captcha_element, ElementAction.FILL, captcha)
                    logger.success("验证码填充成功")
                else:
                    logger.warning("验证码输入框未找到，但已提供验证码")
            
            # 等待表单完全准备
            await asyncio.sleep(1)
            
            # 查找并点击登录按钮
            login_button = await self.find_element(ElementType.LOGIN_BUTTON, timeout=timeout)
            if not login_button:
                logger.error("未找到登录按钮")
                return False
            
            await self.perform_action(login_button, ElementAction.CLICK)
            logger.success("登录按钮点击成功")
            
            logger.success("智能登录流程完成")
            return True
            
        except Exception as e:
            logger.error(f"智能登录失败: {e}")
            return False
    
    def clear_cache(self):
        """清空元素缓存"""
        self.found_elements_cache.clear()
        logger.debug("元素缓存已清空")
