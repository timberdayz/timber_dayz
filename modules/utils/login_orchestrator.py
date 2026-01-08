#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
统一登录编排器
支持妙手ERP、Shopee卖家、TikTok卖家的智能登录流程
包含：登录环节 -> 验证码识别 -> 邮箱OTP -> SMS用户输入
"""

import time
import asyncio
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
from playwright.sync_api import Page, Browser, BrowserContext, Playwright

from modules.core.logger import get_logger
from modules.utils.shopee_login_handler import ShopeeLoginHandler
from modules.utils.smart_verification_handler_v2 import SmartVerificationHandlerV2
from modules.utils.persistent_browser_manager import PersistentBrowserManager

logger = get_logger(__name__)


class LoginOrchestrator:
    """统一登录编排器 - 三平台智能登录流程"""

    def __init__(self, browser: Browser, playwright: Optional[Playwright] = None):
        """
        初始化登录编排器

        Args:
            browser: Playwright浏览器实例
            playwright: Playwright实例（用于持久化上下文）
        """
        self.browser = browser
        self.playwright = playwright
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        # 持久化浏览器管理器
        self.persistent_manager = None
        if playwright:
            self.persistent_manager = PersistentBrowserManager(playwright)
            logger.info("[OK] 持久化浏览器管理器已启用")

        # 平台特定的登录处理器
        self.platform_handlers = {
            'shopee': None,  # 延迟初始化
            'miaoshou': None,
            'tiktok': None
        }

        # 验证码处理器
        self.verification_handler = None

        # 支持的平台列表
        self.supported_platforms = ['miaoshou', 'shopee', 'tiktok', 'miaoshou_erp']

        # 邮箱OTP自动化开关
        self.auto_email_otp = True
        
    def _get_platform_key(self, platform: str) -> str:
        """标准化平台键名"""
        platform_lower = platform.lower()
        if platform_lower in ['miaoshou', 'miaoshou_erp', '妙手erp']:
            return 'miaoshou'
        elif platform_lower in ['shopee']:
            return 'shopee'
        elif platform_lower in ['tiktok', 'tiktok_shop']:
            return 'tiktok'
        else:
            raise ValueError(f"不支持的平台: {platform}")
    
    def _init_platform_handler(self, platform_key: str) -> bool:
        """初始化平台特定的登录处理器"""
        try:
            if platform_key == 'shopee' and not self.platform_handlers['shopee']:
                self.platform_handlers['shopee'] = ShopeeLoginHandler(self.browser)
                logger.info("[OK] Shopee登录处理器初始化完成")
                
            elif platform_key == 'miaoshou' and not self.platform_handlers['miaoshou']:
                # 妙手ERP使用通用处理器
                self.platform_handlers['miaoshou'] = MiaoshouLoginHandler(self.browser)
                logger.info("[OK] 妙手ERP登录处理器初始化完成")
                
            elif platform_key == 'tiktok' and not self.platform_handlers['tiktok']:
                # TikTok使用通用处理器
                self.platform_handlers['tiktok'] = TikTokLoginHandler(self.browser)
                logger.info("[OK] TikTok登录处理器初始化完成")
                
            return True
            
        except Exception as e:
            logger.error(f"[FAIL] 初始化{platform_key}登录处理器失败: {e}")
            return False
    
    def _init_verification_handler(self) -> bool:
        """初始化验证码处理器"""
        try:
            if not self.verification_handler and self.page:
                self.verification_handler = SmartVerificationHandlerV2(self.page)
                logger.info("[OK] 验证码处理器初始化完成")
            return True
        except Exception as e:
            logger.error(f"[FAIL] 验证码处理器初始化失败: {e}")
            return False
    
    async def orchestrate_login(self, account: Dict[str, Any]) -> Tuple[bool, str, Optional[Page]]:
        """
        执行完整的智能登录流程
        
        Args:
            account: 账号信息字典，必须包含platform、username、password、login_url
            
        Returns:
            Tuple[bool, str, Optional[Page]]: (成功状态, 错误信息, 页面对象)
        """
        try:
            # 1. 验证账号信息
            platform = account.get('platform', '').lower()
            username = account.get('username', '')
            password = account.get('password', '')
            login_url = account.get('login_url', '')

            if not all([platform, username or account.get('phone', ''), password, login_url]):
                error_msg = "账号信息不完整，缺少platform/username(或phone)/password/login_url"
                logger.error(f"[FAIL] {error_msg}")
                return False, error_msg, None

            platform_key = self._get_platform_key(platform)
            # TikTok 优先使用 phone 作为登录名
            login_name = account.get('phone') if platform_key == 'tiktok' and account.get('phone') else username
            logger.info(f"[START] 开始{platform}平台登录流程: {login_name}")

            # 2. 创建浏览器上下文和页面（优先使用持久化）
            account_id = account.get('account_id', username)

            if self.persistent_manager:
                # 使用持久化上下文（减少验证码）
                logger.info(f"[RETRY] 使用持久化浏览器上下文: {platform}/{account_id}")
                self.context = self.persistent_manager.get_or_create_persistent_context(
                    platform, account_id, account
                )
            else:
                # 回退到普通上下文
                logger.info("[RETRY] 使用普通浏览器上下文")
                self.context = self.browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
            self.page = self.context.new_page()
            
            # 3. 初始化处理器
            if not self._init_platform_handler(platform_key):
                return False, f"{platform}平台处理器初始化失败", None
                
            if not self._init_verification_handler():
                return False, "验证码处理器初始化失败", None
            
            # 4. 执行登录流程
            login_success, login_error = await self._execute_login_flow(
                platform_key, account, login_url, login_name, password
            )
            
            if not login_success:
                return False, login_error, None
            
            logger.info(f"[OK] {platform}平台登录成功: {username}")
            return True, "登录成功", self.page
            
        except Exception as e:
            error_msg = f"登录编排过程异常: {e}"
            logger.error(f"[FAIL] {error_msg}")
            return False, error_msg, None
    
    async def _execute_login_flow(self, platform_key: str, account: Dict, 
                                login_url: str, username: str, password: str) -> Tuple[bool, str]:
        """执行具体的登录流程"""
        try:
            # 步骤1: 访问登录页面
            logger.info(f"[WEB] 访问登录页面: {login_url}")
            self.page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            
            # 步骤2: 执行平台特定的登录操作
            handler = self.platform_handlers[platform_key]
            if platform_key == 'shopee':
                login_result = handler.login_to_shopee(account)
            else:
                login_result = await self._generic_login(handler, username, password)
            
            if not login_result:
                return False, f"{platform_key}平台基础登录失败"
            
            # 步骤3: 检测并处理验证码（增强邮箱OTP自动化）
            verification_result = await self._handle_verification_flow(account)
            if not verification_result[0]:
                return False, f"验证码处理失败: {verification_result[1]}"

            # 步骤4: 保存持久化状态（减少下次验证码）
            if self.persistent_manager:
                account_id = account.get('account_id', account.get('username', ''))
                self.persistent_manager.save_context_state(self.context, platform_key, account_id)
            
            # 步骤4: 最终登录状态确认
            if await self._verify_login_success(platform_key):
                return True, "登录成功"
            else:
                return False, "登录状态验证失败"
                
        except Exception as e:
            return False, f"登录流程执行异常: {e}"
    
    async def _handle_verification_flow(self, account: Dict) -> Tuple[bool, str]:
        """处理验证码流程"""
        try:
            # 等待页面稳定
            time.sleep(3)

            # 检测验证码类型
            verification_type = await self._detect_verification_type()

            if verification_type == 'none':
                logger.info("[OK] 无需验证码，登录流程继续")
                return True, "无需验证码"

            elif verification_type == 'image_captcha':
                logger.info("[IMG] 检测到图片验证码")
                return await self._handle_image_captcha()

            elif verification_type == 'sms_code':
                logger.info("[PHONE] 检测到SMS验证码")
                return await self._handle_sms_verification()

            elif verification_type == 'email_otp':
                logger.info("[EMAIL] 检测到邮箱OTP")
                if self.auto_email_otp:
                    return await self._handle_email_otp_auto(account)
                else:
                    return await self._handle_email_otp_manual(account)

            else:
                logger.warning(f"[WARN] 未知验证码类型: {verification_type}")
                return True, "跳过未知验证码类型"

        except Exception as e:
            logger.error(f"[FAIL] 验证码处理异常: {e}")
            return False, f"验证码处理异常: {e}"

    async def _detect_verification_type(self) -> str:
        """检测当前页面的验证码类型"""
        try:
            # 检测图片验证码
            image_captcha_selectors = [
                "img[src*='captcha']",
                "img[src*='verify']",
                ".captcha-image",
                "#captcha",
                "canvas[id*='captcha']"
            ]

            for selector in image_captcha_selectors:
                if self.page.query_selector(selector):
                    return 'image_captcha'

            # 检测SMS验证码输入框
            sms_selectors = [
                "input[placeholder*='验证码']",
                "input[placeholder*='短信']",
                "input[placeholder*='手机验证码']",
                "input[name*='sms']",
                "input[name*='code']"
            ]

            for selector in sms_selectors:
                if self.page.query_selector(selector):
                    return 'sms_code'

            # 检测邮箱验证提示
            email_indicators = [
                "text=邮箱验证",
                "text=邮件验证",
                "text=请查收邮件",
                ".email-verification"
            ]

            for indicator in email_indicators:
                if self.page.query_selector(indicator):
                    return 'email_otp'

            return 'none'

        except Exception as e:
            logger.error(f"[FAIL] 验证码类型检测失败: {e}")
            return 'none'

    async def _handle_image_captcha(self) -> Tuple[bool, str]:
        """处理图片验证码"""
        try:
            if self.verification_handler:
                # 使用现有的智能验证码处理器
                result = self.verification_handler.handle_verification()
                if result:
                    return True, "图片验证码处理成功"
                else:
                    return False, "图片验证码处理失败"
            else:
                return False, "验证码处理器未初始化"

        except Exception as e:
            logger.error(f"[FAIL] 图片验证码处理异常: {e}")
            return False, f"图片验证码处理异常: {e}"

    async def _handle_sms_verification(self) -> Tuple[bool, str]:
        """处理SMS验证码 - 用户输入模式"""
        try:
            logger.info("[PHONE] 检测到SMS验证码需求")

            # 在生产环境（无头模式）下，提示用户输入
            print("\n" + "="*50)
            print("[BELL] 需要SMS验证码")
            print("="*50)
            print("系统检测到需要手机短信验证码")
            print("请查收手机短信并输入验证码")
            print("="*50)

            # 获取用户输入的验证码
            sms_code = input("请输入收到的SMS验证码: ").strip()

            if not sms_code:
                return False, "用户未输入SMS验证码"

            # 查找验证码输入框并填入
            sms_input_selectors = [
                "input[placeholder*='验证码']",
                "input[placeholder*='短信']",
                "input[placeholder*='手机验证码']",
                "input[name*='sms']",
                "input[name*='code']",
                "input[type='text']:last-of-type"  # 通常验证码框是最后一个文本输入框
            ]

            code_filled = False
            for selector in sms_input_selectors:
                try:
                    if self.page.query_selector(selector):
                        self.page.fill(selector, sms_code)
                        logger.info(f"[OK] SMS验证码填入成功: {selector}")
                        code_filled = True
                        break
                except Exception:
                    continue

            if not code_filled:
                return False, "未找到SMS验证码输入框"

            # 查找并点击确认按钮
            confirm_selectors = [
                "button:has-text('确认')",
                "button:has-text('验证')",
                "button:has-text('提交')",
                "button[type='submit']",
                ".verify-btn"
            ]

            for selector in confirm_selectors:
                try:
                    if self.page.query_selector(selector):
                        self.page.click(selector)
                        logger.info(f"[OK] SMS验证确认按钮点击成功")
                        time.sleep(2)
                        break
                except Exception:
                    continue

            return True, "SMS验证码处理完成"

        except Exception as e:
            logger.error(f"[FAIL] SMS验证码处理异常: {e}")
            return False, f"SMS验证码处理异常: {e}"

    async def _handle_email_otp(self, account: Dict) -> Tuple[bool, str]:
        """处理邮箱OTP - Playwright模拟真实用户登录"""
        try:
            logger.info("[EMAIL] 开始邮箱OTP处理流程")

            # 获取邮箱信息
            email = account.get('email', '')
            email_password = account.get('email_password', '')

            if not email or not email_password:
                logger.warning("[WARN] 账号未配置邮箱信息，跳过邮箱OTP")
                return True, "跳过邮箱OTP（未配置邮箱）"

            # 使用现有的邮箱登录处理器
            try:
                from modules.utils.email_login_handler import EmailLoginHandler

                email_handler = EmailLoginHandler(self.browser)
                otp_code = await email_handler.get_otp_from_email(email, email_password)

                if otp_code:
                    # 填入OTP验证码
                    otp_selectors = [
                        "input[placeholder*='邮箱验证码']",
                        "input[placeholder*='邮件验证码']",
                        "input[name*='email_code']",
                        "input[name*='otp']"
                    ]

                    for selector in otp_selectors:
                        try:
                            if self.page.query_selector(selector):
                                self.page.fill(selector, otp_code)
                                logger.info(f"[OK] 邮箱OTP填入成功")
                                return True, "邮箱OTP处理成功"
                        except Exception:
                            continue

                    return False, "未找到邮箱OTP输入框"
                else:
                    return False, "未能获取邮箱OTP"

            except ImportError:
                logger.warning("[WARN] 邮箱登录处理器不可用，跳过邮箱OTP")
                return True, "跳过邮箱OTP（处理器不可用）"

        except Exception as e:
            logger.error(f"[FAIL] 邮箱OTP处理异常: {e}")
            return False, f"邮箱OTP处理异常: {e}"

    async def _verify_login_success(self, platform_key: str) -> bool:
        """验证登录是否成功"""
        try:
            time.sleep(3)  # 等待页面跳转

            current_url = self.page.url

            # 通用登录成功判断：URL不再包含login/signin等关键词
            login_keywords = ['login', 'signin', 'auth', '登录']
            url_indicates_login_page = any(keyword in current_url.lower() for keyword in login_keywords)

            if not url_indicates_login_page:
                logger.info(f"[OK] 登录成功确认：URL已跳转离开登录页 ({current_url})")
                return True

            # 平台特定的登录成功判断
            success_indicators = {
                'shopee': ['seller.shopee', 'dashboard'],
                'miaoshou': ['erp.91miaoshou.com', 'dashboard', 'main'],
                'tiktok': ['seller-', 'dashboard', 'home']
            }

            if platform_key in success_indicators:
                indicators = success_indicators[platform_key]
                if any(indicator in current_url for indicator in indicators):
                    logger.info(f"[OK] {platform_key}平台登录成功确认")
                    return True

            logger.warning(f"[WARN] 登录状态不确定，当前URL: {current_url}")
            return False

        except Exception as e:
            logger.error(f"[FAIL] 登录状态验证异常: {e}")
            return False

    async def _generic_login(self, handler, username: str, password: str) -> bool:
        """通用登录处理"""
        try:
            return await handler.login(username, password, self.page)
        except Exception as e:
            logger.error(f"[FAIL] 通用登录处理失败: {e}")
            return False

    def close(self):
        """清理资源"""
        try:
            if self.context:
                self.context.close()
                self.context = None
            self.page = None
            logger.info("[OK] 登录编排器资源清理完成")
        except Exception as e:
            logger.error(f"[WARN] 资源清理异常: {e}")


# 平台特定的登录处理器基类
class BasePlatformLoginHandler:
    """平台登录处理器基类"""
    
    def __init__(self, browser: Browser):
        self.browser = browser
    
    async def login(self, username: str, password: str, page: Page) -> bool:
        """执行登录操作，子类需要实现"""
        raise NotImplementedError("子类必须实现login方法")


class MiaoshouLoginHandler(BasePlatformLoginHandler):
    """妙手ERP登录处理器"""
    
    async def login(self, username: str, password: str, page: Page) -> bool:
        """执行妙手ERP登录"""
        try:
            # 智能填写用户名
            username_selectors = [
                "input[placeholder='手机号/子账号/邮箱']",
                "input[placeholder='手机号/子账号/邮箱/邮箱']",
                "input[placeholder*='账号']",
                "input[name='username']",
                "input[type='text']"
            ]
            
            username_filled = False
            for selector in username_selectors:
                try:
                    if page.query_selector(selector):
                        page.fill(selector, username)
                        logger.info(f"[OK] 妙手ERP用户名填写成功: {selector}")
                        username_filled = True
                        break
                except Exception:
                    continue
            
            if not username_filled:
                logger.error("[FAIL] 妙手ERP未找到用户名输入框")
                return False
            
            # 智能填写密码
            password_selectors = [
                "input[placeholder='密码']",
                "input[name='password']",
                "input[type='password']"
            ]
            
            password_filled = False
            for selector in password_selectors:
                try:
                    if page.query_selector(selector):
                        page.fill(selector, password)
                        logger.info(f"[OK] 妙手ERP密码填写成功")
                        password_filled = True
                        break
                except Exception:
                    continue
            
            if not password_filled:
                logger.error("[FAIL] 妙手ERP未找到密码输入框")
                return False
            
            # 点击登录按钮
            login_selectors = [
                "button:has-text('立即登录')",
                "button:has-text('登录')",
                "button[type='submit']",
                ".login-btn"
            ]
            
            login_clicked = False
            for selector in login_selectors:
                try:
                    if page.query_selector(selector):
                        page.click(selector)
                        logger.info(f"[OK] 妙手ERP登录按钮点击成功")
                        login_clicked = True
                        time.sleep(2)
                        break
                except Exception:
                    continue
            
            if not login_clicked:
                logger.error("[FAIL] 妙手ERP未找到登录按钮")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"[FAIL] 妙手ERP登录失败: {e}")
            return False


class TikTokLoginHandler(BasePlatformLoginHandler):
    """TikTok卖家登录处理器（手机号优先）"""

    async def login(self, username: str, password: str, page: Page) -> bool:
        """执行TikTok登录（手机号+密码为主）。
        username: 对于TikTok应为手机号；若为空将回退到邮箱/用户名。
        """
        try:
            # 延迟导入以避免导入阶段副作用
            from modules.components.base import ExecutionContext
            from modules.platforms.tiktok.components.login import TiktokLogin

            # 组装最小执行上下文（platform/account）
            account_ctx = {
                "login_url": page.url,
                "phone": username or "",
                "username": username or "",
                "password": password or "",
            }
            ctx = ExecutionContext(platform="tiktok", account=account_ctx)
            comp = TiktokLogin(ctx)
            result = comp.run(page)
            return bool(getattr(result, "success", False))

        except Exception as e:
            logger.error(f"[FAIL] TikTok登录失败: {e}")
            return False

    async def _handle_email_otp_auto(self, account: Dict) -> Tuple[bool, str]:
        """自动处理邮箱OTP验证"""
        try:
            logger.info("[BOT] 启动邮箱OTP自动化处理...")

            # 获取邮箱配置（支持多种字段名）
            email = (account.get('email', '') or
                    account.get('E-mail', '') or
                    account.get('Email account', ''))
            email_password = (account.get('email_password', '') or
                            account.get('Email password', ''))

            if not email or not email_password:
                logger.warning("[WARN] 邮箱配置不完整，回退到手动模式")
                return await self._handle_email_otp_manual(account)

            # 检测邮箱OTP输入框
            otp_input_selectors = [
                "input[placeholder*='请输入']",
                "input[placeholder*='验证码']",
                "input[placeholder*='OTP']",
                ".phone-verify-container input",
                ".eds-input__input"
            ]

            otp_input = None
            for selector in otp_input_selectors:
                otp_input = self.page.query_selector(selector)
                if otp_input and otp_input.is_visible():
                    logger.info(f"[OK] 找到OTP输入框: {selector}")
                    break

            if not otp_input:
                logger.error("[FAIL] 未找到OTP输入框")
                return False, "未找到OTP输入框"

            # 创建新的浏览器页面用于邮箱登录
            logger.info("[EMAIL] 正在打开邮箱页面获取验证码...")
            email_page = self.context.new_page()

            try:
                # 获取验证码
                otp_code = await self._get_otp_from_email(email_page, email, email_password)

                if otp_code:
                    # 自动填入验证码
                    logger.info(f"[KEY] 自动填入验证码: {otp_code}")
                    otp_input.fill(otp_code)
                    time.sleep(1)

                    # 点击确认按钮
                    confirm_selectors = [
                        "button:has-text('确认')",
                        "button:has-text('提交')",
                        "button:has-text('验证')",
                        ".eds-button--primary"
                    ]

                    for selector in confirm_selectors:
                        confirm_btn = self.page.query_selector(selector)
                        if confirm_btn and confirm_btn.is_visible():
                            confirm_btn.click()
                            logger.info("[OK] 已点击确认按钮")
                            break

                    # 等待验证结果
                    time.sleep(3)

                    # 检查是否验证成功
                    if self._is_login_successful():
                        logger.success("[DONE] 邮箱OTP自动验证成功！")
                        return True, "邮箱OTP自动验证成功"
                    else:
                        logger.warning("[WARN] OTP验证可能失败，请检查")
                        return False, "OTP验证失败"
                else:
                    logger.error("[FAIL] 无法获取邮箱验证码")
                    return False, "无法获取邮箱验证码"

            finally:
                # 关闭邮箱页面
                email_page.close()

        except Exception as e:
            logger.error(f"[FAIL] 邮箱OTP自动化处理失败: {e}")
            return False, f"邮箱OTP自动化失败: {e}"

    async def _handle_email_otp_manual(self, account: Dict) -> Tuple[bool, str]:
        """手动处理邮箱OTP验证"""
        try:
            logger.info("[STOP] 邮箱OTP手动处理模式")

            # 提示用户手动处理
            print("\n" + "="*50)
            print("[EMAIL] 邮箱验证码处理")
            print("="*50)
            print("请按以下步骤操作：")
            print("1. 打开您的邮箱")
            print("2. 查找最新的验证码邮件")
            print("3. 复制验证码")
            print("4. 在浏览器中输入验证码")
            print("5. 点击确认按钮")
            print("="*50)

            # 等待用户完成
            input("完成邮箱验证后，按回车键继续...")

            # 检查登录状态
            if self._is_login_successful():
                logger.success("[OK] 邮箱验证完成")
                return True, "邮箱验证完成"
            else:
                logger.warning("[WARN] 登录状态未确认")
                return True, "等待登录确认"

        except Exception as e:
            logger.error(f"[FAIL] 邮箱OTP手动处理失败: {e}")
            return False, f"邮箱OTP手动处理失败: {e}"

    async def _get_otp_from_email(self, email_page: Page, email: str, email_password: str) -> Optional[str]:
        """从邮箱获取OTP验证码"""
        try:
            # 根据邮箱类型选择登录URL
            if 'qq.com' in email:
                email_url = 'https://mail.qq.com/'
            elif 'gmail.com' in email:
                email_url = 'https://mail.google.com/'
            elif '163.com' in email:
                email_url = 'https://mail.163.com/'
            elif '126.com' in email:
                email_url = 'https://mail.126.com/'
            else:
                logger.warning(f"[WARN] 未知邮箱类型: {email}")
                return None

            logger.info(f"[EMAIL] 正在登录邮箱: {email_url}")
            email_page.goto(email_url, timeout=30000)
            email_page.wait_for_load_state("networkidle")

            # 这里可以集成现有的邮箱登录处理器
            # 简化版：等待用户手动登录邮箱
            logger.info("[WAIT] 请在邮箱页面完成登录...")
            time.sleep(10)  # 给用户时间登录

            # 查找最新的验证码邮件
            # 这里需要根据不同邮箱的DOM结构来实现
            # 简化版：返回None，让用户手动处理
            logger.info("[TIP] 邮箱OTP自动提取功能开发中，请手动获取验证码")
            return None

        except Exception as e:
            logger.error(f"[FAIL] 邮箱OTP获取失败: {e}")
            return None

    def _is_login_successful(self) -> bool:
        """检查是否登录成功"""
        try:
            # 检查常见的登录成功标识
            success_indicators = [
                "text=控制台",
                "text=仪表板",
                "text=dashboard",
                "text=主页",
                ".user-info",
                ".logout",
                "text=退出登录"
            ]

            for indicator in success_indicators:
                if self.page.query_selector(indicator):
                    return True

            # 检查URL变化
            current_url = self.page.url
            if any(keyword in current_url.lower() for keyword in ['dashboard', 'home', 'portal', 'main']):
                return True

            return False

        except Exception as e:
            logger.error(f"[FAIL] 登录状态检查失败: {e}")
            return False
