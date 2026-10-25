"""妙手仓库清单「更新时间维度 + 自定义区间」筛选器的**只读**取证探针。

为什么重写
----------
上一版探针**假设**筛选器是「picker 面板 + 维度 select + 确定/清空按钮」
（``.jx-picker-panel`` 系列）。真实页面根本没有那个面板 ——
2026-10-26 的采集失败（任务 7b302e24）报「仓库清单日期筛选面板打不开」，
根因就是这个假设。

新版探针**不假设任何结构**，直接把真实 DOM 抓下来：
1. 触发器上显示的维度文案、对应元素的 class 与 outerHTML
2. 日期区间输入框的 placeholder / class / type
3. 页面到底有没有「确定 / 清空」按钮
4. 下拉浮层展开后的选项结构（元素、class、outerHTML）
5. 「SKU总数」锚点

并且**用组件自己的定位逻辑**跑一遍 ``probe_state`` → 探针的结论就是组件的结论，
不会出现「探针能找到、组件找不到」这种两边不一致的情况。

**只读保证**：

- 只 ``load`` 登录态，**从不 save**，登录态文件不会被改动；
- 只读 DOM + 点开维度下拉（只读操作），**不填区间、不点「搜索」、不点「导出」**、
  不触发任何导出弹窗；筛选器状态只存在于这个浏览器上下文里，进程结束即丢弃。

用法::

    python scripts/probe_miaoshou_inventory_date_filter.py
    python scripts/probe_miaoshou_inventory_date_filter.py --headed
    python scripts/probe_miaoshou_inventory_date_filter.py --state <目录>

登录态默认取 ``data/sessions/miaoshou/miaoshou_real_001/storage_state.json``。
登录态失效时脚本会明确提示需要人工登录，不会编造结论。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = REPO_ROOT / "data" / "sessions" / "miaoshou" / "miaoshou_real_001"
CHECKLIST_URL = "https://erp.91miaoshou.com/warehouse/checklist"
OUTPUT_DIR = REPO_ROOT / "output"

DIMENSION_LABELS = ("创建时间", "更新时间")


def _dump(label: str, payload: Any) -> None:
    print(f"\n=== {label} ===")
    print(payload)


async def _safe(label: str, fn: Any) -> Any:
    try:
        return await fn()
    except Exception as exc:  # noqa: BLE001
        print(f"[probe] {label} 失败：{exc}")
        return None


# ----------------------------------------------------------------------
# 真实 DOM 扫描（不假设任何选择器）
# ----------------------------------------------------------------------
SCAN_SCRIPT = """
() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const st = window.getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none';
  };
  const brief = (el) => ({
    tag: el.tagName,
    cls: (el.className || '').toString().slice(0, 160),
    id: el.id || '',
    text: (el.textContent || '').trim().slice(0, 60),
    html: el.outerHTML.slice(0, 400),
  });

  const dimensionNodes = Array.from(document.querySelectorAll('*'))
    .filter((el) => {
      const t = (el.textContent || '').trim();
      return t && t.length <= 6 && visible(el) &&
        ['创建时间', '更新时间'].includes(t) && el.children.length === 0;
    })
    .map(brief);

  const inputs = Array.from(document.querySelectorAll('input'))
    .map((el) => ({
      ...brief(el),
      type: el.type || '',
      placeholder: el.placeholder || '',
      value: el.value || '',
      visible: visible(el),
    }));

  const buttons = Array.from(document.querySelectorAll('button, a[role="button"]'))
    .filter(visible)
    .map((el) => ({ ...brief(el), text: (el.textContent || '').trim().slice(0, 24) }))
    .filter((b) => ['确定', '清空', '搜索', '重置'].some((k) => b.text.includes(k)));

  const skuNodes = Array.from(document.querySelectorAll('*'))
    .filter((el) => (el.textContent || '').includes('SKU总数') && visible(el))
    .map(brief)
    .slice(0, 5);

  return { dimensionNodes, inputs, buttons, skuNodes };
}
"""


async def _scan_dom(page: Any) -> dict[str, Any]:
    return await page.evaluate(SCAN_SCRIPT)


async def _visible_by_text(page: Any, label: str) -> Any | None:
    """页面上第一个**可见**、文本等于 label 的元素。"""
    try:
        candidates = page.get_by_text(label, exact=True)
        count = await candidates.count()
        for index in range(min(count, 12)):
            node = candidates.nth(index)
            if await node.is_visible():
                return node
    except Exception:
        return None
    return None


async def _login_expired(page: Any) -> bool:
    """登录态是否已失效（跳回登录页 / 页面上有「立即登录」）。"""
    url = str(page.url or "")
    if "/login" in url or url.rstrip("/").endswith("erp.91miaoshou.com"):
        return True
    try:
        return await page.locator("text=立即登录").count() > 0
    except Exception:
        return False


def _component_state(page: Any) -> Any:
    """用组件自己的定位逻辑读筛选器状态（只读，async）。"""
    from modules.platforms.miaoshou.components.inventory_config import (
        InventorySelectors,
    )
    from modules.platforms.miaoshou.components.inventory_date_filter import (
        MiaoshouInventoryDateFilter,
    )

    component = MiaoshouInventoryDateFilter(ctx=None, selectors=InventorySelectors())
    return component.probe_state(page)


async def _collect_initial_state(page: Any) -> tuple[Any, Any]:
    """初始状态：组件探测 + 真实 DOM 扫描（全程未做任何操作）。"""
    before_state = await _safe("组件状态（初始）", lambda: _component_state(page))
    _dump("组件 probe_state（初始，未做任何操作）", before_state)
    dom_before = await _safe("DOM 扫描（初始）", lambda: _scan_dom(page))
    _dump("维度文案所在元素", (dom_before or {}).get("dimensionNodes"))
    _dump(
        "页面上的 input（placeholder / class / 可见性）",
        (dom_before or {}).get("inputs"),
    )
    _dump("「确定 / 清空 / 搜索 / 重置」按钮", (dom_before or {}).get("buttons"))
    return before_state, dom_before


async def _open_dimension_dropdown(page: Any) -> bool:
    """点开维度下拉 —— 只读操作（不选、不填）。"""
    for label in DIMENSION_LABELS:
        node = await _visible_by_text(page, label)
        if node is None:
            continue
        try:
            await node.click(timeout=2000)
            await page.wait_for_timeout(800)
            print(f"[probe] 已点开维度下拉（触发器文案 {label!r}）")
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"[probe] 点触发器 {label!r} 失败：{exc}")
    print("[probe] 没找到可点的维度触发器 —— 这是**取证失败**，不是结论。")
    return False


async def _collect_dropdown_state(page: Any) -> tuple[Any, Any]:
    """下拉展开后的状态：浮层结构 + 组件探测。"""
    dom_after = await _safe("DOM 扫描（下拉展开）", lambda: _scan_dom(page))
    _dump("下拉展开后的维度元素", (dom_after or {}).get("dimensionNodes"))
    after_state = await _safe("组件状态（下拉展开）", lambda: _component_state(page))
    _dump("组件 probe_state（下拉展开后）", after_state)
    return after_state, dom_after


async def _write_outputs(page: Any, payload: dict[str, Any]) -> None:
    """把结构证据落盘（JSON + 截图）。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUTPUT_DIR / "probe_inventory_date_filter.json"
    out_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    await page.screenshot(path=str(OUTPUT_DIR / "probe_inventory_date_filter.png"))
    print(
        f"\n[probe] 结构证据：{out_json}\n"
        "[probe] 截图：output/probe_inventory_date_filter.png\n"
        "[probe] （登录态文件未被改动；未填区间、未点搜索、未点导出）"
    )


