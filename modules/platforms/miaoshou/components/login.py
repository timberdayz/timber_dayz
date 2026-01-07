from __future__ import annotations

from typing import Any

from modules.components.base import ExecutionContext
from modules.components.login.base import LoginComponent, LoginResult


class MiaoshouLogin(LoginComponent):
    """Miaoshou ERP login component.

    Uses account['username'] and account['password'] to perform login on
    https://erp.91miaoshou.com.
    """
    
    # Component metadata (v4.8.0)
    platform = "miaoshou"
    component_type = "login"
    data_domain = None
    
    # Success criteria for validation (v4.8.0)
    success_criteria = [
        {
            'type': 'url_contains',
            'value': '/welcome',
            'optional': False,
            'comment': 'After login, should redirect to welcome page'
        },
        {
            'type': 'element_not_exists',
            'selector': 'button.login.login-button',
            'timeout': 5000,
            'optional': True,
            'comment': 'Login button should not exist after successful login'
        }
    ]

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    async def run(self, page: Any) -> LoginResult:  # type: ignore[override]
        """执行妙手ERP登录（带详细步骤提示与诊断）。"""
        acc = self.ctx.account or {}
        login_url = acc.get("login_url", "https://erp.91miaoshou.com/?redirect=%2Fwelcome")
        username = acc.get("username") or acc.get("phone") or acc.get("email")
        password = acc.get("password")

        def _log(msg: str) -> None:
            print(msg)
            if self.logger:
                try:
                    self.logger.info(msg)
                except Exception:
                    pass


        _log(f"[MiaoshouLogin] 步骤1: 打开登录页 -> {login_url}")
        try:
            await page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            try:
                await page.goto(login_url, wait_until="load", timeout=60000)
            except Exception:
                return LoginResult(success=False, message="无法打开登录页")

        # 若打开后立即处于已登录状态（例如已有会话），直接返回成功
        try:
            cur = str(getattr(page, "url", ""))
            login_btn_missing = (
                await page.locator("button.login.login-button").count() == 0
                and await page.locator("text=立即登录").count() == 0
            )
            if ("/welcome" in cur and "redirect=" not in cur) or login_btn_missing:
                _log("[MiaoshouLogin] 已处于登录状态，跳过登录步骤")
                return LoginResult(success=True, message="already logged in")
        except Exception:
            pass

        # 步骤2：填写用户名
        try:
            _log("[MiaoshouLogin] 步骤2: 填写用户名...")
            try:
                await page.get_by_role("textbox", name="手机号/子账号/邮箱").fill(str(username or ""), timeout=10000)
            except Exception:
                await page.locator("input[type='text'], input[type='tel'], input[placeholder*='手机号']").first.fill(str(username or ""), timeout=10000)
            _log("[OK] 用户名已填写")
        except Exception as e:
            _log(f"[FAIL] 无法填写用户名: {e}")
            return LoginResult(success=False, message="fill username failed")

        # 步骤3：填写密码
        try:
            _log("[MiaoshouLogin] 步骤3: 填写密码...")
            try:
                await page.get_by_role("textbox", name="密码").fill(str(password or ""), timeout=10000)
            except Exception:
                await page.locator("input[type='password'], input[placeholder*='密码']").first.fill(str(password or ""), timeout=10000)
            _log("[OK] 密码已填写")
        except Exception as e:
            _log(f"[FAIL] 无法填写密码: {e}")
            return LoginResult(success=False, message="fill password failed")

        # 步骤4：确保"记住账号"为勾选状态（尽力而为）
        try:
            _log("[MiaoshouLogin] 步骤4: 确保'记住账号'为勾选状态...")
            # 优先：直接定位 checkbox 元素
            cb = None
            for s in [
                ".remember-check-box input[type='checkbox']",
                "input[type='checkbox'][name*='remember' i]",
                "input[type='checkbox'][id*='remember' i]",
            ]:
                loc = page.locator(s)
                if await loc.count() > 0:
                    cb = loc.first
                    break
            if cb:
                try:
                    checked = await cb.is_checked()
                except Exception:
                    checked = None
                if checked:
                    _log("[OK] 已是勾选状态（checkbox）")
                else:
                    try:
                        await cb.check(timeout=1500)
                    except Exception:
                        await cb.click(timeout=1500)
                    try:
                        _log("[OK] 已勾选记住账号" if await cb.is_checked() else "[WARN] 勾选可能未生效")
                    except Exception:
                        pass
            else:
                # 退化：根据容器 class/aria 判断
                cont = page.locator(".remember-check-box")
                if await cont.count() > 0:
                    c = cont.first
                    try:
                        cls = (await c.get_attribute("class") or "").lower()
                        aria = (await c.get_attribute("aria-checked") or "").lower()
                    except Exception:
                        cls, aria = "", ""
                    if ("checked" in cls) or (aria in ("true", "1")):
                        _log("[OK] 已是勾选状态（容器）")
                    else:
                        await c.click(timeout=1500)
                        _log("[OK] 已点击记住账号")
                else:
                    _log("[WARN] 未找到记住账号复选框（忽略）")
        except Exception:
            _log("[WARN] 处理记住账号状态时出现异常（忽略）")

        # 步骤5：定位并点击"立即登录"按钮
        submitted = False
        _log("[MiaoshouLogin] 步骤5: 定位并点击'立即登录'按钮...")
        candidates = [
            "button.login.login-button",
            ".login.login-button",
            "button:has-text(立即登录)",
            "[role='button']:has-text(立即登录)",
            "button:has-text(Login)",
        ]
        try:
            for sel in candidates:
                try:
                    loc = page.locator(sel)
                    cnt = await loc.count()
                    if cnt <= 0:
                        continue
                    _log(f"  [SEARCH] 候选: {sel} x{cnt}")
                    btn = loc.first
                    try:
                        await btn.scroll_into_view_if_needed(timeout=1500)
                    except Exception:
                        pass
                    # 输出可用性诊断
                    try:
                        dis = await btn.get_attribute("disabled")
                        aria = (await btn.get_attribute("aria-disabled") or "").lower()
                        cls = (await btn.get_attribute("class") or "").lower()
                        _log(f"  -> 状态: disabled={dis is not None}, aria={aria}, class={cls}")
                    except Exception:
                        pass
                    try:
                        await btn.click(timeout=2500)
                        submitted = True
                        _log("[OK] 已点击登录按钮")
                        break
                    except Exception as c1:
                        _log(f"[WARN] 点击失败，尝试强制点击: {c1}")
                        try:
                            await btn.click(timeout=2000, force=True)
                            submitted = True
                            _log("[OK] 已强制点击登录按钮")
                            break
                        except Exception as _:
                            continue
                except Exception:
                    continue
            if not submitted:
                # 额外回退：使用role定位或键盘回车
                try:
                    await page.get_by_role("button", name="立即登录").click(timeout=2000)
                    submitted = True
                    _log("[OK] 已通过role定位点击登录按钮")
                except Exception:
                    pass
            if not submitted:
                try:
                    await page.keyboard.press("Enter")
                    submitted = True
                    _log("[OK] 已通过键盘回车尝试提交")
                except Exception:
                    _log("[FAIL] 未能触发登录提交")
        except Exception as e:
            _log(f"[FAIL] 点击登录按钮过程异常: {e}")

        # 步骤6：等待登录结果
        _log("[MiaoshouLogin] 步骤6: 等待登录结果...")
        async def _is_logged_in() -> bool:
            try:
                url = str(getattr(page, "url", ""))
                # 登录成功通常跳转到 /welcome（且不再带 redirect 参数）
                if ("/welcome" in url) and ("redirect=" not in url):
                    return True
                # 若已在站内其他业务页（非登录页重定向），且页面无登录表单，也视为成功
                in_site = "erp.91miaoshou.com" in url
                redirected = "redirect=" in url
                no_login_form = (
                    await page.locator("button.login.login-button").count() == 0
                    and await page.locator("text=立即登录").count() == 0
                )
                if in_site and (not redirected) and no_login_form:
                    return True
            except Exception:
                return False
            return False

        try:
            import asyncio
            import time as _t
            deadline = _t.time() + 15.0
            while _t.time() < deadline:
                if await _is_logged_in():
                    break
                await asyncio.sleep(0.5)
        except Exception:
            pass

        ok = await _is_logged_in()
        _log("[OK] 登录成功" if ok else "[FAIL] 登录仍停留在登录页")
        return LoginResult(success=ok, message="ok" if ok else "stay on login")
