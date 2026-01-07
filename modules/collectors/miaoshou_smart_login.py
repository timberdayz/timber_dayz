#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
妙手ERP智能登录模块

使用新的智能元素查找器实现妙手ERP的自动登录功能
支持验证码自动获取和输入
"""

import asyncio
import time
from typing import Dict, Optional, Any
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from loguru import logger
from core.smart_proxy_router import get_smart_proxy_for_url

from ..utils.web_elements import SmartElementFinder, ElementType, ElementAction
from ..utils.web_elements.element_strategies import get_strategy
from ..utils.otp.verification_service import VerificationCodeService
from ..utils.sessions.session_manager import SessionManager
from ..utils.logger import Logger

# 初始化日志
logger_instance = Logger(__name__)


class MiaoshouSmartLogin:
    """妙手ERP智能登录器"""
    
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.element_finder = None
        self.otp_service = VerificationCodeService()
        self.session_manager = SessionManager()
        
    async def login_with_account(
        self,
        account_config: Dict[str, Any],
        headless: bool = False,
        use_session: bool = True,
        screenshot_on_error: bool = True
    ) -> bool:
        """
        使用账号配置进行智能登录
        
        Args:
            account_config: 账号配置字典
            headless: 是否无头模式
            use_session: 是否使用会话复用
            screenshot_on_error: 错误时是否截图
            
        Returns:
            登录是否成功
        """
        account_id = account_config.get("account_id", "unknown")
        login_url = account_config.get("login_url", "https://erp.91miaoshou.com/login")
        
        logger.info(f"开始妙手ERP智能登录: {account_id}")
        
        try:
            # 启动浏览器
            if not await self._start_browser(headless, use_session, account_id, login_url):
                return False
            
            # 检查是否已登录（会话复用）
            if use_session and await self._check_login_status():
                logger.success("检测到已登录状态，跳过登录流程")
                return True
            
            # 访问登录页面 - 直接跳转不显示空白页面
            logger.info(f"正在访问登录页面: {login_url}")
            await self.page.goto(login_url, timeout=90000, wait_until='domcontentloaded')  # 适应VPN环境
            logger.info("页面基础内容加载完成，等待网络稳定...")
            await self.page.wait_for_load_state('networkidle', timeout=60000)
            
            # 创建智能元素查找器
            self.element_finder = SmartElementFinder(self.page)
            
            # 获取妙手ERP策略
            miaoshou_strategy = get_strategy("miaoshou_erp")
            
            # 执行智能登录
            login_success = await self._perform_smart_login(account_config, miaoshou_strategy)
            
            if login_success:
                # 保存会话状态
                if use_session:
                    await self._save_session(account_id)
                
                logger.success(f"妙手ERP登录成功: {account_id}")
                return True
            else:
                if screenshot_on_error:
                    await self._take_error_screenshot(account_id)
                return False
                
        except Exception as e:
            logger.error(f"妙手ERP登录失败: {e}")
            if screenshot_on_error:
                await self._take_error_screenshot(account_id)
            return False
    
    async def _start_browser(self, headless: bool, use_session: bool, account_id: str, login_url: str = None) -> bool:
        """启动浏览器"""
        try:
            self.playwright = await async_playwright().start()
            
            # 浏览器启动参数
            launch_args = {
                'headless': headless,
                'args': [
                    '--no-sandbox',
                    '--disable-web-security',
                    '--disable-blink-features=AutomationControlled'
                ]
            }
            
            # 获取智能代理配置
            proxy_config = None
            if login_url:
                proxy_config = get_smart_proxy_for_url(login_url)
                if proxy_config:
                    logger.info(f"🔗 为 {login_url} 配置智能代理: {proxy_config.get('server', 'unknown')}")
                else:
                    logger.info(f"🌐 {login_url} 使用直连（无代理）")
            
            # 如果使用会话，设置持久化上下文
            if use_session:
                session_dir = self.session_manager.get_profile_path("miaoshou_erp", account_id)
                if session_dir and session_dir.exists():
                    context_args = {}
                    if proxy_config:
                        context_args['proxy'] = proxy_config
                    
                    self.context = await self.playwright.chromium.launch_persistent_context(
                        user_data_dir=str(session_dir),
                        **launch_args,
                        **context_args
                    )
                    self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
                else:
                    if proxy_config:
                        launch_args['proxy'] = proxy_config
                    
                    self.browser = await self.playwright.chromium.launch(**launch_args)
                    self.context = await self.browser.new_context()
                    self.page = await self.context.new_page()
            else:
                if proxy_config:
                    launch_args['proxy'] = proxy_config
                
                self.browser = await self.playwright.chromium.launch(**launch_args)
                self.context = await self.browser.new_context()
                self.page = await self.context.new_page()
            
            # 设置页面超时时间，智能调整
            if proxy_config:
                # 使用代理时，可能需要更长的超时时间
                timeout = 120000  # 120秒
                logger.info("使用代理，设置超时时间为120秒")
            else:
                # 直连时，根据VPN环境调整
                timeout = 90000  # 90秒，适应新加坡VPN访问中国网站
                logger.info("直连模式，设置超时时间为90秒")
            
            self.page.set_default_timeout(timeout)
            
            logger.success("浏览器启动成功")
            return True
            
        except Exception as e:
            logger.error(f"启动浏览器失败: {e}")
            return False
    
    async def _check_login_status(self) -> bool:
        """检查当前是否已登录"""
        try:
            current_url = self.page.url
            
            # 如果URL中包含主页面特征，说明已登录
            login_indicators = [
                "/main/",
                "/dashboard/",
                "/order/",
                "/home/",
                "main.jsp"
            ]
            
            for indicator in login_indicators:
                if indicator in current_url:
                    logger.info("检测到登录状态")
                    return True
            
            # 尝试查找登录后的页面元素
            logout_selectors = [
                'a[href*="logout"]',
                'button:has-text("退出")',
                'span:has-text("退出登录")',
                '.user-info',
                '.user-name'
            ]
            
            for selector in logout_selectors:
                try:
                    element = await self.page.wait_for_selector(selector, timeout=3000)
                    if element and await element.is_visible():
                        logger.info("通过页面元素确认登录状态")
                        return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            logger.debug(f"检查登录状态失败: {e}")
            return False
    
    async def _perform_smart_login(self, account_config: Dict[str, Any], strategy) -> bool:
        """执行智能登录"""
        try:
            username = account_config.get("username", "")
            password = account_config.get("password", "")
            
            if not username or not password:
                logger.error("用户名或密码未配置")
                return False
            
            logger.info("开始填写登录信息...")
            
            # 使用智能元素查找器填写用户名和密码
            success = await self.element_finder.smart_login(
                username=username,
                password=password,
                timeout=30000
            )
            
            if not success:
                logger.error("智能登录填写失败")
                return False
            
            # 等待登录提交
            await asyncio.sleep(3)
            
            # 先快速检查是否登录成功，成功则无需验证码流程
            if await self._quick_login_check():
                logger.success("登录成功，无需验证码")
                return True
            
            # 如果登录未成功，检查是否需要验证码（按需触发）
            logger.info("登录未立即成功，检查是否需要验证码...")
            need_captcha = await self._check_captcha_required()
            
            if need_captcha:
                logger.info("检测到需要验证码，启动验证码流程")
                
                # 请求验证码（通过邮箱或短信）
                captcha_code = await self._get_verification_code(account_config)
                
                if captcha_code:
                    # 填写验证码
                    captcha_element = await self.element_finder.find_element(ElementType.CAPTCHA_INPUT)
                    if captcha_element:
                        await self.element_finder.perform_action(captcha_element, ElementAction.FILL, captcha_code)
                        logger.success(f"验证码已填写: {captcha_code}")
                        
                        # 再次点击登录按钮
                        login_button = await self.element_finder.find_element(ElementType.LOGIN_BUTTON)
                        if login_button:
                            await self.element_finder.perform_action(login_button, ElementAction.CLICK)
                    else:
                        logger.error("未找到验证码输入框")
                        return False
                else:
                    logger.error("未能获取验证码")
                    return False
            else:
                logger.info("未检测到验证码需求，可能是其他登录问题")
            
            # 等待登录完成
            await asyncio.sleep(5)
            
            # 验证登录结果
            if await self._verify_login_success():
                return True
            else:
                logger.error("登录验证失败")
                return False
                
        except Exception as e:
            logger.error(f"智能登录执行失败: {e}")
            return False
    
    async def _quick_login_check(self) -> bool:
        """快速检查登录是否成功"""
        try:
            current_url = self.page.url
            # 如果URL不再包含login，说明可能已经登录成功
            if "login" not in current_url.lower():
                logger.info("URL已跳转，可能登录成功")
                return True
            
            # 检查是否有成功登录的页面元素
            success_indicators = [
                'text="首页"',
                'text="控制台"', 
                'text="订单管理"',
                'text="退出"',
                'text="个人中心"',
                '.user-info',
                '.dashboard',
                '.main-menu'
            ]
            
            for indicator in success_indicators:
                try:
                    element = await self.page.wait_for_selector(indicator, timeout=2000)
                    if element:
                        logger.info(f"检测到登录成功标识: {indicator}")
                        return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            logger.debug(f"快速登录检查失败: {e}")
            return False
    
    async def _check_captcha_required(self) -> bool:
        """检查是否需要验证码"""
        try:
            # 查找验证码输入框（快速检测，避免长时间等待）
            captcha_element = await self.element_finder.find_element(
                ElementType.CAPTCHA_INPUT,
                timeout=5000,  # 5秒快速检测
                must_be_visible=True
            )
            
            if captcha_element:
                logger.info("发现验证码输入框，需要验证码")
                return True
            
            # 检查页面上的验证码相关提示
            error_messages = await self.page.query_selector_all('.error, .alert, .warning, .message')
            for msg_elem in error_messages:
                try:
                    text = await msg_elem.inner_text()
                    if any(keyword in text for keyword in ['验证码', '短信', '邮箱', 'captcha', 'verification']):
                        logger.info("检测到验证码相关错误信息")
                        return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            logger.debug(f"检查验证码需求失败: {e}")
            return False
    
    async def _get_verification_code(self, account_config: Dict[str, Any]) -> Optional[str]:
        """获取验证码"""
        try:
            logger.info("开始获取验证码...")
            
            # 首先尝试通过OTP服务自动获取验证码
            logger.info("尝试自动获取邮箱验证码...")
            otp_code = self.otp_service.request_otp(
                channel="email",  # 默认使用邮箱
                context=account_config,
                timeout_seconds=60  # 减少自动获取的等待时间
            )
            
            if otp_code:
                logger.success(f"成功自动获取验证码: {otp_code}")
                return otp_code
            
            # 如果自动获取失败，提示用户手动输入
            logger.warning("自动获取验证码失败，请手动输入")
            logger.info("请检查您的邮箱或手机短信获取验证码")
            
            # 在控制台请求用户输入验证码
            print("\n" + "="*60)
            print("🔐 妙手ERP平台需要验证码")
            print("📧 请检查您的邮箱或手机短信获取验证码")
            print("💡 如果长时间收不到验证码，可以尝试重新发送")
            print("="*60)
            
            manual_code = input("请输入验证码（4-8位数字）: ").strip()
            
            if manual_code and len(manual_code) >= 4:
                logger.info(f"用户手动输入验证码: {manual_code}")
                return manual_code
            else:
                logger.error("验证码输入无效")
                return None
                
        except Exception as e:
            logger.error(f"获取验证码异常: {e}")
            return None
    
    async def _verify_login_success(self) -> bool:
        """验证登录是否成功"""
        try:
            # 等待页面基础加载完成（避免networkidle超时）
            await self.page.wait_for_load_state('domcontentloaded', timeout=15000)
            
            # 短暂等待，让页面可能的跳转完成
            await asyncio.sleep(3)
            
            current_url = self.page.url
            logger.info(f"登录后URL: {current_url}")
            
            # 检查URL是否包含登录成功的特征
            success_indicators = [
                "/main/",
                "/dashboard/",
                "/order/",
                "/home/",
                "main.jsp",
                "/index"
            ]
            
            for indicator in success_indicators:
                if indicator in current_url:
                    logger.success(f"通过URL确认登录成功: {indicator}")
                    return True
            
            # 检查是否还在登录页面
            if "/login" in current_url or "login.html" in current_url:
                logger.warning("仍在登录页面，检查登录失败原因...")
                await self._check_login_errors()
                return False
            
            # 查找登录后的页面元素（增加更多选择器）
            success_selectors = [
                '.user-info',
                '.user-name', 
                '.username',
                'a[href*="logout"]',
                'span:has-text("退出")',
                '.main-content',
                '.dashboard',
                '.menu',
                '.sidebar',
                '[class*="main"]',
                '[class*="content"]'
            ]
            
            for selector in success_selectors:
                try:
                    element = await self.page.wait_for_selector(selector, timeout=3000)
                    if element and await element.is_visible():
                        logger.success(f"通过页面元素确认登录成功: {selector}")
                        return True
                except:
                    continue
            
            # 如果URL已经不是登录页且找不到明确的失败标识，认为可能成功
            if "/login" not in current_url and "login.html" not in current_url:
                logger.success("URL已跳转离开登录页，认为登录成功")
                return True
            
            # 检查是否有登录失败的错误信息
            await self._check_login_errors()
            logger.warning("无法确定登录状态，但未检测到明确错误，认为可能成功")
            return True
            
        except Exception as e:
            logger.error(f"验证登录状态失败: {e}")
            return False
    
    async def _check_login_errors(self):
        """检查登录错误信息"""
        error_selectors = [
            '.error',
            '.alert-danger', 
            '.message-error',
            '.login-error',
            '.error-message',
            '[class*="error"]',
            '[class*="fail"]'
        ]
        
        for selector in error_selectors:
            try:
                error_elem = await self.page.wait_for_selector(selector, timeout=2000)
                if error_elem and await error_elem.is_visible():
                    error_text = await error_elem.inner_text()
                    logger.error(f"检测到登录错误: {error_text}")
                    break
            except:
                continue
    
    async def _save_session(self, account_id: str):
        """保存会话状态"""
        try:
            if self.context:
                # 保存storage state
                session_data = await self.context.storage_state()
                self.session_manager.save_session("miaoshou_erp", account_id, session_data)
                logger.success(f"会话状态已保存: {account_id}")
        except Exception as e:
            logger.warning(f"保存会话状态失败: {e}")
    
    async def _take_error_screenshot(self, account_id: str):
        """错误时截图"""
        try:
            if self.page:
                screenshot_path = f"temp/media/screenshots/error_{account_id}_{int(time.time())}.png"
                Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
                await self.page.screenshot(path=screenshot_path, full_page=True)
                logger.info(f"错误截图已保存: {screenshot_path}")
        except Exception as e:
            logger.debug(f"截图失败: {e}")
    
    async def close(self):
        """关闭浏览器资源"""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            
            # 清理OTP服务
            self.otp_service.cleanup()
            
            logger.debug("浏览器资源已清理")
            
        except Exception as e:
            logger.warning(f"清理资源时出错: {e}")


# 同步接口
def login_miaoshou_account(
    account_config: Dict[str, Any],
    headless: bool = True,
    use_session: bool = True
) -> bool:
    """
    妙手ERP账号登录（同步接口）
    
    Args:
        account_config: 账号配置
        headless: 无头模式
        use_session: 使用会话复用
        
    Returns:
        登录是否成功
    """
    async def _login():
        login_manager = MiaoshouSmartLogin()
        try:
            return await login_manager.login_with_account(
                account_config, 
                headless=headless,
                use_session=use_session
            )
        finally:
            await login_manager.close()
    
    try:
        return asyncio.run(_login())
    except Exception as e:
        logger.error(f"同步登录接口失败: {e}")
        return False