async def _probe_page(page: Any) -> int:
    await page.goto(CHECKLIST_URL, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(2500)

    print(f"[probe] URL   = {page.url}")
    print(f"[probe] TITLE = {await page.title()}")

    if await _login_expired(page):
        print(
            "[probe] **登录态已失效**（被重定向回登录页）。"
            "请先人工登录并保存状态，再重跑本探针。"
        )
        await page.screenshot(path=str(OUTPUT_DIR / "probe_inventory_date_filter.png"))
        return 1

    before_state, dom_before = await _collect_initial_state(page)
    await _open_dimension_dropdown(page)
    after_state, dom_after = await _collect_dropdown_state(page)

    await _write_outputs(
        page,
        {
            "url": page.url,
            "component_state_before": before_state,
            "component_state_after_dropdown": after_state,
            "dom_before": dom_before,
            "dom_after_dropdown": dom_after,
        },
    )
    return 0


async def probe(state_path: Path, headed: bool) -> int:
    """执行取证。返回进程退出码（0 成功 / 1 登录态失效）。"""
    from playwright.async_api import async_playwright

    storage_state = state_path / "storage_state.json"
    if not storage_state.exists():
        print(f"[probe] 找不到登录态文件：{storage_state}")
        print("[probe] 请先人工登录并保存状态后再运行本探针。")
        return 1

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headed)
        context = await browser.new_context(storage_state=str(storage_state))
        page = await context.new_page()
        try:
            return await _probe_page(page)
        finally:
            await context.close()
            await browser.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="妙手库存日期筛选只读取证探针")
    parser.add_argument("--state", default=str(DEFAULT_STATE), help="登录态目录")
    parser.add_argument("--headed", action="store_true", help="有头模式（默认无头）")
    args = parser.parse_args(argv)
    return asyncio.run(probe(Path(args.state), args.headed))


if __name__ == "__main__":
    sys.exit(main())
