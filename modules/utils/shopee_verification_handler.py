#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Shopee 智能验证码处理器（精简修复版）

- 解决原文件中因意外二进制/空字节导致的无法导入问题
- 保留与现有调用处的最小兼容接口
- 不做导入期副作用；仅在方法调用时操作页面

公开接口（保持向后兼容）：
- class ShopeeVerificationHandler(page, account_config)
  - handle_shopee_verification() -> bool
  - handle_shopee_login_verification() -> bool  # 别名
  - get_performance_stats() -> dict
  - get_status() -> dict

注意：本版本专注稳定导入与基本 OTP 流程；高级邮箱自动获取/IMAP 等能力暂未恢复。
后续如需补充，请在不破坏现有接口的前提下按小步迭代补齐。
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

try:
    # 兼容项目内 logger，如果不可用则回退到 print
    from modules.utils.logger import logger  # type: ignore
except Exception:  # pragma: no cover - 日志兜底
    class _PrintLogger:
        def info(self, msg: str) -> None: print(msg)
        def warning(self, msg: str) -> None: print(msg)
        def error(self, msg: str) -> None: print(msg)
        def debug(self, msg: str) -> None: print(msg)
        def success(self, msg: str) -> None: print(msg)
    logger = _PrintLogger()  # type: ignore


