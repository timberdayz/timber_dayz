# -*- coding: utf-8 -*-
"""
步骤 -> Python 代码生成器（采集录制规范对齐）

将录制步骤（与 /recorder/stop 返回的 steps 结构一致）转换为符合
《采集脚本编写规范》的 Python 组件源码。

以 COLLECTION_SCRIPT_WRITING_GUIDE.md 为准。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def generate_python_code(
    platform: str,
    component_type: str,
    component_name: str,
    steps: List[Dict[str, Any]],
) -> str:
    """
    根据 platform、component_type、component_name 与 steps 生成 Python 源码。

    Args:
        platform: 平台标识，如 miaoshou、shopee
        component_type: 组件类型，如 login、export、navigation
        component_name: 组件名称，用于类名与文件名，如 login、orders_export
        steps: 步骤列表，每项含 action、selector、value、url、optional、comment 等

    Returns:
        符合《采集脚本编写规范》的 Python 源码字符串
    """
    lines: List[str] = []
    captcha_info: Optional[Dict[str, Any]] = None
    cap_platform = (platform or "platform").capitalize()
    cap_name = _to_class_name(component_name or component_type)

    # 文件头
    lines.append('"""')
    lines.append(f"Generated component: {platform}/{component_name}")
    lines.append("Please align with docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md")
    lines.append("Complex interactions, popups, download handling: add explicit wait/comment as needed.")
    lines.append('"""')
    lines.append("")
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("from typing import Any")
    lines.append("")
    lines.append("from modules.components.base import ExecutionContext, ResultBase")
    if component_type == "login":
        lines.append("import asyncio")
        lines.append("import os")
        lines.append("from modules.components.login.base import LoginComponent, LoginResult")
        lines.append("from modules.apps.collection_center.executor_v2 import VerificationRequiredError")
    elif component_type == "export":
        lines.append("from modules.components.export.base import ExportComponent, ExportResult, ExportMode")
    else:
        lines.append("from modules.components.base import ResultBase")
    lines.append("")
    lines.append("")
    # 类定义
    if component_type == "login":
        lines.append(f"class {cap_platform}{cap_name}(LoginComponent):")
        lines.append(f'    """{platform} login component - generated from recorder. Edit as needed."""')
        lines.append("")
        lines.append("    platform = " + repr(platform))
        lines.append("    component_type = \"login\"")
        lines.append("    data_domain = None")
        lines.append("")
        lines.append("    def __init__(self, ctx: ExecutionContext) -> None:")
        lines.append("        super().__init__(ctx)")
        lines.append("")
        lines.append("    async def run(self, page: Any) -> LoginResult:")
        lines.append("        acc = self.ctx.account or {}")
        lines.append("        config = self.ctx.config or {}")
        lines.append("        # 若有弹窗在此 wait 再点击关闭")
        body_indent = "        "
        # 登录组件含验证码步骤时：在 page.goto 之前插入恢复路径（同页继续）
        captcha_info = _find_captcha_and_login_steps(steps)
        if captcha_info:
            lines.extend(_generate_login_captcha_resume_block(body_indent, captcha_info))
            lines.append("")
    elif component_type == "export":
        lines.append(f"class {cap_platform}{cap_name}(ExportComponent):")
        lines.append(f'    """{platform} export component - generated from recorder. Edit as needed."""')
        lines.append("")
        lines.append("    platform = " + repr(platform))
        lines.append("    component_type = \"export\"")
        lines.append("    data_domain = None  # set or read from config")
        lines.append("")
        lines.append("    def __init__(self, ctx: ExecutionContext) -> None:")
        lines.append("        super().__init__(ctx)")
        lines.append("")
        lines.append("    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:")
        lines.append("        config = self.ctx.config or {}")
        lines.append("        acc = self.ctx.account or {}")
        lines.append("        # 若有弹窗在此 wait 再点击关闭")
        body_indent = "        "
    else:
        lines.append(f"class {cap_platform}{cap_name}Component:")
        lines.append(f'    """{platform} {component_type} - generated from recorder. Edit as needed."""')
        lines.append("")
        lines.append("    def __init__(self, ctx: ExecutionContext) -> None:")
        lines.append("        self.ctx = ctx")
        lines.append("")
        lines.append("    async def run(self, page: Any) -> ResultBase:")
        lines.append("        config = self.ctx.config or {}")
        lines.append("        acc = self.ctx.account or {}")
        body_indent = "        "
    if component_type != "login":
        captcha_info = None
    lines.append("")

    for i, step in enumerate(steps):
        action = (step.get("action") or "unknown").strip().lower()
        optional = step.get("optional", False)
        comment = step.get("comment") or ""
        selector = step.get("selector") or ""
        if not selector and step.get("selectors"):
            selector = _selector_from_selectors(step["selectors"])
        value = step.get("value") or ""
        url = step.get("url") or ""
        step_group = (step.get("step_group") or "").strip().lower()
        scene_tags = step.get("scene_tags") or []
        is_popup_step = step_group == "popup" or "popup" in scene_tags
        if is_popup_step and not optional:
            optional = True  # 弹窗/通知栏关闭步骤视为可选，避免遮挡导致失败

        if comment:
            lines.append(body_indent + f"# {comment}")
        if is_popup_step:
            lines.append(body_indent + "# 可预期弹窗/通知栏关闭（场景模板）")
        if optional:
            lines.append(body_indent + "# 可选步骤，执行失败可跳过")
            lines.append(body_indent + "try:")

        step_indent = body_indent + ("    " if optional else "")
        if action in ("navigate", "goto"):
            if url:
                lines.append(step_indent + f"await page.goto({repr(url)}, wait_until=\"domcontentloaded\", timeout=60000)")
            else:
                lines.append(step_indent + "# TODO: set target url from config or account")
        elif action == "click":
            if is_popup_step and not selector.strip():
                # 弹窗步骤且无具体 selector 时，生成通用 wait dialog + 点击确定/关闭
                lines.append(step_indent + 'dialog = page.locator(".ant-modal, .jx-dialog__body, [role=\'dialog\']").first')
                lines.append(step_indent + 'await dialog.wait_for(state="visible", timeout=5000)')
                lines.append(step_indent + 'await dialog.get_by_role("button", name="确定").click(timeout=3000)')
            else:
                # 验证码前 click 步骤且选择器为空时：用稳健的验证码输入框选择器点击聚焦
                is_captcha_click = False
                if not selector.strip() and captcha_info and i + 1 < len(steps):
                    next_step = steps[i + 1]
                    if _is_captcha_step(next_step) and (next_step.get("action") or "").strip().lower() == "fill":
                        is_captcha_click = True
                if is_captcha_click:
                    cap_sel = _build_robust_captcha_selector(captcha_info)
                    lines.append(step_indent + "# 验证码输入框聚焦（录制选择器为空，使用兜底）")
                    lines.append(step_indent + f"_cap_focus = page.locator({repr(cap_sel)})")
                    lines.append(step_indent + "if await _cap_focus.count() > 0:")
                    lines.append(step_indent + "    await _cap_focus.first.click(timeout=5000)")
                else:
                    loc_var = f"_el_{i}"
                    loc_code = _selector_to_locator("page", selector, step_indent, loc_var)
                    if loc_code:
                        lines.extend(loc_code)
                        lines.append(step_indent + f"await expect({loc_var}).to_be_visible()")
                        lines.append(step_indent + f"await {loc_var}.click(timeout=10000)")
                    elif not selector.strip():
                        lines.append(step_indent + "# 选择器为空，已跳过（请录制时补全或人工添加）")
        elif action == "fill":
            is_captcha_step = (
                step_group in ("captcha", "captcha_graphical", "captcha_otp")
                or "graphical_captcha" in (scene_tags or [])
                or "otp" in (scene_tags or [])
            )
            if is_captcha_step and captcha_info:
                # 验证码步骤：不 fill 录制值，改为检测 DOM -> 截图 -> raise VerificationRequiredError
                # 使用与 resume 块一致的稳健选择器（录制+兜底）
                lines.append(step_indent + "# 验证码步骤：检测到验证码则暂停，等待用户回传后同页继续")
                lines.append(step_indent + "await asyncio.sleep(2.5)")
                cap_sel = _build_robust_captcha_selector(captcha_info)
                lines.append(step_indent + f"_cap_inp = page.locator({repr(cap_sel)})")
                lines.append(step_indent + "if await _cap_inp.count() > 0:")
                lines.append(step_indent + "    try:")
                lines.append(step_indent + "        if await _cap_inp.first.is_visible(timeout=3000):")
                lines.append(step_indent + "            import os")
                lines.append(step_indent + "            screenshot_path = None")
                lines.append(step_indent + "            screenshot_dir = config.get(\"task\", {}).get(\"screenshot_dir\")")
                lines.append(step_indent + "            if screenshot_dir:")
                lines.append(step_indent + "                os.makedirs(screenshot_dir, exist_ok=True)")
                lines.append(step_indent + "                screenshot_path = os.path.join(screenshot_dir, \"captcha.png\")")
                lines.append(step_indent + "            else:")
                lines.append(step_indent + "                import tempfile")
                lines.append(step_indent + "                fd, screenshot_path = tempfile.mkstemp(suffix=\".png\", prefix=\"captcha_\")")
                lines.append(step_indent + "                os.close(fd)")
                lines.append(step_indent + "            await page.screenshot(path=screenshot_path, timeout=5000)")
                lines.append(step_indent + "            raise VerificationRequiredError(\"graphical_captcha\", screenshot_path)")
                lines.append(step_indent + "    except VerificationRequiredError:")
                lines.append(step_indent + "        raise")
                lines.append(step_indent + "    except Exception:")
                lines.append(step_indent + "        pass")
            else:
                loc_var = f"_el_{i}"
                loc_code = _selector_to_locator("page", selector, step_indent, loc_var)
                if loc_code:
                    lines.extend(loc_code)
                    lines.append(step_indent + f"await expect({loc_var}).to_be_visible()")
                    if "{{account.username}}" in value or "{{account.password}}" in value:
                        lines.append(step_indent + "# Value from ctx.account - use acc.get(\"username\") / acc.get(\"password\")")
                        fill_val = "acc.get(\"password\", \"\")" if "password" in value.lower() else "acc.get(\"username\", \"\")"
                        lines.append(step_indent + f"await {loc_var}.fill({fill_val}, timeout=10000)")
                    else:
                        lines.append(step_indent + f"await {loc_var}.fill({repr(value)}, timeout=10000)")
        elif action == "wait":
            timeout_ms = step.get("timeout", 1000)
            lines.append(step_indent + f"await page.wait_for_timeout({timeout_ms})")
        else:
            lines.append(step_indent + f"# TODO: action {action!r} - implement per COLLECTION_SCRIPT_WRITING_GUIDE.md")
        if optional:
            lines.append(body_indent + "except Exception:")
            lines.append(body_indent + "    pass")
        lines.append("")
        # 上一步为 navigate/goto 时，下一步前等待页面稳定
        if action in ("navigate", "goto"):
            lines.append(body_indent + 'await page.wait_for_load_state("domcontentloaded", timeout=10000)')
            # 测试模式下的统一弹窗/通知抗干扰钩子
            if component_type in ("login", "export"):
                lines.append(
                    body_indent
                    + f'await self.guard_overlays(page, label="after navigation step {i + 1}")'
                )
            lines.append("")

    # 返回语句
    if component_type == "login":
        lines.append(body_indent + "# TODO: 根据实际成功条件校验 (e.g. URL / element)")
        lines.append(body_indent + "return LoginResult(success=True, message=\"ok\")")
    elif component_type == "export":
        lines.append(body_indent + "# TODO: 等待下载或确认文件路径")
        lines.append(body_indent + "return ExportResult(success=True, message=\"ok\", file_path=None)")
    else:
        lines.append(body_indent + "return ResultBase(success=True, message=\"ok\")")

    # 若使用了 expect，确保有 import
    full_text = "\n".join(lines)
    if "expect(" in full_text and "import expect" not in full_text:
        idx = next((i for i, ln in enumerate(lines) if ln.startswith("from modules.components")), 2)
        lines.insert(idx, "from playwright.async_api import expect")
        lines.insert(idx + 1, "")

    return "\n".join(lines)


