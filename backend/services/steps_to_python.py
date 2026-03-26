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

# 平台默认登录页 URL（_target_url 第四级 fallback，避免空 URL 或 redirect 超时）
PLATFORM_DEFAULT_LOGIN_URLS: Dict[str, str] = {
    "miaoshou": "https://erp.91miaoshou.com",
    "shopee": "https://seller.shopee.cn",
    "tiktok": "https://seller-us.tiktok.com",
}


def generate_python_code(
    platform: str,
    component_type: str,
    component_name: str,
    steps: List[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]] = None,
    success_criteria: Optional[Dict[str, Any]] = None,
) -> str:
    """
    根据 platform、component_type、component_name 与 steps 生成 Python 源码。

    Args:
        platform: 平台标识，如 miaoshou、shopee
        component_type: 组件类型，如 login、export、navigation
        component_name: 组件名称，用于类名与文件名，如 login、orders_export
        steps: 步骤列表，每项含 action、selector、value、url、optional、comment 等
        metadata: 可选元数据，如 container_selector（录制时的容器上下文）

    Returns:
        符合《采集脚本编写规范》的 Python 源码字符串
    """
    lines: List[str] = []
    cap_platform = (platform or "platform").capitalize()
    # 登录组件类名用 component_type 避免重复前缀（如 MiaoshouLogin 而非 MiaoshouMiaoshouLogin）
    cap_name = _to_class_name(component_type if component_type == "login" else (component_name or component_type))

    # 文件头（标准化 component 显示名：login 用 platform/type，与 build_component_name 一致）
    display_name = f"{platform}/{component_type}" if component_type == "login" else f"{platform}/{component_name}"
    lines.append('"""')
    lines.append(f"Generated component: {display_name}")
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
        lines.append("from pathlib import Path")
        lines.append("from modules.components.export.base import ExportComponent, ExportResult, ExportMode, build_standard_output_root")
    elif component_type == "navigation":
        lines.append("from modules.components.navigation.base import NavigationComponent, NavigationResult, TargetPage")
    elif component_type == "date_picker":
        lines.append("from modules.components.date_picker.base import DatePickerComponent, DatePickResult, DateOption")
    else:
        lines.append("from modules.components.base import ComponentBase, ResultBase")
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
    elif component_type == "export":
        lines.append(f"class {cap_platform}{cap_name}(ExportComponent):")
        lines.append(f'    """{platform} export component - generated from recorder. Edit as needed."""')
        lines.append("")
        lines.append("    platform = " + repr(platform))
        lines.append("    component_type = \"export\"")
        lines.append("    data_domain = None  # TODO: set data_domain")
        lines.append("")
        lines.append("    def __init__(self, ctx: ExecutionContext) -> None:")
        lines.append("        super().__init__(ctx)")
        lines.append("")
        lines.append("    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:")
        lines.append("        config = self.ctx.config or {}")
        lines.append("        acc = self.ctx.account or {}")
        lines.append("        output_root = build_standard_output_root(self.ctx, data_type=self.data_domain or \"unknown\", granularity=\"daily\")")
        lines.append("        output_root.mkdir(parents=True, exist_ok=True)")
        body_indent = "        "
    elif component_type == "navigation":
        lines.append(f"class {cap_platform}{cap_name}(NavigationComponent):")
        lines.append(f'    """{platform} navigation component - generated from recorder. Edit as needed."""')
        lines.append("")
        lines.append("    platform = " + repr(platform))
        lines.append("    component_type = \"navigation\"")
        lines.append("    data_domain = None")
        lines.append("")
        lines.append("    def __init__(self, ctx: ExecutionContext) -> None:")
        lines.append("        super().__init__(ctx)")
        lines.append("")
        lines.append("    async def run(self, page: Any, target: TargetPage) -> NavigationResult:")
        lines.append("        config = self.ctx.config or {}")
        lines.append("        acc = self.ctx.account or {}")
        body_indent = "        "
    elif component_type == "date_picker":
        lines.append(f"class {cap_platform}{cap_name}(DatePickerComponent):")
        lines.append(f'    """{platform} date_picker component - generated from recorder. Edit as needed."""')
        lines.append("")
        lines.append("    platform = " + repr(platform))
        lines.append("    component_type = \"date_picker\"")
        lines.append("    data_domain = None")
        lines.append("")
        lines.append("    def __init__(self, ctx: ExecutionContext) -> None:")
        lines.append("        super().__init__(ctx)")
        lines.append("")
        lines.append("    async def run(self, page: Any, option: DateOption) -> DatePickResult:")
        lines.append("        config = self.ctx.config or {}")
        lines.append("        acc = self.ctx.account or {}")
        body_indent = "        "
    else:
        lines.append(f"class {cap_platform}{cap_name}Component(ComponentBase):")
        lines.append(f'    """{platform} {component_type} - generated from recorder. Edit as needed."""')
        lines.append("")
        lines.append("    platform = " + repr(platform))
        lines.append("    component_type = " + repr(component_type))
        lines.append("    data_domain = None")
        lines.append("")
        lines.append("    def __init__(self, ctx: ExecutionContext) -> None:")
        lines.append("        super().__init__(ctx)")
        lines.append("")
        lines.append("    async def run(self, page: Any) -> ResultBase:")
        lines.append("        config = self.ctx.config or {}")
        lines.append("        acc = self.ctx.account or {}")
        body_indent = "        "
    lines.append("")
    # URL 导航：来源优先级 + 平台默认 fallback（组件业务逻辑，保留在组件中）
    if component_type == "login":
        lines.append(body_indent + "params = config.get(\"params\") or {}")
        lines.append(body_indent + "captcha_code = (params.get(\"captcha_code\") or params.get(\"otp\") or \"\").strip()")
        _defaults_repr = ", ".join(f"{repr(k)}: {repr(v)}" for k, v in PLATFORM_DEFAULT_LOGIN_URLS.items())
        lines.append(body_indent + f"_platform_defaults = {{{_defaults_repr}}}")
        lines.append(body_indent + "_target_url = (")
        lines.append(body_indent + "    str(params.get(\"login_url_override\") or \"\").strip()")
        lines.append(body_indent + "    or str(acc.get(\"login_url\") or \"\").strip()")
        lines.append(body_indent + "    or str(config.get(\"default_login_url\") or \"\").strip()")
        lines.append(body_indent + "    or _platform_defaults.get(self.platform, \"\").strip()")
        lines.append(body_indent + ")")
        lines.append(body_indent + "if _target_url and not captcha_code:")
        lines.append(
            body_indent
            + "    await page.goto(_target_url, wait_until=\"domcontentloaded\", timeout=60000)"
        )
        lines.append(body_indent + "    await page.wait_for_load_state(\"domcontentloaded\", timeout=10000)")
        lines.append(body_indent + "    await self.guard_overlays(page, label=\"after login navigation\")")
        _container_sel = metadata.get("container_selector", "").strip() if metadata else ""
        if _container_sel:
            lines.append(body_indent + f"# Container scope: from recording context")
            lines.append(body_indent + f"_form = page.locator({repr(_container_sel)})")
        else:
            lines.append(body_indent + "# Container scope: defaults to page; narrow down if needed")
            lines.append(body_indent + "_form = page")
        lines.append("")

    _skip_indices: set = set()
    for i, step in enumerate(steps):
        if i in _skip_indices:
            continue
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

        if action == "click" and selector.strip() and i + 1 < len(steps):
            next_step = steps[i + 1]
            next_action = (next_step.get("action") or "").strip().lower()
            next_sel = (next_step.get("selector") or "").strip()
            if not next_sel and next_step.get("selectors"):
                next_sel = _selector_from_selectors(next_step["selectors"]).strip()
            if next_action == "fill" and next_sel == selector.strip():
                _skip_indices.add(i)
                continue

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
                lines.append(step_indent + "# 选择器为空，已跳过（请录制时补全或人工添加）")
            else:
                loc_var = f"_el_{i}"
                scope = "_form" if component_type == "login" and not is_popup_step else "page"
                loc_code = _selector_to_locator_scoped(scope, selector, step_indent, loc_var, use_first=False)
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
            loc_var = f"_el_{i}"
            scope = "_form" if component_type == "login" and not is_captcha_step else "page"
            loc_code = _selector_to_locator_scoped(scope, selector, step_indent, loc_var, use_first=False)
            if loc_code:
                lines.extend(loc_code)
                lines.append(step_indent + f"await expect({loc_var}).to_be_visible()")
                if is_captcha_step:
                    verification_type = "otp" if (step_group == "captcha_otp" or "otp" in (scene_tags or [])) else "graphical_captcha"
                    lines.append(step_indent + "value = captcha_code")
                    lines.append(step_indent + "if not value:")
                    lines.append(step_indent + "    screenshot_path = None")
                    lines.append(step_indent + "    screenshot_dir = config.get(\"task\", {}).get(\"screenshot_dir\")")
                    lines.append(step_indent + "    if screenshot_dir:")
                    lines.append(step_indent + "        os.makedirs(screenshot_dir, exist_ok=True)")
                    lines.append(step_indent + "        screenshot_path = os.path.join(screenshot_dir, \"captcha.png\")")
                    lines.append(step_indent + "    else:")
                    lines.append(step_indent + "        import tempfile")
                    lines.append(step_indent + "        fd, screenshot_path = tempfile.mkstemp(suffix=\".png\", prefix=\"captcha_\")")
                    lines.append(step_indent + "        os.close(fd)")
                    lines.append(step_indent + "    await page.screenshot(path=screenshot_path, timeout=5000)")
                    lines.append(step_indent + f"    raise VerificationRequiredError({repr(verification_type)}, screenshot_path)")
                    lines.append(step_indent + f"await {loc_var}.fill(value, timeout=10000)")
                elif "{{account.username}}" in value or "{{account.password}}" in value:
                    lines.append(step_indent + "# Value from ctx.account - use acc.get(\"username\") / acc.get(\"password\")")
                    fill_val = "acc.get(\"password\", \"\")" if "password" in value.lower() else "acc.get(\"username\", \"\")"
                    lines.append(step_indent + f"await {loc_var}.fill({fill_val}, timeout=10000)")
                else:
                    lines.append(step_indent + f"await {loc_var}.fill({repr(value)}, timeout=10000)")
        elif action == "select":
            loc_var = f"_el_{i}"
            loc_code = _selector_to_locator_scoped("page", selector, step_indent, loc_var, use_first=False)
            if loc_code:
                lines.extend(loc_code)
                lines.append(step_indent + f"await expect({loc_var}).to_be_visible()")
                lines.append(step_indent + f"await {loc_var}.select_option({repr(value)}, timeout=10000)")
            else:
                lines.append(step_indent + f"# TODO: select action - selector empty, add manually")
        elif action == "press":
            if selector.strip():
                loc_var = f"_el_{i}"
                loc_code = _selector_to_locator_scoped("page", selector, step_indent, loc_var, use_first=False)
                if loc_code:
                    lines.extend(loc_code)
                    lines.append(step_indent + f"await {loc_var}.press({repr(value)}, timeout=5000)")
                else:
                    lines.append(step_indent + f"await page.keyboard.press({repr(value)})")
            else:
                lines.append(step_indent + f"await page.keyboard.press({repr(value)})")
        elif action == "download":
            lines.append(step_indent + "async with page.expect_download(timeout=60000) as download_info:")
            if selector.strip():
                loc_var = f"_el_{i}"
                loc_code = _selector_to_locator_scoped("page", selector, step_indent + "    ", loc_var, use_first=False)
                if loc_code:
                    lines.extend(loc_code)
                    lines.append(step_indent + f"    await {loc_var}.click(timeout=10000)")
                else:
                    lines.append(step_indent + f"    pass  # TODO: trigger download click")
            else:
                lines.append(step_indent + f"    pass  # TODO: trigger download click")
            lines.append(step_indent + "_download = await download_info.value")
            lines.append(step_indent + "_dl_path = config.get(\"download_dir\", \".\") + \"/\" + _download.suggested_filename")
            lines.append(step_indent + "await _download.save_as(_dl_path)")
        elif action == "wait":
            timeout_ms = step.get("timeout", 1000)
            comment_text = (step.get("comment") or "").strip()
            fixed_reason = step.get("fixed_wait_reason") or ""
            if fixed_reason or any(k in comment_text for k in ("固定", "延时", "sleep", "等待")):
                reason = fixed_reason or comment_text or "固定等待"
                lines.append(step_indent + f"# 固定等待: {reason}")
                lines.append(step_indent + f"await page.wait_for_timeout({timeout_ms})")
            else:
                lines.append(step_indent + "# 页面稳定；可改为 expect(locator).to_be_visible() 等条件等待")
                lines.append(step_indent + f'await page.wait_for_load_state("networkidle", timeout={timeout_ms})')
        else:
            lines.append(step_indent + f"# TODO: action {action!r} - implement per COLLECTION_SCRIPT_WRITING_GUIDE.md")
        if optional:
            # 8.1 可观测处理：记录步骤上下文，避免静默吞错
            lines.append(body_indent + "except Exception as e:")
            lines.append(body_indent + "    if getattr(self.ctx, \"logger\", None):")
            lines.append(
                body_indent
                + f"        self.ctx.logger.warning(\"Optional step {i + 1} skipped (action={action}): %s\", e)"
            )
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

    # 返回语句（验证码步骤 raise 后由 run() 开头 captcha_code 分支处理，此处不生成 return 避免不可达代码）
    if component_type == "login":
        lines.append(body_indent + "# TODO: replace the placeholder below with explicit login_ready detection")
        lines.append(body_indent + "# Standard: pre-check -> action -> post-check")
        lines.append(body_indent + "# Action success does not equal business success")
        lines.append(body_indent + "# Prefer helper names such as detect_login_ready / ensure_popup_closed / wait_export_complete")
        lines.append(body_indent + "# Check at least one observable signal: URL left login page, dashboard marker visible, blocking popup absent")
        lines.append(body_indent + "# Example: await page.wait_for_url(\"**/dashboard**\", timeout=15000)")
        lines.append(body_indent + "# Example: await expect(page.get_by_text(\"Welcome\")).to_be_visible(timeout=10000)")
        lines.append(body_indent + "return LoginResult(success=True, message=\"ok\")")
    elif component_type == "export":
        lines.append(body_indent + "# 下载文件")
        lines.append(body_indent + "async with page.expect_download(timeout=60000) as download_info:")
        lines.append(body_indent + "    pass  # TODO: click the download/export trigger button above if not already done")
        lines.append(body_indent + "_download = await download_info.value")
        lines.append(body_indent + "file_path = output_root / _download.suggested_filename")
        lines.append(body_indent + "await _download.save_as(str(file_path))")
        lines.append(body_indent + "return ExportResult(success=True, message=\"ok\", file_path=str(file_path))")
    elif component_type == "navigation":
        lines.append(body_indent + "return NavigationResult(success=True, message=\"ok\")")
    elif component_type == "date_picker":
        lines.append(body_indent + "return DatePickResult(success=True, message=\"ok\")")
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

    选择器优先级（与 JS 注入 push 顺序一致）:
        role > placeholder > label > text > css

    unique 降级逻辑:
        1. 优先返回 unique=True 的最高优先级选择器
        2. 若最高优先级选择器非唯一，降级到下一个 unique=True 的选择器
        3. 若全部非唯一，返回最高优先级选择器（代码中会附加建议迁移注释）
    """
    if not selectors:
        return ""

    valid: List[Dict[str, Any]] = []
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
        valid.append({"type": t, "value": v, "unique": item.get("unique", True)})

    if not valid:
        return ""

    def _format(t: str, v: str) -> str:
        if t == "role":
            return v if v.startswith("role=") else f"role={v}"
        if t == "text":
            return v if v.startswith("text=") else f"text={v}"
        if t == "label":
            return v if v.startswith("label=") else f"label={v}"
        if t == "placeholder":
            return v if v.startswith("placeholder=") else f"placeholder={v}"
        return v

    unique_items = [s for s in valid if s["unique"]]
    if unique_items:
        return _format(unique_items[0]["type"], unique_items[0]["value"])

    return _format(valid[0]["type"], valid[0]["value"])


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
    use_first: bool = False,
) -> Optional[List[str]]:
    """
    将 selector 转为 locator 代码行。
    优先 get_by_role / get_by_text / get_by_label / get_by_placeholder，否则 locator(selector) 并注释。
    use_first: 为 True 时在赋值后加 .first，避免 _form=page 时多元素 strict mode。
    """
    if not selector or not selector.strip():
        return None
    sel = selector.strip()
    suffix = ".first" if use_first else ""
    out: List[str] = []
    # role=button[name=登录]
    m = re.match(r"role=(\w+)\s*\[\s*name\s*=\s*([^\]]+)\]\s*$", sel, re.I)
    if m:
        role, name = m.group(1), m.group(2).strip().strip('"\'')
        out.append(indent + f"{var_name} = {page_var}.get_by_role({repr(role)}, name={repr(name)}){suffix}")
        return out
    if sel.startswith("text="):
        text = sel[5:].strip().strip('"\'')
        out.append(indent + f"{var_name} = {page_var}.get_by_text({repr(text)}){suffix}")
        return out
    if sel.startswith("label="):
        label = sel[6:].strip().strip('"\'')
        out.append(indent + f"{var_name} = {page_var}.get_by_label({repr(label)}){suffix}")
        return out
    if sel.startswith("placeholder="):
        ph = sel[12:].strip().strip('"\'')
        out.append(indent + f"{var_name} = {page_var}.get_by_placeholder({repr(ph)}){suffix}")
        return out
    out.append(indent + f"# 建议迁移到 get_by_*")
    out.append(indent + f"{var_name} = {page_var}.locator({repr(sel)}){suffix}")
    return out


def _selector_to_locator_scoped(
    page_var: str,
    selector: str,
    indent: str,
    var_name: str,
    use_first: bool = False,
) -> Optional[List[str]]:
    """
    支持容器收敛链式选择器（container >> target）：
    - iframe 作用域：iframe_selector >> target_selector
    - dialog 作用域：dialog_selector >> target_selector
    - row 作用域：row_selector >> target_selector
    其它场景回退到 _selector_to_locator。
    use_first: 透传给 _selector_to_locator，用于 _form=page 时防 strict mode。
    """
    if not selector or ">>" not in selector:
        return _selector_to_locator(page_var, selector, indent, var_name, use_first=use_first)

    parts = [p.strip() for p in selector.split(">>") if p.strip()]
    if len(parts) < 2:
        return _selector_to_locator(page_var, selector, indent, var_name)

    container = parts[0]
    target = " >> ".join(parts[1:]).strip()
    c_low = container.lower()

    out: List[str] = []
    if "iframe" in c_low:
        frame_var = f"_frame_scope_{var_name}"
        out.append(indent + f"{frame_var} = {page_var}.frame_locator({repr(container)})")
        out.append(indent + "# 作用域收敛：iframe 内定位")
        inner = _selector_to_locator(frame_var, target, indent, var_name, use_first=use_first)
        if inner:
            out.extend(inner)
            return out
        return _selector_to_locator(page_var, selector, indent, var_name, use_first=use_first)

    if any(k in c_low for k in ("dialog", "modal")):
        dialog_var = f"_dialog_scope_{var_name}"
        out.append(indent + f"{dialog_var} = {page_var}.locator({repr(container)})")
        out.append(indent + f"await expect({dialog_var}).to_have_count(1)")
        out.append(indent + "# 作用域收敛：dialog 内定位")
        inner = _selector_to_locator(dialog_var, target, indent, var_name, use_first=use_first)
        if inner:
            out.extend(inner)
            return out
        return _selector_to_locator(page_var, selector, indent, var_name, use_first=use_first)

    if any(k in c_low for k in (" tr", "tr[", "tbody", "row")):
        row_var = f"_row_scope_{var_name}"
        out.append(indent + f"{row_var} = {page_var}.locator({repr(container)})")
        out.append(indent + f"await expect({row_var}).to_have_count(1)")
        out.append(indent + "# 作用域收敛：表格行内定位")
        inner = _selector_to_locator(row_var, target, indent, var_name, use_first=use_first)
        if inner:
            out.extend(inner)
            return out
        return _selector_to_locator(page_var, selector, indent, var_name, use_first=use_first)

    container_var = f"_scope_{var_name}"
    out.append(indent + f"{container_var} = {page_var}.locator({repr(container)})")
    out.append(indent + f"await expect({container_var}).to_have_count(1)")
    out.append(indent + "# 作用域收敛：容器内定位")
    inner = _selector_to_locator(container_var, target, indent, var_name, use_first=use_first)
    if inner:
        out.extend(inner)
        return out
    return _selector_to_locator(page_var, selector, indent, var_name, use_first=use_first)


def _build_captcha_locator_expr(selector: str) -> str:
    """将 selector 转为 page.locator(...) 表达式；8.4/8.5 不追加 .first，由调用处做唯一性检查。"""
    if not selector or not selector.strip():
        return "page.locator(\"input[placeholder*='验证码'], input[name*='captcha' i], input[name*='code' i]\")"
    sel = selector.strip()
    return f"page.locator({repr(sel)})"


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


def _generate_login_captcha_resume_block(
    body_indent: str, captcha_info: Dict[str, Any], success_criteria: Optional[Dict[str, Any]] = None
) -> List[str]:
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
    # 8.5 移除 .first，改为唯一性检查 + 失败可诊断（含 URL/selector 上下文）
    out = [
        body_indent + "# 恢复路径：若有回传的验证码/OTP，同页继续，不 goto",
        body_indent + "captcha_code = params.get(\"captcha_code\") or params.get(\"otp\")",
        body_indent + "if captcha_code:",
        body_indent + "    value = (captcha_code or \"\").strip()",
        body_indent + "    if value:",
        body_indent + "        try:",
        body_indent + f"            _cap_inp = {cap_loc}",
        body_indent + "            await expect(_cap_inp).to_have_count(1)",
        body_indent + "            await _cap_inp.fill(value, timeout=5000)",
        body_indent + f"            _login_btn = page.locator({repr(login_sel)})",
        body_indent + "            await expect(_login_btn).to_have_count(1)",
        body_indent + "            await _login_btn.click(timeout=3000)",
        body_indent + "            # 固定等待: 验证码回传后等待登录态回写/跳转",
        body_indent + "            await asyncio.sleep(2.0)",
        body_indent + "            cur = str(getattr(page, \"url\", \"\"))",
    ]
    sc = success_criteria or {}
    url_contains = sc.get("url_contains")
    url_not_contains = sc.get("url_not_contains")
    if url_contains or url_not_contains:
        conditions = []
        if url_contains:
            conditions.append(f"{repr(url_contains)} in cur")
        if url_not_contains:
            conditions.append(f"{repr(url_not_contains)} not in cur.lower()")
        cond_str = " or ".join(conditions)
        out.append(body_indent + f"            if {cond_str}:")
    else:
        out.append(body_indent + "            # TODO: configure success URL condition via success_criteria")
        out.append(body_indent + "            if \"login\" not in cur.lower():")
    out += [
        body_indent + "                return LoginResult(success=True, message=\"ok\")",
        body_indent + "            # 若验证码提交后仍停留在登录页，则视为失败，避免继续执行主流程再次触发验证码",
        body_indent + "            return LoginResult(success=False, message=\"验证码提交后登录未跳转或仍在登录页\")",
        body_indent + "        except Exception as e:",
        body_indent
        + "            _ctx = \"url=\" + str(getattr(page, \"url\", \"\")) + \" cap_sel=\" + "
        + repr(cap_sel)
        + " + \" login_sel=\" + "
        + repr(login_sel),
        body_indent + "            return LoginResult(success=False, message=\"验证码恢复失败: \" + str(e) + \" (\" + _ctx + \")\")",
        body_indent + "",
    ]
    return out


def _generate_captcha_detection_block(
    body_indent: str, step_indent: str, selector: str, verification_type: str = "graphical_captcha"
) -> List[str]:
    """生成验证码检测与 VerificationRequiredError 抛出逻辑；8.5 使用 expect 唯一性检查，避免 count()+is_visible()。"""
    cap_loc = _build_captcha_locator_expr(selector)
    out = [
        step_indent + "# 检测验证码 DOM，若唯一且可见则截图并暂停等待用户回传",
        step_indent + "await asyncio.sleep(2.5)",
        step_indent + f"_cap_loc = {cap_loc}",
        step_indent + "try:",
        step_indent + "    await expect(_cap_loc).to_have_count(1)",
        step_indent + "    await expect(_cap_loc).to_be_visible(timeout=3000)",
        step_indent + "    screenshot_path = None",
        step_indent + "    screenshot_dir = config.get(\"task\", {}).get(\"screenshot_dir\")",
        step_indent + "    if screenshot_dir:",
        step_indent + "        os.makedirs(screenshot_dir, exist_ok=True)",
        step_indent + "        screenshot_path = os.path.join(screenshot_dir, \"captcha.png\")",
        step_indent + "    else:",
        step_indent + "        import tempfile",
        step_indent + "        fd, screenshot_path = tempfile.mkstemp(suffix=\".png\", prefix=\"captcha_\")",
        step_indent + "        os.close(fd)",
        step_indent + "    await page.screenshot(path=screenshot_path, timeout=5000)",
        step_indent + f"    raise VerificationRequiredError({repr(verification_type)}, screenshot_path)",
        step_indent + "except VerificationRequiredError:",
        step_indent + "    raise",
        step_indent + "except Exception as e:",
        step_indent + "    if getattr(self.ctx, \"logger\", None):",
        step_indent + "        self.ctx.logger.warning(\"Captcha detection/screenshot failed: %s\", e)",
        step_indent + "    raise",
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
