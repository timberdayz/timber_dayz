#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Shopee登录处理器模块

模块化设计：
- 纯粹的Shopee登录逻辑
- 集成邮箱验证码处理
- 验证码验证逻辑修复
- 统一的登录接口
"""

import time
from typing import Optional, Dict, Any
from loguru import logger
from playwright.sync_api import Page, Browser

from .shopee_verification_config import get_verification_config, get_email_button_wait_time, get_debug_screenshot_path
from .email_login_handler import EmailLoginHandler

from modules.services.platform_login_service import LoginService


class ShopeeLoginHandler:
    """Shopee登录处理器（模块化设计）"""

    def __init__(self, browser: Browser):
        self.browser = browser
        self.config = get_verification_config()
        self.email_handler = EmailLoginHandler(browser)

    def login_to_shopee(self, account_info: Dict[str, Any]) -> bool:
        """
        Shopee登录主函数（统一接口）

        Args:
            account_info: 账号信息字典

        Returns:
            bool: 登录是否成功
        """
        try:
            # 基础登录操作
            page = self._perform_basic_login(account_info)
            if not page:
                return False

            # 处理验证码（如果需要）
            verification_success = self._handle_verification_if_needed(page, account_info)

            if verification_success:
                # 验证最终登录状态
                final_success = self._verify_final_login_success(page)
                logger.info(f"[TARGET] Shopee登录最终结果: {'成功' if final_success else '失败'}")
                return final_success
            else:
                logger.error("[FAIL] Shopee验证码处理失败")
                return False

        except Exception as e:
            logger.error(f"[FAIL] Shopee登录异常: {e}")
            return False

    def _perform_basic_login(self, account_info: Dict[str, Any]) -> Optional[Page]:
        """执行基础登录操作"""
        try:
            login_url = account_info.get('login_url', '')
            username = account_info.get('Username', '')
            password = account_info.get('Password', '')

            logger.info(f"[START] 开始Shopee基础登录: {username}")

            # 创建新页面
            page = self.browser.new_page()

            # 导航到登录页面
            page.goto(login_url, wait_until='domcontentloaded')
            page.wait_for_timeout(1200)

            # 优先走统一登录服务（与单次/批量流程一致），失败再回退到本地选择器策略
            try:
                svc_account = {
                    "login_url": login_url,
                    "username": account_info.get("Username") or account_info.get("username", ""),
                    "password": account_info.get("Password") or account_info.get("password", ""),
                    "email": account_info.get("E-mail") or account_info.get("email", ""),
                    "email_password": account_info.get("Email password") or account_info.get("email_password", ""),
                }
                svc = LoginService()
                if svc.ensure_logged_in("shopee", page, svc_account):
                    logger.success("[OK] 基础登录使用 LoginService 完成")
                    return page
                else:
                    logger.error("[FAIL] LoginService 未完成登录（修正模式统一入口），判定失败")
                    page.close()
                    return None
            except Exception as e:
                logger.error(f"[FAIL] LoginService 调用失败（修正模式统一入口）: {e}")
                page.close()
                return None

            # 下方旧本地选择器逻辑已不再执行（保留代码以便回溯），函数已提前返回
            page.wait_for_timeout(3000)

            # 填写用户名 - 使用更全面的选择器
            username_selectors = [
                'input[name="loginKey"]',  # Shopee特有
                'input[name="username"]',
                'input[type="text"]',
                'input[placeholder*="邮箱"]',
                'input[placeholder*="手机"]',
                'input[placeholder*="Email"]',
                'input[placeholder*="Phone"]',
                'input[placeholder*="用户名"]',
                '.ant-input[type="text"]',  # Ant Design组件
                '[data-testid*="username"]',
                '[data-testid*="email"]'
            ]
            username_filled = False
            for selector in username_selectors:
                try:
                    username_input = page.query_selector(selector)
                    if username_input and username_input.is_visible():
                        username_input.clear()
                        username_input.fill(username)
                        logger.info(f"[OK] 用户名填写成功: {selector}")
                        username_filled = True
                        break
                except Exception as e:
                    logger.debug(f"尝试选择器失败 {selector}: {e}")
                    continue

            if not username_filled:
                logger.error("[FAIL] 用户名填写失败")
                # 保存调试截图
                try:
                    from pathlib import Path
                    screenshot_dir = Path("temp/screenshots")
                    screenshot_dir.mkdir(parents=True, exist_ok=True)
                    screenshot_path = screenshot_dir / f"debug_login_failed_{int(time.time())}.png"
                    page.screenshot(path=str(screenshot_path))
                    logger.info(f"[CAM] 已保存调试截图: {screenshot_path}")
                except:
                    pass
                page.close()
                return None

            # 等待页面稳定
            page.wait_for_timeout(1000)

            # 填写密码 - 使用更全面的选择器
            password_selectors = [
                'input[type="password"]',
                'input[name="password"]',
                '.ant-input[type="password"]',  # Ant Design组件
                '[data-testid*="password"]'
            ]
            password_filled = False
            for selector in password_selectors:
                try:
                    password_input = page.query_selector(selector)
                    if password_input and password_input.is_visible():
                        password_input.clear()
                        password_input.fill(password)
                        logger.info(f"[OK] 密码填写成功: {selector}")
                        password_filled = True
                        break
                except Exception as e:
                    logger.debug(f"尝试密码选择器失败 {selector}: {e}")
                    continue

            if not password_filled:
                logger.error("[FAIL] 密码填写失败")
                # 保存调试截图
                try:
                    from pathlib import Path
                    screenshot_dir = Path("temp/screenshots")
                    screenshot_dir.mkdir(parents=True, exist_ok=True)
                    screenshot_path = screenshot_dir / f"debug_password_failed_{int(time.time())}.png"
                    page.screenshot(path=str(screenshot_path))
                    logger.info(f"[CAM] 已保存调试截图: {screenshot_path}")
                except:
                    pass
                page.close()
                return None

            # 勾选“记住我”复选框（若存在）— 强化版：多策略点击 + 状态校验
            try:
                def _is_checked() -> bool:
                    try:
                        box = page.locator('input[type="checkbox"]').first
                        if box.count() > 0:
                            try:
                                return box.is_checked()
                            except Exception:
                                val = box.get_attribute('value') or ''
                                return val.strip().lower() in ['true', '1', 'on']
                    except Exception:
                        return False
                    return False

                # 如果未勾选，尝试多种点击方式
                if not _is_checked():
                    tried = False
                    # 1) 直接对input使用check/click
                    for csel in [
                        'input.eds-checkbox__input[type="checkbox"]',
                        'label:has-text("记住我") input[type="checkbox"]',
                        'input[type="checkbox"]',
                    ]:
                        try:
                            loc = page.locator(csel).first
                            if loc.count() > 0 and loc.is_visible():
                                try:
                                    loc.check(force=True)  # type: ignore[attr-defined]
                                except Exception:
                                    loc.click(force=True)
                                tried = True
                                logger.info("[OK] 已尝试直接勾选‘记住我’复选框")
                                break
                        except Exception:
                            continue

                    # 2) 点击文本“记住我”
                    if not _is_checked():
                        try:
                            lab = page.get_by_text('记住我')  # type: ignore[attr-defined]
                            if lab and lab.count() > 0:
                                lab.first.click(force=True)
                                tried = True
                                logger.info("[OK] 通过文本点击触发‘记住我’")
                        except Exception:
                            pass

                    # 3) 在form中点击可能的图标/img或span（基于你录制的脚本）
                    if not _is_checked():
                        try:
                            frm = page.locator('form').first
                            if frm and frm.count() > 0:
                                try:
                                    frm.get_by_role('img').first.click()  # type: ignore[attr-defined]
                                    tried = True
                                except Exception:
                                    try:
                                        frm.locator('span').first.click()
                                        tried = True
                                    except Exception:
                                        pass
                        except Exception:
                            pass

                    # 4) 再次验证状态
                    if _is_checked():
                        logger.success("[OK] ‘记住我’已处于勾选状态")
                    else:
                        if tried:
                            logger.warning("[WARN] 已尝试点击‘记住我’，但状态未改变，继续登录（不阻塞）")
                        else:
                            logger.debug("[i] 未找到‘记住我’元素，跳过勾选步骤")
                else:
                    logger.info("[i] ‘记住我’已是勾选状态")
            except Exception as e:
                logger.debug(f"勾选‘记住我’过程忽略异常: {e}")

            # 点击登录按钮
            login_selectors = ['button:has-text("登入")', 'button:has-text("登录")', 'button[type="submit"]']
            login_clicked = False
            for selector in login_selectors:
                try:
                    login_button = page.query_selector(selector)
                    if login_button and login_button.is_visible():
                        login_button.click()
                        logger.info(f"[OK] 登录按钮点击成功: {selector}")
                        login_clicked = True
                        break
                except:
                    continue

            if not login_clicked:
                logger.error("[FAIL] 登录按钮点击失败")
                page.close()
                return None

            # 等待登录响应
            page.wait_for_timeout(3000)
            logger.success("[OK] Shopee基础登录操作完成")
            return page

        except Exception as e:
            logger.error(f"[FAIL] Shopee基础登录失败: {e}")
            if 'page' in locals():
                try:
                    page.close()
                except:
                    pass
            return None

    def _handle_verification_if_needed(self, page: Page, account_info: Dict[str, Any]) -> bool:
        """处理验证码（如果需要）"""
        logger.info("[SEARCH] 检查是否需要验证码处理...")

        # 检测验证码弹窗
        verification_popup = self._detect_verification_popup(page)
        if not verification_popup:
            logger.info("[i] 未检测到验证码弹窗，可能已直接登录成功")
            return True

        logger.info("[OK] 检测到验证码弹窗，开始处理...")

        # 点击发送至邮箱按钮
        email_sent = self._click_send_to_email_button(page)
        if not email_sent:
            logger.error("[FAIL] 发送至邮箱按钮点击失败")
            return False

        # 等待邮箱按钮响应
        wait_time = get_email_button_wait_time()
        logger.info(f"[TIME] 等待验证码按钮响应... ({wait_time}秒)")
        time.sleep(wait_time)

        # 尝试自动获取验证码
        verification_code = self._auto_get_verification_code(account_info)

        if verification_code:
            # 自动输入验证码
            return self._input_verification_code(page, verification_code)
        else:
            # 转为手动输入模式
            logger.warning("[WARN] 自动获取验证码失败，等待用户手动输入")
            return self._wait_for_manual_input(page)

    def _detect_verification_popup(self, page: Page) -> bool:
        """检测验证码弹窗"""
        popup_selectors = self.config.verification_popup_selectors

        for selector in popup_selectors:
            try:
                popup = page.query_selector(selector)
                if popup and popup.is_visible():
                    logger.info(f"[OK] 检测到验证码弹窗: {selector}")
                    return True
            except:
                continue

        return False

    def _click_send_to_email_button(self, page: Page) -> bool:
        """点击发送至邮箱按钮"""
        logger.info("[EMAIL] 尝试点击发送至邮箱按钮...")

        email_button_selectors = self.config.email_button_selectors

        for selector in email_button_selectors:
            try:
                button = page.query_selector(selector)
                if button and button.is_visible():
                    button_text = button.text_content()
                    logger.info(f"[SEARCH] 找到匹配按钮: {selector} (文本: '{button_text}')")

                    # 点击按钮
                    button.click()
                    logger.success(f"[OK] 成功点击发送至邮箱按钮: {selector}")
                    return True

            except Exception as e:
                logger.debug(f"发送至邮箱按钮点击失败 {selector}: {e}")
                continue

        logger.error("[FAIL] 未找到可用的发送至邮箱按钮")
        return False

    def _auto_get_verification_code(self, account_info: Dict[str, Any]) -> Optional[str]:
        """自动获取验证码"""
        try:
            email = account_info.get('E-mail', '')
            email_password = account_info.get('Email password', '')

            if not email or not email_password:
                logger.warning("[WARN] 缺少邮箱信息，无法自动获取验证码")
                return None

            logger.info(f"[EMAIL] 尝试自动获取验证码: {email}")

            # 登录邮箱
            email_page = self.email_handler.login_to_email(email, email_password)
            if not email_page:
                logger.error("[FAIL] 邮箱登录失败")
                return None

            # 等待邮件到达
            logger.info("[WAIT] 等待验证码邮件到达...")
            time.sleep(10)  # 等待邮件到达

            # 获取验证码
            verification_code = self.email_handler.get_verification_code_from_email(email_page)

            # 关闭邮箱页面
            email_page.close()

            return verification_code

        except Exception as e:
            logger.error(f"[FAIL] 自动获取验证码失败: {e}")
            return None

    def _input_verification_code(self, page: Page, code: str) -> bool:
        """输入验证码"""
        logger.info(f"[123] 尝试输入验证码: {code}")

        input_selectors = self.config.verification_input_selectors

        for selector in input_selectors:
            try:
                input_field = page.query_selector(selector)
                if input_field and input_field.is_visible():
                    input_field.clear()
                    input_field.fill(code)
                    logger.info(f"[OK] 验证码输入成功: {selector}")

                    # 点击确认按钮
                    return self._click_confirm_button(page)

            except Exception as e:
                logger.debug(f"验证码输入失败 {selector}: {e}")
                continue

        logger.error("[FAIL] 验证码输入失败")
        return False

    def _click_confirm_button(self, page: Page) -> bool:
        """点击确认按钮"""
        confirm_selectors = self.config.confirm_button_selectors

        for selector in confirm_selectors:
            try:
                confirm_button = page.query_selector(selector)
                if confirm_button and confirm_button.is_visible():
                    confirm_button.click()
                    logger.success(f"[OK] 确认按钮点击成功: {selector}")
                    time.sleep(3)  # 等待验证完成
                    return True
            except Exception as e:
                logger.debug(f"确认按钮点击失败 {selector}: {e}")
                continue

        logger.error("[FAIL] 确认按钮点击失败")
        return False

    def _wait_for_manual_input(self, page: Page) -> bool:
        """等待用户手动输入验证码"""
        logger.info("[WAIT] 等待用户手动输入验证码...")

        # 显示用户指引
        self._show_user_guidance()

        # 监控验证码输入
        start_time = time.time()
        timeout = 300  # 5分钟超时

        while time.time() - start_time < timeout:
            try:
                # 检查验证码输入框是否有内容
                verification_code = self._get_current_verification_input(page)
                if verification_code and len(verification_code) >= 6:
                    logger.success(f"[OK] 检测到验证码输入: {verification_code}")

                    # 点击确认按钮
                    if self._click_confirm_button(page):
                        # 验证验证码是否正确（关键修复）
                        return self._verify_verification_code_success(page)

                time.sleep(1)  # 每秒检查一次

            except Exception as e:
                logger.debug(f"监控验证码输入异常: {e}")
                time.sleep(1)
                continue

        logger.error("[FAIL] 用户手动输入验证码超时")
        return False

    def _get_current_verification_input(self, page: Page) -> Optional[str]:
        """获取当前验证码输入框的内容"""
        input_selectors = self.config.verification_input_selectors

        for selector in input_selectors:
            try:
                input_field = page.query_selector(selector)
                if input_field and input_field.is_visible():
                    value = input_field.input_value()
                    if value and len(value) > 0:
                        return value
            except:
                continue

        return None

    def _verify_verification_code_success(self, page: Page) -> bool:
        """
        验证验证码是否验证成功（关键修复）

        修复问题：空验证码被误判为成功
        """
        logger.info("[SEARCH] 验证验证码验证结果...")

        # 等待验证结果
        time.sleep(3)

        # 检查错误提示（关键修复点）
        error_indicators = [
            '此栏为必填',
            '验证码错误',
            '验证码不正确',
            '请输入正确的验证码',
            'verification code is incorrect',
            'invalid verification code',
            'required field',
            'field is required'
        ]

        for indicator in error_indicators:
            try:
                error_element = page.query_selector(f'*:has-text("{indicator}")')
                if error_element and error_element.is_visible():
                    logger.error(f"[FAIL] 验证码验证失败: {indicator}")
                    return False
            except:
                continue

        # 检查验证码弹窗是否还存在（如果存在说明验证失败）
        if self._detect_verification_popup(page):
            logger.error("[FAIL] 验证码弹窗仍然存在，验证失败")
            return False

        # 检查是否跳转到成功页面或出现成功标识
        current_url = page.url
        success_indicators = [
            '卖家中心', 'Seller Center', 'Dashboard', '仪表板',
            '.seller-center', '.dashboard', '#portal',
        ]
        for ind in success_indicators:
            try:
                if ind.startswith('.') or ind.startswith('#'):
                    el = page.query_selector(ind)
                else:
                    el = page.query_selector(f'*:has-text("{ind}")')
                if el and el.is_visible():
                    logger.success("[OK] 验证码验证成功（页面元素确认）")
                    return True
            except Exception:
                continue
        if 'signin' not in current_url and 'login' not in current_url:
            logger.success("[OK] URL已变化，验证码验证成功")
            return True

        logger.warning("[WARN] 验证码验证结果不确定（未检测到成功信号），按失败处理")
        return False

    def _show_user_guidance(self):
        """显示用户操作指引"""
        print("\n" + "="*60)
        print("[LIST] 用户操作指引")
        print("="*60)
        print("\n[TARGET] Shopee验证码处理指引")
        print("\n[PHONE] 操作步骤:")
        print("   1. 检查您的邮箱新邮件")
        print("   2. 查找Shopee发送的验证码邮件")
        print("   3. 复制邮件中的6位数验证码")
        print("   4. 在弹窗中输入验证码")
        print("   5. 点击'确认'按钮完成验证")
        print("\n[TIME] 注意事项:")
        print("   - 验证码通常在1-2分钟内到达")
        print("   - 验证码有效期约10分钟")
        print("   - 如未收到邮件，请检查垃圾邮件文件夹")
        print("\n[RETRY] 系统将自动检测验证码输入并完成后续流程")
        print("\n" + "="*60)

    def _verify_final_login_success(self, page: Page) -> bool:
        """验证最终登录成功状态"""
        logger.info("[SEARCH] 验证最终登录成功状态...")

        # 等待页面加载
        time.sleep(5)

        # 若仍是登录页（URL或元素提示），直接判定失败，防止登录页文案误判
        try:
            url_lc = (page.url or "").lower()
        except Exception:
            url_lc = ""
        if 'signin' in url_lc or 'login' in url_lc:
            logger.warning("[WARN] 仍处于登录URL，判定为未登录")
            return False

        # 仅使用登录后页面特有的容器/结构作为成功信号，避免‘卖家中心’等登录页文案误判
        success_indicators = [
            '#portal',
            '.seller-dashboard',
            '.seller-center-layout',
            '.navigation',
            'header .user-menu',
            'a[href*="/portal/"]',
        ]

        for indicator in success_indicators:
            try:
                element = page.query_selector(indicator)
                if element and element.is_visible():
                    logger.success(f"[OK] 登录成功标识验证通过: {indicator}")
                    return True
            except Exception as e:
                logger.debug(f"登录成功验证失败 {indicator}: {e}")
                continue

        logger.warning("[WARN] 登录成功状态验证不确定")

        # 保存调试截图
        try:
            debug_screenshot = get_debug_screenshot_path("login_final_status")
            page.screenshot(path=debug_screenshot)
            logger.info(f"[CAM] 已保存最终状态截图: {debug_screenshot}")
        except:
            pass

        return False