def _selector_from_selectors(selectors: List[Dict[str, Any]]) -> str:
    """
    从 Inspector 的 selectors 列表推导出单个 selector 字符串，供 _selector_to_locator 使用。
    优先级: role > text > label > placeholder > css/other。
    """
    if not selectors:
        return ""
    for item in selectors:
        if not isinstance(item, dict):
            continue
        t = (item.get("type") or "").strip().lower()
        v = item.get("value")
        if v is None:
            continue
        v = str(v).strip()
        if not v:
            continue
        if t == "role":
            return v if v.startswith("role=") else f"role={v}"
        if t == "text":
            return v if v.startswith("text=") else f"text={v}"
        if t == "label":
            return v if v.startswith("label=") else f"label={v}"
        if t == "placeholder":
            return v if v.startswith("placeholder=") else f"placeholder={v}"
        return v  # css 或其它
    return ""


def _to_class_name(name: str) -> str:
    """将 component_name 转为类名片段，如 orders_export -> OrdersExport."""
    if not name:
        return "Component"
    parts = name.replace("-", "_").split("_")
    return "".join(p.capitalize() for p in parts if p)


def _selector_to_locator(
    page_var: str,
    selector: str,
    indent: str,
    var_name: str,
) -> Optional[List[str]]:
    """
    将 selector 转为 locator 代码行。
    优先 get_by_role / get_by_text / get_by_label / get_by_placeholder，否则 locator(selector) 并注释。
    """
    if not selector or not selector.strip():
        return None
    sel = selector.strip()
    out: List[str] = []
    # role=button[name=登录]
    m = re.match(r"role=(\w+)\s*\[\s*name\s*=\s*([^\]]+)\]\s*$", sel, re.I)
    if m:
        role, name = m.group(1), m.group(2).strip().strip('"\'')
        out.append(indent + f"{var_name} = {page_var}.get_by_role({repr(role)}, name={repr(name)})")
        return out
    if sel.startswith("text="):
        text = sel[5:].strip().strip('"\'')
        out.append(indent + f"{var_name} = {page_var}.get_by_text({repr(text)})")
        return out
    if sel.startswith("label="):
        label = sel[6:].strip().strip('"\'')
        out.append(indent + f"{var_name} = {page_var}.get_by_label({repr(label)})")
        return out
    if sel.startswith("placeholder="):
        ph = sel[12:].strip().strip('"\'')
        out.append(indent + f"{var_name} = {page_var}.get_by_placeholder({repr(ph)})")
        return out
    out.append(indent + f"# 建议迁移到 get_by_*")
    out.append(indent + f"{var_name} = {page_var}.locator({repr(sel)})")
    return out


