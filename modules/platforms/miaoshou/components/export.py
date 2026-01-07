from __future__ import annotations

from typing import Any
from pathlib import Path

from modules.components.base import ExecutionContext
from modules.components.export.base import ExportComponent, ExportResult, ExportMode
from modules.platforms.miaoshou.components.warehouse_config import WarehouseSelectors


class MiaoshouExporterComponent(ExportComponent):
    # Component metadata (v4.8.0)
    platform = "miaoshou"
    component_type = "export"
    data_domain = None  # Dynamically inferred

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    def _first_click(self, page: Any, selectors: list[str], *, timeout: int = 5000) -> bool:
        """Try multiple resilient click strategies for a list of selectors.

        - scroll into view then click
        - try get_by_role fallback with accessible name
        - try JS click() as last resort
        """
        # Quick ESC to dismiss transient overlays
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                # scroll + visibility best-effort
                try:
                    loc.scroll_into_view_if_needed(timeout=1200)
                except Exception:
                    pass
                try:
                    loc.click(timeout=timeout)
                    return True
                except Exception:
                    pass
                # Fallback: role-based by text
                try:
                    btn = page.get_by_role("button", name=sel.split("has-text(")[-1].rstrip(")"))
                    if btn and btn.first.count() >= 0:
                        try:
                            btn.first.scroll_into_view_if_needed(timeout=800)
                        except Exception:
                            pass
                        btn.first.click(timeout=timeout)
                        return True
                except Exception:
                    pass
                # JS fallback
                try:
                    handle = loc.element_handle(timeout=800)
                    if handle:
                        page.evaluate("el => el.click()", handle)
                        return True
                except Exception:
                    pass
            except Exception:
                continue
        return False

    def _infer_data_type(self, url: str, fallback: str | None) -> str:
        if fallback:
            return fallback
        u = (url or "").lower()
        # v4.10.0更新：warehouse页面返回inventory（库存快照），而非warehouse
        if "warehouse" in u:
            return "inventory"
        if "product" in u or "goods" in u:
            return "products"
        if "traffic" in u or "overview" in u or "analytics" in u:
            return "traffic"
        # 订单页在妙手为 stat/profit_statistics/detail?platform=*
        if "profit_statistics" in u or "/stat/" in u or "order" in u:
            return "orders"
        if "service" in u or "cs" in u or "chat" in u:
            return "services"
        if "finance" in u or "settlement" in u:
            return "finance"
        return "unknown"

    def _close_popups(self, page: Any) -> None:
        """统一的“观察-关闭弹窗”守护：从配置读取选择器与轮询策略，遍历顶层与所有 frame，并包含 ESC 兜底。"""
        try:
            if self.logger:
                try:
                    self.logger.info("[MiaoshouExporter] [SCAN] Check and close possible notification popups...")
                except Exception:
                    pass
            # 从配置读取关闭选择器与轮询策略（优先 Warehouse，其次 Products 合并）
            from modules.platforms.miaoshou.components.products_config import ProductsSelectors as _PS
            ws = WarehouseSelectors()
            try:
                ps = _PS()
            except Exception:
                ps = None
            sels = set(getattr(ws, "popup_close_buttons", []))
            if ps:
                sels.update(getattr(ps, "popup_close_buttons", []))
            rounds = int(getattr(ws, "close_poll_max_rounds", 20))
            interval = int(getattr(ws, "close_poll_interval_ms", 300))
            # ESC 兜底
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            sels = list(sels)
            for _ in range(rounds):
                closed = False
                for s in sels:
                    try:
                        el = page.locator(s).first
                        if el.count() > 0 and el.is_visible():
                            el.click(timeout=800)
                            closed = True
                    except Exception:
                        pass
                try:
                    for fr in page.frames:
                        for s in sels:
                            try:
                                el2 = fr.locator(s).first
                                if el2.count() > 0 and el2.is_visible():
                                    el2.click(timeout=800)
                                    closed = True
                            except Exception:
                                pass
                except Exception:
                    pass
                try:
                    page.wait_for_timeout(interval)
                except Exception:
                    pass
            return
        except Exception:
            # 忽略弹窗处理异常
            pass

    def _wait_download_with_progress(self, page: Any, texts: list[str], *, total_ms: int = 900000, interval_ms: int = 3000):
        """Wait for a browser download, logging lightweight progress hints.

        Improvements:
        - Listen on page.context first (covers footer-triggered downloads better)
        - Reduce progress log frequency to ~8s to avoid noise
        - EARLY EXIT: if we've seen progress text and then it disappears for >8s, stop waiting so caller can scan the Downloads dir immediately
        - Also exit immediately if a global tap listener (context._aug_latest_download) already captured a download
        """
        waited = 0
        ctx = None
        try:
            ctx = page.context
        except Exception:
            ctx = None
        # Optional tap container attached by caller
        try:
            tap = getattr(ctx, "_aug_latest_download", None)
        except Exception:
            tap = None
        last_log_ms = -999999
        log_every_ms = 8000
        ever_seen = False
        last_seen_ms = -999999
        while waited < total_ms:
            # Early exit if a download has already been captured by the shared tap
            try:
                if tap and isinstance(tap, dict) and tap.get("dl") is not None:
                    return tap.get("dl")
            except Exception:
                pass
            # Prefer context-level download event
            try:
                if ctx is not None:
                    return ctx.wait_for_event("download", timeout=interval_ms)
            except Exception:
                pass
            # Fallback to page-level
            try:
                return page.wait_for_event("download", timeout=200)
            except Exception:
                pass
            # Lightweight progress logging, throttled
            visible_any = False
            if waited - last_log_ms >= log_every_ms:
                for t in texts or []:
                    try:
                        el = page.get_by_text(t, exact=False).first
                        if el and el.is_visible():
                            visible_any = True
                            ever_seen = True
                            last_seen_ms = waited
                            try:
                                print(f"[MiaoshouExporter] 进度: 检测到‘{t}’…")
                            except Exception:
                                pass
                            if self.logger:
                                try:
                                    self.logger.info(f"[MiaoshouExporter] progress: {t}")
                                except Exception:
                                    pass
                            last_log_ms = waited
                            break
                    except Exception:
                        pass
            # If progress was seen before and now disappeared for >8s, exit early to let caller scan files
            if ever_seen and (waited - last_seen_ms) >= 8000:
                raise RuntimeError("progress disappeared; trigger scan")
            try:
                page.wait_for_timeout(min(interval_ms, 3000))
            except Exception:
                pass
            waited += interval_ms
        raise TimeoutError("Timeout waiting for download")
    def _scan_latest_download(
        self,
        since_ts: float | None = None,
        *,
        max_age_sec: int = 600,
        suffixes: tuple[str, ...] | None = (".xlsx", ".xls", ".csv"),
    ) -> Path | None:
        """Scan likely download directories (including configured/custom) for the most recent file.

        Improvements over the generic version:
        - Include ctx.config.downloads_path when provided
        - Include project ./downloads and its immediate subfolders (e.g., ./downloads/miaoshou)
        - Include ./test_downloads for developer runs
        - Accept suffixes=None to allow partially-downloaded files (e.g., *.crdownload) when caller opts in
        """
        try:
            import time
            now = time.time()

            # 1) Build candidate roots
            candidates: list[Path] = []
            home = Path.home()
            candidates += [home / "Downloads", home / "下载"]
            # project-level downloads roots
            proj_downloads = Path.cwd() / "downloads"
            candidates.append(proj_downloads)
            # include platform-namespaced subdir if exists
            try:
                plat = str(getattr(self.ctx, "platform", "")).lower() or "miaoshou"
            except Exception:
                plat = "miaoshou"
            candidates.append(proj_downloads / plat)

            # persistent profile default Downloads (when using launch_persistent_context without explicit downloads_path)
            try:
                account = (self.ctx.account or {})
                ids: list[str] = []
                for k in ("store_name", "username", "account_id", "label"):
                    v = account.get(k)
                    if v:
                        s = str(v)
                        if s not in ids:
                            ids.append(s)
                if not ids:
                    ids = ["account"]
                for acct_id in ids:
                    prof = Path("profiles") / plat / acct_id
                    candidates.append(prof / "Default" / "Downloads")
                    candidates.append(prof / "Downloads")
            except Exception:
                pass

            # developer test downloads
            candidates.append(Path.cwd() / "test_downloads")
            candidates.append(Path.cwd() / "test_downloads" / plat)
            # explicit configured downloads_path from ctx.config
            try:
                cfg_path = (self.ctx.config or {}).get("downloads_path")
                if cfg_path:
                    candidates.append(Path(str(cfg_path)))
            except Exception:
                pass

            latest: Path | None = None
            latest_mtime = -1.0

            def iter_files(root: Path):
                """Yield files within root (non-recursive), and for known aggregate roots also check one level deeper."""
                try:
                    if not root.exists():
                        return
                    # For aggregate roots (./downloads, ./test_downloads), also check one level deeper
                    aggregate = False
                    try:
                        aggregate = root.samefile(proj_downloads) or root.samefile(Path.cwd() / "test_downloads")
                    except Exception:
                        pass
                    # current level
                    if suffixes is None:
                        for f in root.glob("*"):
                            if f.is_file():
                                yield f
                    else:
                        for suf in suffixes:
                            for f in root.glob(f"*{suf}"):
                                if f.is_file():
                                    yield f
                    # one level deeper for aggregate roots
                    if aggregate:
                        try:
                            for sub in root.iterdir():
                                if not sub.is_dir():
                                    continue
                                if suffixes is None:
                                    for f in sub.glob("*"):
                                        if f.is_file():
                                            yield f
                                else:
                                    for suf in suffixes:
                                        for f in sub.glob(f"*{suf}"):
                                            if f.is_file():
                                                yield f
                        except Exception:
                            pass
                except Exception:
                    return

            for d in candidates:
                try:
                    for f in iter_files(d):
                        try:
                            m = f.stat().st_mtime
                        except Exception:
                            continue
                        if max_age_sec is not None and (now - m) > max_age_sec:
                            continue
                        if since_ts is not None and m + 1 < since_ts:
                            # +1s tolerance for clock skew
                            continue
                        if m > latest_mtime:
                            latest = f
                            latest_mtime = m
                except Exception:
                    continue

            return latest
        except Exception:
            return None


    def _ensure_order_status_all(self, page: Any) -> None:
        """Ensure '订单状态' filter has all options checked.
        Strategy:
        1) Open the dropdown of data-field=appOrderStatus
        2) Click '全选' if available
        3) Iterate over visible checkbox items; click those not having 'is-checked'
        4) Close dropdown (ESC)
        """
        try:
            root = page.locator("[data-field='appOrderStatus']").first
            if not root or root.count() < 0:
                return
            # 步骤2: 打开‘订单状态’下拉
            try:
                print("[MiaoshouExporter] 步骤2: 打开‘订单状态’下拉…")
            except Exception:
                pass
            try:
                root.locator(".jx-select__wrapper").first.click(timeout=1500)
            except Exception:
                try:
                    root.click(timeout=1500)
                except Exception:
                    pass
            try:
                page.wait_for_timeout(150)
            except Exception:
                pass
            try:
                print("[MiaoshouExporter] 已打开‘订单状态’，准备点击‘全选’…")
            except Exception:
                pass
            # Repeatedly click the header '全选' until is-checked appears
            try:
                # find dropdown scope and header row
                scopes = [
                    page.locator(".jx-select-dropdown").last,
                    page.locator(".jx-select__dropdown").last,
                    page.locator(".jx-popper").last,
                    page,
                ]
                header = None
                inpt = None
                toggler = None
                for sc in scopes:
                    try:
                        header = sc.locator(".jx-select-dropdown__header .jx-checkbox").first
                        if header and header.count() >= 1:
                            inpt = header.locator(".jx-checkbox__input").first
                            toggler = header.locator(".jx-checkbox__inner").first
                            break
                    except Exception:
                        continue
                # 兜底：通过“全选”文本反推父级 label
                if (not header) or (header.count() < 1):
                    for sc in scopes:
                        try:
                            el = sc.get_by_text("全选", exact=False).first
                            if el and el.count() >= 1:
                                # 取 label 根并获取 input/inner
                                label = el.locator("..").locator("label.jx-checkbox").first
                                if label and label.count() >= 1:
                                    header = label
                                    inpt = label.locator(".jx-checkbox__input").first
                                    toggler = label.locator(".jx-checkbox__inner").first
                                    break
                        except Exception:
                            continue
                # 最终兜底：通过角色定位复选框
                if (not header) or (header.count() < 1):
                    for sc in scopes:
                        try:
                            cb = sc.get_by_role("checkbox", name="全选").first
                            if cb and cb.count() >= 1:
                                header = cb
                                inpt = cb
                                toggler = cb
                                break
                        except Exception:
                            continue
                # 多次尝试点击，直到 .is-checked 出现
                for i in range(6):
                    try:
                        cls = (inpt.get_attribute("class") or "") if inpt else ""
                    except Exception:
                        cls = ""
                    if "is-checked" in cls:
                        try:
                            print("[MiaoshouExporter] 已确认‘全选’为选中状态")
                        except Exception:
                            pass
                        break
                    try:
                        # 优先点击专用 inner；退化为点击文本或 checkbox 本体
                        if toggler and toggler.count() >= 1:
                            toggler.click(timeout=1200)
                        elif header and header.count() >= 1:
                            header.click(timeout=1200)
                        else:
                            page.get_by_text("全选", exact=False).first.click(timeout=1200)
                        page.wait_for_timeout(100)
                        print(f"[MiaoshouExporter] 正在尝试勾选‘全选’，第{i+1}次…")
                    except Exception:
                        try:
                            page.get_by_text("全选", exact=False).first.click(timeout=1200)
                            page.wait_for_timeout(100)
                        except Exception:
                            pass
            except Exception:
                pass
            # ensure every checkbox is checked (skip the '全选' row itself)
            # Build dropdown scope (newer class: .jx-select-dropdown)
            dropdown = None
            for sel in [".jx-select-dropdown", ".jx-select__dropdown", ".jx-popper"]:
                try:
                    cand = page.locator(sel).last
                    if cand and cand.count() >= 0:
                        dropdown = cand
                        break
                except Exception:
                    continue
            scope = dropdown if dropdown else page
            try:
                items = scope.locator("label.jx-checkbox").all()  # type: ignore[attr-defined]
            except Exception:
                items = []
            for i in range(0, len(items)):
                try:
                    el = items[i]
                    # skip the '全选' option
                    try:
                        if "全选" in (el.inner_text() or ""):
                            continue
                    except Exception:
                        pass
                    # check wrapper or child input class
                    wcls = (el.get_attribute("class") or "")
                    is_checked = "is-checked" in wcls
                    if not is_checked:
                        try:
                            inp = el.locator(".jx-checkbox__input").first
                            icls = (inp.get_attribute("class") or "")
                            is_checked = "is-checked" in icls
                        except Exception:
                            is_checked = False
                    if not is_checked:
                        el.locator(".jx-checkbox__inner").first.click(timeout=1000)
                        try:
                            page.wait_for_timeout(60)
                        except Exception:
                            pass
                except Exception:
                    continue
            # Debug: count checked items
            try:
                checked = scope.locator(".jx-checkbox__input.is-checked").count()
                if checked == 0:
                    checked = scope.locator("label.jx-checkbox.is-checked, .jx-checkbox.is-checked").count()
                try:
                    print(f"[MiaoshouExporter] 订单状态勾选数: {checked}")
                except Exception:
                    pass
            except Exception:
                pass
            # Close dropdown
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            try:
                page.wait_for_timeout(120)
            except Exception:
                pass
        except Exception:
            pass

    def _trigger_search(self, page: Any) -> None:
        """Click '搜索' to apply filters if present."""
        try:
            # Prefer class hook used by Miaoshou page
            btn = page.locator("button.J_queryFormSearch").first
            if btn and btn.count() >= 0:
                btn.click(timeout=1500)
                return
        except Exception:
            pass
        try:
            page.get_by_role('button', name='搜索').first.click(timeout=2000)
        except Exception:
            pass

    def _get_range_values(self, page: Any) -> tuple[str | None, str | None]:
        try:
            inputs = page.locator(".jx-date-editor--datetimerange input.jx-range-input")
            if inputs.count() < 2:
                inputs = page.locator("input.jx-range-input")
            if inputs.count() < 2:
                return (None, None)
            s = inputs.nth(0).input_value(timeout=800)
            e = inputs.nth(1).input_value(timeout=800)
            return (s, e)
        except Exception:
            return (None, None)

    def _ensure_date_range_from_config(self, page: Any) -> None:
        """If ctx.config has start_date/end_date, type them into the range inputs.
        Only type when current inputs differ, to avoid重复设置时间。
        """
        try:
            cfg = self.ctx.config or {}
            s = str(cfg.get("start_date") or "").strip()
            e = str(cfg.get("end_date") or "").strip()
            if not (s and e):
                return
            cur_s, cur_e = self._get_range_values(page)
            if cur_s == s and cur_e == e:
                try:
                    print("[MiaoshouExporter] 检测到时间区间已正确，跳过重复设置")
                except Exception:
                    pass
                return
            inputs = page.locator(".jx-date-editor--datetimerange input.jx-range-input")
            if inputs.count() < 2:
                inputs = page.locator("input.jx-range-input")
            if inputs.count() < 2:
                return
            # start
            st = inputs.nth(0)
            st.click(timeout=1500)
            try: st.press("Control+A")
            except Exception: pass
            st.fill(s, timeout=1500)
            try: st.press("Enter")
            except Exception: pass
            try: page.wait_for_timeout(100)
            except Exception: pass
            # end
            ed = inputs.nth(1)
            ed.click(timeout=1500)
            try: ed.press("Control+A")
            except Exception: pass
            ed.fill(e, timeout=1500)
            try: ed.press("Enter")
            except Exception: pass
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
        except Exception:
            pass

    def _export_via_dropdown(self, page: Any) -> Any | None:
        """Open '导出数据' dropdown and click '导出全部订单'. Return Download or None.
        Handles both hover-to-open and click-to-open behaviors.
        """
        try:
            # Try hover first — find the real '导出数据' button via multiple selectors
            candidates = [
                page.get_by_role('button', name='导出数据').first,
                page.locator("button:has-text(导出数据)").first,
                page.locator(".jx-button:has-text(导出数据)").first,
                page.locator(".pro-button:has-text(导出数据)").first,
                page.locator("button.jx-button--primary:has-text(导出数据)").first,
            ]
            btn = None
            for c in candidates:
                try:
                    if c and c.count() >= 1:
                        btn = c
                        break
                except Exception:
                    continue
            if not btn:
                return None
            try:
                btn.hover(timeout=1200)
                try:
                    print("[MiaoshouExporter] 已悬停‘导出数据’，等待下拉菜单…")
                except Exception:
                    pass
            except Exception:
                pass
            # Use aria-expanded/aria-controls to detect menu open state and scope
            try:
                ctrl_id = (btn.get_attribute("aria-controls") or "").strip()
            except Exception:
                ctrl_id = ""
            expanded = None
            try:
                expanded = (btn.get_attribute("aria-expanded") or "").strip().lower()
            except Exception:
                expanded = None
            # Ensure dropdown is opened
            for _ in range(3):
                if expanded == "true":
                    break
                try:
                    btn.hover(timeout=800)
                except Exception:
                    pass
                try:
                    btn.click(timeout=1500)
                except Exception:
                    pass
                try:
                    page.wait_for_timeout(120)
                except Exception:
                    pass
                try:
                    expanded = (btn.get_attribute("aria-expanded") or "").strip().lower()
                except Exception:
                    expanded = None
            # Build scopes, prioritizing aria-controls target if present
            try:
                scopes = []
                if ctrl_id:
                    scopes.append(page.locator(f"#{ctrl_id}").first)
                    scopes.append(page.locator(f"[id='{ctrl_id}']").first)
                scopes.extend([
                    page.locator("[role='menu']").last,
                    page.locator(".jx-popper").last,
                    page.locator(".el-popper").last,
                    page.locator(".jx-select-dropdown").last,
                    page.locator(".jx-select__dropdown").last,
                    page.locator("body"),
                ])
                # Try clicking the target menu item
                for sc in scopes:
                    try:
                        # 1) 精确类名命中（你提供的 DOM）：li.J_purchaseBillExportAllOrderBill.jx-dropdown-menu__item[role='menuitem']
                        try:
                            item_by_class = sc.locator("li.J_purchaseBillExportAllOrderBill.jx-dropdown-menu__item[role='menuitem'][aria-disabled='false']").first
                            if item_by_class and item_by_class.count() >= 1:
                                try:
                                    print("[MiaoshouExporter] 点击目标（class=J_purchaseBillExportAllOrderBill）…")
                                except Exception:
                                    pass
                                # 保持菜单容器处于 hover，防止项被收起
                                try:
                                    sc.hover(timeout=800)
                                except Exception:
                                    pass
                                try:
                                   item_by_class.scroll_into_view_if_needed(timeout=1200)
                                except Exception:
                                   pass
                                try:
                                   item_by_class.hover(timeout=1200)
                                except Exception:
                                   pass
                                try:
                                   item_by_class.wait_for(state="visible", timeout=2000)
                                except Exception:
                                   pass
                                try:
                                   item_by_class.focus()
                                except Exception:
                                   pass
                                # Early monitor to avoid missing instant downloads
                                try:
                                    with page.context.expect_download(timeout=12000) as dl_early:
                                        item_by_class.click(timeout=2500, force=True)
                                    return dl_early.value
                                except Exception:
                                    pass
                                # 多策略点击（用于弹出确认框的场景）
                                tried = False
                                try:
                                    item_by_class.click(timeout=2500, force=True)
                                    tried = True
                                except Exception:
                                    pass
                                if not tried:
                                    try:
                                        item_by_class.focus(); page.keyboard.press("Enter")
                                        tried = True
                                    except Exception:
                                        pass
                                if not tried:
                                    try:
                                        item_by_class.dispatch_event("click")
                                        tried = True
                                    except Exception:
                                        pass
                                if not tried:
                                    try:
                                        page.evaluate("el => el.click()", item_by_class)
                                        tried = True
                                    except Exception:
                                        pass
                                if not tried:
                                    try:
                                        box = item_by_class.bounding_box()
                                        if box:
                                            page.mouse.move(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                                            page.mouse.down(); page.mouse.up()
                                            tried = True
                                    except Exception:
                                        pass
                                # Try dialog confirm ('导出'/'确定'/'开始导出') immediately after selecting menu item
                                try:
                                    footer = page.locator('.jx-dialog__footer').last
                                    if footer and footer.count() >= 1:
                                        for _name in ['导出', '确定', '开始导出']:
                                            try:
                                                with page.context.expect_download(timeout=120000) as dl2:
                                                    footer.get_by_role('button', name=_name).first.click(timeout=1800)
                                                return dl2.value
                                            except Exception:
                                                continue
                                except Exception:
                                    pass
                                # Or direct download without dialog (short wait)
                                try:
                                    return page.context.wait_for_event('download', timeout=5000)
                                except Exception:
                                    pass
                                return None
                        except Exception:
                            pass
                        # 2) 语义命中：role=menuitem + name
                        try:
                            item_by_role = sc.get_by_role('menuitem', name='导出全部订单').first
                            if item_by_role and item_by_role.count() >= 1:
                                try:
                                    print("[MiaoshouExporter] 点击目标（role=menuitem, name=导出全部订单）…")
                                except Exception:
                                    pass
                                #  hover 
                                try:
                                    sc.hover(timeout=800)
                                except Exception:
                                    pass
                                try:
                                    item_by_role.scroll_into_view_if_needed(timeout=1200)
                                except Exception:
                                    pass
                                try:
                                    item_by_role.hover(timeout=1200)
                                except Exception:
                                    pass
                                try:
                                    item_by_role.wait_for(state='visible', timeout=2000)
                                except Exception:
                                    pass
                                try:
                                    item_by_role.focus()
                                except Exception:
                                    pass
                                # Early monitor to avoid missing instant downloads
                                try:
                                    with page.context.expect_download(timeout=12000) as dl_early:
                                        item_by_role.click(timeout=2500, force=True)
                                    return dl_early.value
                                except Exception:
                                    pass
                                tried = False
                                try:
                                    item_by_role.click(timeout=2500, force=True)
                                    tried = True
                                except Exception:
                                    pass
                                if not tried:
                                    try:
                                        item_by_role.focus(); page.keyboard.press("Enter")
                                        tried = True
                                    except Exception:
                                        pass
                                if not tried:
                                    try:
                                        item_by_role.dispatch_event("click")
                                        tried = True
                                    except Exception:
                                        pass
                                if not tried:
                                    try:
                                        page.evaluate("el => el.click()", item_by_role)
                                        tried = True
                                    except Exception:
                                        pass
                                if not tried:
                                    try:
                                        box = item_by_role.bounding_box()
                                        if box:
                                            page.mouse.move(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                                            page.mouse.down(); page.mouse.up()
                                            tried = True
                                    except Exception:
                                        pass
                                # Try dialog confirm ('导出'/'确定'/'开始导出') immediately after selecting menu item
                                try:
                                    footer = page.locator('.jx-dialog__footer').last
                                    if footer and footer.count() >= 1:
                                        for btn_name in ['导出', '确定', '开始导出']:
                                            try:
                                                with page.context.expect_download(timeout=120000) as dl2:
                                                    footer.get_by_role('button', name=btn_name).first.click(timeout=1800)
                                                return dl2.value
                                            except Exception:
                                                continue
                                except Exception:
                                    pass
                                # Fallback: short wait for direct download
                                try:
                                    return page.context.wait_for_event('download', timeout=5000)
                                except Exception:
                                    pass
                                return None
                        except Exception:
                            pass
                        # 3) 文本命中（包含匹配）：导出全部订单/导出全部数据/导出全部
                        for text in ["导出全部订单", "导出全部数据", "导出全部"]:
                            try:
                                dd_item = sc.get_by_text(text, exact=False).first
                                if dd_item and dd_item.is_visible():
                                    try:
                                        print("[MiaoshouExporter] 点击‘导出全部订单/数据’…")
                                    except Exception:
                                        pass
                                    try:
                                        sc.hover(timeout=800)
                                    except Exception:
                                        pass
                                    try:
                                        dd_item.scroll_into_view_if_needed(timeout=1200)
                                    except Exception:
                                        pass
                                    try:
                                        dd_item.hover(timeout=1200)
                                    except Exception:
                                        pass
                                    try:
                                        dd_item.wait_for(state="visible", timeout=2000)
                                    except Exception:
                                        pass
                                    try:
                                        dd_item.focus()
                                    except Exception:
                                        pass
                                    # Early monitor to catch immediate download
                                    try:
                                        with page.context.expect_download(timeout=12000) as dl_early:
                                            dd_item.click(timeout=2500, force=True)
                                        return dl_early.value
                                    except Exception:
                                        pass
                                    tried = False
                                    try:
                                        dd_item.click(timeout=2500, force=True)
                                        tried = True
                                    except Exception:
                                        pass
                                    if not tried:
                                        try:
                                            dd_item.focus(); page.keyboard.press("Enter")
                                            tried = True
                                        except Exception:
                                            pass
                                    if not tried:
                                        try:
                                            dd_item.dispatch_event("click")
                                            tried = True
                                        except Exception:
                                            pass
                                    if not tried:
                                        try:
                                            page.evaluate("el => el.click()", dd_item)
                                            tried = True
                                        except Exception:
                                            pass
                                    if not tried:
                                        try:
                                            box = dd_item.bounding_box()
                                            if box:
                                                page.mouse.move(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                                                page.mouse.down(); page.mouse.up()
                                                tried = True
                                        except Exception:
                                            pass
                                    # Confirm dialog if presented
                                    try:
                                        footer = page.locator('.jx-dialog__footer').last
                                        if footer and footer.count() >= 1:
                                            for btn_name in ['导出', '确定', '开始导出']:
                                                try:
                                                    with page.context.expect_download(timeout=120000) as dl2:
                                                        footer.get_by_role('button', name=btn_name).first.click(timeout=1800)
                                                    return dl2.value
                                                except Exception:
                                                    continue
                                    except Exception:
                                        pass
                                    # Or direct download without dialog (short wait)
                                    try:
                                        return page.context.wait_for_event('download', timeout=5000)
                                    except Exception:
                                        pass
                                    return None
                            except Exception:
                                continue
                    except Exception:
                        continue
            except Exception:
                pass
            # Keyboard navigation fallback: focus menu UL then ArrowDown→ArrowDown→Enter
            try:
                menu = None
                try:
                    if ctrl_id:
                        menu = page.locator(f"ul#" + ctrl_id).first
                        if (not menu) or menu.count() < 1:
                            menu = page.locator(f"[id='{ctrl_id}']").first
                except Exception:
                    menu = None
                if (not menu) or menu.count() < 1:
                    menu = page.locator("ul.jx-dropdown-menu[role='menu']").last
                if menu and menu.count() >= 1:
                    try:
                        menu.scroll_into_view_if_needed(timeout=800)
                    except Exception:
                        pass
                    try:
                        menu.hover(timeout=800)
                    except Exception:
                        pass
                    try:
                        menu.focus()
                    except Exception:
                        try:
                            page.evaluate("el => el.focus()", menu)
                        except Exception:
                            pass
                    try:
                        page.keyboard.press("ArrowDown")
                        page.keyboard.press("ArrowDown")
                        page.keyboard.press("Enter")
                    except Exception:
                        pass
                    try:
                        dl_kb = page.wait_for_event("download", timeout=8000)
                        return dl_kb
                    except Exception:
                        pass
            except Exception:
                pass
            # Fallback: click to open then click the item
            with page.context.expect_download(timeout=60000) as dl_info2:
                try:
                    btn.click(timeout=1500)
                    try:
                        print("[MiaoshouExporter] 已点击‘导出数据’，展开下拉…")
                    except Exception:
                        pass
                except Exception:
                    pass
                try:
                    page.wait_for_timeout(150)
                except Exception:
                    pass
                # Try by text in visible menus/scopes
                clicked = False
                scope_list = []
                if 'ctrl_id' in locals() and ctrl_id:
                    scope_list.extend([page.locator(f"#{ctrl_id}").first, page.locator(f"[id='{ctrl_id}']").first])
                scope_list.extend([
                    page.locator("[role='menu']").last,
                    page.locator(".jx-popper").last,
                    page.locator(".el-popper").last,
                    page.locator(".jx-select-dropdown").last,
                    page.locator(".jx-select__dropdown").last,
                    page,
                ])
                for sc in scope_list:
                    try:
                        # 优先按 class 精确命中（你提供的 DOM）
                        item_by_class = sc.locator("li.J_purchaseBillExportAllOrderBill.jx-dropdown-menu__item[role='menuitem'][aria-disabled='false']").first
                        if item_by_class and item_by_class.count() >= 1:
                            try: item_by_class.scroll_into_view_if_needed(timeout=1200)
                            except Exception: pass
                            try: item_by_class.hover(timeout=1200)
                            except Exception: pass
                            try: item_by_class.wait_for(state="visible", timeout=2000)
                            except Exception: pass
                            tried=False
                            try:
                                item_by_class.click(timeout=2500, force=True)
                                tried=True
                            except Exception:
                                pass
                            if not tried:
                                try:
                                    item_by_class.dispatch_event("click")
                                    tried=True
                                except Exception:
                                    pass
                            if not tried:
                                try:
                                    page.evaluate("el => el.click()", item_by_class)
                                    tried=True
                                except Exception:
                                    pass
                            if not tried:
                                try:
                                    box=item_by_class.bounding_box()
                                    if box:
                                        page.mouse.move(box["x"]+box["width"]/2, box["y"]+box["height"]/2)
                                        page.mouse.down(); page.mouse.up()
                                        tried=True
                                except Exception:
                                    pass
                            clicked = True
                            break
                        # 文本匹配兜底
                        item = sc.get_by_text("导出全部订单", exact=False).first
                        try:
                            item.scroll_into_view_if_needed(timeout=1200)
                        except Exception:
                            pass
                        try:
                            item.hover(timeout=1200)
                        except Exception:
                            pass
                        try:
                            item.wait_for(state="visible", timeout=2000)
                        except Exception:
                            pass
                        tried=False
                        try:
                            item.click(timeout=2500, force=True)
                            tried=True
                        except Exception:
                            pass
                        if not tried:
                            try:
                                item.dispatch_event("click")
                                tried=True
                            except Exception:
                                pass
                        if not tried:
                            try:
                                page.evaluate("el => el.click()", item)
                                tried=True
                            except Exception:
                                pass
                        if not tried:
                            try:
                                box=item.bounding_box()
                                if box:
                                    page.mouse.move(box["x"]+box["width"]/2, box["y"]+box["height"]/2)
                                    page.mouse.down(); page.mouse.up()
                                    tried=True
                            except Exception:
                                pass
                        clicked = True
                        break
                    except Exception:
                        try:
                            item2 = sc.get_by_text("导出全部", exact=False).first
                            try:
                                item2.scroll_into_view_if_needed(timeout=1200)
                            except Exception:
                                pass
                            try:
                                item2.wait_for(state="visible", timeout=2000)
                            except Exception:
                                pass
                            item2.click(timeout=2500, force=True)
                            clicked = True
                            break
                        except Exception:
                            continue
                if not clicked:
                    # Ultimate fallback: click the 2nd item in dropdown-like lists
                    for sc in [page.locator(".jx-popper").last, page.locator(".el-popper").last, page]:
                        try:
                            items = sc.locator("li, .jx-dropdown-item, .menu-item, .arco-dropdown-item").all()
                            if len(items) >= 2:
                                items[1].click(timeout=2500)
                                clicked = True
                                break
                        except Exception:
                            continue
            return dl_info2.value
        except Exception:
            return None



    def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        try:
            selectors = WarehouseSelectors()
            current_url = str(getattr(page, "url", ""))
            is_warehouse = "warehouse/checklist" in current_url

            # 预防性关闭可能的公告/通知弹窗
            # 网络层候选下载链接收集（用于最终兜底：HAR-like轻量抓取）
            net_candidates: list[str] = []
            def _on_response(res):
                try:
                    url = getattr(res, 'url', lambda: '')() if callable(getattr(res, 'url', None)) else getattr(res, 'url', '')
                    headers = getattr(res, 'headers', {}) or {}
                    status = int(getattr(res, 'status', 0) or 0)
                    ct = (headers.get('content-type', '') or '').lower()
                    cd = (headers.get('content-disposition', '') or '').lower()
                    if status == 200 and (
                        ('export' in url.lower()) or ('download' in url.lower()) or
                        ('excel' in ct) or ('application/vnd' in ct) or ('octet-stream' in ct) or ('attachment' in cd)
                    ):
                        net_candidates.append(url)
                except Exception:
                    pass
            try:
                page.on('response', _on_response)
            except Exception:
                pass

            # 步骤1: 观察并关闭通知弹窗
            try:
                print("[MiaoshouExporter] 步骤1: 观察并关闭通知弹窗…")
                if self.logger:
                    self.logger.info("[MiaoshouExporter] 步骤1: 观察并关闭通知弹窗…")
            except Exception:
                pass
            self._close_popups(page)
            try:
                print("[MiaoshouExporter] 步骤1完成")
            except Exception:
                pass

            if is_warehouse:
                if self.logger:
                    self.logger.info("[MiaoshouExporter] warehouse/checklist flow detected, using iFrame export path")
                # 【步骤3】点击导出
                try:
                    print("[MiaoshouExporter] 步骤3: 点击导出按钮（iFrame）…")
                    if self.logger:
                        self.logger.info("[MiaoshouExporter] 步骤3: 点击导出按钮（iFrame）…")
                except Exception:
                    pass
                # 强制保证“全部时间”：若为商品表现域，重置或清空时间筛选，避免误用昨日/近7天
                try:
                    cfg = self.ctx.config or {}
                    if str(cfg.get("data_domain") or "").lower() == "products":
                        try:
                            page.get_by_role('button', name='重置').first.click(timeout=1000)
                            try:
                                page.wait_for_timeout(120)
                            except Exception:
                                pass
                        except Exception:
                            try:
                                inputs = page.locator(".jx-date-editor--datetimerange input.jx-range-input")
                                if inputs.count() < 2:
                                    inputs = page.locator("input.jx-range-input")
                                if inputs.count() >= 2:
                                    for i in (0, 1):
                                        box = inputs.nth(i)
                                        try:
                                            box.click(timeout=800)
                                            try:
                                                box.press("Control+A")
                                            except Exception:
                                                pass
                                            box.fill("", timeout=800)
                                            try:
                                                box.press("Enter")
                                            except Exception:
                                                pass
                                            try:
                                                page.wait_for_timeout(60)
                                            except Exception:
                                                pass
                                        except Exception:
                                            continue
                            except Exception:
                                pass
                except Exception:
                    pass

                # Open export menu then choose "导出搜索的商品"
                if not self._first_click(page, list(selectors.open_export_menu), timeout=7000):
                    return ExportResult(success=False, message="open export menu failed")
                try:
                    print("[MiaoshouExporter] 已点击‘导入/导出商品’，准备选择‘导出搜索的商品’…")
                except Exception:
                    pass
                ok_menu = self._first_click(page, list(selectors.menu_export_searched), timeout=6000)
                if not ok_menu:
                    return ExportResult(success=False, message="menu item '导出搜索的商品' not found")
                try:
                    print("[MiaoshouExporter] 已选择‘导出搜索的商品’，弹出字段选择弹窗…")
                except Exception:
                    pass

                # Prefer dialog in main page; fallback to iframe if present
                dlg = None
                try:
                    dlg = page.locator('.jx-dialog__body').last
                    dlg.wait_for(timeout=4000)
                except Exception:
                    dlg = None
                fr = None
                if dlg is None:
                    for css in list(selectors.iframe_locators):
                        try:
                            fr = page.frame_locator(css).first
                            fr.locator('body').first.wait_for(timeout=2500)
                            break
                        except Exception:
                            fr = None
                            continue

                # Ensure two groups are checked: 商品信息 & 其他信息 -> 全选
                group_marked = 0
                query_root = dlg if dlg is not None else (fr if fr is not None else page)
                for group in list(selectors.group_titles):
                    try:
                        header = query_root.get_by_text(group, exact=False).first
                        scope = header.locator('..')
                        # A. 就近checkbox by class
                        toggle = scope.locator('.jx-checkbox__input').first
                        if toggle.count() > 0:
                            cls = (toggle.get_attribute('class') or '')
                            if 'is-checked' not in cls:
                                scope.locator('.jx-checkbox__inner').first.click(timeout=3000)
                                try:
                                    page.wait_for_timeout(120)
                                except Exception:
                                    pass
                                cls = (toggle.get_attribute('class') or '')
                            if 'is-checked' in cls:
                                group_marked += 1
                                continue
                        # B. label.pro-checkbox-group-all-select（常见于“其他信息”）
                        container = header.locator('..').locator('..')
                        label = container.locator('label.pro-checkbox-group-all-select').first
                        if label.count() > 0:
                            lcls = (label.get_attribute('class') or '')
                            if 'is-checked' not in lcls:
                                label.locator('.jx-checkbox__inner').first.click(timeout=3000)
                                try:
                                    page.wait_for_timeout(120)
                                except Exception:
                                    pass
                                lcls = (label.get_attribute('class') or '')
                            if 'is-checked' in lcls:
                                group_marked += 1
                                continue
                        # C. 文本“全选”兜底
                        try:
                            el = scope.get_by_text(selectors.group_check_all_text, exact=False).first
                            box = el.locator('..').locator('.jx-checkbox__input').first
                            ok = False
                            if box.count() > 0:
                                bcls = (box.get_attribute('class') or '')
                                if 'is-checked' not in bcls:
                                    el.click(timeout=2000)
                                    try:
                                        page.wait_for_timeout(80)
                                    except Exception:
                                        pass
                                    bcls = (box.get_attribute('class') or '')
                                ok = ('is-checked' in bcls)
                            else:
                                el.click(timeout=2000)
                                ok = True
                            if ok:
                                group_marked += 1
                        except Exception:
                            pass
                    except Exception:
                        pass
                # CSS fallbacks (dialog-first)
                if group_marked < 2:
                    try:
                        (query_root or page).locator('.jx-checkbox__input.is-indeterminate > .jx-checkbox__inner').first.click(timeout=1500)
                        group_marked += 1
                    except Exception:
                        pass
                if group_marked < 2:
                    try:
                        (query_root or page).locator('div:nth-child(2) > .pro-checkbox-group > .pro-checkbox-group-header > .jx-checkbox > .jx-checkbox__input > .jx-checkbox__inner').first.click(timeout=1500)
                        group_marked += 1
                    except Exception:
                        pass
                try:
                    print(f"[MiaoshouExporter] 全选勾选完成: marked={group_marked}/2")
                except Exception:
                    pass

                # Click export button inside dialog, then wait for download
                try:
                    print("[MiaoshouExporter] 准备点击‘导出’按钮…")
                except Exception:
                    pass
                download = None  # type: ignore[assignment]
                downloaded_file: Path | None = None

                # Early: wrap the very first click attempt within expect_download to avoid missing the event
                try:
                    with page.context.expect_download(timeout=120000) as dl_early:
                        try:
                            footer = page.locator('.jx-dialog__footer').last
                            if footer and footer.count() >= 0:
                                footer.get_by_role('button', name='导出').first.click(timeout=1500)
                        except Exception:
                            pass
                    download = dl_early.value
                    clicked = True
                    try:
                        print("[MiaoshouExporter] 首次点击已在 expect_download 中触发")
                    except Exception:
                        pass
                except Exception:
                    pass


                clicked = (download is not None)
                # Target dialog footer first (most reliable)
                try:
                    footer = page.locator('.jx-dialog__footer').last
                    if footer and footer.count() > 0:
                        try:
                            footer.wait_for(timeout=2000)
                        except Exception:
                            pass
                        # a) role-based within footer
                        try:
                            fbtn = footer.get_by_role('button', name='导出').first
                            if fbtn and fbtn.count() >= 0:
                                try:
                                    fbtn.scroll_into_view_if_needed(timeout=800)
                                except Exception:
                                    pass
                                fbtn.click(timeout=4000)
                                clicked = True
                                print("[MiaoshouExporter] 已点击导出按钮（footer role=button）")
                        except Exception:
                            pass
                        # b) primary button selector with text filter
                        if not clicked:
                            try:
                                fbtn2 = footer.locator('button.jx-button--primary').filter(has_text='导出').first
                                if fbtn2 and fbtn2.count() >= 0:
                                    try:
                                        fbtn2.scroll_into_view_if_needed(timeout=800)
                                    except Exception:
                                        pass
                                    fbtn2.click(timeout=4000)
                                    clicked = True
                                    print("[MiaoshouExporter] 已点击导出按钮（footer .jx-button--primary）")
                            except Exception:
                                pass
                        # c) click inner span as last try
                        if not clicked:
                            try:
                                fspan = footer.locator('button:has-text(导出) span').first
                                if fspan and fspan.count() >= 0:
                                    fspan.click(timeout=4000)
                                    clicked = True
                                    print("[MiaoshouExporter] 已点击导出按钮（footer span）")
                            except Exception:
                                pass
                except Exception:
                    pass

                click_roots = [query_root, page]
                btn_sels = list(selectors.export_buttons) + [
                    ".jx-dialog__footer button:has-text(导出)",
                    ".jx-dialog__footer .pro-button:has-text(导出)",
                ]
                for root in click_roots:
                    if root is None:
                        continue
                    for btn in btn_sels:
                        try:
                            loc = root.locator(btn).first
                            if loc.count() >= 0:
                                try:
                                    loc.scroll_into_view_if_needed(timeout=800)
                                except Exception:
                                    pass
                            loc.click(timeout=4000)
                            clicked = True
                            try:
                                print(f"[MiaoshouExporter] 已点击导出按钮（selector={btn}）")
                            except Exception:
                                pass
                            break
                        except Exception:
                            continue
                    if clicked:
                        break
                if not clicked:
                    try:
                        page.get_by_role('button', name='导出').first.click(timeout=4000)
                        clicked = True
                        print("[MiaoshouExporter] 已点击导出按钮（role=button, name=导出）")
                    except Exception:
                        pass
                if not clicked:
                    return ExportResult(success=False, message="export button not found or not clickable")
                # 【步骤4】等待下载（持久监听context级事件，避免遗漏）
                if download is None:
                    try:
                        print("[MiaoshouExporter] 步骤5: 等待下载任务完成…")
                        if self.logger:
                            self.logger.info("[MiaoshouExporter] 步骤5: 等待下载任务完成…")
                    except Exception:
                        pass

                    # 标记等待起始时间（用于目录扫描兜底）
                    import time as _t
                    start_ts = _t.time()

                    # 最终网络层兜底：若捕获到可疑直连URL，使用 fetch(blob) 触发浏览器下载
                    if downloaded_file is None and net_candidates:
                        try:
                            candidate_url = net_candidates[-1]
                            with page.context.expect_download(timeout=60000) as dl_info2:
                                page.evaluate(
                                    "(url)=>{ fetch(url, {credentials:'include'})"
                                    ".then(r=>r.blob()).then(b=>{ const u=URL.createObjectURL(b);"
                                    " const a=document.createElement('a'); a.href=u; a.download='export.xlsx';"
                                    " document.body.appendChild(a); a.click(); setTimeout(()=>URL.revokeObjectURL(u), 5000); }); }",
                                    candidate_url,
                                )
                            download = dl_info2.value
                        except Exception:
                            pass

                    # 再触发一次受保护点击，确保捕获事件
                    try:
                        with page.context.expect_download(timeout=15000) as dl_info:
                            try:
                                footer = page.locator('.jx-dialog__footer').last
                                if footer and footer.count() >= 0:
                                    footer.get_by_role('button', name='导出').first.click(timeout=1000)
                            except Exception:
                                pass
                        download = dl_info.value
                    except Exception:
                        # 回退1：短时进度监听，若仍未捕获则进入目录扫描兜底
                        try:
                            texts = list(getattr(selectors, 'progress_texts', []))
                        except Exception:
                            texts = ['正在导出', '生成中', 'Processing', 'Generating']
                        try:
                            dl = self._wait_download_with_progress(page, texts, total_ms=600000, interval_ms=3000)
                            download = dl
                        except Exception:
                            downloaded_file = self._scan_latest_download(start_ts, max_age_sec=900, suffixes=None)
            else:
                # Generic export flow (non-warehouse pages)
                # 再次尝试关闭弹窗，确保按钮可点击
                self._close_popups(page)
                # Ensure '订单状态' is set to 全选, and apply filters
                try:
                    self._ensure_order_status_all(page)
                    try:
                        print("[MiaoshouExporter] 步骤2: 设置筛选-订单状态=全选")
                    except Exception:
                        pass
                    # 再设置时间区间（使用先前写入 ctx.config 的 start/end）
                    self._ensure_date_range_from_config(page)
                    try:
                        print("[MiaoshouExporter] 步骤3: 点击‘搜索’应用筛选（已设置时间区间）…")
                    except Exception:
                        pass
                    self._trigger_search(page)
                except Exception:
                    pass
                try:
                    page.wait_for_timeout(400)
                except Exception:
                    pass

                try:
                    print("[MiaoshouExporter] 步骤4: 导出操作——打开‘导出数据’下拉并点击‘导出全部订单’…")
                    if self.logger:
                        self.logger.info("[MiaoshouExporter] 步骤4: 导出操作——打开‘导出数据’下拉并点击‘导出全部订单’…")
                except Exception:
                    pass
                export_buttons = [
                    "button:has-text(导出)",
                    "button:has-text(Export)",
                    "[role='button']:has-text(导出)",
                    "[role='button']:has-text(Export)",
                    "a:has-text(导出)",
                ]
                confirm_buttons = [
                    "button:has-text(确认)",
                    "button:has-text(确定)",
                    "button:has-text(下载)",
                    "button:has-text(Export)",
                ]
                import time as _t
                start_ts = _t.time()
                try:
                    print("[MiaoshouExporter] 步骤5: 等待下载任务完成…")
                    if self.logger:
                        self.logger.info("[MiaoshouExporter] 步骤5: 等待下载任务完成…")
                except Exception:
                    pass
                download = None  # type: ignore[assignment]
                downloaded_file = None
                # Global download tap: capture any download even if it fires earlier/later
                _latest_download: dict[str, Any] = {"dl": None}
                def _on_download(evt):
                    try:
                        _latest_download["dl"] = evt
                        try:
                            print("[MiaoshouExporter] 捕获到下载事件 (tap)", getattr(evt, 'suggested_filename', None))
                            if self.logger:
                                self.logger.info(f"[MiaoshouExporter] 捕获到下载事件 (tap): {getattr(evt, 'suggested_filename', None)}")
                        except Exception:
                            pass
                    except Exception:
                        pass
                def _on_new_page(p):
                    try:
                        p.on("download", _on_download)
                    except Exception:
                        pass
                try:
                    page.on("download", _on_download)
                except Exception:
                    pass
                try:
                    page.context.on("page", _on_new_page)
                except Exception:
                    pass
                # 直接在 context 级别也监听下载，最大化捕获概率
                try:
                    page.context.on("download", _on_download)
                except Exception:
                    pass
                # 将 tap 容器挂到 context，供进度等待函数即时退出
                try:
                    setattr(page.context, "_aug_latest_download", _latest_download)
                except Exception:
                    pass

                triggered_processing = False

                # 优先使用“导出数据”下拉 -> “导出全部订单” 专用流程（带重试）
                # 修复：一旦捕获到任意下载事件（全局 listener），立刻停止重复点击，避免多次导出
                for attempt in range(1, 4):
                    try:
                        # 若全局监听已捕获下载，直接退出重试循环
                        try:
                            if _latest_download.get("dl") is not None:
                                download = _latest_download["dl"]
                                break
                        except Exception:
                            pass

                        if attempt > 1:
                            try:
                                print(f"[MiaoshouExporter] 导出下拉点击重试，第{attempt}次…")
                            except Exception:
                                pass
                        dl0 = self._export_via_dropdown(page)
                        # 再次检查：如果函数未返回但全局监听已捕获，仍然视为成功并停止
                        try:
                            if dl0 is None and _latest_download.get("dl") is not None:
                                download = _latest_download["dl"]
                                break
                        except Exception:
                            pass
                        if dl0 is not None:
                            download = dl0
                            break
                        # If no immediate download, short‑poll for progress dialog and stop re‑clicking
                        try:
                            from modules.platforms.miaoshou.components.orders_config import OrdersSelectors as _OS
                            _texts = list(getattr(_OS(), "progress_texts", []))
                        except Exception:
                            _texts = ["导出成功，正在下载", "导出成功", "正在下载", "正在导出", "生成中", "处理中", "排队中", "Processing", "Generating"]
                        try:
                            found_progress = False
                            # wait up to ~3.5s after click for the progress modal to appear
                            for _i in range(7):
                                try:
                                    for _t in _texts:
                                        el = page.get_by_text(_t, exact=False).first
                                        if el and el.is_visible():
                                            found_progress = True
                                            triggered_processing = True
                                            try:
                                                print("[MiaoshouExporter] 检测到导出进度弹窗，停止重复点击，进入轮询等待…")
                                            except Exception:
                                                pass
                                            break
                                except Exception:
                                    pass
                                if found_progress:
                                    break
                                try:
                                    page.wait_for_timeout(500)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        # Also detect common full‑screen loading overlays (no text)
                        try:
                            overlay_selectors = [
                                '.jx-loading', '.jx-loading-mask', '.jx-dialog__loading',
                                '.ant-spin-spinning', '.el-loading-mask', '.arco-spin',
                                '.arco-spin-mask', '.loading-mask', '.full-loading', '.loading-overlay',
                            ]
                            for sel in overlay_selectors:
                                loc = page.locator(sel)
                                if loc and loc.count() >= 1 and loc.first.is_visible():
                                    triggered_processing = True
                                    break
                        except Exception:
                            pass

                        # 已识别到进度弹窗/加载遮罩，停止后续重试与按键，直接进入下载等待
                        if triggered_processing:
                            break

                    except Exception:
                        pass
                    # 仅在未检测到进度的情况下，关闭可能残留的下拉/遮挡后再试
                    if not triggered_processing:
                        try:
                            page.keyboard.press("Escape")
                            page.wait_for_timeout(150)
                        except Exception:
                            pass

                    # Escape 后再做一次兜底检查：若此时已有下载，停止重试
                    try:
                        if _latest_download.get("dl") is not None:
                            download = _latest_download["dl"]
                            break
                    except Exception:
                        pass
                # 若下拉流程未捕获，优先尝试对话框确认按钮
                # If we saw progress texts, switch to progress-waiting mode instead of re-clicking
                if download is None and triggered_processing:
                    try:
                        try:
                            from modules.platforms.miaoshou.components.orders_config import OrdersSelectors as _OS
                            texts = list(getattr(_OS(), "progress_texts", []))
                        except Exception:
                            texts = ["导出成功，正在下载", "导出成功", "正在下载", "正在导出", "生成中", "处理中", "排队中", "Processing", "Generating"]
                        dl_info = self._wait_download_with_progress(page, texts, total_ms=240000, interval_ms=3000)
                        download = dl_info
                    except Exception:
                        try:
                            downloaded_file = self._scan_latest_download(start_ts, max_age_sec=900, suffixes=None)
                        except Exception:
                            pass

                if download is None:
                    try:
                        footer = page.locator('.jx-dialog__footer').last
                        if footer and footer.count() >= 1:
                            for btn_name in ['导出', '确定', '开始导出']:
                                try:
                                    with page.context.expect_download(timeout=120000) as dl_conf:
                                        footer.get_by_role('button', name=btn_name).first.click(timeout=1800)
                                    download = dl_conf.value
                                    break
                                except Exception:
                                    continue
                    except Exception:
                        pass
                # 若仍未捕获，回退到通用按钮点击流程
                if download is None:
                    try:
                        with page.context.expect_download(timeout=60000) as dl_info:
                            if not self._first_click(page, export_buttons, timeout=7000):
                                raise RuntimeError("export button not found")

                            try:
                                page.wait_for_timeout(600)
                            except Exception:
                                pass
                            # 可能弹出确认框，再次兜底关闭遮挡
                            self._close_popups(page)
                            self._first_click(page, confirm_buttons, timeout=3000)
                        download = dl_info.value
                    except Exception:
                        try:
                            from modules.platforms.miaoshou.components.orders_config import OrdersSelectors as _OS
                            texts = list(getattr(_OS(), "progress_texts", []))
                        except Exception:
                            texts = ["导出成功，正在下载", "导出成功", "正在下载", "正在导出", "生成中", "处理中", "排队中", "Processing", "Generating"]
                        try:
                            dl_info = self._wait_download_with_progress(page, texts, total_ms=600000, interval_ms=3000)
                            download = dl_info
                        except Exception:
                            downloaded_file = self._scan_latest_download(start_ts, max_age_sec=900, suffixes=None)
                # 最终网络层兜底（通用流程）：若存在可疑直连URL，使用 fetch(blob) 触发浏览器下载
                if download is None and downloaded_file is None and net_candidates:
                    try:
                        candidate_url = net_candidates[-1]
                        with page.context.expect_download(timeout=60000) as dl_info2:
                            page.evaluate(
                                "(url)=>{ fetch(url, {credentials:'include'})"
                                ".then(r=>r.blob()).then(b=>{ const u=URL.createObjectURL(b);"
                                " const a=document.createElement('a'); a.href=u; a.download='export.xlsx';"
                                " document.body.appendChild(a); a.click(); setTimeout(()=>URL.revokeObjectURL(u), 5000); }); }",
                                candidate_url,
                            )
                        download = dl_info2.value
                    except Exception:
                        pass


            # Build output path and filename (Shopee/TikTok-compatible naming)
            from modules.components.export.base import build_standard_output_root
            from modules.utils.path_sanitizer import build_filename
            from datetime import datetime as _dt

            cfg = self.ctx.config or {}
            gran = ("snapshot" if is_warehouse else (cfg.get("granularity") or "range")).lower()
            # v4.10.0更新：对于仓库清单页（库存快照），命名和分流一律归并到 inventory，避免出现意外的 'warehouse' 目录
            data_domain = cfg.get("data_domain") or ("inventory" if is_warehouse else None)
            data_type = self._infer_data_type(current_url, data_domain)
            # Use globally tapped download if normal flows missed it
            try:
                if download is None and _latest_download.get("dl") is not None:
                    download = _latest_download["dl"]
            except Exception:
                pass
            # keep global download listener until final cleanup


            # orders subtype — prefer URL query (?platform=shopee|tiktok|lazada), fallback to ctx.config
            sub: str | None = None
            try:
                if data_type == "orders":
                    # 1) URL-derived
                    try:
                        from urllib.parse import urlparse, parse_qs
                        _qs = parse_qs(urlparse(current_url).query)
                        _pf = (_qs.get("platform") or [None])[0]
                        if _pf:
                            _pf = str(_pf).lower().strip()
                            if _pf in {"shopee", "tiktok", "lazada"}:
                                sub = _pf
                    except Exception:
                        pass
                    # 2) Fallback to exec ctx config
                    if not sub:
                        sub = str(cfg.get("orders_subtype") or "").strip() or None
            except Exception:
                sub = None

            out_root = build_standard_output_root(self.ctx, data_type=data_type, granularity=gran, subtype=sub)
            out_root.mkdir(parents=True, exist_ok=True)

            # Save temp file: prefer Playwright download object; fallback to scanned file
            import shutil as _shutil
            if download is not None:
                # Sanitize suggested filename to be Windows-safe
                raw_name = (getattr(download, 'suggested_filename', None) or f"{data_type}.xlsx")
                try:
                    _suffix = Path(raw_name).suffix or ".xlsx"
                except Exception:
                    _suffix = ".xlsx"
                try:
                    from modules.utils.path_sanitizer import safe_slug as _safe
                    _stem = _safe(Path(raw_name).stem) or "export"
                except Exception:
                    _stem = "export"
                tmp_name = f"{_stem}{_suffix}"
                tmp_path = out_root / tmp_name
                try:
                    download.save_as(str(tmp_path))
                except Exception:
                    # In rare cases, get temp path and copy
                    try:
                        p = download.path()
                        if p:
                            _shutil.copy2(p, tmp_path)
                        else:
                            raise
                    except Exception:
                        raise
            elif downloaded_file is not None:
                tmp_path = out_root / Path(downloaded_file).name
                _shutil.copy2(Path(downloaded_file), tmp_path)
            else:
                # Final grace wait for late download event before failing
                try:
                    dl_late = page.wait_for_event('download', timeout=45000)
                    download = dl_late
                    # Save as with regular download path
                    raw_name = (getattr(download, 'suggested_filename', None) or f"{data_type}.xlsx")
                    try:
                        _suffix = Path(raw_name).suffix or ".xlsx"
                    except Exception:
                        _suffix = ".xlsx"
                    try:
                        from modules.utils.path_sanitizer import safe_slug as _safe
                        _stem = _safe(Path(raw_name).stem) or "export"
                    except Exception:
                        _stem = "export"
                    tmp_name = f"{_stem}{_suffix}"
                    tmp_path = out_root / tmp_name
                    try:
                        download.save_as(str(tmp_path))
                    except Exception:
                        try:
                            p = download.path()
                            if p:
                                _shutil.copy2(p, tmp_path)
                            else:
                                raise
                        except Exception:
                            raise
                except Exception:
                    raise RuntimeError("download finished but no file captured (event/scan both failed)")

            account = self.ctx.account or {}
            account_label = account.get("label") or account.get("store_name") or account.get("username") or "unknown"
            shop_name = (cfg.get("shop_name") or account.get("display_shop_name") or account.get("store_name") or "unknown_shop")
            ts = _dt.now().strftime("%Y%m%d_%H%M%S")
            target_name = build_filename(
                ts=ts,
                account_label=account_label,
                shop_name=shop_name,
                data_type=data_type,
                granularity=gran,
                start_date=cfg.get("start_date"),
                end_date=cfg.get("end_date"),
                suffix=(tmp_path.suffix or ".xlsx"),
            )
            target = out_root / target_name
            try:
                tmp_path.rename(target)
            except Exception:
                import shutil
                shutil.copy2(tmp_path, target)
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass

            if self.logger:
                self.logger.info(f"[MiaoshouExporter] saved: {target}")
            print(f"\n[OK] 导出成功: {target}")
            # cleanup download listener
            try:
                page.off("download", _on_download)
            except Exception:
                pass
            try:
                page.context.off("page", _on_new_page)
            except Exception:
                pass

            # cleanup response listener
            try:
                page.off('response', _on_response)
            except Exception:
                pass

            return ExportResult(success=True, file_path=str(target), message="ok")
        except Exception as e:
            # cleanup download listener
            try:
                page.off("download", _on_download)
            except Exception:
                pass
            try:
                page.context.off("page", _on_new_page)
            except Exception:
                pass

            # cleanup response listener
            try:
                page.off('response', _on_response)
            except Exception:
                pass

            if self.logger:
                self.logger.error(f"[MiaoshouExporter] failed: {e}")
            return ExportResult(success=False, message=str(e))
