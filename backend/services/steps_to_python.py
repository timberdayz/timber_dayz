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
        lines.append("from modules.components.login.base import LoginComponent, LoginResult")
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

        if comment:
            lines.append(body_indent + f"# {comment}")
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
            loc_var = f"_el_{i}"
            loc_code = _selector_to_locator("page", selector, step_indent, loc_var)
            if loc_code:
                lines.extend(loc_code)
                lines.append(step_indent + f"await expect({loc_var}).to_be_visible()")
                lines.append(step_indent + f"await {loc_var}.click(timeout=10000)")
        elif action == "fill":
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