class ShopeeVerificationHandler:
    """Shopee 验证码处理器（最小稳定实现）。

    仅处理：
    - 检测是否存在 OTP/验证弹窗
    - 尝试触发“发送至邮箱”之类按钮
    - 引导用户输入验证码，并自动点击“确认”
    - 判断是否已通过验证/进入已登录页面
    """

    def __init__(self, page: Any, account_config: Dict[str, Any]) -> None:
        self.page = page
        self.account_config = account_config or {}
        self._start_time = time.time()
        self._last_error: Optional[str] = None
        self._last_state: str = "initialized"
        # Flags: disable email-based flows by default (project policy)
        flags = (self.account_config.get("login_flags") or {}) if isinstance(self.account_config, dict) else {}
        self.disable_email: bool = bool(flags.get("shopee_disable_email", True))

    # -------- 对外接口 --------
    def handle_shopee_verification(self) -> bool:
        """入口：处理 Shopee 登录验证码流程。

        返回 True 表示已通过（或无需）验证，False 表示失败/超时。
        """
        try:
            self._last_state = "detecting"
            logger.info("[LOCK] 检测 Shopee 验证码/OTP 界面...")

            if not self._maybe_on_verification_page():
                logger.info("[OK] 未检测到验证码输入需求，视为通过")
                self._last_state = "no_verification"
                return True

            logger.info("🪄 检测到验证码流程，开始处理...")
            self._last_state = "processing"

            # 优先尝试点击“发送至邮箱/发送验证码”等按钮
            self._try_click_send_code_buttons()

            # 引导用户，并等待输入 + 提交
            self._show_user_guidance()
            ok = self._monitor_verification_input_and_submit()

            # 最终校验
            if ok and self._verify_login_success():
                logger.success("[DONE] 验证码验证通过，登录成功！")
                self._last_state = "login_success"
                return True

            # 若已离开登录页也视作成功（部分站点无明确提示）
            if self._left_login_page():
                logger.success("[DONE] 页面已离开登录页，视作登录成功")
                self._last_state = "login_success"
                return True

            logger.warning("[WARN] 验证码处理可能失败或超时")
            self._last_state = "verification_failed"
            return False
        except Exception as e:  # noqa: BLE001
            self._last_error = str(e)
            self._last_state = "exception"
            logger.error(f"[FAIL] Shopee 验证码处理异常: {e}")
            return False

    # 别名（兼容调用）
    def handle_shopee_login_verification(self) -> bool:
        return self.handle_shopee_verification()

    def get_performance_stats(self) -> Dict[str, Any]:
        duration = max(0.0, time.time() - self._start_time)
        return {"total_time": duration, "current_state": self._last_state}

    def get_status(self) -> Dict[str, Any]:
        return {"current_state": self._last_state, "error_message": self._last_error}

    # -------- 内部实现 --------
    def _maybe_on_verification_page(self) -> bool:
        selectors = [
            "input[name*='otp']",
            "input[placeholder*='验证码']",
            "input[aria-label*='验证码']",
            "input[name*='code']",
            "#verification_code",
            "text=发送验证码",
            "text=发送至邮箱",
            "button:has-text('发送')",
            "text=验证",
            "text=确认",
            "text=验证并登录",
        ]
        try:
            for sel in selectors:
                try:
                    loc = self.page.locator(sel)
                    if loc.count() > 0 and loc.first.is_visible():
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def _try_click_send_code_buttons(self) -> None:
        # Respect project policy: do not use email flows when disabled
        if getattr(self, "disable_email", True):
            logger.info("[EMAIL] 已禁用邮箱验证码流程，跳过 '发送至邮箱/发送验证码' 按钮点击")
            return
        btn_selectors = [
            "button:has-text('发送至邮箱')",
            "button:has-text('发送验证码')",
            "text=发送至邮箱",
            "text=发送验证码",
            "text=获取验证码",
        ]
        for sel in btn_selectors:
            try:
                loc = self.page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible() and loc.first.is_enabled():
                    logger.info(f"[EMAIL] 尝试点击按钮: {sel}")
                    loc.first.click()
                    self.page.wait_for_timeout(800)
                    break
            except Exception:
                continue

    def _show_user_guidance(self) -> None:
        # When email flow is disabled, keep guidance minimal and avoid encouraging email usage
        if getattr(self, "disable_email", True):
            try:
                logger.info("[LIST] 已禁用邮箱验证码指引；请在弹窗内直接输入短信验证码并点击‘确认’。")
            except Exception:
                pass
            return
        email_address = (
            self.account_config.get("email", "")
            or self.account_config.get("E-mail", "")
            or self.account_config.get("Email account", "")
            or "您的邮箱"
        )
        guidance = (
            "=" * 60
            + "\n[LIST] 用户操作指引\n"
            + "=" * 60
            + "\n\n[TARGET] Shopee 验证码处理指引\n\n"
            + f"[EMAIL] 邮箱信息:\n   邮箱地址: {email_address}\n\n"
            + "[PHONE] 操作步骤:\n"
            + f"   1. 检查邮箱 {email_address} 的新邮件\n"
            + "   2. 查找 Shopee 发送的验证码邮件\n"
            + "   3. 复制邮件中的 6 位数验证码\n"
            + "   4. 在页面输入验证码\n"
            + "   5. 点击“确认/验证”按钮完成验证\n\n"
            + "[TIME] 注意事项:\n"
            + "   - 验证码通常在 1-2 分钟内到达\n"
            + "   - 验证码有效期约 10 分钟\n"
            + "   - 如未收到邮件，请检查垃圾邮件文件夹\n\n"
            + "[RETRY] 系统将自动检测验证码输入并完成后续流程\n"
            + "=" * 60
        )
        try:
            print(guidance)
            logger.info("[LIST] 已显示用户操作指引")
        except Exception as e:  # noqa: BLE001
            logger.error(f"显示用户指引失败: {e}")

    def _monitor_verification_input_and_submit(self, wait_seconds: int = 120) -> bool:
        """
        等待用户输入验证码并提交；仅在检测到输入后短促点击一次确认；若识别到错误提示则不再点击，等待用户更正。
        """
        deadline = time.time() + max(5, wait_seconds)
        last_submit = 0.0
        while time.time() < deadline:
            try:
                # 检测是否已离开登录页
                if self._left_login_page():
                    return True

                # 检测是否出现“验证码错误”提示；如有则暂停点击，等待用户修正
                try:
                    error_loc = None
                    for sel in [
                        "text=验证码填写错误",
                        "text=请输入正确的验证码",
                        "text=验证码错误",
                        "text=验证码不正确",
                        ".toast:has-text('验证码')",
                        ".ant-message:has-text('验证码')",
                    ]:
                        loc = self.page.locator(sel)
                        if loc.count() > 0 and loc.first.is_visible():
                            error_loc = loc.first
                            break
                    if error_loc is not None:
                        # 明确不点击，等待用户重新输入
                        time.sleep(1.0)
                        continue
                except Exception:
                    pass

                # 判断输入框是否已有验证码内容
                has_code = False
                for inp_sel in [
                    "input[name*='otp']",
                    "input[placeholder*='验证码']",
                    "input[aria-label*='验证码']",
                    "input[name*='code']",
                    "#verification_code",
                ]:
                    try:
                        loc = self.page.locator(inp_sel)
                        if loc.count() > 0 and loc.first.is_visible():
                            value = loc.first.input_value() or ""
                            if len(value.strip()) >= 4:
                                has_code = True
                                break
                    except Exception:
                        continue

                # 仅当检测到输入后，且距离上次点击超过 2s 时，尝试点击确认一次
                if has_code and (time.time() - last_submit) > 2.0:
                    for btn_sel in [
                        "div[role='dialog'] button:has-text('确认')",
                        "div[aria-modal='true'] button:has-text('确认')",
                        "button:has-text('确认')",
                        "button:has-text('验证')",
                    ]:
                        try:
                            loc = self.page.locator(btn_sel)
                            if loc.count() > 0 and loc.first.is_visible() and loc.first.is_enabled():
                                loc.first.click()
                                last_submit = time.time()
                                break
                        except Exception:
                            continue

                # 小等待，避免高频操作
                try:
                    self.page.wait_for_timeout(300)
                except Exception:
                    time.sleep(0.3)
            except Exception:
                pass
        return False

    def _left_login_page(self) -> bool:
        try:
            url = str(getattr(self.page, "url", "") or "")
            return ("signin" not in url and "login" not in url) and ("shopee" in url)
        except Exception:
            return False

    def _verify_login_success(self) -> bool:
        """
        轻量校验：页面是否可见卖家端关键元素/是否已跳转离开登录页。
        """
        try:
            if self._left_login_page():
                return True
            # 也可加一些元素判断（按需扩展）
            dashboard_markers = [
                "#dashboard",
                "text=店铺",
                "text=首页",
                "text=订单",
            ]
            for sel in dashboard_markers:
                try:
                    loc = self.page.locator(sel)
                    if loc.count() > 0 and loc.first.is_visible():
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

