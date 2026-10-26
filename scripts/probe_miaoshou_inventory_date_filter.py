"""妙手仓库清单「更新时间维度 + 自定义区间」筛选器的取证探针（v3）。

这一版修了两件事

--------------------------------------------------------------------
1. **登录态来源修正**
   采集任务把**内层** storage_state 直接喂给 Playwright
   （见 ``modules/apps/collection_center/executor_v2.py``：
   ``context_options["storage_state"] = storage_state``），
   而会话文件 ``data/sessions/<platform>/<account>/storage_state.json``
   是**外层包装**：

       { "platform": ..., "account_id": ..., "storage_state": {"cookies": [...], "origins": [...]}, ... }

   上一版探针把**整个包装**喂给 ``new_context(storage_state=...)``
   → 顶层没有 ``cookies``/``origins`` 键 → 实际 cookie 数 = 0
   → 永远被重定向回登录页 → 被误判成「登录态失效」。
   真凶是**探针取错了那一层**，不是妙手把 Walter 踢下线。
   现在探针按 ``session_manager._extract_state_payload`` 的同一规则取内层。

2. **点击落点取证**
   上一版只记「找到 / 没找到」，无法回答
   *「点这个候选，到底点到了哪个元素？」*
   现在对每个候选算它的中心点，再用 ``document.elementFromPoint``
   报出**真正会被点中的那个元素** ——
   「为什么点到了创建时间」从此是可读证据，不是推测。

**只读保证（scan 模式）**

- 只加载登录态，**从不 save**；
- 只读 DOM + 点开维度下拉（只读操作），**不填区间、不点「搜索」、不点「导出」**；
- 筛选器状态只存在于这个浏览器上下文里，进程结束即丢弃。

**verify 模式**（``--mode verify``）

- 额外**真的执行一次维度切换**，用来验收组件修好了没有；
- 只切换维度，**不填区间、不点搜索、不点导出**。

用法::

    python scripts/probe_miaoshou_inventory_date_filter.py
    python scripts/probe_miaoshou_inventory_date_filter.py --mode verify
    python scripts/probe_miaoshou_inventory_date_filter.py --headed
    python scripts/probe_miaoshou_inventory_date_filter.py --profile <目录>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote_plus

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ACCOUNT = "miaoshou_real_001"
DEFAULT_SESSION_DIR = REPO_ROOT / "data" / "sessions" / "miaoshou" / DEFAULT_ACCOUNT
CHECKLIST_URL = "https://erp.91miaoshou.com/warehouse/checklist"
OUTPUT_DIR = REPO_ROOT / "output"

DIMENSION_LABELS = ("创建时间", "更新时间")


def _dump(label: str, payload: Any) -> None:
    print(f"\n=== {label} ===")
    print(payload)


async def _safe(label: str, fn: Any) -> Any:
    """跑一个可能失败的动作；失败只记录，不中断整轮取证。"""
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
  const chain = (el) => {
    const out = [];
    let cur = el;
    for (let i = 0; i < 6 && cur; i += 1) {
      out.push(`${cur.tagName}.${(cur.className || '').toString().trim().split(/\\s+/).slice(0, 3).join('.')}`);
      cur = cur.parentElement;
    }
    return out;
  };

  const dimensionNodes = Array.from(document.querySelectorAll('*'))
    .filter((el) => {
      const t = (el.textContent || '').trim();
      return t && t.length <= 6 && visible(el) &&
        ['创建时间', '更新时间'].includes(t);
    })
    .map((el) => ({ ...brief(el), leaf: el.children.length === 0, chain: chain(el) }));

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

  // 挡住点击的弹窗（采集时由 popup_handler 关掉）
  const dialogs = Array.from(document.querySelectorAll('[role="dialog"], .jx-overlay-dialog'))
    .filter(visible)
    .map((el) => ({ ...brief(el), html: el.outerHTML.slice(0, 800) }))
    .slice(0, 4);

  // 所有可见的浮层容器（找维度下拉浮层用）
  const popups = Array.from(document.querySelectorAll('body *'))
    .filter((el) => {
      const st = window.getComputedStyle(el);
      const r = el.getBoundingClientRect();
      return visible(el) && r.width > 20 && r.height > 10 &&
        (st.position === 'absolute' || st.position === 'fixed') &&
        (el.getAttribute('role') === 'listbox' || /dropdown|popper|menu|popup/i.test(el.className || ''));
    })
    .map((el) => ({ ...brief(el), html: el.outerHTML.slice(0, 1200), chain: chain(el) }))
    .slice(0, 6);

  // 组件配置里那组浮层容器选择器，各命中了什么
  const dropdownCandidates = Array.from(document.querySelectorAll(
    ".jx-select-dropdown, .jx-dropdown-menu, .ant-select-dropdown, [role='listbox']"
  )).map((el) => ({
    ...brief(el),
    visible: visible(el),
    html: el.outerHTML.slice(0, 1600),
    chain: chain(el),
  })).slice(0, 40);

  // 维度下拉浮层：里面含「创建时间 / 更新时间」的那个
  const dimensionDropdown = Array.from(document.querySelectorAll(
    ".jx-select-dropdown, .jx-dropdown-menu, .ant-select-dropdown, [role='listbox']"
  )).filter((el) => {
    const t = (el.textContent || '');
    return t.includes('创建时间') && t.includes('更新时间');
  }).map((el) => ({
    ...brief(el),
    visible: visible(el),
    html: el.outerHTML.slice(0, 2000),
    chain: chain(el),
  })).slice(0, 3);

  // 维度下拉触发器（带 modelvaluegroup 的 select 根）
  const dimensionSelects = Array.from(document.querySelectorAll('[modelvaluegroup]'))
    .filter((el) => visible(el) && /gmt/i.test(el.getAttribute('modelvaluegroup') || ''))
    .map((el) => ({
      ...brief(el),
      modelvaluegroup: el.getAttribute('modelvaluegroup'),
      html: el.outerHTML.slice(0, 900),
    }));

  return { dimensionNodes, inputs, buttons, skuNodes, dialogs, popups, dropdownCandidates, dimensionSelects, dimensionDropdown };
}
"""