def _build_captcha_locator_expr(selector: str) -> str:
    """将 selector 转为 page.locator(...) 表达式字符串。"""
    if not selector or not selector.strip():
        return "page.locator(\"input[placeholder*='验证码'], input[name*='captcha' i], input[name*='code' i]\").first"
    sel = selector.strip()
    return f"page.locator({repr(sel)}).first"


def _build_robust_captcha_selector(captcha_info: Optional[Dict[str, Any]]) -> str:
    """
    构建与 resume 块一致的稳健验证码选择器（录制选择器 + 兜底），供检测块使用。
    当 captcha_info 为 None 时返回纯兜底。
    """
    fallback_cap = "input[placeholder*='验证码'], input[name*='captcha' i], input[name*='code' i]"
    if not captcha_info:
        return fallback_cap
    cap_sel = (captcha_info.get("captcha_selector") or "").strip()
    cap_sel = cap_sel if cap_sel else fallback_cap
    if cap_sel != fallback_cap:
        cap_sel = f"{cap_sel}, {fallback_cap}"
    return cap_sel


def _generate_login_captcha_resume_block(body_indent: str, captcha_info: Dict[str, Any]) -> List[str]:
    """生成登录组件的验证码恢复路径（在 page.goto 之前，同页继续）。"""
    cap_sel = captcha_info.get("captcha_selector") or ""
    fallback_cap = "input[placeholder*='验证码'], input[name*='captcha' i], input[name*='code' i]"
    cap_sel = cap_sel if cap_sel.strip() else fallback_cap
    # 合并录制选择器与兜底，提高匹配率
    if cap_sel != fallback_cap:
        cap_sel = f"{cap_sel}, {fallback_cap}"
    login_sel = captcha_info.get("login_selector") or ""
    fallback_login = "button.login.login-button, button:has-text('立即登录'), button.login"
    login_sel = login_sel if login_sel.strip() else fallback_login
    # 合并录制选择器与兜底，提高匹配率（与验证码逻辑一致）
    if login_sel != fallback_login:
        login_sel = f"{login_sel}, {fallback_login}"
    cap_loc = _build_captcha_locator_expr(cap_sel)
    out = [
        body_indent + "# 恢复路径：若有回传的验证码/OTP，同页继续，不 goto",
        body_indent + "params = config.get(\"params\") or {}",
        body_indent + "captcha_code = params.get(\"captcha_code\") or params.get(\"otp\")",
        body_indent + "if captcha_code:",
        body_indent + "    value = (captcha_code or \"\").strip()",
        body_indent + "    if value:",
        body_indent + "        try:",
        body_indent + f"            _cap_inp = {cap_loc}",
        body_indent + "            await _cap_inp.fill(value, timeout=5000)",
        body_indent + f"            await page.locator({repr(login_sel)}).first.click(timeout=3000)",
        body_indent + "            await asyncio.sleep(2.0)",
        body_indent + "            cur = str(getattr(page, \"url\", \"\"))",
        body_indent + "            if \"/welcome\" in cur or \"/dashboard\" in cur or \"login\" not in cur.lower():",
        body_indent + "                return LoginResult(success=True, message=\"ok\")",
        body_indent + "            # 若验证码提交后仍停留在登录页，则视为失败，避免继续执行主流程再次触发验证码",
        body_indent + "            return LoginResult(success=False, message=\"验证码提交后登录未跳转或仍在登录页\")",
        body_indent + "        except Exception as e:",
        body_indent + "            return LoginResult(success=False, message=f\"验证码填入失败: {e}\")",
        body_indent + "",
    ]
    return out


