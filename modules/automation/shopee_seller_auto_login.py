#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Shopee卖家端自动登录模块

专家级全自动登录系统，能够：
1. 自动打开对应账号登录网页
2. 自动填写用户名和密码
3. 自动处理验证码弹窗
4. 自动进入卖家端后台
5. 实现完整的登录流程自动化

技术特性：
- 使用Playwright实现反检测
- 智能等待和重试机制
- 完善的错误处理和日志
- 模块化设计，易于维护
"""

import time
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from loguru import logger

from playwright.sync_api import sync_playwright, Browser, Page, Playwright
from playwright.async_api import async_playwright

# 本地模块导入
from ..utils.shopee_login_handler import ShopeeLoginHandler
from ..utils.shopee_verification_handler import ShopeeVerificationHandler
from ..utils.enhanced_recording_wizard import EnhancedRecordingWizard
from ..services.platform_login_service import LoginService


@dataclass
class LoginResult:
    """登录结果数据类"""
    success: bool
    account_id: str
    login_url: str
    final_url: str = ""
    error_message: str = ""
    verification_required: bool = False
    login_time: float = 0.0
    screenshots: List[str] = None
    
    def __post_init__(self):
        if self.screenshots is None:
            self.screenshots = []


class ShopeeSellerAutoLogin:
    """Shopee卖家端自动登录器"""
    
    def __init__(self, headless: bool = False, slow_mo: int = 100):
        """
        初始化自动登录器
        
        Args:
            headless: 是否无头模式
            slow_mo: 操作间隔时间（毫秒）
        """
        self.headless = headless
        self.slow_mo = slow_mo
        self.browser: Optional[Browser] = None
        self.playwright: Optional[Playwright] = None
        
        # 初始化处理器
        self.login_handler: Optional[ShopeeLoginHandler] = None
        self.verification_handler: Optional[ShopeeVerificationHandler] = None
        self.recording_wizard: Optional[EnhancedRecordingWizard] = None
        
        # 配置信息
        self.config = {
            'timeout': 30000,  # 30秒超时
            'wait_for_selector_timeout': 10000,  # 10秒选择器等待
            'navigation_timeout': 30000,  # 30秒导航超时
            'screenshot_on_failure': True,
            'max_retries': 3,
            'retry_delay': 2.0
        }
        
        logger.info("🤖 Shopee卖家端自动登录器已初始化")
    
    def __enter__(self):
        """上下文管理器入口"""
        self.start_browser()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close_browser()
    
    def start_browser(self) -> bool:
        """启动浏览器"""
        try:
            logger.info("🚀 启动浏览器...")
            
            self.playwright = sync_playwright().start()
            
            # 浏览器启动参数
            browser_args = [
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
                '--disable-extensions',
                '--no-first-run',
                '--disable-default-apps',
                '--disable-component-extensions-with-background-pages'
            ]
            
            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                slow_mo=self.slow_mo,
                args=browser_args
            )
            
            # 初始化处理器
            self.login_handler = ShopeeLoginHandler(self.browser)
            self.recording_wizard = EnhancedRecordingWizard()
            
            logger.success("✅ 浏览器启动成功")
            return True
            
        except Exception as e:
            logger.error(f"❌ 浏览器启动失败: {e}")
            return False
    
    def close_browser(self):
        """关闭浏览器"""
        try:
            if self.browser:
                self.browser.close()
                logger.info("✅ 浏览器已关闭")
            
            if self.playwright:
                self.playwright.stop()
                logger.info("✅ Playwright已停止")
                
        except Exception as e:
            logger.error(f"⚠️ 关闭浏览器时出错: {e}")
    
    def login_single_account(self, account_info: Dict[str, Any]) -> LoginResult:
        """
        登录单个账号
        
        Args:
            account_info: 账号信息字典
            
        Returns:
            LoginResult: 登录结果
        """
        start_time = time.time()
        account_id = account_info.get('account_id', 'Unknown')
        login_url = account_info.get('login_url', '')
        
        logger.info(f"🎯 开始登录账号: {account_id}")
        logger.info(f"🔗 登录URL: {login_url}")
        
        try:
            # 步骤1: 验证账号信息
            if not self._validate_account_info(account_info):
                return LoginResult(
                    success=False,
                    account_id=account_id,
                    login_url=login_url,
                    error_message="账号信息验证失败"
                )
            
            # 步骤2: 打开登录页面
            page = self._open_login_page(account_info)
            if not page:
                return LoginResult(
                    success=False,
                    account_id=account_id,
                    login_url=login_url,
                    error_message="打开登录页面失败"
                )

            # 步骤3: 优先调用统一登录服务（成功则直接返回）
            try:
                svc = LoginService()
                if svc.ensure_logged_in("shopee", page, account_info):
                    final_url = page.url
                    login_time = time.time() - start_time
                    logger.success(f"🎉 账号 {account_id} 登录成功！（LoginService）")
                    logger.info(f"📊 登录耗时: {login_time:.2f} 秒")
                    logger.info(f"🔗 最终URL: {final_url}")
                    return LoginResult(
                        success=True,
                        account_id=account_id,
                        login_url=login_url,
                        final_url=final_url,
                        login_time=login_time,
                    )
                else:
                    logger.warning("⚠️ LoginService 未完成登录，回退到 legacy 自动登录")
            except Exception as e:
                logger.warning(f"⚠️ LoginService 调用失败，回退到 legacy 自动登录: {e}")

            # 步骤3(b): 执行 legacy 自动登录
            login_success = self._perform_auto_login(page, account_info)

            # 步骤4: 验证登录结果
            if login_success:
                final_url = page.url
                login_time = time.time() - start_time
                
                logger.success(f"🎉 账号 {account_id} 登录成功！")
                logger.info(f"📊 登录耗时: {login_time:.2f} 秒")
                logger.info(f"🔗 最终URL: {final_url}")
                
                return LoginResult(
                    success=True,
                    account_id=account_id,
                    login_url=login_url,
                    final_url=final_url,
                    login_time=login_time
                )
            else:
                return LoginResult(
                    success=False,
                    account_id=account_id,
                    login_url=login_url,
                    error_message="自动登录过程失败"
                )
                
        except Exception as e:
            error_msg = f"登录过程异常: {e}"
            logger.error(f"❌ {error_msg}")
            
            return LoginResult(
                success=False,
                account_id=account_id,
                login_url=login_url,
                error_message=error_msg
            )
    
    def login_multiple_accounts(self, accounts: List[Dict[str, Any]]) -> List[LoginResult]:
        """
        批量登录多个账号
        
        Args:
            accounts: 账号信息列表
            
        Returns:
            List[LoginResult]: 登录结果列表
        """
        logger.info(f"🚀 开始批量登录 {len(accounts)} 个账号")
        
        results = []
        
        for i, account in enumerate(accounts, 1):
            account_id = account.get('account_id', f'Account_{i}')
            logger.info(f"📋 正在处理账号 {i}/{len(accounts)}: {account_id}")
            
            try:
                # 登录单个账号
                result = self.login_single_account(account)
                results.append(result)
                
                # 短暂休息，避免请求过快
                if i < len(accounts):
                    logger.info("⏳ 账号间隔休息...")
                    time.sleep(3.0)
                    
            except Exception as e:
                logger.error(f"❌ 账号 {account_id} 处理异常: {e}")
                results.append(LoginResult(
                    success=False,
                    account_id=account_id,
                    login_url=account.get('login_url', ''),
                    error_message=f"处理异常: {e}"
                ))
        
        # 输出批量登录汇总
        self._print_batch_summary(results)
        
        return results
    
    def _validate_account_info(self, account_info: Dict[str, Any]) -> bool:
        """验证账号信息完整性"""
        required_fields = ['account_id', 'login_url', 'username', 'password']
        
        for field in required_fields:
            if not account_info.get(field):
                logger.error(f"❌ 缺少必要字段: {field}")
                return False
        
        # 验证URL格式
        login_url = account_info.get('login_url', '')
        if not login_url.startswith(('http://', 'https://')):
            logger.error(f"❌ 登录URL格式无效: {login_url}")
            return False
        
        logger.success("✅ 账号信息验证通过")
        return True
    
    def _open_login_page(self, account_info: Dict[str, Any]) -> Optional[Page]:
        """打开登录页面"""
        login_url = account_info.get('login_url', '')
        
        try:
            logger.info(f"🌐 正在打开登录页面: {login_url}")
            
            # 创建新页面
            page = self.browser.new_page()
            
            # 设置页面配置
            page.set_default_timeout(self.config['timeout'])
            page.set_default_navigation_timeout(self.config['navigation_timeout'])
            
            # 导航到登录页面
            page.goto(login_url, wait_until='domcontentloaded')
            
            # 等待页面稳定
            logger.info("⏳ 等待页面加载完成...")
            time.sleep(3.0)
            
            # 验证页面是否正确加载
            if self._verify_login_page(page):
                logger.success("✅ 登录页面加载成功")
                return page
            else:
                logger.error("❌ 登录页面验证失败")
                page.close()
                return None
                
        except Exception as e:
            logger.error(f"❌ 打开登录页面失败: {e}")
            if 'page' in locals():
                try:
                    page.close()
                except:
                    pass
            return None
    
    def _verify_login_page(self, page: Page) -> bool:
        """验证登录页面是否正确"""
        try:
            # 检查页面标题
            title = page.title().lower()
            if any(keyword in title for keyword in ['login', 'signin', 'seller', 'shopee']):
                logger.info(f"✅ 页面标题验证通过: {title}")
                return True
            
            # 检查关键元素
            login_indicators = [
                'input[type="text"]',
                'input[type="password"]',
                'button:has-text("登入")',
                'button:has-text("登录")',
                'button:has-text("Login")',
                '[placeholder*="用户名"]',
                '[placeholder*="username"]',
                '[placeholder*="密码"]',
                '[placeholder*="password"]'
            ]
            
            for indicator in login_indicators:
                try:
                    element = page.query_selector(indicator)
                    if element and element.is_visible():
                        logger.info(f"✅ 找到登录元素: {indicator}")
                        return True
                except:
                    continue
            
            logger.warning("⚠️ 未找到明确的登录页面标识")
            return False
            
        except Exception as e:
            logger.error(f"❌ 验证登录页面时出错: {e}")
            return False
    
    def _perform_auto_login(self, page: Page, account_info: Dict[str, Any]) -> bool:
        """执行自动登录过程"""
        try:
            logger.info("🤖 开始执行自动登录...")
            
            # 方法1: 使用改进的录制向导
            if self._try_enhanced_recording_wizard(page, account_info):
                return True
            
            # 方法2: 使用登录处理器
            if self._try_login_handler(account_info):
                return True
            
            # 方法3: 使用基础登录方法
            if self._try_basic_login(page, account_info):
                return True
            
            logger.error("❌ 所有登录方法均失败")
            return False
            
        except Exception as e:
            logger.error(f"❌ 自动登录执行异常: {e}")
            return False
    
    def _try_enhanced_recording_wizard(self, page: Page, account_info: Dict[str, Any]) -> bool:
        """尝试使用改进的录制向导"""
        try:
            logger.info("🎯 尝试使用改进的录制向导...")
            
            if not self.recording_wizard:
                logger.warning("⚠️ 录制向导未初始化")
                return False
            
            # 使用录制向导执行登录
            result = self.recording_wizard.record_shopee_login(
                username=account_info.get('username', ''),
                password=account_info.get('password', ''),
                login_url=account_info.get('login_url', ''),
                account_id=account_info.get('account_id', '')
            )
            
            if result:
                logger.success("✅ 录制向导登录成功")
                return True
            else:
                logger.warning("⚠️ 录制向导登录失败")
                return False
                
        except Exception as e:
            logger.error(f"❌ 录制向导登录异常: {e}")
            return False
    
    def _try_login_handler(self, account_info: Dict[str, Any]) -> bool:
        """尝试使用登录处理器"""
        try:
            logger.info("🎯 尝试使用登录处理器...")
            
            if not self.login_handler:
                logger.warning("⚠️ 登录处理器未初始化")
                return False
            
            # 转换账号信息格式
            handler_account_info = {
                'login_url': account_info.get('login_url', ''),
                'Username': account_info.get('username', ''),
                'Password': account_info.get('password', ''),
                'E-mail': account_info.get('email', ''),
                'Email password': account_info.get('email_password', '')
            }
            
            result = self.login_handler.login_to_shopee(handler_account_info)
            
            if result:
                logger.success("✅ 登录处理器登录成功")
                return True
            else:
                logger.warning("⚠️ 登录处理器登录失败")
                return False
                
        except Exception as e:
            logger.error(f"❌ 登录处理器异常: {e}")
            return False
    
    def _try_basic_login(self, page: Page, account_info: Dict[str, Any]) -> bool:
        """尝试基础登录方法"""
        try:
            logger.info("🎯 尝试基础登录方法...")
            
            username = account_info.get('username', '')
            password = account_info.get('password', '')
            
            # 填写用户名
            if not self._fill_username(page, username):
                return False
            
            # 填写密码
            if not self._fill_password(page, password):
                return False
            
            # 点击登录按钮
            if not self._click_login_button(page):
                return False
            
            # 等待登录响应
            logger.info("⏳ 等待登录响应...")
            time.sleep(5.0)
            
            # 检查是否需要验证码
            if self._detect_verification_needed(page):
                logger.info("📱 检测到验证码需求，等待手动处理...")
                return self._handle_verification_manually(page)
            
            # 验证登录成功
            return self._verify_login_success(page)
            
        except Exception as e:
            logger.error(f"❌ 基础登录方法异常: {e}")
            return False
    
    def _fill_username(self, page: Page, username: str) -> bool:
        """填写用户名"""
        username_selectors = [
            'input[type="text"]',
            'input[name="username"]',
            'input[placeholder*="用户名"]',
            'input[placeholder*="username"]',
            'input[placeholder*="邮箱"]',
            'input[placeholder*="email"]'
        ]
        
        for selector in username_selectors:
            try:
                element = page.query_selector(selector)
                if element and element.is_visible():
                    element.clear()
                    element.fill(username)
                    logger.success(f"✅ 用户名填写成功: {selector}")
                    return True
            except:
                continue
        
        logger.error("❌ 用户名填写失败")
        return False
    
    def _fill_password(self, page: Page, password: str) -> bool:
        """填写密码"""
        password_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            'input[placeholder*="密码"]',
            'input[placeholder*="password"]'
        ]
        
        for selector in password_selectors:
            try:
                element = page.query_selector(selector)
                if element and element.is_visible():
                    element.clear()
                    element.fill(password)
                    logger.success(f"✅ 密码填写成功: {selector}")
                    return True
            except:
                continue
        
        logger.error("❌ 密码填写失败")
        return False
    
    def _click_login_button(self, page: Page) -> bool:
        """点击登录按钮"""
        login_selectors = [
            'button:has-text("登入")',
            'button:has-text("登录")',
            'button:has-text("Login")',
            'button:has-text("Sign in")',
            'button[type="submit"]',
            'input[type="submit"]',
            '[role="button"]:has-text("登入")'
        ]
        
        for selector in login_selectors:
            try:
                element = page.query_selector(selector)
                if element and element.is_visible():
                    element.click()
                    logger.success(f"✅ 登录按钮点击成功: {selector}")
                    return True
            except:
                continue
        
        logger.error("❌ 登录按钮点击失败")
        return False
    
    def _detect_verification_needed(self, page: Page) -> bool:
        """检测是否需要验证码"""
        verification_indicators = [
            'text="验证码"',
            'text="verification"',
            'text="OTP"',
            '[placeholder*="验证码"]',
            '[placeholder*="verification"]',
            'div[role="dialog"]',
            '.modal',
            '.popup'
        ]
        
        for indicator in verification_indicators:
            try:
                element = page.query_selector(indicator)
                if element and element.is_visible():
                    logger.info(f"✅ 检测到验证码需求: {indicator}")
                    return True
            except:
                continue
        
        return False
    
    def _handle_verification_manually(self, page: Page) -> bool:
        """手动处理验证码"""
        logger.info("📱 等待用户手动处理验证码...")
        
        # 显示用户指引
        self._show_verification_guidance()
        
        # 等待用户处理（最多5分钟）
        start_time = time.time()
        timeout = 300  # 5分钟
        
        while time.time() - start_time < timeout:
            try:
                # 检查验证码是否已处理
                if not self._detect_verification_needed(page):
                    logger.success("✅ 验证码已处理")
                    return self._verify_login_success(page)
                
                time.sleep(2)  # 每2秒检查一次
                
            except:
                time.sleep(2)
                continue
        
        logger.error("❌ 验证码处理超时")
        return False
    
    def _show_verification_guidance(self):
        """显示验证码处理指引"""
        print("\n" + "="*60)
        print("📱 验证码处理指引")
        print("="*60)
        print("\n🎯 请按照以下步骤处理验证码:")
        print("   1. 查看弹出的验证码窗口")
        print("   2. 根据提示获取验证码（邮箱/短信）")
        print("   3. 在输入框中输入验证码")
        print("   4. 点击确认按钮")
        print("\n⏰ 系统将自动检测处理结果")
        print("💡 如有问题，请查看浏览器窗口进行手动操作")
        print("\n" + "="*60)
    
    def _verify_login_success(self, page: Page) -> bool:
        """验证登录是否成功"""
        try:
            logger.info("🔍 验证登录成功状态...")
            
            # 等待页面加载
            time.sleep(3.0)
            
            # 检查URL变化
            current_url = page.url
            if any(keyword not in current_url.lower() for keyword in ['signin', 'login']):
                logger.success("✅ URL验证：已离开登录页面")
                return True
            
            # 检查页面内容
            success_indicators = [
                '卖家中心',
                'seller center',
                'dashboard',
                '店铺管理',
                '商品管理',
                '订单管理',
                'shop management',
                'product management',
                'order management'
            ]
            
            for indicator in success_indicators:
                try:
                    element = page.query_selector(f'*:has-text("{indicator}")')
                    if element and element.is_visible():
                        logger.success(f"✅ 内容验证：找到成功标识 {indicator}")
                        return True
                except:
                    continue
            
            # 检查页面标题
            title = page.title().lower()
            if any(keyword in title for keyword in ['seller', 'dashboard', '卖家', '后台']):
                logger.success(f"✅ 标题验证：{title}")
                return True
            
            logger.warning("⚠️ 登录成功状态验证不确定")
            return False
            
        except Exception as e:
            logger.error(f"❌ 验证登录成功时出错: {e}")
            return False
    
    def _print_batch_summary(self, results: List[LoginResult]):
        """输出批量登录汇总"""
        total = len(results)
        success_count = sum(1 for r in results if r.success)
        
        print("\n" + "="*80)
        print("📊 批量登录汇总报告")
        print("="*80)
        print(f"\n📈 整体统计:")
        print(f"   总账号数: {total}")
        print(f"   成功登录: {success_count}")
        print(f"   失败登录: {total - success_count}")
        print(f"   成功率: {success_count/total*100:.1f}%")
        
        if success_count > 0:
            print(f"\n✅ 成功登录的账号:")
            for result in results:
                if result.success:
                    print(f"   - {result.account_id} ({result.login_time:.1f}s)")
        
        if total - success_count > 0:
            print(f"\n❌ 失败登录的账号:")
            for result in results:
                if not result.success:
                    print(f"   - {result.account_id}: {result.error_message}")
        
        print("\n" + "="*80)


# 便捷函数
def auto_login_shopee_accounts(accounts: List[Dict[str, Any]], headless: bool = False) -> List[LoginResult]:
    """
    便捷函数：自动登录Shopee账号
    
    Args:
        accounts: 账号信息列表
        headless: 是否无头模式
        
    Returns:
        List[LoginResult]: 登录结果列表
    """
    with ShopeeSellerAutoLogin(headless=headless) as auto_login:
        return auto_login.login_multiple_accounts(accounts)


def auto_login_single_shopee_account(account_info: Dict[str, Any], headless: bool = False) -> LoginResult:
    """
    便捷函数：自动登录单个Shopee账号
    
    Args:
        account_info: 账号信息
        headless: 是否无头模式
        
    Returns:
        LoginResult: 登录结果
    """
    with ShopeeSellerAutoLogin(headless=headless) as auto_login:
        return auto_login.login_single_account(account_info)


if __name__ == "__main__":
    # 测试代码
    test_account = {
        'account_id': '测试账号',
        'username': 'test_user',
        'password': 'test_password',
        'login_url': 'https://seller.shopee.com.br/',
        'email': 'test@example.com',
        'email_password': 'email_password'
    }
    
    result = auto_login_single_shopee_account(test_account)
    print(f"登录结果: {result.success}") 