async def _scan_dom(page: Any) -> dict[str, Any]:
    # Playwright 对字符串表达式不会自动调用 → 必须显式加上 ()
    return await page.evaluate(f"({SCAN_SCRIPT})()")


async def _dismiss_dialogs(page: Any, rounds: int = 15) -> list[dict[str, Any]]:
    """关掉挡住点击的「提示」弹窗。

    两手一起上：
    1. 采集自己那套 ``UniversalPopupHandler.close_safe_notices``（同款关闭逻辑）；
    2. 兜底：可见的 MessageBox 关闭按钮
       （真实结构：``div.jx-overlay-dialog > div.jx-message-box >
       button.jx-message-box__headerbtn[aria-label="关闭此对话框"]``，
       Escape 对它无效）。

    ⚠️ 妙手的通知是**异步弹出的**：页面就绪后还会再冒一个出来
    （实测第一个关掉后 ~7 秒又来一个）。所以这里要**持续巡检到安静**，
    关一次就收工会被下一个挡住。

    关之前先把弹窗内容记下来 —— 免得只看到「有弹窗」却不知道弹的是什么。
    """
    recorded: list[dict[str, Any]] = []
    try:
        from modules.apps.collection_center.popup_handler import UniversalPopupHandler

        handler = UniversalPopupHandler()
        closed = await handler.close_safe_notices(page, platform="miaoshou")
        print(f"[probe] popup_handler 关掉 {closed} 个安全通知")
    except Exception as exc:  # noqa: BLE001
        print(f"[probe] popup_handler 关闭失败：{exc}")

    quiet = 0
    for _ in range(rounds):
        entry = await _close_one_dialog(page)
        if entry is not None:
            recorded.append(entry)
            quiet = 0
            continue
        quiet += 1
        if quiet >= 3:
            break
        await page.wait_for_timeout(600)
    print(f"[probe] 共关掉 {len(recorded)} 个提示弹窗")
    return recorded


