"""
Shopee自动登录模块 - 完整封装版本
=================================

功能特性：
- 🎯 智能登录状态检测
- 📝 自动表单填写
- 📱 手机验证码自动处理
- 🛡️ 持久化浏览器Profile
- 🔄 错误恢复机制

版本：v2.0.0
作者：跨境电商ERP系统
更新：2025-08-29
"""

import time
from typing import Dict, Optional
from playwright.sync_api import Page
from modules.utils.logger import logger


class ShopeeAutoLogin:
    """Shopee自动登录处理器"""
    
    def __init__(self, page: Page, account: Dict):
        """
        初始化Shopee自动登录处理器
        
        Args:
            page: Playwright页面对象
            account: 账号配置信息
        """
        self.page = page
        self.account = account
        self.username = account.get('username', '')
        self.password = account.get('password', '')
        
    def execute_auto_login(self) -> bool:
        """
        执行完整的自动登录流程
        
        Returns:
            bool: 登录是否成功
        """
        try:
            logger.info("🚀 启动Shopee自动登录流程")
            
            # 1. 检查是否已经登录
            if self._check_already_logged_in():
                logger.success("🎉 检测到已经登录，跳过登录流程")
                return True
            
            # 2. 执行登录表单填写
            if not self._fill_login_form():
                logger.error("❌ 登录表单填写失败")
                return False
            
            # 3. 处理验证码（如需要）
            if self._check_verification_needed():
                if not self._handle_verification():
                    logger.error("❌ 验证码处理失败")
                    return False
            
            # 4. 验证登录结果
            if self._verify_login_success():
                logger.success("🎉 Shopee自动登录成功！")
                return True
            else:
                logger.warning("⚠️ 登录状态不明确")
                return False
                
        except Exception as e:
            logger.error(f"❌ Shopee自动登录异常: {e}")
            return False
    
    def _check_already_logged_in(self) -> bool:
        """检查是否已经登录"""
        try:
            current_url = self.page.url
            logger.info(f"📍 当前页面: {current_url}")
            
            # URL检测 - 排除登录页面
            if 'signin' in current_url or 'login' in current_url:
                logger.info("🔍 当前在登录页面，需要进行登录")
                return False
            
            # 检查是否在后台页面
            backend_urls = [
                'seller.shopee.cn/portal',
                'seller.shopee.cn/dashboard', 
                'no-permission'
            ]
            
            if any(url in current_url for url in backend_urls):
                logger.success("🎉 检测到已在卖家后台页面")
                return True
            
            # DOM元素检测
            return self._check_backend_elements()
            
        except Exception as e:
            logger.error(f"❌ 登录状态检测失败: {e}")
            return False
    
    def _check_backend_elements(self) -> bool:
        """检查后台页面元素"""
        try:
            # 检查是否有登录表单
            login_inputs = self.page.query_selector_all(
                'input[type="password"], input[placeholder*="密码"], '
                'input[placeholder*="邮箱"], input[placeholder*="用户名"]'
            )
            login_buttons = self.page.query_selector_all(
                'button:has-text("登入"), button:has-text("登录")'
            )
            
            if len(login_inputs) > 0 or len(login_buttons) > 0:
                logger.info("🔍 检测到登录表单元素，确认在登录页面")
                return False
            
            # 检查后台内容
            page_content = self.page.text_content('body') or ""
            backend_indicators = [
                '店铺管理',
                '商品管理', 
                '订单管理',
                '数据概况',
                '营销中心'
            ]
            
            if any(indicator in page_content for indicator in backend_indicators):
                logger.success("🎉 检测到后台页面内容")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ 后台元素检测失败: {e}")
            return False
    
    def _fill_login_form(self) -> bool:
        """填写登录表单"""
        try:
            logger.info("📝 开始填写登录表单")
            
            # 查找用户名输入框
            username_selectors = [
                'input[placeholder*="邮箱"]',
                'input[placeholder*="用户名"]',
                'input[type="email"]',
                'input[name="username"]',
                'input[name="email"]'
            ]
            
            username_input = None
            for selector in username_selectors:
                try:
                    username_input = self.page.wait_for_selector(selector, timeout=3000)
                    if username_input:
                        logger.success(f"✅ 找到用户名输入框: {selector}")
                        break
                except:
                    continue
            
            if not username_input:
                logger.error("❌ 未找到用户名输入框")
                return False
            
            # 填写用户名
            username_input.fill(self.username)
            logger.success(f"✅ 已填写用户名: {self.username}")
            
            # 查找密码输入框
            password_selectors = [
                'input[name="password"]',
                'input[type="password"]',
                'input[placeholder*="密码"]'
            ]
            
            password_input = None
            for selector in password_selectors:
                try:
                    password_input = self.page.wait_for_selector(selector, timeout=3000)
                    if password_input:
                        logger.success(f"✅ 找到密码输入框: {selector}")
                        break
                except:
                    continue
            
            if not password_input:
                logger.error("❌ 未找到密码输入框")
                return False
            
            # 填写密码
            password_input.fill(self.password)
            logger.success("✅ 已填写密码")
            
            # 尝试勾选记住我（可选）
            self._try_check_remember_me()
            
            # 点击登录按钮
            return self._click_login_button()
            
        except Exception as e:
            logger.error(f"❌ 登录表单填写失败: {e}")
            return False
    
    def _try_check_remember_me(self):
        """尝试勾选记住我复选框（可选功能）"""
        try:
            logger.info("🔍 尝试查找'记住我'复选框...")
            
            # 简化的查找逻辑
            checkboxes = self.page.query_selector_all('input[type="checkbox"]')
            for checkbox in checkboxes:
                if checkbox.is_visible():
                    try:
                        parent = checkbox.locator('xpath=..')
                        parent_text = parent.text_content() or ""
                        if any(keyword in parent_text for keyword in ['记住我', '记住登录', '保持登录']):
                            if not checkbox.is_checked():
                                checkbox.click()
                                logger.success("✅ 已勾选'记住我'")
                            return
                    except:
                        continue
            
            logger.warning("⚠️ 未找到'记住我'复选框，继续登录流程")
            
        except Exception as e:
            logger.warning(f"⚠️ '记住我'处理失败: {e}")
    
    def _click_login_button(self) -> bool:
        """点击登录按钮"""
        try:
            login_button_selectors = [
                'button:has-text("登入")',
                'button:has-text("登录")',
                'input[type="submit"]',
                'button[type="submit"]'
            ]
            
            login_button = None
            for selector in login_button_selectors:
                try:
                    login_button = self.page.wait_for_selector(selector, timeout=3000)
                    if login_button and login_button.is_visible():
                        logger.success(f"✅ 找到登录按钮: {selector}")
                        break
                except:
                    continue
            
            if not login_button:
                logger.error("❌ 未找到登录按钮")
                return False
            
            # 点击登录按钮
            login_button.click()
            logger.success("✅ 已点击登录按钮")
            
            # 等待页面响应
            self.page.wait_for_timeout(3000)
            return True
            
        except Exception as e:
            logger.error(f"❌ 点击登录按钮失败: {e}")
            return False
    
    def _check_verification_needed(self) -> bool:
        """检查是否需要验证码"""
        try:
            verification_selectors = [
                '.phone-verify-container',
                '.verification-modal',
                '.otp-modal',
                '[class*="verify"]'
            ]
            
            for selector in verification_selectors:
                try:
                    element = self.page.wait_for_selector(selector, timeout=2000)
                    if element and element.is_visible():
                        logger.info(f"🔐 检测到验证弹窗: {selector}")
                        return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"❌ 验证检查失败: {e}")
            return False
    
    def _handle_verification(self) -> bool:
        """处理验证码"""
        try:
            logger.info("📱 启动验证码处理流程")
            
            # 提示用户输入验证码
            print("\n" + "🔥"*60)
            print("📱 Shopee 手机验证码输入")
            print("🔥"*60)
            print("🔔 请查看您的手机短信，获取 Shopee 发送的验证码")
            print("📞 验证码格式：4-6位数字（例如：123456）")
            print("⏰ 验证码有效期：5-10分钟")
            print("🚀 输入验证码后将自动完成登录并保存登录状态")
            print("🔥"*60)
            
            # 获取用户输入
            verification_code = input("🎯 请输入手机验证码: ").strip()
            
            if not verification_code:
                logger.error("❌ 验证码不能为空")
                return False
            
            logger.info(f"✅ 收到验证码: {verification_code}，准备自动填写...")
            
            # 查找验证码输入框
            otp_input = self._find_verification_input()
            if not otp_input:
                logger.error("❌ 未找到验证码输入框")
                return False
            
            # 填写验证码
            otp_input.click()
            self.page.wait_for_timeout(500)
            otp_input.fill("")
            otp_input.fill(verification_code)
            logger.success(f"✅ 已填写验证码: {verification_code}")
            
            # 点击确认按钮
            return self._click_confirm_button()
            
        except Exception as e:
            logger.error(f"❌ 验证码处理失败: {e}")
            return False
    
    def _find_verification_input(self):
        """查找验证码输入框"""
        selectors = [
            'input[placeholder*="请输入"]',
            'input[placeholder*="验证码"]',
            'input[placeholder*="OTP"]',
            '.phone-verify-container input[type="text"]',
            '.verification-modal input[type="text"]',
            'input[maxlength="6"]',
            'input[maxlength="4"]'
        ]
        
        for selector in selectors:
            try:
                input_elem = self.page.wait_for_selector(selector, timeout=3000)
                if input_elem and input_elem.is_visible():
                    logger.success(f"✅ 找到验证码输入框: {selector}")
                    return input_elem
            except:
                continue
        
        return None
    
    def _click_confirm_button(self) -> bool:
        """点击确认按钮"""
        try:
            confirm_selectors = [
                'button:has-text("确认")',
                'button:has-text("确定")',
                'button:has-text("提交")',
                'button:has-text("验证")',
                '.phone-verify-container button',
                '.verification-modal button'
            ]
            
            confirm_button = None
            for selector in confirm_selectors:
                try:
                    confirm_button = self.page.wait_for_selector(selector, timeout=3000)
                    if confirm_button and confirm_button.is_visible() and not confirm_button.is_disabled():
                        logger.success(f"✅ 找到确认按钮: {selector}")
                        break
                except:
                    continue
            
            if not confirm_button:
                logger.error("❌ 未找到确认按钮")
                return False
            
            # 点击确认按钮
            confirm_button.click()
            logger.success("✅ 已点击确认按钮")
            
            # 等待验证结果
            self.page.wait_for_timeout(8000)
            return True
            
        except Exception as e:
            logger.error(f"❌ 点击确认按钮失败: {e}")
            return False
    
    def _verify_login_success(self) -> bool:
        """验证登录是否成功"""
        try:
            current_url = self.page.url
            logger.info(f"📍 最终页面检查: {current_url}")
            
            # URL成功标志
            success_indicators = [
                'seller.shopee.cn/portal',
                'seller.shopee.cn/dashboard',
                'no-permission',
                'seller.shopee.cn/account/shop'
            ]
            
            # URL失败标志
            failure_indicators = [
                'signin',
                'login',
                'account/signin'
            ]
            
            is_success_url = any(indicator in current_url.lower() for indicator in success_indicators)
            is_failure_url = any(indicator in current_url.lower() for indicator in failure_indicators)
            
            if is_success_url:
                logger.success("🎉 登录成功！已进入卖家后台")
                if 'no-permission' in current_url:
                    logger.info("📋 当前显示权限页面，这是正常的卖家后台页面")
                return True
            elif is_failure_url:
                logger.warning("⚠️ 仍在登录页面，登录可能未完成")
                return False
            else:
                logger.info("❓ 页面状态不明确，但可能已登录")
                return True
                
        except Exception as e:
            logger.error(f"❌ 登录结果验证失败: {e}")
            return False


# 使用示例
def create_shopee_auto_login(page: Page, account: Dict) -> ShopeeAutoLogin:
    """
    创建Shopee自动登录实例
    
    Args:
        page: Playwright页面对象
        account: 账号配置
        
    Returns:
        ShopeeAutoLogin: 自动登录处理器实例
    """
    return ShopeeAutoLogin(page, account)