def _generate_captcha_detection_block(
    body_indent: str, step_indent: str, selector: str, verification_type: str = "graphical_captcha"
) -> List[str]:
    """生成验证码检测与 VerificationRequiredError 抛出逻辑（替代 fill）。"""
    cap_loc = _build_captcha_locator_expr(selector)
    out = [
        step_indent + "# 检测验证码 DOM，若出现则截图并暂停等待用户回传",
        step_indent + "await asyncio.sleep(2.5)",
        step_indent + f"_cap_loc = {cap_loc}",
        step_indent + "if await _cap_loc.count() > 0:",
        step_indent + "    try:",
        step_indent + "        if await _cap_loc.is_visible(timeout=3000):",
        step_indent + "            screenshot_path = None",
        step_indent + "            screenshot_dir = config.get(\"task\", {}).get(\"screenshot_dir\")",
        step_indent + "            if screenshot_dir:",
        step_indent + "                os.makedirs(screenshot_dir, exist_ok=True)",
        step_indent + "                screenshot_path = os.path.join(screenshot_dir, \"captcha.png\")",
        step_indent + "            else:",
        step_indent + "                import tempfile",
        step_indent + "                fd, screenshot_path = tempfile.mkstemp(suffix=\".png\", prefix=\"captcha_\")",
        step_indent + "                os.close(fd)",
        step_indent + "            await page.screenshot(path=screenshot_path, timeout=5000)",
        step_indent + f"            raise VerificationRequiredError({repr(verification_type)}, screenshot_path)",
        step_indent + "    except VerificationRequiredError:",
        step_indent + "        raise",
        step_indent + "    except Exception:",
        step_indent + "        pass",
    ]
    return out


