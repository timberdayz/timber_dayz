#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
浏览器邮箱OTP客户端

使用Playwright模拟真实浏览器登录邮箱获取验证码
绕过IMAP安全限制，支持163、QQ等各种邮箱
"""

import time
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from loguru import logger


class BrowserEmailOTPClient:
    """浏览器邮箱OTP客户端"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化浏览器邮箱客户端
        
        Args:
            config: 邮箱配置
                - email_address: 邮箱地址
                - email_password: 邮箱密码（网页登录密码，不是授权码）
                - email_url: 邮箱网址（如 https://mail.163.com）
                - platform: 平台名称
                - account_id: 账号ID
        """
        self.config = config
        self.email_address = config["email_address"]
        self.email_password = config["email_password"]
        self.email_url = config.get("email_url", "https://mail.163.com")
        self.platform = config.get("platform", "unknown")
        self.account_id = config.get("account_id", "unknown")
        
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        
        logger.info(f"初始化浏览器邮箱OTP客户端: {self.email_address} ({self.platform})")
    
    async def start_browser(self) -> bool:
        """
        启动浏览器
        
        Returns:
            启动是否成功
        """
        try:
            logger.info("正在启动浏览器...")
            
            self.playwright = await async_playwright().start()
            
            # 启动浏览器（使用Chrome，模拟真实用户）
            self.browser = await self.playwright.chromium.launch(
                headless=False,  # 显示浏览器窗口，方便调试
                args=[
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                    '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36'
                ]
            )
            
            # 创建上下文
            self.context = await self.browser.new_context(
                viewport={'width': 1280, 'height': 720},
                locale='zh-CN'
            )
            
            # 创建页面
            self.page = await self.context.new_page()
            
            logger.success("浏览器启动成功")
            return True
            
        except Exception as e:
            logger.error(f"启动浏览器失败: {e}")
            return False
    
    async def login_email(self) -> bool:
        """
        登录邮箱
        
        Returns:
            登录是否成功
        """
        try:
            logger.info(f"正在登录邮箱: {self.email_url}")
            
            # 访问邮箱首页
            await self.page.goto(self.email_url)
            await self.page.wait_for_load_state('networkidle')
            
            # 等待登录表单出现
            await self.page.wait_for_timeout(2000)
            
            # 针对163邮箱的登录逻辑
            if "163.com" in self.email_url:
                return await self._login_163()
            elif "qq.com" in self.email_url:
                return await self._login_qq()
            else:
                logger.warning(f"未知邮箱类型: {self.email_url}")
                return False
                
        except Exception as e:
            logger.error(f"登录邮箱失败: {e}")
            return False
    
    async def _login_163(self) -> bool:
        """163邮箱登录"""
        try:
            logger.info("执行163邮箱登录...")
            
            # 等待页面加载
            await self.page.wait_for_timeout(5000)
            
            # 163邮箱使用iframe，需要先找到登录iframe
            login_frame = await self._find_login_iframe()
            if not login_frame:
                logger.error("未找到163邮箱登录iframe")
                return False
            
            logger.info("找到登录iframe，开始在iframe中查找登录元素...")
            
            # 在iframe中查找用户名输入框
            username_selectors = [
                'input[name="email"]',
                'input[name="username"]', 
                'input[placeholder*="邮箱"]',
                'input[placeholder*="用户名"]',
                'input[type="email"]',
                'input[type="text"]',
                '.loginform input[type="text"]',
                '#username',
                'input.u-input[type="text"]',  # 163特有样式
                '.j-inputtext',  # 163特有样式
            ]
            
            username_input = None
            for selector in username_selectors:
                try:
                    username_input = await login_frame.wait_for_selector(selector, timeout=3000)
                    if username_input:
                        logger.debug(f"在iframe中找到用户名输入框: {selector}")
                        break
                except:
                    continue
            
            if not username_input:
                logger.error("在iframe中未找到用户名输入框")
                # 尝试获取iframe中的所有输入框进行调试
                await self._debug_iframe_inputs(login_frame)
                return False
            
            # 输入用户名
            await username_input.fill(self.email_address)
            logger.debug(f"已输入邮箱地址: {self.email_address}")
            
            # 在iframe中查找密码输入框
            password_selectors = [
                'input[type="password"][name="password"]',  # 163特有：name="password"
                'input[type="password"]',
                'input[name="password"]',
                '.loginform input[type="password"]',
                '#password',
                'input.u-input[type="password"]',
                'input.j-inputtext.dlpwd',  # 163特有样式
            ]
            
            password_input = None
            for selector in password_selectors:
                try:
                    password_input = await login_frame.wait_for_selector(selector, timeout=3000)
                    if password_input:
                        # 检查输入框是否可见
                        is_visible = await password_input.is_visible()
                        if is_visible:
                            logger.debug(f"在iframe中找到可见密码输入框: {selector}")
                            break
                        else:
                            logger.debug(f"密码输入框不可见，跳过: {selector}")
                except:
                    continue
            
            if not password_input:
                logger.error("在iframe中未找到密码输入框")
                return False
            
            # 输入密码
            await password_input.fill(self.email_password)
            logger.debug("已输入密码")
            
            # 在iframe中查找登录按钮
            # 163邮箱的登录按钮是<a>标签，文本为"登  录"（中间有空格）
            login_selectors = [
                'a:has-text("登录")',
                'a:has-text("登 录")',
                'a:has-text("登  录")',  # 163特有：两个空格
                'input[type="submit"]',
                'button[type="submit"]',
                'button:has-text("登录")',
                '.loginbtn',
                '#loginBtn',
                '.j-btn',
                '.u-btn',
                'input.u-btn[value*="登录"]'
            ]
            
            login_button = None
            for selector in login_selectors:
                try:
                    login_button = await login_frame.wait_for_selector(selector, timeout=3000)
                    if login_button:
                        # 检查按钮是否可见
                        is_visible = await login_button.is_visible()
                        is_enabled = await login_button.is_enabled()
                        if is_visible and is_enabled:
                            button_text = await login_button.inner_text()
                            logger.debug(f"在iframe中找到可用登录按钮: {selector}, 文本: '{button_text.strip()}'")
                            break
                        else:
                            logger.debug(f"登录按钮不可用，跳过: {selector} (可见:{is_visible}, 启用:{is_enabled})")
                except Exception as e:
                    logger.debug(f"尝试登录按钮选择器失败: {selector} - {e}")
                    continue
            
            # 如果没找到，尝试更通用的方式
            if not login_button:
                logger.warning("未找到预定义的登录按钮，尝试查找包含'登录'文本的所有元素...")
                try:
                    # 查找所有包含登录文本的可点击元素
                    all_clickable = await login_frame.query_selector_all('a, button, input[type="button"], input[type="submit"], [role="button"], [onclick]')
                    
                    for elem in all_clickable:
                        try:
                            text = await elem.inner_text()
                            value = await elem.get_attribute('value') or ''
                            is_visible = await elem.is_visible()
                            is_enabled = await elem.is_enabled()
                            
                            if (('登录' in text or '登 录' in text or '登  录' in text or 
                                 '登录' in value or 'login' in text.lower()) and 
                                is_visible and is_enabled):
                                login_button = elem
                                logger.debug(f"找到登录按钮候选: 文本='{text.strip()}', 值='{value}'")
                                break
                        except:
                            continue
                            
                except Exception as e:
                    logger.debug(f"通用搜索登录按钮失败: {e}")
            
            if not login_button:
                logger.error("在iframe中未找到可用的登录按钮")
                await self._debug_iframe_inputs(login_frame)
                return False
            
            # 点击登录
            await login_button.click()
            logger.info("已点击登录按钮")
            
            # 等待登录完成
            await self.page.wait_for_timeout(8000)  # 增加等待时间
            
            # 检查是否需要验证码或其他验证
            current_url = self.page.url
            logger.info(f"登录后URL: {current_url}")
            
            # 检查是否成功进入邮箱主界面
            if "mail.163.com" in current_url and ("/js6/" in current_url or "/m/" in current_url or "/home/" in current_url):
                logger.success("163邮箱登录成功")
                return True
            else:
                logger.warning("163邮箱登录状态未确定，可能需要额外验证")
                
                # 检查是否有短信验证码输入框
                sms_handled = await self._handle_sms_verification()
                if sms_handled:
                    return True
                
                logger.info("等待用户手动处理其他验证步骤（如滑块验证等）...")
                await self.page.wait_for_timeout(15000)  # 给用户足够时间处理验证
                
                # 再次检查URL
                current_url = self.page.url
                logger.info(f"验证后URL: {current_url}")
                
                if "mail.163.com" in current_url and ("/js6/" in current_url or "/m/" in current_url or "/home/" in current_url):
                    logger.success("163邮箱验证完成，登录成功")
                    return True
                else:
                    logger.warning("请确保已完成登录验证，继续执行...")
                    return True  # 暂时返回True，继续后续操作
                
        except Exception as e:
            logger.error(f"163邮箱登录失败: {e}")
            return False
    
    async def _handle_sms_verification(self) -> bool:
        """
        处理短信验证码验证
        
        Returns:
            是否成功处理短信验证码
        """
        try:
            # 查找短信验证码相关的元素
            sms_selectors = [
                'input[placeholder*="验证码"]',
                'input[placeholder*="短信"]',
                'input[name*="sms"]',
                'input[name*="captcha"]',
                'input[name*="code"]',
                '.captcha-input input',
                '.sms-input input',
                '.verify-input input'
            ]
            
            sms_input = None
            
            # 首先检查主页面
            for selector in sms_selectors:
                try:
                    sms_input = await self.page.wait_for_selector(selector, timeout=3000)
                    if sms_input and await sms_input.is_visible():
                        logger.info(f"在主页面找到验证码输入框: {selector}")
                        break
                except:
                    continue
            
            # 如果主页面没找到，检查iframe
            if not sms_input:
                login_frame = await self._find_login_iframe()
                if login_frame:
                    for selector in sms_selectors:
                        try:
                            sms_input = await login_frame.wait_for_selector(selector, timeout=3000)
                            if sms_input and await sms_input.is_visible():
                                logger.info(f"在iframe中找到验证码输入框: {selector}")
                                break
                        except:
                            continue
            
            if not sms_input:
                logger.debug("未找到短信验证码输入框")
                return False
            
            # 找到了验证码输入框，提示用户输入
            logger.warning("[LOCK] 检测到需要短信验证码！")
            logger.info("[PHONE] 请查看您的手机短信，获取验证码")
            
            # 在控制台请求用户输入验证码
            print("\n" + "="*50)
            print("[LOCK] 邮箱登录需要短信验证码")
            print("[PHONE] 请查看您的手机短信获取验证码")
            print("="*50)
            
            sms_code = input("请输入6位短信验证码: ").strip()
            
            if not sms_code or len(sms_code) < 4:
                logger.error("验证码输入无效")
                return False
            
            # 输入验证码
            await sms_input.fill(sms_code)
            logger.info(f"已输入验证码: {sms_code}")
            
            # 查找确认按钮
            confirm_selectors = [
                'button:has-text("确认")',
                'button:has-text("确定")',
                'button:has-text("提交")',
                'button:has-text("下一步")',
                'input[type="submit"]',
                'button[type="submit"]',
                '.confirm-btn',
                '.submit-btn'
            ]
            
            confirm_button = None
            for selector in confirm_selectors:
                try:
                    # 先在主页面查找
                    confirm_button = await self.page.wait_for_selector(selector, timeout=2000)
                    if confirm_button and await confirm_button.is_visible():
                        break
                    
                    # 如果主页面没找到，在iframe中查找
                    login_frame = await self._find_login_iframe()
                    if login_frame:
                        confirm_button = await login_frame.wait_for_selector(selector, timeout=2000)
                        if confirm_button and await confirm_button.is_visible():
                            break
                except:
                    continue
            
            if confirm_button:
                await confirm_button.click()
                logger.info("已点击确认按钮")
            else:
                # 尝试按回车键
                await sms_input.press('Enter')
                logger.info("已按回车键提交验证码")
            
            # 等待验证完成
            await self.page.wait_for_timeout(5000)
            
            # 检查是否成功登录
            current_url = self.page.url
            if "mail.163.com" in current_url and ("/js6/" in current_url or "/m/" in current_url or "/home/" in current_url):
                logger.success("[OK] 短信验证码验证成功，邮箱登录完成！")
                return True
            else:
                logger.warning("短信验证码提交后状态未确定，继续等待...")
                return False
                
        except Exception as e:
            logger.error(f"处理短信验证码失败: {e}")
            return False
    
    async def _find_login_iframe(self):
        """找到163邮箱登录iframe"""
        try:
            # 等待iframe加载
            await self.page.wait_for_timeout(3000)
            
            # 可能的iframe选择器
            iframe_selectors = [
                'iframe[src*="dl.reg.163.com"]',  # 163登录iframe
                'iframe[src*="reg.163.com"]',
                'iframe[name="x-URS-iframe"]',
                'iframe[id*="x-URS-iframe"]',
                'iframe:first-child'
            ]
            
            for selector in iframe_selectors:
                try:
                    iframe_element = await self.page.wait_for_selector(selector, timeout=3000)
                    if iframe_element:
                        login_frame = await iframe_element.content_frame()
                        if login_frame:
                            logger.debug(f"找到登录iframe: {selector}")
                            # 等待iframe内容加载
                            await login_frame.wait_for_load_state('networkidle', timeout=10000)
                            return login_frame
                except Exception as e:
                    logger.debug(f"尝试iframe选择器 {selector} 失败: {e}")
                    continue
            
            # 如果都没找到，尝试获取所有iframe
            logger.debug("尝试查找所有iframe...")
            all_iframes = await self.page.query_selector_all('iframe')
            logger.debug(f"页面中共有 {len(all_iframes)} 个iframe")
            
            for i, iframe_element in enumerate(all_iframes):
                try:
                    iframe_src = await iframe_element.get_attribute('src')
                    logger.debug(f"iframe {i+1}: {iframe_src}")
                    
                    login_frame = await iframe_element.content_frame()
                    if login_frame:
                        # 在iframe中查找是否有登录相关元素
                        try:
                            inputs = await login_frame.query_selector_all('input')
                            if len(inputs) >= 2:  # 至少有用户名和密码两个输入框
                                logger.debug(f"iframe {i+1} 包含 {len(inputs)} 个输入框，可能是登录iframe")
                                await login_frame.wait_for_load_state('networkidle', timeout=5000)
                                return login_frame
                        except:
                            continue
                except Exception as e:
                    logger.debug(f"检查iframe {i+1} 失败: {e}")
                    continue
            
            logger.error("未能找到有效的登录iframe")
            return None
            
        except Exception as e:
            logger.error(f"查找登录iframe失败: {e}")
            return None
    
    async def _debug_iframe_inputs(self, frame):
        """调试iframe中的输入框"""
        try:
            logger.debug("调试iframe中的输入框...")
            inputs = await frame.query_selector_all('input')
            
            logger.debug(f"iframe中共有 {len(inputs)} 个输入框:")
            for i, input_elem in enumerate(inputs):
                input_type = await input_elem.get_attribute('type') or 'text'
                input_name = await input_elem.get_attribute('name') or ''
                input_id = await input_elem.get_attribute('id') or ''
                input_class = await input_elem.get_attribute('class') or ''
                input_placeholder = await input_elem.get_attribute('placeholder') or ''
                
                logger.debug(f"  输入框 {i+1}: type={input_type}, name={input_name}, id={input_id}")
                logger.debug(f"    class={input_class}, placeholder={input_placeholder}")
                
        except Exception as e:
            logger.debug(f"调试iframe输入框失败: {e}")
    
    async def _login_qq(self) -> bool:
        """QQ邮箱登录（预留）"""
        logger.info("QQ邮箱登录功能待实现")
        return False
    
    async def get_latest_otp(
        self, 
        since_timestamp: Optional[float] = None,
        max_age_seconds: int = 300
    ) -> Optional[str]:
        """
        获取最新的验证码
        
        Args:
            since_timestamp: 开始时间戳
            max_age_seconds: 最大邮件年龄（秒）
            
        Returns:
            验证码字符串，未找到返回None
        """
        try:
            logger.info("开始在网页邮箱中查找验证码...")
            
            # 确保在收件箱页面
            await self._navigate_to_inbox()
            
            # 刷新收件箱
            await self.page.reload()
            await self.page.wait_for_load_state('networkidle')
            await self.page.wait_for_timeout(3000)
            
            # 查找最新的邮件
            return await self._find_otp_in_emails(since_timestamp, max_age_seconds)
            
        except Exception as e:
            logger.error(f"获取验证码失败: {e}")
            return None
    
    async def _navigate_to_inbox(self):
        """导航到收件箱"""
        try:
            logger.debug("导航到收件箱...")
            
            # 163邮箱收件箱导航
            inbox_selectors = [
                'a:has-text("收件箱")',
                'span:has-text("收件箱")',
                '.nui-folder-item:has-text("收件箱")',
                '[title="收件箱"]'
            ]
            
            for selector in inbox_selectors:
                try:
                    inbox_link = await self.page.wait_for_selector(selector, timeout=3000)
                    if inbox_link:
                        await inbox_link.click()
                        logger.debug("已点击收件箱链接")
                        await self.page.wait_for_timeout(2000)
                        break
                except:
                    continue
                    
        except Exception as e:
            logger.debug(f"导航到收件箱时出错: {e}")
    
    async def _find_otp_in_emails(
        self, 
        since_timestamp: Optional[float], 
        max_age_seconds: int
    ) -> Optional[str]:
        """在邮件列表中查找验证码"""
        try:
            logger.debug("在邮件列表中查找验证码...")
            
            # 查找邮件列表项
            email_selectors = [
                '.nui-mail-item',
                '.mail-item',
                'tr[id^="mail"]',
                '.list-item'
            ]
            
            emails = None
            for selector in email_selectors:
                try:
                    emails = await self.page.query_selector_all(selector)
                    if emails:
                        logger.debug(f"找到 {len(emails)} 封邮件")
                        break
                except:
                    continue
            
            if not emails:
                logger.warning("未找到邮件列表")
                return None
            
            # 遍历前几封邮件查找验证码
            for i, email_element in enumerate(emails[:5]):  # 只检查前5封
                try:
                    # 点击邮件打开
                    await email_element.click()
                    await self.page.wait_for_timeout(2000)
                    
                    # 获取邮件内容
                    email_content = await self._extract_email_content()
                    
                    if email_content:
                        # 从内容中提取验证码
                        otp_code = self._extract_otp_from_content(email_content)
                        if otp_code:
                            logger.success(f"在第{i+1}封邮件中找到验证码: {otp_code}")
                            return otp_code
                    
                    # 返回邮件列表继续查找
                    await self.page.go_back()
                    await self.page.wait_for_timeout(1000)
                    
                except Exception as e:
                    logger.debug(f"处理第{i+1}封邮件时出错: {e}")
                    continue
            
            logger.warning("未在邮件中找到验证码")
            return None
            
        except Exception as e:
            logger.error(f"查找邮件验证码失败: {e}")
            return None
    
    async def _extract_email_content(self) -> str:
        """提取邮件内容"""
        try:
            # 等待邮件内容加载
            await self.page.wait_for_timeout(2000)
            
            # 尝试不同的内容选择器
            content_selectors = [
                '.nui-mail-detail-content',
                '.mail-content',
                '.mail-body',
                'iframe[name="contentFrame"]',  # 163邮箱使用iframe
                '.content-body'
            ]
            
            email_content = ""
            
            for selector in content_selectors:
                try:
                    if selector.startswith('iframe'):
                        # 处理iframe内容
                        frame = await self.page.wait_for_selector(selector, timeout=3000)
                        if frame:
                            frame_content = await frame.content_frame()
                            if frame_content:
                                email_content = await frame_content.inner_text('body')
                    else:
                        # 处理普通元素
                        content_element = await self.page.wait_for_selector(selector, timeout=3000)
                        if content_element:
                            email_content = await content_element.inner_text()
                    
                    if email_content and len(email_content.strip()) > 10:
                        logger.debug(f"成功提取邮件内容: {len(email_content)} 字符")
                        break
                        
                except:
                    continue
            
            return email_content
            
        except Exception as e:
            logger.error(f"提取邮件内容失败: {e}")
            return ""
    
    def _extract_otp_from_content(self, content: str) -> Optional[str]:
        """从邮件内容中提取验证码"""
        if not content:
            return None
        
        import re
        
        # 验证码的正则表达式模式（复用之前的逻辑）
        otp_patterns = [
            r'(?:验证码|verification code|code)[^\d]*(\d{6})',
            r'(\d{6})(?:\s*(?:是您的|is your)?(?:验证码|verification code))',
            r'(?:验证码|verification code|code)[^\d]*(\d{4})',
            r'(\d{4})(?:\s*(?:是您的|is your)?(?:验证码|verification code))',
            r'(?:验证码|verification code|code)[^\d]*(\d{4,8})',
            r'(\d{4,8})(?:\s*(?:是您的|is your)?(?:验证码|verification code))',
            r'\b(\d{6})\b',
            r'\b(\d{4})\b',
        ]
        
        content_lower = content.lower()
        
        for pattern in otp_patterns:
            matches = re.findall(pattern, content_lower, re.IGNORECASE | re.DOTALL)
            if matches:
                otp_code = matches[0].strip()
                if otp_code.isdigit() and 4 <= len(otp_code) <= 8:
                    logger.debug(f"使用模式 '{pattern}' 匹配到验证码: {otp_code}")
                    return otp_code
        
        logger.debug("未能从邮件内容中提取到验证码")
        return None
    
    async def cleanup(self):
        """清理资源"""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            
            logger.debug("浏览器资源已清理")
            
        except Exception as e:
            logger.warning(f"清理浏览器资源时出错: {e}")


def run_browser_email_otp(config: Dict[str, Any], timeout_seconds: int = 120) -> Optional[str]:
    """
    运行浏览器邮箱OTP获取（同步接口）
    
    Args:
        config: 邮箱配置
        timeout_seconds: 超时时间
        
    Returns:
        验证码字符串
    """
    async def _run():
        client = BrowserEmailOTPClient(config)
        
        try:
            # 启动浏览器
            if not await client.start_browser():
                return None
            
            # 登录邮箱
            if not await client.login_email():
                return None
            
            # 等待用户触发验证码发送
            logger.info("请现在触发验证码发送...")
            start_time = time.time()
            
            # 轮询获取验证码
            poll_interval = 3
            while time.time() - start_time < timeout_seconds:
                otp_code = await client.get_latest_otp(
                    since_timestamp=start_time,
                    max_age_seconds=timeout_seconds
                )
                
                if otp_code:
                    return otp_code
                
                await asyncio.sleep(poll_interval)
            
            logger.error("获取验证码超时")
            return None
            
        finally:
            await client.cleanup()
    
    # 运行异步函数
    try:
        return asyncio.run(_run())
    except Exception as e:
        logger.error(f"运行浏览器邮箱OTP失败: {e}")
        return None