async def _close_one_dialog(page: Any) -> Optional[dict[str, Any]]:
    """关掉当前**一个**弹窗；没有就返回 None。"""
    try:
        dialog = page.locator('.jx-message-box, [role="dialog"]').first
        if await dialog.count() == 0:
            return None
        entry = {
            "text": ((await dialog.text_content()) or "")[:300],
            "html": (await dialog.inner_html())[:300],
        }
        if not await _click_visible_close(page):
            await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
        return entry
    except Exception as exc:  # noqa: BLE001
        print(f"[probe] 关弹窗失败：{exc}")
        return None


async def _click_visible_close(page: Any) -> bool:
    """点第一个**可见**的关闭按钮（``locator.first`` 常常命中隐藏的那个）。"""
    closers = page.locator(
        "button.jx-message-box__headerbtn, "
        'button[aria-label="关闭此对话框"], '
        ".notice-message-box-dialog .jx-dialog__headerbtn"
    )
    try:
        count = await closers.count()
    except Exception:
        return False
    for index in range(min(count, 6)):
        node = closers.nth(index)
        try:
            if not await node.is_visible():
                continue
            await node.click(timeout=2000)
            return True
        except Exception:
            continue
    return False


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
    if "/login" in url:
        return True
    try:
        return await page.locator("text=立即登录").count() > 0
    except Exception:
        return False


def _component() -> Any:
    """构造组件实例（探针与采集跑同一套定位逻辑）。"""
    from modules.platforms.miaoshou.components.inventory_config import (
        InventorySelectors,
    )
    from modules.platforms.miaoshou.components.inventory_date_filter import (
        MiaoshouInventoryDateFilter,
    )

    return MiaoshouInventoryDateFilter(ctx=None, selectors=InventorySelectors())


# ----------------------------------------------------------------------
# 点击落点取证
# ----------------------------------------------------------------------
async def _describe_node(page: Any, node: Any) -> dict[str, Any]:
    """描述一个候选节点，并算出「点它会点到哪个元素」。"""
    info: dict[str, Any] = {"tag": None, "cls": None, "text": None, "rect": None}
    for key, expr in (
        ("tag", "el => el.tagName"),
        ("cls", "el => (el.className || '').toString().slice(0, 120)"),
    ):
        try:
            info[key] = await node.evaluate(expr)
        except Exception:
            info[key] = None
    try:
        info["text"] = ((await node.text_content()) or "").strip()[:80]
    except Exception:
        info["text"] = None
    try:
        info["rect"] = await node.bounding_box()
    except Exception:
        info["rect"] = None
    info["click_hits"] = await _element_at_center(page, info["rect"])
    return info


async def _element_at_center(page: Any, rect: Any) -> Any:
    """候选中心点上真正会接收点击的元素。"""
    if not rect:
        return None
    cx = float(rect["x"]) + float(rect["width"]) / 2
    cy = float(rect["y"]) + float(rect["height"]) / 2
    script = """
    ([x, y]) => {
      const el = document.elementFromPoint(x, y);
      if (!el) return null;
      return {
        tag: el.tagName,
        cls: (el.className || '').toString().slice(0, 120),
        text: (el.textContent || '').trim().slice(0, 40),
      };
    }
    """
    try:
        return await page.evaluate(script, [cx, cy])
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


