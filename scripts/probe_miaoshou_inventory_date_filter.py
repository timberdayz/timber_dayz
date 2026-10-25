"""妙手仓库清单「更新时间维度 + 自定义区间」筛选器的**只读**取证探针。

用途：回答三个至今没有真实页面证据的问题——

1. 仓库清单页的日期筛选控件锚点是什么（有没有 ``data-field`` 之类的稳定属性，
   还是只能靠 class / 文案）；
2. 维度下拉的真实结构：选项是不是只有「创建时间 / 更新时间」两项，
   选中值是不是真的写在 ``modelvaluegroup`` 上（代码里假设是 ``gmtModified`` / ``gmtCreate``）；
3. 点「确定」之后，**已应用区间**写在哪个节点的哪个属性上
   （代码里假设是筛选器根节点的 ``modelvaluegroup``）。

**只读保证**：

- 只 ``load`` 登录态，**从不 save**，登录态文件不会被改动；
- 只读 DOM + 点开筛选面板 + 切维度 + 填区间 + 点「确定」，
  **不点「搜索」、不点「导出」、不触发任何导出弹窗**；
  筛选器状态只存在于这个浏览器上下文里，进程结束即丢弃。

用法::

    python scripts/probe_miaoshou_inventory_date_filter.py
    python scripts/probe_miaoshou_inventory_date_filter.py --headed
    python scripts/probe_miaoshou_inventory_date_filter.py --cdp 9222

登录态默认取 ``data/sessions/miaoshou/miaoshou_real_001/storage_state.json``。
登录态失效时脚本会明确提示需要人工登录，不会编造结论。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = REPO_ROOT / "data" / "sessions" / "miaoshou" / "miaoshou_real_001"
CHECKLIST_URL = "https://erp.91miaoshou.com/warehouse/checklist"

VALUE_ATTR = "modelvaluegroup"

# 代码里假设的选择器（探针会逐个验证，不成立就报出来）
ASSUMED = {
    "面板": ".jx-picker-panel",
    "维度下拉": ".jx-picker-panel .jx-select",
    "维度选项": ".jx-picker-panel .jx-select-dropdown li",
    "区间输入": ".jx-picker-panel input.jx-range-input",
    "确定": "button.jx-picker-panel__link-btn.is-plain",
    "清空": "button.jx-picker-panel__link-btn.is-text",
}

# 打开筛选面板的候选触发器（按证据强度排序）
TRIGGER_CANDIDATES = (
    "[data-field='gmtModified']",
    "[data-field='gmtCreate']",
    "[data-field='updateTime']",
    "[data-field='createTime']",
    "text=更新时间",
    "text=创建时间",
)


def _dump(label: str, payload: Any) -> None:
    print(f"\n=== {label} ===")
    print(payload)


def _safe(label: str, fn: Any) -> Any:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        print(f"[probe] {label} 失败：{exc}")
        return None


def _first_visible(page: Any, selector: str) -> Any | None:
    try:
        locator = page.locator(selector).first
        if locator.count() and locator.is_visible():
            return locator
    except Exception:
        return None
    return None


def _scan_value_attr_nodes(page: Any) -> list[dict[str, Any]]:
    """扫出页面上**所有**带 modelvaluegroup 属性的节点。

    这是定位「维度下拉」与「筛选器根」最直接的证据：
    哪个节点的属性值是 gmtCreate / gmtModified，哪个是已应用的区间，全在这里。
    """
    return page.evaluate(
        """(attr) => Array.from(document.querySelectorAll('[' + attr + ']')).map((el) => ({
            tag: el.tagName,
            cls: el.className || '',
            field: el.getAttribute('data-field') || '',
            value: el.getAttribute(attr) || '',
            text: (el.textContent || '').trim().slice(0, 80),
        }))""",
        VALUE_ATTR,
    )


def _open_panel(page: Any) -> Any | None:
    """按候选锚点依次尝试点开筛选面板。"""
    for selector in TRIGGER_CANDIDATES:
        try:
            locator = page.locator(selector).first
            if not locator.count():
                continue
            locator.click(timeout=2000)
            panel = _first_visible(page, ASSUMED["面板"])
            if panel is not None:
                print(f"[probe] 用触发器 {selector} 打开了面板")
                return panel
        except Exception as exc:  # noqa: BLE001
            print(f"[probe] 触发器 {selector} 不可用：{exc}")
    return None


def _panel_select_modelvalue(panel: Any) -> str:
    try:
        return (
            panel.locator(".jx-select").first.get_attribute(VALUE_ATTR) or ""
        ).strip()
    except Exception:
        return ""


def _panel_option_texts(panel: Any) -> list[str]:
    try:
        items = panel.locator(".jx-select-dropdown li")
        count = items.count()
        return [(items.nth(i).text_content() or "").strip() for i in range(count)]
    except Exception:
        return []


def _switch_to_modified(panel: Any) -> str:
    """把维度切到「更新时间」，返回切换后的 modelvaluegroup。"""
    before = _panel_select_modelvalue(panel)
    try:
        panel.locator(".jx-select").first.click(timeout=2000)
    except Exception:
        try:
            panel.locator(".jx-select__wrapper").first.click(timeout=2000)
        except Exception as exc:  # noqa: BLE001
            print(f"[probe] 维度下拉点不开：{exc}")
            return before
    try:
        items = panel.locator(".jx-select-dropdown li")
        count = items.count()
        for index in range(count):
            option = items.nth(index)
            text = (option.text_content() or "").strip()
            if "更新时间" in text:
                option.click(timeout=2000)
                break
    except Exception as exc:  # noqa: BLE001
        print(f"[probe] 切维度失败：{exc}")
    after = _panel_select_modelvalue(panel)
    print(f"[probe] 维度 modelvaluegroup：{before!r} → {after!r}")
    return after


def _apply_range(panel: Any, start: str, end: str) -> None:
    """填区间并点「确定」（不点搜索、不导出）。"""
    try:
        inputs = panel.locator("input.jx-range-input")
        if inputs.count() >= 2:
            inputs.nth(0).fill(start)
            inputs.nth(1).fill(end)
        else:
            print(f"[probe] 区间输入框只有 {inputs.count()} 个，跳过填写")
            return
    except Exception as exc:  # noqa: BLE001
        print(f"[probe] 填区间失败：{exc}")
        return
    try:
        confirm = panel.locator("button.jx-picker-panel__link-btn.is-plain").first
        confirm.click(timeout=2000)
    except Exception as exc:  # noqa: BLE001
        print(f"[probe] 点「确定」失败：{exc}")


def _login_expired(page: Any) -> bool:
    """登录态是否已失效（跳回登录页 / 页面上有「立即登录」）。"""
    url = str(page.url or "")
    if "/login" in url or url.rstrip("/").endswith("erp.91miaoshou.com"):
        return True
    try:
        return page.locator("text=立即登录").count() > 0
    except Exception:
        return False


def _probe_page(page: Any, start: str, end: str) -> int:
    page.goto(CHECKLIST_URL, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(2500)

    print(f"[probe] URL   = {page.url}")
    print(f"[probe] TITLE = {page.title()}")

    if _login_expired(page):
        print(
            "[probe] **登录态已失效**（被重定向回登录页）。"
            "请先用 pwcli 人工登录并保存状态，再重跑本探针。"
        )
        page.screenshot(
            path=str(REPO_ROOT / "output" / "probe_inventory_date_filter.png")
        )
        return 1

    _dump("页面上所有带 modelvaluegroup 的节点", _scan_value_attr_nodes(page))

    panel = _open_panel(page)
    if panel is None:
        print(
            "[probe] 没能打开筛选面板 —— 这是**取证失败**，不是结论。"
            "请把上面的 modelvaluegroup 节点清单和截图发我，我按真实结构改选择器。"
        )
        page.screenshot(
            path=str(REPO_ROOT / "output" / "probe_inventory_date_filter.png")
        )
        return 2

    _dump("维度下拉当前 modelvaluegroup", _panel_select_modelvalue(panel))
    _dump("维度下拉选项文本", _panel_option_texts(panel))

    _switch_to_modified(panel)
    _apply_range(panel, start, end)
    page.wait_for_timeout(800)

    _dump("操作后页面上所有带 modelvaluegroup 的节点", _scan_value_attr_nodes(page))

    page.screenshot(path=str(REPO_ROOT / "output" / "probe_inventory_date_filter.png"))
    print(
        "\n[probe] 截图：output/probe_inventory_date_filter.png"
        "（登录态文件未被改动；未点搜索、未点导出）"
    )
    return 0


def probe(state_path: Path, headed: bool, start: str, end: str) -> int:
    """执行取证。返回进程退出码（0 成功 / 1 登录态失效 / 2 取证失败）。"""
    from playwright.sync_api import sync_playwright

    storage_state = state_path / "storage_state.json"
    if not storage_state.exists():
        print(f"[probe] 找不到登录态文件：{storage_state}")
        print("[probe] 请先用 pwcli 人工登录并保存状态后再运行本探针。")
        return 1

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        context = browser.new_context(storage_state=str(storage_state))
        page = context.new_page()
        try:
            return _probe_page(page, start, end)
        finally:
            context.close()
            browser.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="妙手库存日期筛选只读取证探针")
    parser.add_argument("--state", default=str(DEFAULT_STATE), help="登录态目录")
    parser.add_argument("--headed", action="store_true", help="有头模式（默认无头）")
    parser.add_argument("--start", default="2026-10-20 00:00:00", help="区间起点")
    parser.add_argument("--end", default="2026-10-25 23:59:59", help="区间终点")
    args = parser.parse_args(argv)
    return probe(Path(args.state), args.headed, args.start, args.end)


if __name__ == "__main__":
    sys.exit(main())
