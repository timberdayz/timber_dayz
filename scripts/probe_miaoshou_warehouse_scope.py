"""妙手仓库范围筛选控件的**只读**取证探针。

用途：回答三个至今没有真实页面证据的问题——

1. 仓库筛选字段在 DOM 上有没有稳定的 ``data-field`` 之类的属性（若有，
   定位器可以完全不依赖 class / 文案）；
2. 仓库范围下拉浮层的真实 class 名（现在代码里只有
   ``.jx-select-dropdown`` / ``.jx-select__dropdown`` / ``.jx-popper``
   三个**候选**，来源是归档脚本，不是页面实证）；
3. ``jx-select`` 是否响应键盘（``Enter`` / ``ArrowDown``）——决定
   ``warehouse_filters.py`` 的**层 D 键盘兜底**是否真的有效。

**只读保证**：

- 只 ``load`` 登录态，**从不 save**，登录态文件不会被改动；
- 只做「读 DOM + 点开下拉 + 按一次键盘」的观察，不提交任何业务动作；
- 不执行导出、不触发导出弹窗。

用法::

    python scripts/probe_miaoshou_warehouse_scope.py
    python scripts/probe_miaoshou_warehouse_scope.py --state <storage_state.json>

登录态默认取 ``data/sessions/miaoshou/miaoshou_real_001/storage_state.json``。
登录态失效时脚本会明确提示需要人工登录，不会编造结论。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = REPO_ROOT / "data" / "sessions" / "miaoshou" / "miaoshou_real_001"
CHECKLIST_URL = "https://erp.91miaoshou.com/warehouse/checklist"

# 仓库筛选的候选锚点：文案 / 角色 / class 三路都试，任一命中即可。
FIELD_ANCHORS = [
    ('get_by_label("仓库")', "label"),
    ('get_by_text("仓库")', "text"),
    ('locator(".jx-select")', "select"),
]


def _dump(label: str, payload: Any) -> None:
    print(f"\n=== {label} ===")
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    # 控制台可能是 GBK（Windows 默认），逐字符降级，避免整个探针因编码中断
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(text.encode(encoding, errors="replace").decode(encoding, errors="replace"))


def _first_visible(page: Any) -> Any | None:
    """按 FIELD_ANCHORS 找仓库筛选控件，取第一个可见的。"""
    for description, kind in FIELD_ANCHORS:
        try:
            if kind == "label":
                locator = page.get_by_label("仓库").first
            elif kind == "text":
                locator = page.get_by_text("仓库", exact=False).first
            else:
                locator = page.locator(".jx-select").first
            if locator.count() > 0 and locator.is_visible():
                return locator
        except Exception as exc:  # noqa: BLE001 - 取证脚本，探针失败不算错误
            print(f"[probe] 锚点 {description} 不可用：{exc}")
    return None


def _ancestor_chain(locator: Any, max_depth: int = 6) -> list[dict[str, Any]]:
    """沿祖先链往上取 class / 属性（最多 max_depth 层）。"""
    chain: list[dict[str, Any]] = []
    try:
        chain = locator.evaluate(
            """el => {
                const out = [];
                let node = el;
                for (let i = 0; i < 6 && node; i += 1) {
                    out.push({
                        tag: node.tagName ? node.tagName.toLowerCase() : '',
                        className: node.className && typeof node.className === 'string'
                            ? node.className : '',
                        id: node.id || '',
                        role: node.getAttribute ? (node.getAttribute('role') || '') : '',
                        ariaControls: node.getAttribute
                            ? (node.getAttribute('aria-controls') || '') : '',
                        ariaHaspopup: node.getAttribute
                            ? (node.getAttribute('aria-haspopup') || '') : '',
                        dataField: node.getAttribute
                            ? (node.getAttribute('data-field') || '') : '',
                        dataFields: node.getAttribute
                            ? (node.getAttribute('data-fields') || '') : '',
                        name: node.getAttribute ? (node.getAttribute('name') || '') : '',
                    });
                    node = node.parentElement;
                }
                return out;
            }"""
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[probe] 读取祖先链失败：{exc}")
    return chain[:max_depth]


def _overlay_candidates(page: Any) -> list[dict[str, Any]]:
    """列出页面上所有疑似下拉浮层的元素（class + role）。"""
    try:
        return page.evaluate(
            """() => {
                const out = [];
                document.querySelectorAll('body *').forEach(el => {
                    const cls = typeof el.className === 'string' ? el.className : '';
                    const role = el.getAttribute ? (el.getAttribute('role') || '') : '';
                    const looksLikeDropdown =
                        cls.includes('select-dropdown') ||
                        cls.includes('select__dropdown') ||
                        cls.includes('popper') ||
                        cls.includes('dropdown') ||
                        role === 'listbox' ||
                        role === 'tooltip';
                    if (!looksLikeDropdown) return;
                    const rect = el.getBoundingClientRect();
                    out.push({
                        tag: el.tagName.toLowerCase(),
                        className: cls,
                        role: role,
                        visible: rect.width > 0 && rect.height > 0,
                        childCount: el.children.length,
                    });
                });
                return out;
            }"""
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[probe] 扫描浮层候选失败：{exc}")
        return []


# ── CDP 取证用的 JS 载荷（与 _cdp_dumps 一一对应）──────────────────────

_JS_ANCESTOR_CHAIN = """() => {
    const attrMap = (el) => {
        const out = {};
        for (const a of el.attributes) out[a.name] = a.value;
        return out;
    };
    // 用「仓库」标签文案定位到所属的 jx-select
    let anchor = null;
    const labels = Array.from(document.querySelectorAll('label'));
    for (const lab of labels) {
        if ((lab.textContent || '').replace(/\\s+/g, '').includes('仓库')) {
            let node = lab;
            while (node && node !== document.body) {
                if (node.classList
                    && node.classList.contains('jx-select')) {
                    anchor = node;
                    break;
                }
                node = node.parentElement;
            }
            if (anchor) break;
            // 标签的兄弟节点里找 jx-select
            const sib = lab.parentElement
                ? lab.parentElement.querySelector('.jx-select')
                : null;
            if (sib) { anchor = sib; break; }
        }
    }
    if (!anchor) return { error: '没找到仓库筛选的 jx-select 根节点' };
    const chain = [];
    let node = anchor;
    for (let i = 0; i < 7 && node && node !== document.body; i += 1) {
        chain.push({
            tag: node.tagName.toLowerCase(),
            attrs: attrMap(node),
            text: (node.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 30),
        });
        node = node.parentElement;
    }
    return { chain };
}"""

_JS_SELECT_DETAILS = """() => Array.from(document.querySelectorAll('.jx-select')).map(el => {
    const attrMap = (node) => {
        const out = {};
        for (const a of node.attributes) out[a.name] = a.value;
        return out;
    };
    const input = el.querySelector('.jx-select__input');
    return {
        attrs: attrMap(el),
        inputAttrs: input ? attrMap(input) : null,
        selectedItems: Array.from(
            el.querySelectorAll('.jx-select__selected-item')
        ).map(si => ({
            className: si.className,
            text: (si.textContent || '').trim().slice(0, 40),
        })),
        tagCount: el.querySelectorAll('.jx-tag').length,
        checkboxCount: el.querySelectorAll('.jx-checkbox').length,
        visible: (() => {
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        })(),
    };
})"""

_JS_FIELD_ANCHORS_JS = """() => {
    const out = [];
    document.querySelectorAll('[data-field], [data-name], [name]').forEach(el => {
        const t = (el.textContent || '').replace(/\\s+/g, ' ').trim();
        if (t.includes('仓库') || (el.getAttribute('data-field') || '').includes('arehouse')
            || (el.getAttribute('data-name') || '').includes('arehouse')) {
            out.push({
                tag: el.tagName.toLowerCase(),
                dataField: el.getAttribute('data-field'),
                dataName: el.getAttribute('data-name'),
                name: el.getAttribute('name'),
                className: typeof el.className === 'string' ? el.className : '',
                text: t.slice(0, 30),
            });
        }
    });
    return out;
}"""

_JS_DATA_ATTRS = """() => {
    const out = [];
    document.querySelectorAll('*').forEach(el => {
        for (const a of el.attributes) {
            if (a.name.startsWith('data-') && a.value) {
                out.push({
                    tag: el.tagName.toLowerCase(),
                    attr: a.name,
                    value: a.value.slice(0, 60),
                    text: (el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 24),
                });
                break;
            }
        }
    });
    return out.slice(0, 40);
}"""


def _cdp_pick_page(browser: Any, endpoint: str) -> Any | None:
    """在 CDP 上挑出目标页面（优先 /warehouse/checklist）。"""
    contexts = browser.contexts
    if not contexts:
        print("[probe] CDP 上没有可用 context")
        return None
    pages = [p for ctx in contexts for p in ctx.pages]
    print(f"[probe] CDP {endpoint} 上有 {len(pages)} 个页面")
    for candidate in pages:
        try:
            if "/warehouse/checklist" in candidate.url:
                return candidate
        except Exception:
            continue
    if not pages:
        print("[probe] 没有可用的页面")
        return None
    return pages[0]


def _cdp_dumps(page: Any) -> None:
    """把四组仓库筛选 DOM 事实打到标准输出。"""
    _dump(
        "仓库筛选控件的祖先链（含全部属性）",
        page.evaluate(_JS_ANCESTOR_CHAIN),
    )
    _dump(
        "jx-select 根节点明细（属性 / 选中项 / tag 数）",
        page.evaluate(_JS_SELECT_DETAILS),
    )
    _dump(
        "仓库字段的兄弟/容器结构（找 data-field 之类的稳定锚点）",
        page.evaluate(_JS_FIELD_ANCHORS_JS),
    )
    _dump(
        "所有含 data-* 属性的表单字段（前 40 个）",
        page.evaluate(_JS_DATA_ATTRS),
    )


def _probe_cdp(cdp: str, url: str) -> int:
    """连到**已在运行的**浏览器会话取证（不新建浏览器、不碰登录态）。

    pwcli 的 ``open`` 会把调试端口写进
    ``output/playwright/.pwcli_native/sessions/<session>/session.json``。
    连 CDP 的好处：直接用人工登录好的那个页面，登录态不受 storage_state
    是否可复用的影响。
    """
    from playwright.sync_api import sync_playwright

    endpoint = cdp if "://" in cdp else f"http://127.0.0.1:{cdp}"
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(endpoint)
        try:
            page = _cdp_pick_page(browser, endpoint)
            if page is None:
                return 2
            print(f"[probe] 目标页面 URL：{page.url}")
            if "/warehouse/checklist" not in page.url:
                print(
                    "[probe] 该页面不是仓库清单页，请切到 /warehouse/checklist 后重跑。"
                )
                return 1

            _cdp_dumps(page)
            return 0
        finally:
            browser.close()


def _keyboard_probe(page: Any, field: Any) -> dict[str, Any]:
    """键盘兜底可行性（层 D）：焦点落到控件后按 Enter / ArrowDown。"""
    result: dict[str, Any] = {}
    try:
        field.focus(timeout=3000)
        result["focus_before"] = page.evaluate(
            "() => document.querySelectorAll('.jx-select__input')"
            ".length && document.activeElement ? document.activeElement.tagName : ''"
        )
        page.keyboard.press("Enter")
        page.wait_for_timeout(1000)
        result["after_enter_active_element"] = page.evaluate(
            "() => { const el = document.activeElement;"
            " return el ? { tag: el.tagName, expanded: el.getAttribute"
            "('aria-expanded'), expandedAttr: el.getAttribute('aria-expanded') } : null; }"
        )
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(1000)
        result["overlay_after_enter_and_arrowdown"] = _overlay_candidates(page)
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    return result


def _probe_storage_state(page: Any, url: str) -> int:
    """用 storage_state 打开页面并取证。返回退出码。"""
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(3000)
    print(f"[probe] 当前 URL：{page.url}")
    if "/warehouse/checklist" not in page.url:
        # 没落在目标页：妙手会把未登录的访问重定向到首页并带 redirect 参数
        has_password = page.evaluate(
            "() => !!document.querySelector('input[type=\"password\"]')"
        )
        print(
            "[probe] 未进入仓库清单页"
            f"（密码框存在={has_password}）——登录态已失效，"
            "需要人工重新登录后重跑本探针。"
        )
        _dump("页面可见文本片段", page.inner_text("body")[:2000])
        return 1

    field = _first_visible(page)
    if field is None:
        print("[probe] 没找到仓库筛选控件（可能页面结构与预期不符）。")
        _dump("页面可见文本片段", page.inner_text("body")[:2000])
        return 2

    _dump("仓库筛选控件的祖先链", _ancestor_chain(field))

    # 点开下拉框（只点，不做业务动作）
    try:
        field.click(timeout=3000)
    except Exception as exc:  # noqa: BLE001
        print(f"[probe] 直接点触发器失败（与线上症状一致）：{exc}")
    page.wait_for_timeout(1200)
    _dump("下拉浮层候选（页面全量扫描）", _overlay_candidates(page))
    _dump(
        "aria-expanded 状态",
        page.evaluate(
            "() => Array.from(document.querySelectorAll('.jx-select__input'))"
            ".map(el => ({ id: el.id, expanded: el.getAttribute('aria-expanded'),"
            " controls: el.getAttribute('aria-controls') }))"
        ),
    )

    _dump("键盘兜底可行性（层 D）", _keyboard_probe(page, field))

    page.screenshot(path=str(REPO_ROOT / "output" / "probe_warehouse_scope.png"))
    print("\n[probe] 截图：output/probe_warehouse_scope.png" "（登录态文件未被改动）")
    return 0


def probe(state_path: Path, url: str, headed: bool, cdp: str | None = None) -> int:
    """执行取证。返回进程退出码（0 成功 / 1 登录态失效 / 2 其它异常）。"""
    from playwright.sync_api import sync_playwright

    if cdp:
        return _probe_cdp(cdp, url)

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
            return _probe_storage_state(page, url)
        finally:
            context.close()
            browser.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="妙手仓库范围筛选只读取证探针")
    parser.add_argument("--state", default=str(DEFAULT_STATE), help="登录态目录")
    parser.add_argument("--url", default=CHECKLIST_URL, help="目标页面 URL")
    parser.add_argument("--headed", action="store_true", help="有头模式（默认无头）")
    parser.add_argument(
        "--cdp",
        default=None,
        help="连到已在运行的浏览器调试端口（端口号或 http/ws URL），"
        "用于复用人工已登录的会话",
    )
    args = parser.parse_args(argv)
    return probe(Path(args.state), args.url, args.headed, args.cdp)


if __name__ == "__main__":
    sys.exit(main())