async def _diagnose_candidates(page: Any, label: str) -> dict[str, Any]:
    """把 ``get_by_text`` 两种匹配模式下的候选逐个摊开。"""
    out: dict[str, Any] = {"label": label}
    for exact in (True, False):
        key = "exact" if exact else "loose"
        bucket: list[dict[str, Any]] = []
        try:
            locator = page.get_by_text(label, exact=exact)
            count = await locator.count()
        except Exception as exc:  # noqa: BLE001
            out[key] = {"error": str(exc)}
            continue
        for index in range(min(count, 12)):
            node = locator.nth(index)
            try:
                visible = await node.is_visible()
            except Exception:
                visible = False
            entry: dict[str, Any] = {"index": index, "visible": visible}
            if visible:
                entry.update(await _describe_node(page, node))
            bucket.append(entry)
        out[key] = {"total": count, "candidates": bucket}
    return out


# ----------------------------------------------------------------------
# 阶段
# ----------------------------------------------------------------------
async def _open_dimension_dropdown(page: Any) -> bool:
    """点开维度下拉 —— 只读操作（不选、不填）。

    触发器用 ``modelvaluegroup`` 认（实测维度 select 根带
    ``modelvaluegroup="gmtCreate,"``）→ 天然排除表格表头里同名的「创建时间」。
    """
    trigger = page.locator("[modelvaluegroup*='gmt']").first
    try:
        if await trigger.count():
            wrapper = trigger.locator(".jx-select__wrapper").first
            target = wrapper if await wrapper.count() else trigger
            await target.click(timeout=3000)
            await page.wait_for_timeout(900)
            print("[probe] 已点开维度下拉（modelvaluegroup 定位）")
            return True
    except Exception as exc:  # noqa: BLE001
        print(f"[probe] 点维度触发器失败：{exc}")

    for label in DIMENSION_LABELS:
        node = await _visible_by_text(page, label)
        if node is None:
            continue
        try:
            await node.click(timeout=2000)
            await page.wait_for_timeout(800)
            print(f"[probe] 已点开维度下拉（兜底：触发器文案 {label!r}）")
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"[probe] 点触发器 {label!r} 失败：{exc}")
    print("[probe] 没找到可点的维度触发器 —— 这是**取证失败**，不是结论。")
    return False


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
        "[probe] 截图：output/probe_inventory_date_filter.png"
    )


