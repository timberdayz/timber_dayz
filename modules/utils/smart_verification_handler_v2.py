#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
智能验证码处理器 V2.0 - 专家级重构版本
采用状态机模式和分层选择器策略，提供更稳定和可靠的验证码处理
"""

import time
import re
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class VerificationState(Enum):
    """验证码处理状态枚举"""
    DETECTING = "detecting"           # 检测验证码弹窗
    EMAIL_STAGE = "email_stage"       # 邮箱验证阶段
    PHONE_STAGE = "phone_stage"       # 电话验证阶段
    OTP_INPUT = "otp_input"          # OTP输入阶段
    CONFIRMING = "confirming"         # 确认提交阶段
    SUCCESS = "success"               # 处理成功
    FAILED = "failed"                 # 处理失败
    USER_INTERVENTION = "user_required" # 需要用户介入


@dataclass
class SelectorGroup:
    """选择器组配置"""
    name: str
    selectors: List[str]
    priority: int = 1
    timeout: int = 5000
    description: str = ""


@dataclass
class VerificationContext:
    """验证码处理上下文"""
    current_state: VerificationState
    popup_element: Optional[Any] = None
    stage_data: Dict[str, Any] = None
    attempt_count: int = 0
    last_error: str = ""
    user_guidance: str = ""


class SmartVerificationHandlerV2:
    """
    智能验证码处理器 V2.0

    核心特性:
    - 状态机模式管理复杂流程
    - 分层选择器策略提高成功率
    - 人机协作优化用户体验
    - 学习优化机制持续改进
    """

    def __init__(self, page, account_config: Dict[str, Any]):
        self.page = page
        self.account_config = account_config
        self.context = VerificationContext(VerificationState.DETECTING)
        self.selector_success_stats = {}  # 选择器成功率统计
        self._init_selector_groups()

    def _init_selector_groups(self):
        """初始化分层选择器组"""
        # 弹窗检测选择器组 - 按优先级分层
        self.popup_detectors = [
            SelectorGroup(
                name="primary_detectors",
                priority=1,
                timeout=3000,
                selectors=[
                    '.phone-verify-container',  # 基于实际DOM结构
                    '.eds-modal:has-text("验证电话号码")',
                    '.eds-modal:has-text("OTP")',
                ],
                description="主要检测器 - 基于实际DOM结构"
            ),
            SelectorGroup(
                name="secondary_detectors",
                priority=2,
                timeout=5000,
                selectors=[
                    'div:has-text("验证电话号码")',
                    'div:has-text("邮箱验证")',
                    'div:has(button:has-text("发送至邮箱"))',
                ],
                description="备用检测器 - 基于文本内容"
            ),
            SelectorGroup(
                name="fallback_detectors",
                priority=3,
                timeout=2000,
                selectors=[
                    '.eds-modal',
                    'div[role="dialog"]',
                    '.modal',
                ],
                description="兜底检测器 - 通用模态框"
            )
        ]

        # 按钮操作选择器组
        self.button_selectors = {
            'send_to_email': SelectorGroup(
                name="send_email_buttons",
                selectors=[
                    '.phone-verify-container button:has-text("发送至邮箱")',
                    '.pov-modal__footer button:has-text("发送至邮箱")',
                    '.eds-button--link:has-text("发送至邮箱")',
                    'button:has-text("发送至邮箱")',
                ],
                description="发送至邮箱按钮"
            ),
            'confirm': SelectorGroup(
                name="confirm_buttons",
                selectors=[
                    '.phone-verify-container button:has-text("确认")',
                    '.pov-modal__footer button:has-text("确认")',
                    '.eds-button--primary:has-text("确认")',
                    'button:has-text("确认")',
                ],
                description="确认按钮"
            ),
            'input_field': SelectorGroup(
                name="input_fields",
                selectors=[
                    '.phone-verify-container input[placeholder="请输入"]',
                    '.eds-input__input[placeholder="请输入"]',
                    '.eds-modal input[placeholder="请输入"]',
                    'input[placeholder="请输入"]',
                ],
                description="验证码输入框"
            )
        }

    def handle_verification(self) -> bool:
        """主入口方法 - 处理验证码流程"""
        logger.info("🚀 开始智能验证码处理流程 V2.0")

        try:
            # 状态机主循环
            while self.context.current_state not in [VerificationState.SUCCESS,
                                                    VerificationState.FAILED,
                                                    VerificationState.USER_INTERVENTION]:

                success = self._execute_current_state()
                if not success:
                    self._handle_state_failure()
                    break

                # 防止无限循环
                self.context.attempt_count += 1
                if self.context.attempt_count > 20:
                    logger.error("❌ 状态机执行次数超限，终止处理")
                    self.context.current_state = VerificationState.FAILED
                    break

            return self.context.current_state == VerificationState.SUCCESS

        except Exception as e:
            logger.error(f"❌ 验证码处理过程异常: {e}")
            return False

    def _execute_current_state(self) -> bool:
        """执行当前状态对应的操作"""
        state_handlers = {
            VerificationState.DETECTING: self._handle_detecting_state,
            VerificationState.EMAIL_STAGE: self._handle_email_stage,
            VerificationState.PHONE_STAGE: self._handle_phone_stage,
            VerificationState.OTP_INPUT: self._handle_otp_input_state,
            VerificationState.CONFIRMING: self._handle_confirming_state,
        }

        handler = state_handlers.get(self.context.current_state)
        if handler:
            logger.info(f"🔄 执行状态: {self.context.current_state.value}")
            return handler()
        else:
            logger.error(f"❌ 未知状态: {self.context.current_state}")
            return False

    def _handle_detecting_state(self) -> bool:
        """处理弹窗检测状态"""
        logger.info("🔍 开始检测验证码弹窗...")

        # 使用分层选择器检测弹窗
        for selector_group in self.popup_detectors:
            element = self._try_selector_group(selector_group)
            if element:
                self.context.popup_element = element
                logger.info(f"✅ 弹窗检测成功，使用: {selector_group.name}")

                # 分析弹窗类型并转换状态
                next_state = self._analyze_popup_type(element)
                self.context.current_state = next_state
                return True

        logger.warning("❌ 未检测到验证码弹窗")
        self.context.current_state = VerificationState.FAILED
        return False

    def _handle_email_stage(self) -> bool:
        """处理邮箱验证阶段"""
        logger.info("📧 处理邮箱验证阶段...")

        # 点击发送至邮箱按钮
        if self._click_button('send_to_email'):
            logger.info("✅ 成功点击'发送至邮箱'按钮")

            # 等待状态变化
            if self._wait_for_state_transition():
                self.context.current_state = VerificationState.OTP_INPUT
                return True
            else:
                logger.warning("⚠️ 等待状态变化超时")
                self.context.current_state = VerificationState.USER_INTERVENTION
                self.context.user_guidance = "请手动点击'发送至邮箱'按钮，然后等待页面变化"
                return False
        else:
            logger.error("❌ 无法点击'发送至邮箱'按钮")
            self.context.current_state = VerificationState.USER_INTERVENTION
            self.context.user_guidance = "请手动点击'发送至邮箱'按钮"
            return False

    def _handle_otp_input_state(self) -> bool:
        """处理OTP输入状态"""
        logger.info("🔢 进入OTP输入等待阶段...")

        # 设计理念改变：不自动处理邮箱，而是智能引导用户
        self.context.user_guidance = self._generate_user_guidance()

        # 监控验证码输入
        if self._monitor_code_input():
            self.context.current_state = VerificationState.CONFIRMING
            return True
        else:
            self.context.current_state = VerificationState.USER_INTERVENTION
            return False

    def _handle_confirming_state(self) -> bool:
        """处理确认提交状态"""
        logger.info("✅ 处理确认提交...")

        if self._click_button('confirm'):
            logger.info("✅ 成功点击确认按钮")

            # 等待页面响应
            if self._wait_for_login_success():
                self.context.current_state = VerificationState.SUCCESS
                return True
            else:
                logger.warning("⚠️ 登录可能失败，请检查")
                self.context.current_state = VerificationState.FAILED
                return False
        else:
            logger.error("❌ 无法点击确认按钮")
            self.context.current_state = VerificationState.USER_INTERVENTION
            self.context.user_guidance = "请手动点击确认按钮"
            return False

    def _handle_phone_stage(self) -> bool:
        """处理手机验证阶段（最小实现）：直接进入 OTP 输入阶段。"""
        try:
            logger.info("📱 处理手机验证阶段(最小) -> 进入OTP输入阶段")
        except Exception:
            pass
        self.context.current_state = VerificationState.OTP_INPUT
        return True

    def _try_selector_group(self, selector_group: SelectorGroup) -> Optional[Any]:
        """尝试选择器组，返回找到的元素"""
        for selector in selector_group.selectors:
            try:
                element = self.page.wait_for_selector(
                    selector,
                    timeout=selector_group.timeout,
                    state='visible'
                )
                if element and element.is_visible():
                    # 记录成功统计
                    self._record_selector_success(selector)
                    logger.info(f"✅ 选择器成功: {selector}")
                    return element
            except Exception as e:
                logger.debug(f"⚠️ 选择器失败: {selector} - {e}")
                continue
        return None

    def _click_button(self, button_type: str) -> bool:
        """智能按钮点击"""
        selector_group = self.button_selectors.get(button_type)
        if not selector_group:
            return False

        element = self._try_selector_group(selector_group)
        if element:
            try:
                # 智能点击策略
                element.scroll_into_view_if_needed()
                element.wait_for_element_state('visible')
                element.click()
                return True
            except Exception as e:
                logger.error(f"❌ 点击失败: {e}")
                return False
        return False

    def _analyze_popup_type(self, element) -> VerificationState:
        """分析弹窗类型，决定下一状态（适配“验证电话号码”短信页）
        判定原则：
        - 若出现“验证电话号码/手机号/短信/OTP/请输入”等关键词 → 视为手机验证码页（OTP_INPUT）
        - 若出现“发送至邮箱” → 表示当前是手机验证页，可切换到邮箱；仍判定为 OTP_INPUT
        - 若出现“发送至电话/确认发送至电话” → 表示当前是邮箱验证页，可切换到手机；判定为 EMAIL_STAGE
        - 若能定位到验证码输入框 → OTP_INPUT；否则 EMAIL_STAGE
        """
        try:
            text_content_raw = (element.inner_text() or '')
            text_content = text_content_raw.lower()
            phone_keywords = ['验证电话号码', '验证手机号', '验证手机号码', '短信', 'phone', 'otp', '请输入']
            has_phone_hint = any(k.lower() in text_content for k in phone_keywords)
            has_send_to_email = ('发送至邮箱' in text_content_raw) or ('发送到邮箱' in text_content_raw)
            has_send_to_phone = ('发送至电话' in text_content_raw) or ('确认发送至电话' in text_content_raw)

            if has_phone_hint or has_send_to_email:
                return VerificationState.OTP_INPUT
            if has_send_to_phone:
                return VerificationState.EMAIL_STAGE

            # 兜底：如果能找到验证码输入框，也视为OTP阶段
            input_hint = self._try_selector_group(self.button_selectors['input_field'])
            if input_hint:
                return VerificationState.OTP_INPUT
            return VerificationState.EMAIL_STAGE
        except Exception as e:
            logger.error(f"❌ 弹窗类型分析失败: {e}")
            return VerificationState.EMAIL_STAGE

    def _generate_user_guidance(self) -> str:
        """生成用户操作指引"""
        email_config = self.account_config.get('email_config', {})
        if email_config:
            email_addr = email_config.get('username', '您的邮箱')
            return f"""