def _is_captcha_step(step: Dict[str, Any]) -> bool:
    """判断步骤是否为验证码步骤（图形验证码或短信/OTP）。"""
    group = (step.get("step_group") or "").strip().lower()
    tags = step.get("scene_tags") or []
    return group in ("captcha", "captcha_graphical", "captcha_otp") or any(
        t in ("captcha", "graphical_captcha", "otp") for t in (tags or [])
    )


def _find_captcha_and_login_steps(steps: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    从步骤列表中识别验证码步骤与登录按钮步骤，供生成「验证码恢复路径」使用。
    返回 {captcha_idx, captcha_selector, login_selector} 或 None。
    """
    captcha_idx = None
    captcha_selector = ""
    login_selector = ""
    for i, step in enumerate(steps):
        action = (step.get("action") or "").strip().lower()
        sel = step.get("selector") or ""
        if not sel and step.get("selectors"):
            sel = _selector_from_selectors(step["selectors"])
        if _is_captcha_step(step) and action == "fill":
            captcha_idx = i
            captcha_selector = sel or "input[placeholder*='验证码'], input[name*='captcha' i], input[name*='code' i]"
        if action == "click" and sel and ("login" in sel.lower() or "登录" in sel):
            login_selector = sel
    if captcha_idx is None:
        return None
    if not login_selector:
        login_selector = "button.login.login-button, button:has-text('立即登录'), button:has-text('登录')"
    return {"captcha_idx": captcha_idx, "captcha_selector": captcha_selector, "login_selector": login_selector}