async def _collect_initial(
    page: Any, component: Any
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """初始取证：关弹窗 → 等就绪 → 组件状态 + DOM 扫描。"""
    dialogs = await _safe("关掉提示弹窗", lambda: _dismiss_dialogs(page))
    if dialogs:
        _dump("关掉的提示弹窗内容", dialogs)
    await _safe("等页面就绪", lambda: _wait_page_ready(page))

    before_state = await _safe("组件状态（初始）", lambda: component.probe_state(page))
    _dump("组件 probe_state（初始，未做任何操作）", before_state)
    dom_before = await _safe("DOM 扫描（初始）", lambda: _scan_dom(page))
    _dump("维度文案所在元素", (dom_before or {}).get("dimensionNodes"))
    _dump("页面上的 input", (dom_before or {}).get("inputs"))
    _dump("「确定 / 清空 / 搜索 / 重置」按钮", (dom_before or {}).get("buttons"))
    return before_state or {}, dom_before or {}, dialogs or []


async def _collect_open(
    page: Any, component: Any
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """下拉展开后的取证：DOM 扫描 + 候选点击落点 + 组件状态。"""
    await _open_dimension_dropdown(page)

    dom_after = await _safe("DOM 扫描（下拉展开）", lambda: _scan_dom(page))
    _dump("下拉展开后的维度元素", (dom_after or {}).get("dimensionNodes"))
    _dump(
        "下拉浮层容器（配置里的选择器各命中什么）",
        (dom_after or {}).get("dropdownCandidates"),
    )
    _dump(
        "维度下拉浮层（含创建时间+更新时间）",
        (dom_after or {}).get("dimensionDropdown"),
    )
    _dump(
        "维度 select 根（带 modelvaluegroup）",
        (dom_after or {}).get("dimensionSelects"),
    )

    diag = await _safe(
        "候选点击落点",
        lambda: _diagnose_candidates(page, "更新时间"),
    )
    _dump("「更新时间」候选的点击落点（exact vs loose）", diag)

    after_state = await _safe(
        "组件状态（下拉展开）", lambda: component.probe_state(page)
    )
    _dump("组件 probe_state（下拉展开后）", after_state)
    return after_state or {}, dom_after or {}, diag or {}


async def _probe_page(page: Any, mode: str) -> int:
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

    component = _component()
    before_state, dom_before, dialogs = await _collect_initial(page, component)
    after_state, dom_after, diag = await _collect_open(page, component)

    payload: dict[str, Any] = {
        "url": page.url,
        "mode": mode,
        "dismissed_dialogs": dialogs,
        "component_state_before": before_state,
        "component_state_after_dropdown": after_state,
        "dom_before": dom_before,
        "dom_after_dropdown": dom_after,
        "candidate_click_targets": diag,
    }

    if mode == "verify":
        payload["switch_verification"] = await _verify_switch(component, page)

    await _write_outputs(page, payload)
    return 0


VERIFY_RANGE_START = "2026-10-01 00:00:00"
VERIFY_RANGE_END = "2026-10-25 23:59:59"


async def _verify_switch(component: Any, page: Any) -> dict[str, Any]:
    """**真的**跑一遍采集真正用的入口，验收组件修好没有。

    调的是 ``apply_incremental_range``（切维度 + 填区间 + 断言证据）——
    和采集流程走的是同一条路。
    **仍然不点「搜索」、不点「导出」**，所以不会触发任何导出行为。
    """
    result: dict[str, Any] = {
        "ok": False,
        "error": None,
        "final_dimension": None,
        "applied_range": None,
        "range_start_value": None,
        "range_end_value": None,
    }
    try:
        evidence = await component.apply_incremental_range(
            page, start=VERIFY_RANGE_START, end=VERIFY_RANGE_END
        )
        result["ok"] = True
        result["applied_range"] = evidence.applied_range
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"
    try:
        result["final_dimension"] = await component.read_current_dimension(page)
    except Exception as exc:  # noqa: BLE001
        result["final_dimension"] = f"<读取失败：{exc}>"
    for key, placeholder in (
        ("range_start_value", "开始时间"),
        ("range_end_value", "结束时间"),
    ):
        try:
            node = await component._first_visible_by_placeholder(page, (placeholder,))
            result[key] = await component._read_input_value(node) if node else None
        except Exception:
            result[key] = None
    result["date_panel"] = await _dump_date_panel(page)
    result["search_request_dates"] = await _grab_search_dates(page)
    print(f"[probe] 筛选器整体验收：{result}")
    return result


async def _grab_search_dates(page: Any) -> dict[str, Any]:
    """点「搜索」并抓列表查询请求里的日期参数 —— **最硬的落地证据**。

    妙手的日期条件就是请求里的
    ``gmtCreateStart/End``（维度=创建时间）与 ``gmtModifiedStart/End``（维度=更新时间）。
    """
    captured: list[Any] = []

    def listener(req: Any) -> None:
        if "searchGoodsSkuWarehouseList" in req.url:
            captured.append(req)

    page.on("request", listener)
    try:
        await page.locator("button.J_queryFormSearch").first.click(timeout=10000)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"点搜索失败：{exc}"}
    await page.wait_for_timeout(3500)
    page.remove_listener("request", listener)
    if not captured:
        return {"error": "没抓到列表查询请求"}
    try:
        body = captured[-1].post_data or ""
    except Exception:
        body = ""
    found = dict(
        re.findall(
            r"(gmtModifiedStart|gmtModifiedEnd|gmtCreateStart|gmtCreateEnd)=([^&]*)",
            body,
        )
    )
    return {key: unquote_plus(value) for key, value in found.items()}


PANEL_SCRIPT = """
() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const st = window.getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none';
  };
  const brief = (el) => ({
    tag: el.tagName,
    cls: (el.className || '').toString().slice(0, 200),
    text: (el.textContent || '').trim().slice(0, 30),
    visible: visible(el),
    html: el.outerHTML.slice(0, 300),
  });
  const panels = Array.from(document.querySelectorAll(
    '.jx-picker-panel, [class*="picker-panel"], .jx-date-picker, [class*="date-range"]'
  )).map(brief);
  const buttons = Array.from(document.querySelectorAll('button, a[role="button"]'))
    .filter((el) => {
      const t = (el.textContent || '').trim();
      return visible(el) && ['确定', '清空', '搜索', '重置'].some((k) => t.includes(k));
    })
    .map(brief);
  return { panels, buttons };
}
"""


async def _dump_date_panel(page: Any) -> dict[str, Any]:
    """抓日期选择面板的结构（填完区间后会弹出来，可能挡住「搜索」按钮）。"""
    try:
        return await page.evaluate(f"({PANEL_SCRIPT})()")
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _load_storage_state(session_dir: Path) -> Optional[dict[str, Any]]:
    """取会话文件里的**内层** Playwright storage_state。

    会话文件是外层包装（platform/account_id/storage_state/metadata），
    真正能被 Playwright 吃的是 ``storage_state`` 那一层。
    """
    session_file = session_dir / "storage_state.json"
    if not session_file.exists():
        print(f"[probe] 找不到会话文件：{session_file}")
        return None
    try:
        raw = json.loads(session_file.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"[probe] 读会话文件失败：{exc}")
        return None
    inner = raw.get("storage_state") if isinstance(raw, dict) else None
    payload = inner if isinstance(inner, dict) else raw
    cookies = payload.get("cookies") if isinstance(payload, dict) else None
    count = len(cookies) if isinstance(cookies, list) else 0
    print(f"[probe] 会话文件：{session_file}（内层 cookie 数 = {count}）")
    if count == 0:
        print("[probe] **内层没有 cookie** —— 探针会跳回登录页，这是取证失败不是结论。")
        return None
    return payload


async def _wait_page_ready(page: Any, timeout_ms: int = 20000) -> bool:
    """等筛选栏和结果计数都渲染出来（关弹窗会触发一次重渲染）。"""
    waited = 0
    while waited < timeout_ms:
        try:
            total = page.get_by_text("SKU总数", exact=False).first
            start = page.locator("input[placeholder*='开始时间']").first
            if await total.is_visible(timeout=800) and await start.is_visible(
                timeout=800
            ):
                print(f"[probe] 页面已就绪（等待 {waited}ms）")
                return True
        except Exception:
            pass
        await page.wait_for_timeout(400)
        waited += 400
    print(f"[probe] 页面在 {timeout_ms}ms 内没就绪 —— 取证可能不完整")
    return False


async def probe(session_dir: Path, headed: bool, mode: str) -> int:
    """执行取证。返回进程退出码（0 成功 / 1 登录态失效）。"""
    from playwright.async_api import async_playwright

    storage_state = _load_storage_state(session_dir)
    if storage_state is None:
        return 1

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headed)
        context = await browser.new_context(
            storage_state=storage_state,
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        page = context.pages[0] if context.pages else await context.new_page()
        try:
            return await _probe_page(page, mode)
        finally:
            await context.close()
            await browser.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="妙手库存日期筛选只读取证探针")
    parser.add_argument(
        "--session-dir",
        default=str(DEFAULT_SESSION_DIR),
        help="会话目录（含 storage_state.json）",
    )
    parser.add_argument(
        "--mode",
        default="scan",
        choices=("scan", "verify"),
        help="scan=只读取证；verify=额外真的切一次维度（验收用）",
    )
    parser.add_argument("--headed", action="store_true", help="有头模式（默认无头）")
    args = parser.parse_args(argv)
    return asyncio.run(probe(Path(args.session_dir), args.headed, args.mode))


if __name__ == "__main__":
    sys.exit(main())
