#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
邮箱验证码处理器

实现双网页协同验证码处理：
1. A网页点击"发送至邮箱"
2. B网页自动登录邮箱获取验证码
3. 将验证码输入到A网页完成验证
"""

import time
import re
import os
from typing import Dict, Any, Optional, Tuple
from playwright.sync_api import sync_playwright, Page, BrowserContext
from modules.utils.logger import logger


class EmailVerificationHandler:
    """邮箱验证码处理器"""
    
    def __init__(self, account_config: Dict[str, Any]):
        self.account_config = account_config
        # 支持两种配置格式：新的email_config和旧的分散字段格式
        if 'email_config' in account_config:
            self.email_config = account_config.get('email_config', {})
        else:
            # 兼容旧的分散字段格式
            self.email_config = {
                'email_url': account_config.get('Email address', ''),
                'username': account_config.get('Email account', account_config.get('E-mail', '')),
                'password': account_config.get('Email password', ''),
                'license': account_config.get('Email License', '')
            }
        self.email_browser = None
        self.email_context = None
        self.email_page = None
        
        # 邮箱登录选择器配置
        self.email_login_selectors = {
            # 163邮箱
            '163.com': {
                'username': 'input[placeholder*="邮箱账号"], input[placeholder*="用户名"], input[name="email"], input[name="username"], #loginDiv input[name="email"]',
                'password': 'input[type="password"], input[name="password"], #loginDiv input[name="password"]',
                'login_button': 'input[type="submit"], button:has-text("登录"), button:has-text("登入"), #loginDiv input[type="submit"], .loginBtn, div[onclick*="login"], span[onclick*="login"], a[role="button"]:has-text("登录"), div[tabindex]:has-text("登录")',
                'verification_input': 'input[name="captcha"]',
                'verification_prompt': '请输入验证码',
                'switch_to_password': 'a:has-text("密码登录"), .js-tab-password, #switchToPassword, [data-module="login.password"], .loginTab a:nth-child(2)',
                'login_frame': '#loginDiv, #dloginframe, iframe[name="dloginframe"]'
            },
            # QQ邮箱
            'qq.com': {
                'username': 'input[name="u"]',
                'password': 'input[name="p"]', 
                'login_button': 'input[type="submit"]',
                'verification_input': 'input[name="verifycode"]',
                'verification_prompt': '请输入验证码'
            },
            # Gmail
            'gmail.com': {
                'username': 'input[type="email"]',
                'password': 'input[type="password"]',
                'login_button': 'button:has-text("Next")',
                'verification_input': 'input[type="text"]',
                'verification_prompt': 'Enter verification code'
            },
            # 通用选择器
            'default': {
                'username': 'input[type="email"], input[name="email"], input[name="username"]',
                'password': 'input[type="password"], input[name="password"]',
                'login_button': 'button:has-text("登录"), button:has-text("登入"), button:has-text("Login"), input[type="submit"]',
                'verification_input': 'input[placeholder*="验证码"], input[placeholder*="captcha"], input[name="captcha"]',
                'verification_prompt': '验证码'
            }
        }
    
    def get_verification_code_from_email(self, playwright_instance) -> Optional[str]:
        """从邮箱获取验证码"""
        try:
            logger.info("📧 启动邮箱验证码获取流程...")
            
            # 验证邮箱配置
            if not self._validate_email_config():
                return None
            
            # 启动邮箱浏览器
            if not self._setup_email_browser(playwright_instance):
                return None
            
            try:
                # 登录邮箱
                if not self._login_to_email():
                    return None
                
                # 获取验证码
                verification_code = self._fetch_verification_code()
                return verification_code
                
            finally:
                # 清理邮箱浏览器
                self._cleanup_email_browser()
                
        except Exception as e:
            logger.error(f"❌ 邮箱验证码获取失败: {e}")
            return None
    
    def _validate_email_config(self) -> bool:
        """验证邮箱配置"""
        try:
            email_url = self.email_config.get('email_url')
            username = self.email_config.get('username')
            password = self.email_config.get('password')
            
            if not email_url:
                logger.error("❌ 未配置邮箱URL (email_url)")
                return False
                
            if not username:
                logger.error("❌ 未配置邮箱用户名 (username)")
                return False
                
            if not password:
                logger.error("❌ 未配置邮箱密码 (password)")
                return False
            
            logger.info(f"✅ 邮箱配置验证通过: {username}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 邮箱配置验证失败: {e}")
            return False
    
    def _setup_email_browser(self, playwright_instance) -> bool:
        """设置邮箱浏览器"""
        try:
            logger.info("🌐 启动邮箱浏览器...")
            
            # 启动新的浏览器实例（用于邮箱）
            self.email_browser = playwright_instance.chromium.launch(
                headless=False,  # 显示浏览器以便用户观察
                args=['--no-sandbox', '--disable-web-security']
            )
            
            self.email_context = self.email_browser.new_context()
            self.email_page = self.email_context.new_page()
            
            logger.info("✅ 邮箱浏览器启动成功")
            return True
            
        except Exception as e:
            logger.error(f"❌ 邮箱浏览器启动失败: {e}")
            return False
    
    def _login_to_email(self) -> bool:
        """登录邮箱"""
        try:
            email_url = self.email_config.get('email_url')
            username = self.email_config.get('username')
            password = self.email_config.get('password')
            
            logger.info(f"🔗 访问邮箱: {email_url}")
            # VPN环境下增加超时时间到120秒，并添加重试机制
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    logger.info(f"🔄 第 {attempt + 1}/{max_retries} 次尝试访问邮箱...")
                    self.email_page.goto(email_url, timeout=120000)  # 2分钟超时
                    # VPN环境下等待网络稳定
                    logger.info("⏳ 等待页面完全加载（VPN环境适配）...")
                    self.email_page.wait_for_load_state("domcontentloaded", timeout=60000)
                    time.sleep(5)  # 额外等待动态内容加载
                    logger.info("✅ 邮箱页面加载成功")
                    break
                except Exception as e:
                    logger.warning(f"⚠️ 第 {attempt + 1} 次访问失败: {e}")
                    if attempt == max_retries - 1:
                        raise e
                    logger.info("🔄 等待10秒后重试...")
                    time.sleep(10)  # VPN环境下增加重试间隔
            
            # 获取邮箱类型对应的选择器
            selectors = self._get_email_selectors(username)
            
            # 调试页面结构（开发环境）
            # self._debug_page_structure()  # 暂时禁用以简化输出
            
            # 处理动态登录框（如163邮箱的扫码/密码切换）
            if not self._handle_dynamic_login_form(selectors):
                logger.error("❌ 动态登录框处理失败")
                return False
            
            # 填写用户名
            logger.info("📝 填写邮箱用户名...")
            username_input = self._find_input_element(selectors['username'])
            if username_input:
                # 清空输入框并填写用户名
                username_input.click()
                username_input.fill('')  # 先清空
                username_input.fill(username)
                logger.info("✅ 用户名已填写")
            else:
                logger.error("❌ 未找到用户名输入框")
                return False
            
            # 填写密码
            logger.info("🔐 填写邮箱密码...")
            password_input = self._find_input_element(selectors['password'])
            if password_input:
                # 清空输入框并填写密码
                password_input.click()
                password_input.fill('')  # 先清空
                password_input.fill(password)
                logger.info("✅ 密码已填写")
            else:
                logger.error("❌ 未找到密码输入框")
                return False
            
            # 点击登录按钮
            logger.info("🖱️ 点击登录按钮...")
            login_button = self._find_input_element(selectors['login_button'])
            if login_button:
                login_button.click()
                logger.info("✅ 登录按钮已点击")
            else:
                # 如果没有找到登录按钮，尝试其他提交方式
                logger.info("🔄 未找到登录按钮，尝试其他提交方式...")
                
                # 方法1：在密码框中按回车键
                if password_input:
                    logger.info("⌨️ 在密码框中按回车键提交...")
                    password_input.press('Enter')
                    logger.info("✅ 已按回车键提交")
                else:
                    # 方法2：查找并提交表单
                    logger.info("📝 尝试查找并提交表单...")
                    forms = self.email_page.query_selector_all('form')
                    if forms:
                        for form in forms:
                            if form.is_visible():
                                logger.info("✅ 找到可见表单，尝试提交...")
                                try:
                                    # 使用JavaScript提交表单
                                    self.email_page.evaluate('(form) => form.submit()', form)
                                    logger.info("✅ 表单已提交")
                                    break
                                except Exception as e:
                                    logger.debug(f"表单提交失败: {e}")
                    else:
                        logger.error("❌ 未找到任何提交方式")
                        return False
            
            # VPN环境下需要更长的等待时间
            logger.info("⏳ 等待登录响应（VPN环境适配）...")
            time.sleep(8)
            
            # 检查是否需要验证码
            verification_type = self._check_email_verification_needed(selectors)
            if verification_type != "no_verification":
                if not self._handle_email_verification(verification_type, selectors):
                    return False
            
            # 验证登录成功
            return self._verify_email_login_success()
                
        except Exception as e:
            logger.error(f"❌ 邮箱登录失败: {e}")
            return False
    
    def _get_email_selectors(self, email: str) -> Dict[str, str]:
        """根据邮箱类型获取选择器"""
        try:
            # 提取邮箱域名
            domain = email.split('@')[-1].lower() if '@' in email else ''
            
            # 返回对应的选择器
            if domain in self.email_login_selectors:
                return self.email_login_selectors[domain]
            else:
                return self.email_login_selectors['default']
                
        except Exception as e:
            logger.warning(f"⚠️ 获取邮箱选择器失败，使用默认配置: {e}")
            return self.email_login_selectors['default']
    
    def _handle_dynamic_login_form(self, selectors: Dict[str, str]) -> bool:
        """处理动态登录框（如163邮箱的扫码/密码切换）"""
        try:
            logger.info("🔄 检测动态登录框...")
            
            # VPN环境下需要更长的等待时间
            time.sleep(5)
            
            # 检查是否有登录框切换按钮（如163邮箱的密码登录）
            if 'switch_to_password' in selectors:
                switch_selectors = selectors['switch_to_password'].split(', ')
                for selector in switch_selectors:
                    try:
                        switch_btn = self.email_page.query_selector(selector)
                        if switch_btn and switch_btn.is_visible():
                            logger.info(f"✅ 找到登录方式切换按钮: {selector}")
                            switch_btn.click()
                            logger.info("🔄 已切换到密码登录模式")
                            time.sleep(3)  # 等待切换完成
                            break
                    except Exception as e:
                        logger.debug(f"切换按钮检测失败 {selector}: {e}")
                        continue
            
            # 检查是否有iframe登录框（如163邮箱）
            iframe_found = False
            
            # 先尝试查找URS登录iframe（163邮箱特有）
            urs_iframes = self.email_page.query_selector_all('iframe[id*="URS-iframe"]')
            if urs_iframes:
                for iframe in urs_iframes:
                    try:
                        if iframe.is_visible():
                            logger.info(f"✅ 找到163邮箱URS登录iframe")
                            self.email_page = iframe.content_frame()
                            logger.info("🔄 已切换到URS iframe内部")
                            iframe_found = True
                            break
                    except Exception as e:
                        logger.debug(f"URS iframe切换失败: {e}")
            
            # 如果没找到URS iframe，尝试其他iframe
            if not iframe_found and 'login_frame' in selectors:
                frame_selectors = selectors['login_frame'].split(', ')
                for selector in frame_selectors:
                    try:
                        frame = self.email_page.query_selector(selector)
                        if frame and frame.is_visible():
                            logger.info(f"✅ 检测到登录iframe: {selector}")
                            # 如果是iframe，需要切换到iframe内部
                            if 'iframe' in selector:
                                self.email_page = frame.content_frame()
                                logger.info("🔄 已切换到iframe内部")
                                iframe_found = True
                            break
                    except Exception as e:
                        logger.debug(f"iframe检测失败 {selector}: {e}")
                        continue
            
            # 如果切换到了iframe，等待iframe内容加载
            if iframe_found:
                time.sleep(3)
                logger.info("⏳ 等待iframe内容加载...")
                # 调试iframe内容
                # self._debug_iframe_content()  # 暂时禁用以简化输出
            
            logger.info("✅ 动态登录框处理完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ 动态登录框处理失败: {e}")
            return False
    
    def _find_input_element(self, selectors: str):
        """查找输入元素，支持多选择器"""
        try:
            selector_list = selectors.split(', ')
            for selector in selector_list:
                try:
                    element = self.email_page.query_selector(selector)
                    if element and element.is_visible():
                        logger.debug(f"✅ 找到元素: {selector}")
                        return element
                except Exception as e:
                    logger.debug(f"选择器失败 {selector}: {e}")
                    continue
            
            logger.debug(f"❌ 未找到任何匹配的元素: {selectors}")
            return None
            
        except Exception as e:
            logger.error(f"❌ 查找元素失败: {e}")
            return None
    
    def _debug_page_structure(self):
        """调试页面结构"""
        try:
            logger.info("🔍 调试页面结构...")
            
            # 获取页面标题和URL
            title = self.email_page.title()
            url = self.email_page.url
            logger.info(f"📄 页面标题: {title}")
            logger.info(f"🔗 页面URL: {url}")
            
            # 查找所有input元素
            inputs = self.email_page.query_selector_all('input')
            logger.info(f"📝 找到 {len(inputs)} 个input元素:")
            
            for i, input_elem in enumerate(inputs[:10]):  # 只显示前10个
                try:
                    input_type = input_elem.get_attribute('type') or 'text'
                    input_name = input_elem.get_attribute('name') or ''
                    input_placeholder = input_elem.get_attribute('placeholder') or ''
                    input_id = input_elem.get_attribute('id') or ''
                    is_visible = input_elem.is_visible()
                    
                    logger.info(f"  {i+1}. type={input_type}, name={input_name}, id={input_id}, placeholder={input_placeholder}, visible={is_visible}")
                except Exception as e:
                    logger.debug(f"调试input元素失败: {e}")
            
            # 查找所有button元素
            buttons = self.email_page.query_selector_all('button')
            logger.info(f"🔘 找到 {len(buttons)} 个button元素:")
            
            for i, btn in enumerate(buttons[:5]):  # 只显示前5个
                try:
                    btn_text = btn.text_content() or ''
                    btn_class = btn.get_attribute('class') or ''
                    is_visible = btn.is_visible()
                    
                    logger.info(f"  {i+1}. text={btn_text}, class={btn_class}, visible={is_visible}")
                except Exception as e:
                    logger.debug(f"调试button元素失败: {e}")
            
            # 查找所有iframe
            iframes = self.email_page.query_selector_all('iframe')
            logger.info(f"🖼️ 找到 {len(iframes)} 个iframe元素:")
            
            for i, iframe in enumerate(iframes[:3]):  # 只显示前3个
                try:
                    iframe_src = iframe.get_attribute('src') or ''
                    iframe_name = iframe.get_attribute('name') or ''
                    iframe_id = iframe.get_attribute('id') or ''
                    is_visible = iframe.is_visible()
                    
                    logger.info(f"  {i+1}. src={iframe_src}, name={iframe_name}, id={iframe_id}, visible={is_visible}")
                except Exception as e:
                    logger.debug(f"调试iframe元素失败: {e}")
            
            # 查找所有可点击的元素（a标签）
            links = self.email_page.query_selector_all('a')
            logger.info(f"🔗 找到 {len(links)} 个链接元素:")
            
            for i, link in enumerate(links[:10]):  # 只显示前10个
                try:
                    link_text = link.text_content() or ''
                    link_href = link.get_attribute('href') or ''
                    link_class = link.get_attribute('class') or ''
                    is_visible = link.is_visible()
                    
                    if '登录' in link_text or '密码' in link_text or 'login' in link_text.lower():
                        logger.info(f"  {i+1}. text={link_text}, href={link_href}, class={link_class}, visible={is_visible}")
                except Exception as e:
                    logger.debug(f"调试link元素失败: {e}")
                    
        except Exception as e:
            logger.debug(f"页面结构调试失败: {e}")
    
    def _debug_iframe_content(self):
        """调试iframe内容结构"""
        try:
            logger.info("🔍 调试iframe内容结构...")
            
            # 查找iframe内的input元素
            inputs = self.email_page.query_selector_all('input')
            logger.info(f"📝 iframe内找到 {len(inputs)} 个input元素:")
            
            for i, input_elem in enumerate(inputs[:10]):  # 只显示前10个
                try:
                    input_type = input_elem.get_attribute('type') or 'text'
                    input_name = input_elem.get_attribute('name') or ''
                    input_placeholder = input_elem.get_attribute('placeholder') or ''
                    input_id = input_elem.get_attribute('id') or ''
                    is_visible = input_elem.is_visible()
                    
                    logger.info(f"  {i+1}. type={input_type}, name={input_name}, id={input_id}, placeholder={input_placeholder}, visible={is_visible}")
                except Exception as e:
                    logger.debug(f"调试iframe input元素失败: {e}")
            
            # 查找iframe内的button元素（包括所有可能的登录按钮）
            buttons = self.email_page.query_selector_all('button, input[type="submit"], a[role="button"], div[role="button"], span[role="button"], .btn, .button, [onclick*="login"]')
            logger.info(f"🔘 iframe内找到 {len(buttons)} 个按钮元素:")
            
            for i, btn in enumerate(buttons[:10]):  # 显示前10个
                try:
                    btn_text = btn.text_content() or ''
                    btn_type = btn.get_attribute('type') or ''
                    btn_class = btn.get_attribute('class') or ''
                    btn_onclick = btn.get_attribute('onclick') or ''
                    is_visible = btn.is_visible()
                    
                    logger.info(f"  {i+1}. text={btn_text}, type={btn_type}, class={btn_class}, onclick={btn_onclick}, visible={is_visible}")
                except Exception as e:
                    logger.debug(f"调试iframe button元素失败: {e}")
            
            # 查找所有可点击的div元素（可能是登录按钮）
            clickable_divs = self.email_page.query_selector_all('div[tabindex], div[onclick], span[onclick]')
            logger.info(f"🖱️ iframe内找到 {len(clickable_divs)} 个可点击元素:")
            
            for i, div in enumerate(clickable_divs[:5]):  # 显示前5个
                try:
                    div_text = div.text_content() or ''
                    div_class = div.get_attribute('class') or ''
                    div_onclick = div.get_attribute('onclick') or ''
                    is_visible = div.is_visible()
                    
                    if '登录' in div_text or 'login' in div_text.lower() or 'submit' in div_onclick.lower():
                        logger.info(f"  {i+1}. text={div_text}, class={div_class}, onclick={div_onclick}, visible={is_visible}")
                except Exception as e:
                    logger.debug(f"调试可点击元素失败: {e}")
                    
        except Exception as e:
            logger.debug(f"iframe内容调试失败: {e}")
    
    def _check_email_verification_needed(self, selectors: Dict[str, str]) -> str:
        """
        检查是否需要验证以及验证类型
        返回值：
        - "login_success": 已经登录成功
        - "password_error": 密码错误
        - "slide_captcha": 图形滑动验证码
        - "sms_verification": 手机验证码
        - "image_captcha": 图片验证码
        - "text_verification": 文本验证码
        - "no_verification": 无需验证
        - "unknown": 未知状态
        """
        try:
            current_url = self.email_page.url
            logger.info(f"🔍 当前页面URL: {current_url}")
            
            # 等待页面稳定
            time.sleep(2)
            
            # 获取页面内容用于关键词检测
            try:
                page_content = self.email_page.content().lower()
            except:
                page_content = ""
            
            # 0. 检查验证码错误（新增）
            verification_error_keywords = [
                '验证码错误', '验证码不正确', '验证码填错', '验证码输入错误',
                'captcha error', 'verification code error', 'captcha incorrect',
                'captcha wrong', '请输入正确的验证码', '验证码有误', '验证失败',
                'captcha failed', 'verification failed', '验证码过期',
                '验证码填错了', '请输入正确的验证码'
            ]
            
            # 检查页面内容中的验证码错误提示
            if any(keyword in page_content for keyword in verification_error_keywords):
                logger.error("❌ 检测到验证码错误提示")
                return "verification_code_error"
            
            # 1. 检查密码错误
            password_error_keywords = [
                '密码错误', '密码不正确', '用户名或密码错误', 'password incorrect', 
                'wrong password', 'invalid password', '账号或密码错误', 
                '登录失败', 'login failed', '认证失败', '用户名不存在',
                '账号不存在', 'account not found', '验证失败'
            ]
            
            # 检查页面内容中的密码错误提示
            if any(keyword in page_content for keyword in password_error_keywords):
                logger.error("❌ 检测到密码错误提示")
                return "password_error"
            
            # 检查错误提示元素
            error_selectors = [
                '.error', '.err-msg', '.login-error', '[class*="error"]',
                '.warning', '.alert', '.message', '[role="alert"]',
                '#errormsg', '#error_msg', '.errormsg', '.captcha-error',
                '.verify-error', '[class*="captcha-error"]', '[id*="error"]'
            ]
            
            for selector in error_selectors:
                try:
                    error_elements = self.email_page.query_selector_all(selector)
                    for element in error_elements:
                        if element.is_visible():
                            error_text = element.text_content().lower()
                            # 优先检查验证码错误
                            if any(keyword in error_text for keyword in verification_error_keywords):
                                logger.error(f"❌ 检测到验证码错误元素: {error_text}")
                                return "verification_code_error"
                            # 然后检查密码错误
                            elif any(keyword in error_text for keyword in password_error_keywords):
                                logger.error(f"❌ 检测到密码错误元素: {error_text}")
                                return "password_error"
                except:
                    continue
            
            # 1. 检查是否已经登录成功
            success_indicators = [
                '收件箱', 'inbox', '邮箱', 'mail', '写邮件', 'compose', 
                '发送', 'send', '草稿', 'draft', '退出', 'logout', 'sign out'
            ]
            
            if any(indicator in page_content for indicator in success_indicators):
                logger.info("✅ 检测到邮箱登录成功")
                return "login_success"
            
            # 检查URL是否包含成功标识
            if any(indicator in current_url for indicator in ['mail', 'inbox', 'home']):
                logger.info("✅ 根据URL判断邮箱登录成功")
                return "login_success"
            
            # 2. 图形滑动验证码 (优先级最高)
            slide_elements = self.email_page.query_selector_all('[class*="slide"], [class*="drag"], [id*="slide"], [id*="drag"]')
            if slide_elements or any(keyword in page_content for keyword in [
                '滑动验证', 'slide', '拖拽', 'drag', '图形验证', '请拖动滑块', 
                '向右滑动', '滑动完成验证', '拖动滑块'
            ]):
                logger.info("🔍 检测到图形滑动验证码")
                return "slide_captcha"
            
            # 3. 手机验证码
            if any(keyword in page_content for keyword in [
                '手机验证码', '短信验证码', 'sms', '发送验证码', '获取验证码',
                '输入手机号', '手机号码', 'phone', 'mobile', '短信'
            ]):
                logger.info("🔍 检测到手机验证码需求")
                return "sms_verification"
            
            # 4. 图片验证码
            captcha_images = self.email_page.query_selector_all('img[src*="captcha"], img[src*="verify"], img[alt*="验证码"], img[class*="captcha"]')
            if captcha_images:
                logger.info("🔍 检测到图片验证码")
                return "image_captcha"
            
            # 5. 通用验证码输入框
            verification_input = self.email_page.query_selector(selectors['verification_input'])
            if verification_input and verification_input.is_visible():
                logger.info("🔍 检测到邮箱登录验证码输入框")
                return "text_verification"
            
            # 6. 检查页面内容中的验证码关键词
            if any(keyword in page_content for keyword in ['验证码', 'captcha', 'verification code']):
                logger.info("🔍 检测到验证码相关提示")
                return "text_verification"
            
            logger.info("🔍 未检测到验证需求")
            return "no_verification"
            
        except Exception as e:
            logger.debug(f"验证检测异常: {e}")
            return "unknown"
    
    def _handle_email_verification(self, verification_type: str, selectors: Dict[str, str]) -> bool:
        """处理邮箱登录验证"""
        try:
            logger.info(f"🔐 处理邮箱登录验证: {verification_type}")
            
            if verification_type == "login_success":
                logger.info("🎉 邮箱已经登录成功")
                return True
            
            elif verification_type == "verification_code_error":
                logger.error("❌ 检测到验证码错误")
                return self._handle_verification_code_error()
            
            elif verification_type == "password_error":
                logger.error("❌ 检测到密码错误")
                print("\n" + "="*60)
                print("❌ 邮箱密码错误")
                print("="*60)
                print("🔍 系统检测到您的邮箱密码不正确")
                print("📝 请检查以下配置文件中的密码设置：")
                print("   - local_accounts.py (主要账号配置文件)")
                print("   - account_key.key (加密账号配置文件，通过local_accounts.py同步生成)")
                print("\n💡 解决方法：")
                print("   1. 确认邮箱密码是否正确")
                print("   2. 检查是否需要使用授权码而非密码")
                print("   3. 确认邮箱是否已开启IMAP/POP3服务")
                print("   4. 更新配置文件中的密码")
                print("="*60)
                
                # 询问用户是否要更新密码
                user_input = input("\n🔧 是否现在修改邮箱密码？(y/n): ").strip().lower()
                if user_input in ['y', 'yes', '是']:
                    new_password = input("请输入新的邮箱密码（或授权码）: ").strip()
                    if new_password:
                        # 更新内存中的配置
                        self.email_config['password'] = new_password
                        
                        # 尝试更新local_accounts.py文件
                        success = self._update_local_accounts_password(new_password)
                        if success:
                            print("✅ 密码已更新到local_accounts.py，重新尝试登录...")
                        else:
                            print("⚠️ 内存中的密码已更新，但未能自动更新local_accounts.py")
                            print("💡 请手动更新local_accounts.py文件中的相应邮箱密码")
                        
                        return self._login_to_email()
                    else:
                        print("❌ 密码不能为空")
                        return False
                else:
                    print("❌ 请手动修改配置文件后重新运行程序")
                    return False
            
            elif verification_type == "slide_captcha":
                return self._handle_slide_captcha()
            
            elif verification_type == "sms_verification":
                return self._handle_sms_verification()
            
            elif verification_type == "image_captcha":
                return self._handle_image_captcha()
            
            elif verification_type == "text_verification":
                return self._handle_text_verification(selectors)
            
            elif verification_type == "no_verification":
                logger.info("✅ 无需验证")
                return True
            
            else:
                logger.warning(f"⚠️ 未知验证类型: {verification_type}")
                print(f"\n⚠️ 检测到未知的验证类型: {verification_type}")
                print("💡 请手动完成验证后继续...")
                input("完成后请按回车键继续...")
                return True
                
        except Exception as e:
            logger.error(f"验证处理失败: {e}")
            return False
    
    def _update_local_accounts_password(self, new_password: str) -> bool:
        """更新local_accounts.py文件中的邮箱密码"""
        try:
            import re
            
            # 读取local_accounts.py文件
            local_accounts_path = "local_accounts.py"
            if not os.path.exists(local_accounts_path):
                logger.warning("local_accounts.py文件不存在")
                return False
            
            with open(local_accounts_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 获取当前邮箱用户名
            current_email = self.email_config.get('username', '')
            if not current_email:
                logger.warning("无法获取当前邮箱用户名")
                return False
            
            # 创建备份
            backup_path = f"local_accounts_backup_{int(time.time())}.py"
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"已创建备份文件: {backup_path}")
            
            # 更新邮箱密码 - 尝试多种匹配模式
            updated = False
            
            # 模式1: Email password在Email account之前
            pattern1 = r'("Email password":\\s*")[^"]*(".*?(?=\\s*"Email account":\\s*"' + re.escape(current_email) + '"))'
            if re.search(pattern1, content, re.DOTALL):
                content = re.sub(pattern1, r'\1' + new_password + r'\2', content, flags=re.DOTALL)
                updated = True
                logger.info("使用模式1更新密码")
            
            # 模式2: Email account在Email password之前
            if not updated:
                pattern2 = r'("Email account":\\s*"' + re.escape(current_email) + '".*?"Email password":\\s*")[^"]*(")'
                if re.search(pattern2, content, re.DOTALL):
                    content = re.sub(pattern2, r'\1' + new_password + r'\2', content, flags=re.DOTALL)
                    updated = True
                    logger.info("使用模式2更新密码")
            
            # 模式3: 简单的Email License匹配（可能是授权码字段）
            if not updated:
                pattern3 = r'("Email account":\\s*"' + re.escape(current_email) + '".*?"Email License":\\s*")[^"]*(")'
                if re.search(pattern3, content, re.DOTALL):
                    content = re.sub(pattern3, r'\1' + new_password + r'\2', content, flags=re.DOTALL)
                    updated = True
                    logger.info("使用模式3更新Email License")
            
            if not updated:
                logger.warning(f"未找到邮箱 {current_email} 的配置条目")
                return False
            
            # 写入更新后的内容
            with open(local_accounts_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.success(f"✅ 已成功更新 {current_email} 的邮箱密码")
            return True
            
        except Exception as e:
            logger.error(f"更新local_accounts.py失败：{e}")
            return False
    
    def _handle_verification_code_error(self) -> bool:
        """处理验证码错误，要求重新输入"""
        try:
            logger.info("🔄 处理验证码错误，准备重新输入...")
            
            print("\n" + "="*60)
            print("❌ 验证码输入错误")
            print("="*60)
            print("🔍 系统检测到您输入的验证码不正确")
            print("💡 请重新输入正确的验证码")
            print("⚠️ 请仔细核对验证码内容")
            print("="*60)
            
            # 等待页面恢复并关闭错误提示
            time.sleep(2)
            
            # 尝试关闭错误提示弹窗
            try:
                close_selectors = [
                    '.close', '.modal-close', '[aria-label="close"]', 
                    '.popup-close', '.dialog-close', 'button:has-text("确定")',
                    'button:has-text("知道了")', 'button:has-text("关闭")'
                ]
                
                for selector in close_selectors:
                    try:
                        close_btn = self.email_page.query_selector(selector)
                        if close_btn and close_btn.is_visible():
                            close_btn.click()
                            logger.info(f"✅ 关闭错误提示: {selector}")
                            time.sleep(1)
                            break
                    except:
                        continue
            except Exception as e:
                logger.debug(f"关闭错误提示失败: {e}")
            
            # 重新检测验证类型并处理
            selectors = self._get_email_selectors()
            verification_type = self._detect_email_verification_type(selectors)
            
            logger.info(f"🔄 重新检测到验证类型: {verification_type}")
            
            # 处理重新检测到的验证类型
            if verification_type == "image_captcha":
                print("🔄 准备重新输入图片验证码...")
                return self._handle_image_captcha()
            elif verification_type == "text_verification":
                print("🔄 准备重新输入文本验证码...")
                return self._handle_text_verification(selectors)
            elif verification_type == "verification_code_error":
                # 如果仍然是错误状态，给用户手动机会
                print("⚠️ 系统检测仍有验证码错误")
                print("💡 请手动清除错误提示并重新输入验证码")
                user_input = input("是否重试？(y/n): ").strip().lower()
                if user_input in ['y', 'yes', '是']:
                    # 递归重试，但限制次数
                    return self._handle_verification_code_error()
                else:
                    input("请手动完成验证后按回车继续...")
                    return True
            elif verification_type == "login_success":
                logger.info("🎉 验证码错误已解决，登录成功")
                return True
            else:
                print("💡 请重新输入正确的验证码")
                input("请手动完成验证后按回车继续...")
                return True
                
        except Exception as e:
            logger.error(f"验证码错误处理失败: {e}")
            print("⚠️ 自动处理验证码错误失败")
            print("💡 请手动清除错误提示并重新输入正确的验证码")
            input("请手动完成验证后按回车继续...")
            return True
    
    def _handle_slide_captcha(self) -> bool:
        """处理滑动验证码"""
        try:
            logger.info("🎯 处理滑动验证码...")
            
            # 查找滑动验证码元素
            slide_selectors = [
                '[class*="slide"]', '[class*="drag"]', '[id*="slide"]', 
                '[id*="captcha"]', '.nc_wrapper', '.nc-container',
                '[data-nc-idx]', '.captcha-slider'
            ]
            
            slider = None
            for selector in slide_selectors:
                elements = self.email_page.query_selector_all(selector)
                for element in elements:
                    if element.is_visible():
                        slider = element
                        logger.info(f"✅ 找到滑动验证码元素: {selector}")
                        break
                if slider:
                    break
            
            if not slider:
                logger.error("❌ 未找到滑动验证码元素")
                return self._manual_verification_fallback("滑动验证码")
            
            # 尝试自动滑动
            try:
                # 获取滑块位置和目标位置
                bbox = slider.bounding_box()
                if bbox:
                    start_x = bbox['x'] + 10
                    start_y = bbox['y'] + bbox['height'] / 2
                    end_x = bbox['x'] + bbox['width'] - 10
                    end_y = start_y
                    
                    logger.info(f"🖱️ 执行滑动操作: ({start_x}, {start_y}) -> ({end_x}, {end_y})")
                    
                    # 模拟人工滑动（使用页面对象而不是iframe对象）
                    main_page = self.email_page.page if hasattr(self.email_page, 'page') else self.email_browser.pages[0]
                    main_page.mouse.move(start_x, start_y)
                    main_page.mouse.down()
                    
                    # 分步滑动，模拟人工操作
                    steps = 10
                    for i in range(steps):
                        progress = (i + 1) / steps
                        current_x = start_x + (end_x - start_x) * progress
                        main_page.mouse.move(current_x, end_y, steps=2)
                        time.sleep(0.1)
                    
                    main_page.mouse.up()
                    
                    logger.info("✅ 滑动操作完成")
                    time.sleep(3)
                    
                    # 检查是否验证成功
                    if self._check_slide_captcha_success():
                        logger.info("✅ 滑动验证成功")
                        return True
                    else:
                        logger.warning("⚠️ 滑动验证可能失败，尝试手动处理")
                        return self._manual_verification_fallback("滑动验证码")
                        
            except Exception as e:
                logger.error(f"❌ 自动滑动失败: {e}")
                return self._manual_verification_fallback("滑动验证码")
                
        except Exception as e:
            logger.error(f"❌ 滑动验证码处理失败: {e}")
            return False
    
    def _check_slide_captcha_success(self) -> bool:
        """检查滑动验证码是否成功"""
        try:
            # 等待验证结果
            time.sleep(2)
            
            # 检查页面是否有成功标识
            page_content = self.email_page.text_content('body').lower()
            
            # 检查是否进入邮箱主页面
            if any(keyword in page_content for keyword in [
                '收件箱', 'inbox', '邮件列表', '发件箱'
            ]):
                return True
            
            # 检查是否还有验证码相关元素
            slide_elements = self.email_page.query_selector_all('[class*="slide"], [class*="drag"]')
            return len(slide_elements) == 0
            
        except Exception as e:
            logger.debug(f"滑动验证检查异常: {e}")
            return False
    
    def _handle_sms_verification(self) -> bool:
        """处理手机验证码"""
        try:
            logger.info("📱 处理手机验证码...")
            
            print("\n" + "="*60)
            print("📱 手机验证码")
            print("="*60)
            print("📧 邮箱登录需要手机验证码")
            print("👀 请查看您的手机短信")
            print("📝 验证码通常是4-6位数字")
            
            # 获取用户输入的验证码
            user_code = input("\n请输入手机验证码: ").strip()
            
            if not user_code:
                logger.error("❌ 手机验证码不能为空")
                return False
            
            # 查找验证码输入框
            verification_input = None
            input_selectors = [
                'input[name*="sms"]', 'input[name*="phone"]', 'input[name*="mobile"]',
                'input[id*="sms"]', 'input[id*="phone"]', 'input[placeholder*="手机"]',
                'input[placeholder*="短信"]', 'input[placeholder*="验证码"]',
                'input[class*="sms"]', 'input[class*="phone"]', 'input[type="text"]',
                '#sms', '#phone_code', '.sms-input', '.phone-input'
            ]
            
            for selector in input_selectors:
                try:
                    element = self.email_page.query_selector(selector)
                    if element and element.is_visible():
                        verification_input = element
                        logger.info(f"✅ 找到手机验证码输入框: {selector}")
                        break
                except:
                    continue
            
            if not verification_input:
                logger.error("❌ 未找到手机验证码输入框")
                print("⚠️ 请手动填写验证码到页面上的输入框")
                input("完成后请按回车键继续...")
                return True
            
            # 填写验证码
            try:
                verification_input.clear()
                verification_input.fill(user_code)
                logger.info("✅ 手机验证码已填写")
                
                # 尝试自动提交
                submit_success = False
                
                # 1. 查找提交按钮
                submit_selectors = [
                    'button[type="submit"]', 'input[type="submit"]', 
                    'button:has-text("登录")', 'button:has-text("确认")', 
                    'button:has-text("提交")', '.login-btn', '#login', '.submit-btn'
                ]
                
                for selector in submit_selectors:
                    try:
                        submit_btn = self.email_page.query_selector(selector)
                        if submit_btn and submit_btn.is_visible():
                            submit_btn.click()
                            logger.info(f"✅ 点击提交按钮: {selector}")
                            submit_success = True
                            break
                    except:
                        continue
                
                # 2. 如果没找到按钮，尝试按回车
                if not submit_success:
                    verification_input.press('Enter')
                    logger.info("✅ 在验证码输入框按回车提交")
                    submit_success = True
                
                if submit_success:
                    print("✅ 验证码已提交，等待验证结果...")
                    time.sleep(3)
                    return True
                else:
                    logger.warning("⚠️ 未能自动提交，请手动点击登录按钮")
                    input("请手动点击登录按钮后按回车继续...")
                    return True
                    
            except Exception as e:
                logger.error(f"填写验证码失败: {e}")
                print("⚠️ 自动填写失败，请手动操作")
                input("请手动填写验证码并提交后按回车继续...")
                return True
            
        except Exception as e:
            logger.error(f"手机验证码处理失败: {e}")
            return self._manual_verification_fallback("手机验证码")
    
    def _handle_image_captcha(self) -> bool:
        """处理图片验证码"""
        try:
            logger.info("🖼️ 处理图片验证码...")
            
            # 先截图保存当前页面
            screenshot_path = None
            try:
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = f"temp/screenshots/image_captcha_{timestamp}.png"
                
                # 确保目录存在
                import os
                os.makedirs("temp/screenshots", exist_ok=True)
                
                self.email_page.screenshot(path=screenshot_path)
                logger.info(f"📸 已保存页面截图: {screenshot_path}")
            except Exception as e:
                logger.debug(f"截图保存失败: {e}")
            
            # 尝试定位图片验证码
            captcha_image = None
            captcha_selectors = [
                'img[src*="captcha"]', 'img[src*="verify"]', 'img[alt*="验证码"]', 
                'img[class*="captcha"]', 'img[class*="verify"]', '.captcha img',
                '[id*="captcha"] img', '[class*="captcha-img"]', '.verify-img'
            ]
            
            for selector in captcha_selectors:
                try:
                    elements = self.email_page.query_selector_all(selector)
                    for element in elements:
                        if element.is_visible():
                            captcha_image = element
                            logger.info(f"✅ 找到验证码图片: {selector}")
                            break
                    if captcha_image:
                        break
                except:
                    continue
            
            print("\n" + "="*60)
            print("🖼️ 图片验证码")
            print("="*60)
            print("📧 邮箱登录需要图片验证码")
            
            if captcha_image:
                try:
                    # 高亮验证码图片
                    self.email_page.evaluate("""(element) => {
                        element.style.border = '3px solid red';
                        element.style.boxShadow = '0 0 10px red';
                        element.scrollIntoView({behavior: 'smooth', block: 'center'});
                    }""", captcha_image)
                    print("🎯 已高亮显示验证码图片（红色边框）")
                    
                    # 尝试获取图片信息
                    try:
                        bbox = captcha_image.bounding_box()
                        if bbox:
                            print(f"📍 验证码图片位置: 左上角({bbox['x']:.0f}, {bbox['y']:.0f}), 大小({bbox['width']:.0f}×{bbox['height']:.0f})")
                    except:
                        pass
                        
                except Exception as e:
                    logger.debug(f"高亮图片失败: {e}")
                    print("🔍 请查看邮箱登录页面的验证码图片")
            else:
                print("🔍 请查看邮箱登录页面的验证码图片")
                print("⚠️ 系统未能自动定位验证码图片，请手动查找")
            
            if screenshot_path:
                print(f"📸 页面截图已保存至: {screenshot_path}")
            
            print("\n👀 请仔细查看验证码图片")
            print("📝 验证码通常是4-6位数字或字母")
            print("💡 如果看不清楚，可以尝试点击图片刷新")
            
            # 获取用户输入的验证码
            user_code = input("\n请输入图片验证码: ").strip()
            
            if not user_code:
                logger.error("❌ 图片验证码不能为空")
                return False
            
            # 查找验证码输入框
            verification_input = None
            input_selectors = [
                'input[name*="captcha"]', 'input[id*="captcha"]', 'input[placeholder*="验证码"]',
                'input[placeholder*="captcha"]', 'input[class*="captcha"]', 'input[type="text"]',
                '#captcha', '.captcha-input', '[data-testid*="captcha"]'
            ]
            
            for selector in input_selectors:
                try:
                    element = self.email_page.query_selector(selector)
                    if element and element.is_visible():
                        verification_input = element
                        logger.info(f"✅ 找到验证码输入框: {selector}")
                        break
                except:
                    continue
            
            if not verification_input:
                logger.error("❌ 未找到验证码输入框")
                print("⚠️ 请手动填写验证码到页面上的输入框")
                input("完成后请按回车键继续...")
                return True
            
            # 填写验证码
            try:
                verification_input.clear()
                verification_input.fill(user_code)
                logger.info("✅ 图片验证码已填写")
                
                # 高亮输入框
                try:
                    self.email_page.evaluate("""(element) => {
                        element.style.border = '2px solid green';
                        element.style.backgroundColor = '#e8f5e8';
                    }""", verification_input)
                except:
                    pass
                
                # 尝试自动提交
                submit_success = False
                
                # 1. 查找提交按钮
                submit_selectors = [
                    'button[type="submit"]', 'input[type="submit"]', 
                    'button:has-text("登录")', 'button:has-text("确认")', 
                    'button:has-text("提交")', '.login-btn', '#login', '.submit-btn'
                ]
                
                for selector in submit_selectors:
                    try:
                        submit_btn = self.email_page.query_selector(selector)
                        if submit_btn and submit_btn.is_visible():
                            submit_btn.click()
                            logger.info(f"✅ 点击提交按钮: {selector}")
                            submit_success = True
                            break
                    except:
                        continue
                
                # 2. 如果没找到按钮，尝试按回车
                if not submit_success:
                    verification_input.press('Enter')
                    logger.info("✅ 在验证码输入框按回车提交")
                    submit_success = True
                
                if submit_success:
                    print("✅ 验证码已提交，等待验证结果...")
                    time.sleep(3)
                    
                    # 检查验证结果
                    selectors = self._get_email_selectors()
                    verification_result = self._detect_email_verification_type(selectors)
                    
                    # 清除高亮效果
                    try:
                        if captcha_image:
                            self.email_page.evaluate("""(element) => {
                                element.style.border = '';
                                element.style.boxShadow = '';
                            }""", captcha_image)
                    except:
                        pass
                    
                    # 根据验证结果决定下一步
                    if verification_result == "verification_code_error":
                        logger.error("❌ 图片验证码错误，需要重新输入")
                        return self._handle_verification_code_error()
                    elif verification_result == "login_success":
                        logger.info("🎉 图片验证码验证成功，登录成功")
                        return True
                    elif verification_result in ["image_captcha", "text_verification"]:
                        logger.warning("⚠️ 验证码可能错误，页面仍显示验证码输入")
                        print("⚠️ 验证码可能输入错误，请重新输入")
                        return self._handle_verification_code_error()
                    else:
                        # 假设成功
                        logger.info("✅ 图片验证码处理完成")
                        return True
                else:
                    logger.warning("⚠️ 未能自动提交，请手动点击登录按钮")
                    input("请手动点击登录按钮后按回车继续...")
                    return True
                    
            except Exception as e:
                logger.error(f"填写验证码失败: {e}")
                print("⚠️ 自动填写失败，请手动操作")
                input("请手动填写验证码并提交后按回车继续...")
                return True
            
        except Exception as e:
            logger.error(f"图片验证码处理失败: {e}")
            return self._manual_verification_fallback("图片验证码")
    
    def _handle_text_verification(self, selectors: Dict[str, str]) -> bool:
        """处理文本验证码"""
        try:
            logger.info("📝 处理文本验证码...")
            
            print("\n" + "="*60)
            print("🔐 邮箱登录验证码")
            print("="*60)
            print("📧 邮箱登录需要验证码")
            print("👀 请查看邮箱登录页面的验证码")
            print("📝 请在下方输入验证码:")
            
            # 获取用户输入的验证码
            user_code = input("请输入验证码: ").strip()
            
            if not user_code:
                logger.error("❌ 验证码不能为空")
                return False
            
            # 填写验证码
            verification_input = self.email_page.query_selector(selectors['verification_input'])
            if verification_input:
                verification_input.fill(user_code)
                logger.info("✅ 验证码已填写")
                
                # 再次点击登录或确认
                login_button = self.email_page.query_selector(selectors['login_button'])
                if login_button:
                    login_button.click()
                    logger.info("✅ 确认按钮已点击")
                    time.sleep(3)
                else:
                    # 尝试按回车键
                    verification_input.press('Enter')
                    logger.info("✅ 已按回车键提交")
                    time.sleep(3)
                
                # 检查验证结果
                verification_result = self._detect_email_verification_type(selectors)
                
                # 根据验证结果决定下一步
                if verification_result == "verification_code_error":
                    logger.error("❌ 文本验证码错误，需要重新输入")
                    return self._handle_verification_code_error()
                elif verification_result == "login_success":
                    logger.info("🎉 文本验证码验证成功，登录成功")
                    return True
                elif verification_result in ["image_captcha", "text_verification"]:
                    logger.warning("⚠️ 验证码可能错误，页面仍显示验证码输入")
                    print("⚠️ 验证码可能输入错误，请重新输入")
                    return self._handle_verification_code_error()
                else:
                    # 假设成功
                    logger.info("✅ 文本验证码处理完成")
                    return True
            else:
                logger.error("❌ 未找到验证码输入框")
                return False
                
        except Exception as e:
            logger.error(f"❌ 文本验证码处理失败: {e}")
            return False
    
    def _manual_verification_fallback(self, verification_type: str) -> bool:
        """手动验证回退方案"""
        try:
            print("\n" + "="*60)
            print(f"⚠️ {verification_type}自动处理失败")
            print("="*60)
            print("📧 请手动完成验证后继续")
            print("👀 请在浏览器中完成验证操作")
            print("✅ 完成后请按回车键继续...")
            
            input("按回车键继续...")
            
            # 等待页面更新
            time.sleep(3)
            
            # 检查是否验证成功
            return self._verify_email_login_success()
            
        except Exception as e:
            logger.error(f"❌ 手动验证回退失败: {e}")
            return False
    
    def _verify_email_login_success(self) -> bool:
        """验证邮箱登录成功"""
        try:
            logger.info("🔍 验证邮箱登录状态...")
            
            # 等待页面加载
            time.sleep(5)
            
            current_url = self.email_page.url
            page_title = self.email_page.title()
            
            # 检查登录成功的标志
            success_indicators = [
                '收件箱', 'inbox', '邮箱', 'mail',
                '写邮件', 'compose', '发件箱', 'sent'
            ]
            
            page_content = self.email_page.text_content('body').lower()
            
            for indicator in success_indicators:
                if indicator in page_content or indicator in page_title.lower():
                    logger.info(f"✅ 邮箱登录成功: {indicator}")
                    return True
            
            # 检查URL变化
            if 'login' not in current_url and 'signin' not in current_url:
                logger.info("✅ 邮箱登录成功 (URL检查)")
                return True
            
            logger.error(f"❌ 邮箱登录失败，当前页面: {page_title}")
            return False
            
        except Exception as e:
            logger.error(f"❌ 验证邮箱登录状态失败: {e}")
            return False
    
    def _fetch_verification_code(self) -> Optional[str]:
        """获取验证码邮件"""
        try:
            logger.info("📬 搜索Shopee验证码邮件...")
            
            # 等待邮件到达
            max_wait = 120  # 最多等待2分钟
            for attempt in range(max_wait // 10):
                logger.info(f"🔍 第 {attempt + 1} 次搜索验证码邮件...")
                
                # 刷新邮箱
                try:
                    if hasattr(self.email_page, 'reload'):
                        self.email_page.reload()
                    else:
                        # 如果是iframe，需要重新加载主页面
                        main_page = self.email_browser.pages[0]
                        main_page.reload()
                    time.sleep(2)
                except Exception as reload_error:
                    logger.debug(f"页面重载失败: {reload_error}")
                    time.sleep(2)
                
                # 搜索Shopee相关邮件
                verification_code = self._search_shopee_verification_email()
                if verification_code:
                    return verification_code
                
                logger.info("⏳ 等待10秒后重新搜索...")
                time.sleep(10)
            
            logger.error("❌ 未找到Shopee验证码邮件")
            return None
            
        except Exception as e:
            logger.error(f"❌ 获取验证码邮件失败: {e}")
            return None
    
    def _search_shopee_verification_email(self) -> Optional[str]:
        """搜索Shopee验证码邮件"""
        try:
            # Shopee邮件特征
            shopee_keywords = ['shopee', 'verification', '验证', 'OTP', '验证码']
            
            # 查找邮件列表
            email_links = self.email_page.query_selector_all('a[href*="mail"], tr[class*="mail"], div[class*="mail"]')
            
            for email_element in email_links:
                try:
                    email_text = email_element.text_content().lower()
                    
                    # 检查是否是Shopee验证码邮件
                    if any(keyword in email_text for keyword in shopee_keywords):
                        logger.info("✅ 找到Shopee验证码邮件")
                        
                        # 点击邮件
                        email_element.click()
                        time.sleep(3)
                        
                        # 提取验证码
                        verification_code = self._extract_verification_code()
                        if verification_code:
                            return verification_code
                            
                except Exception as e:
                    logger.debug(f"邮件检查失败: {e}")
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"❌ 搜索验证码邮件失败: {e}")
            return None
    
    def _extract_verification_code(self) -> Optional[str]:
        """从邮件内容中提取验证码"""
        try:
            # 获取邮件内容
            email_content = self.email_page.text_content('body')
            
            # 验证码正则模式
            code_patterns = [
                r'验证码[：:\s]*(\d{6})',  # 验证码: 123456
                r'OTP[：:\s]*(\d{6})',     # OTP: 123456
                r'code[：:\s]*(\d{6})',    # code: 123456
                r'(\d{6})',                # 直接匹配6位数字
            ]
            
            for pattern in code_patterns:
                matches = re.findall(pattern, email_content, re.IGNORECASE)
                if matches:
                    code = matches[0]
                    if code.isdigit() and len(code) == 6:
                        logger.info(f"✅ 成功提取验证码: {code}")
                        return code
            
            logger.error("❌ 未能从邮件中提取验证码")
            return None
            
        except Exception as e:
            logger.error(f"❌ 提取验证码失败: {e}")
            return None
    
    def _cleanup_email_browser(self):
        """清理邮箱浏览器"""
        try:
            if self.email_page:
                self.email_page.close()
            if self.email_context:
                self.email_context.close()
            if self.email_browser:
                self.email_browser.close()
            
            logger.info("✅ 邮箱浏览器已清理")
            
        except Exception as e:
            logger.debug(f"清理邮箱浏览器异常: {e}") 