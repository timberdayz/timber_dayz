#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
邮箱登录处理模块

模块化设计：
- 独立的邮箱登录处理器
- 支持多种邮箱类型（QQ、163、Gmail等）
- 统一的登录接口
- 智能密码登录切换
"""

import time
import re
from typing import Optional, Dict, Any
from loguru import logger
from playwright.sync_api import Page, Browser

from .shopee_verification_config import get_verification_config, get_email_login_config, get_debug_screenshot_path


class EmailLoginHandler:
    """邮箱登录处理器（模块化设计）"""
    
    def __init__(self, browser: Browser):
        self.browser = browser
        self.config = get_verification_config()
        
    def login_to_email(self, email: str, password: str) -> Optional[Page]:
        """
        登录到邮箱（统一接口）
        
        Args:
            email: 邮箱地址
            password: 邮箱密码
            
        Returns:
            Page: 登录成功的页面对象，失败返回None
        """
        logger.info(f"📧 开始邮箱登录: {email}")
        
        # 获取邮箱域名
        email_domain = email.split('@')[-1] if '@' in email else 'qq.com'
        email_config = get_email_login_config(email_domain)
        
        try:
            # 创建新页面
            email_page = self.browser.new_page()
            
            # 导航到邮箱登录页面
            logger.info(f"🌐 导航到邮箱: {email_config['login_url']}")
            email_page.goto(email_config['login_url'], wait_until='domcontentloaded')
            
            # 等待页面加载
            email_page.wait_for_timeout(3000)
            
            # 如果需要密码登录切换（主要针对QQ邮箱）
            if email_config.get('needs_password_switch', False):
                success = self._switch_to_password_login(email_page, email_config)
                if not success:
                    logger.warning("⚠️ 密码登录切换失败，尝试继续登录")
            
            # 执行登录操作
            success = self._perform_login(email_page, email, password, email_config)
            
            if success:
                logger.success(f"✅ 邮箱登录成功: {email}")
                return email_page
            else:
                logger.error(f"❌ 邮箱登录失败: {email}")
                email_page.close()
                return None
                
        except Exception as e:
            logger.error(f"❌ 邮箱登录异常 {email}: {e}")
            if 'email_page' in locals():
                try:
                    email_page.close()
                except:
                    pass
            return None
    
    def _switch_to_password_login(self, page: Page, email_config: Dict[str, Any]) -> bool:
        """
        切换到密码登录模式（主要针对QQ邮箱）
        
        Args:
            page: 页面对象
            email_config: 邮箱配置
            
        Returns:
            bool: 切换是否成功
        """
        logger.info("🔄 尝试切换到密码登录模式...")
        
        password_switch_selectors = email_config.get('password_switch_selectors', [])
        
        for selector in password_switch_selectors:
            try:
                logger.debug(f"🔍 尝试选择器: {selector}")
                
                # 等待元素加载
                page.wait_for_timeout(1000)
                
                # 查找切换按钮
                switch_button = None
                if selector.startswith('text='):
                    switch_button = page.get_by_text(selector[5:]).first
                else:
                    switch_button = page.query_selector(selector)
                
                if switch_button and switch_button.is_visible():
                    logger.info(f"✅ 找到密码登录切换按钮: {selector}")
                    
                    # 滚动到元素可见区域
                    switch_button.scroll_into_view_if_needed()
                    
                    # 点击切换按钮
                    switch_button.click()
                    logger.success("🔄 成功切换到密码登录模式")
                    
                    # 等待切换完成
                    page.wait_for_timeout(3000)
                    return True
                    
            except Exception as e:
                logger.debug(f"切换按钮尝试失败 {selector}: {e}")
                continue
        
        logger.warning("⚠️ 未找到有效的密码登录切换按钮")
        return False
    
    def _perform_login(self, page: Page, email: str, password: str, email_config: Dict[str, Any]) -> bool:
        """
        执行邮箱登录操作
        
        Args:
            page: 页面对象
            email: 邮箱地址
            password: 邮箱密码
            email_config: 邮箱配置
            
        Returns:
            bool: 登录是否成功
        """
        try:
            # 填写用户名
            username_filled = self._fill_username(page, email, email_config)
            if not username_filled:
                logger.error("❌ 用户名填写失败")
                return False
            
            # 填写密码
            password_filled = self._fill_password(page, password, email_config)
            if not password_filled:
                logger.error("❌ 密码填写失败")
                return False
            
            # 点击登录按钮
            login_clicked = self._click_login_button(page, email_config)
            if not login_clicked:
                logger.error("❌ 登录按钮点击失败")
                return False
            
            # 等待登录结果
            page.wait_for_timeout(5000)
            
            # 验证登录是否成功
            return self._verify_login_success(page, email_config)
            
        except Exception as e:
            logger.error(f"❌ 登录操作失败: {e}")
            # 保存调试截图
            try:
                debug_screenshot = get_debug_screenshot_path("email_login_failed")
                page.screenshot(path=debug_screenshot)
                logger.info(f"📸 已保存调试截图: {debug_screenshot}")
            except:
                pass
            return False
    
    def _fill_username(self, page: Page, email: str, email_config: Dict[str, Any]) -> bool:
        """填写用户名"""
        username_selectors = email_config.get('username_selectors', [])
        
        for selector in username_selectors:
            try:
                username_input = page.query_selector(selector)
                if username_input and username_input.is_visible():
                    username_input.clear()
                    username_input.fill(email)
                    logger.info(f"✅ 用户名填写成功: {selector}")
                    return True
            except Exception as e:
                logger.debug(f"用户名填写失败 {selector}: {e}")
                continue
        
        logger.error("❌ 未找到可用的用户名输入框")
        return False
    
    def _fill_password(self, page: Page, password: str, email_config: Dict[str, Any]) -> bool:
        """填写密码"""
        password_selectors = email_config.get('password_selectors', [])
        
        for selector in password_selectors:
            try:
                password_input = page.query_selector(selector)
                if password_input and password_input.is_visible():
                    password_input.clear()
                    password_input.fill(password)
                    logger.info(f"✅ 密码填写成功: {selector}")
                    return True
            except Exception as e:
                logger.debug(f"密码填写失败 {selector}: {e}")
                continue
        
        logger.error("❌ 未找到可用的密码输入框")
        return False
    
    def _click_login_button(self, page: Page, email_config: Dict[str, Any]) -> bool:
        """点击登录按钮"""
        # 通用登录按钮选择器
        login_button_selectors = [
            'input[type="submit"]',
            'button[type="submit"]',
            'button:has-text("登录")',
            'button:has-text("登入")',
            'button:has-text("Sign In")',
            'button:has-text("Login")',
            'a:has-text("登录")',
            '.login-btn',
            '.login-button',
            '#login_button',
            '.u-btn'
        ]
        
        for selector in login_button_selectors:
            try:
                login_button = page.query_selector(selector)
                if login_button and login_button.is_visible():
                    login_button.click()
                    logger.info(f"✅ 登录按钮点击成功: {selector}")
                    return True
            except Exception as e:
                logger.debug(f"登录按钮点击失败 {selector}: {e}")
                continue
        
        logger.error("❌ 未找到可用的登录按钮")
        return False
    
    def _verify_login_success(self, page: Page, email_config: Dict[str, Any]) -> bool:
        """验证登录是否成功"""
        # 通用成功标识
        success_indicators = [
            '收件箱',
            'inbox',
            '邮件',
            'mail',
            '发件箱',
            'sent',
            '草稿',
            'draft',
            '.mail-list',
            '.inbox',
            '.mailbox'
        ]
        
        for indicator in success_indicators:
            try:
                if indicator.startswith('.'):
                    element = page.query_selector(indicator)
                else:
                    element = page.query_selector(f'*:has-text("{indicator}")')
                
                if element and element.is_visible():
                    logger.success(f"✅ 邮箱登录成功验证: {indicator}")
                    return True
            except Exception as e:
                logger.debug(f"登录验证失败 {indicator}: {e}")
                continue
        
        # 检查URL是否变化（也是成功的标识）
        current_url = page.url
        if 'login' not in current_url and 'signin' not in current_url:
            logger.success("✅ 邮箱登录成功（URL验证）")
            return True
        
        logger.warning("⚠️ 邮箱登录状态不确定")
        return False
    
    def get_verification_code_from_email(self, email_page: Page, sender_keywords: list = None) -> Optional[str]:
        """
        从邮箱中获取验证码
        
        Args:
            email_page: 邮箱页面对象
            sender_keywords: 发件人关键词列表
            
        Returns:
            str: 验证码，失败返回None
        """
        if sender_keywords is None:
            sender_keywords = ['shopee', 'Shopee', 'SHOPEE', '虾皮']
        
        logger.info("📧 开始从邮箱获取验证码...")
        
        try:
            # 刷新邮箱页面
            email_page.reload(wait_until='domcontentloaded')
            email_page.wait_for_timeout(3000)
            
            # 查找最新的验证码邮件
            verification_email = self._find_verification_email(email_page, sender_keywords)
            
            if verification_email:
                # 提取验证码
                verification_code = self._extract_verification_code(verification_email)
                if verification_code:
                    logger.success(f"✅ 成功获取验证码: {verification_code}")
                    return verification_code
            
            logger.warning("⚠️ 未找到验证码邮件")
            return None
            
        except Exception as e:
            logger.error(f"❌ 获取验证码失败: {e}")
            return None
    
    def _find_verification_email(self, page: Page, sender_keywords: list) -> Optional[str]:
        """查找验证码邮件"""
        # 邮件列表选择器
        email_selectors = [
            '.mail-item',
            '.email-item',
            '.message',
            '.mail-list li',
            '.inbox-item',
            'tr[id*="mail"]',
            '.list-item'
        ]
        
        for selector in email_selectors:
            try:
                emails = page.query_selector_all(selector)
                for email in emails[:5]:  # 只检查最新的5封邮件
                    email_text = email.text_content()
                    if any(keyword in email_text for keyword in sender_keywords):
                        logger.info(f"✅ 找到验证码邮件: {email_text[:50]}...")
                        
                        # 点击邮件查看详情
                        email.click()
                        page.wait_for_timeout(2000)
                        
                        # 获取邮件内容
                        email_content = page.text_content()
                        return email_content
                        
            except Exception as e:
                logger.debug(f"邮件查找失败 {selector}: {e}")
                continue
        
        return None
    
    def _extract_verification_code(self, email_content: str) -> Optional[str]:
        """从邮件内容中提取验证码"""
        # 验证码匹配模式
        patterns = [
            r'验证码[：:\s]*(\d{6})',
            r'verification code[：:\s]*(\d{6})',
            r'code[：:\s]*(\d{6})',
            r'(\d{6})',  # 6位数字
            r'验证码.*?(\d{4,8})',  # 4-8位数字
            r'code.*?(\d{4,8})'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, email_content, re.IGNORECASE)
            if matches:
                # 返回第一个匹配的6位数字
                for match in matches:
                    if len(match) == 6 and match.isdigit():
                        return match
        
        return None 