📧 请按以下步骤手动获取验证码：

1. 打开您的邮箱: {email_addr}
2. 查找来自Shopee的验证码邮件
3. 复制6位数验证码
4. 返回此页面，在验证码输入框中填入验证码
5. 系统将自动检测并点击确认按钮

💡 提示：验证码邮件通常在1-2分钟内到达
            """
        else:
            return """
📧 请手动获取验证码：

1. 检查您的邮箱中的Shopee验证码邮件
2. 复制验证码并填入验证码输入框
3. 系统将自动点击确认按钮
            """

    def _monitor_code_input(self, timeout: int = 300) -> bool:
        """监控验证码输入 - 等待用户输入验证码"""
        logger.info(f"👁️ 监控验证码输入，超时: {timeout}秒")

        start_time = time.time()
        while time.time() - start_time < timeout:
            # 检查输入框是否有内容
            input_element = self._try_selector_group(self.button_selectors['input_field'])
            if input_element:
                try:
                    value = input_element.input_value()
                    if value and len(value.strip()) >= 4:  # 至少4位数字
                        logger.info(f"✅ 检测到验证码输入: {len(value)}位")
                        return True
                except:
                    pass

            # 每秒检查一次
            time.sleep(1)

        logger.warning("⏰ 验证码输入监控超时")
        return False

    def _wait_for_state_transition(self) -> bool:
        """等待页面状态变化"""
        logger.info("⏳ 等待页面状态变化...")

        # 等待按钮变化或新元素出现
        transition_indicators = [
            'button:has-text("发送至电话")',
            'input[placeholder="请输入"]',
            '.verification-code-sent',
        ]

        for indicator in transition_indicators:
            try:
                self.page.wait_for_selector(indicator, timeout=10000, state='visible')
                logger.info(f"✅ 检测到状态变化: {indicator}")
                return True
            except:
                continue

        logger.warning("❌ 未检测到状态变化")
        return False

    def _wait_for_login_success(self) -> bool:
        """
        严格等待登录成功：
        - 成功：URL离开 signin/login，或出现卖家中心/仪表板等强信号元素；
        - 失败：出现“验证码错误/不正确/已过期/请重试”等提示，或长时间仍停留在验证码弹窗。
        """
        logger.info("⏳ 等待登录完成（严格模式）...")
        try:
            start = time.time()
            timeout = 20
            error_keywords = [
                '验证码错误', '不正确', '已过期', '请重试', 'invalid', 'incorrect', 'expired',
            ]
            success_indicators = [
                'div:has-text("卖家中心")', 'div:has-text("Seller Center")',
                'div:has-text("Dashboard")', 'div:has-text("仪表板")',
                '.seller-center', '.dashboard', '#portal',
            ]
            while time.time() - start < timeout:
                # 失败快速检测
                try:
                    page_text = (self.page.content() or '')
                    if any(k in page_text for k in error_keywords):
                        logger.error("❌ 检测到验证码错误提示，登录失败")
                        return False
                except Exception:
                    pass

                # 成功强信号：元素或URL
                try:
                    for ind in success_indicators:
                        try:
                            if self.page.locator(ind).count() > 0:
                                logger.success("✅ 登录成功元素检测通过")
                                return True
                        except Exception:
                            continue
                    url = self.page.url
                    if 'signin' not in url and 'login' not in url:
                        logger.success("✅ URL验证通过，登录成功")
                        return True
                except Exception:
                    pass

                # 若验证码弹窗仍可见则继续等待
                try:
                    modal = self.page.locator('.phone-verify-container, .eds-modal').first
                    if modal and modal.count() > 0 and modal.is_visible():
                        time.sleep(1)
                        continue
                except Exception:
                    pass

                time.sleep(1)

            logger.warning("⚠️ 登录状态不明确或可能失败")
            return False
        except Exception as e:
            logger.error(f"❌ 等待登录成功异常: {e}")
            return False

    def _handle_state_failure(self):
        """处理状态执行失败"""
        self.context.last_error = f"状态 {self.context.current_state.value} 执行失败"
        self.context.current_state = VerificationState.USER_INTERVENTION

    def _record_selector_success(self, selector: str):
        """记录选择器成功率统计"""
        if selector not in self.selector_success_stats:
            self.selector_success_stats[selector] = {'success': 0, 'total': 0}

        self.selector_success_stats[selector]['success'] += 1
        self.selector_success_stats[selector]['total'] += 1

    def get_current_status(self) -> Dict[str, Any]:
        """获取当前处理状态"""
        return {
            'state': self.context.current_state.value,
            'attempt_count': self.context.attempt_count,
            'last_error': self.context.last_error,
            'user_guidance': self.context.user_guidance,
            'popup_detected': self.context.popup_element is not None
        }

    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计信息"""
        return {
            'selector_stats': self.selector_success_stats,
            'total_attempts': self.context.attempt_count,
            'current_state': self.context.current_state.value
        }