from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable, List, Optional

from modules.components.base import ExecutionContext
from modules.components.date_picker.base import DatePickerComponent, DatePickResult, DateOption


class TiktokDatePicker(DatePickerComponent):
    """TikTok Shop 日期选择组件（EDS 日期控件 + iframe + testId 优先）。

    设计约束:
    - 仅做 UI 操作（打开面板 -> 选择快捷项/自定义），不做硬编码导航
    - 优先使用 data-testid（time-selector-last-7-days / -last-28-days）
    - 面板在 iframe 内，使用 frame_locator("iframe").first 进入
    - 失败不抛异常，由上层决定是否兜底
    """

    # Component metadata (v4.8.0)
    platform = "tiktok"
    component_type = "date_picker"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    # -------- helpers --------
    async def _click_first(self, page: Any, selectors: Iterable[str], *, timeout: int = 2000) -> bool:
        for sel in selectors:
            try:
                loc = page.locator(sel)
                if await loc.count() > 0 and await loc.first.is_visible():
                    await loc.first.click(timeout=timeout)
                    return True
            except Exception:
                continue
        return False

    async def _click_role_button_by_names(self, page: Any, names: Iterable[str], *, timeout: int = 1500) -> bool:
        for name in names:
            try:
                btn = page.get_by_role("button", name=name)
                if btn and await btn.count() > 0 and await btn.first.is_visible():
                    await btn.first.click(timeout=timeout)
                    return True
            except Exception:
                continue
        return False

    async def _wait_any_visible(self, page: Any, selectors: Iterable[str], *, timeout_ms: int = 3000) -> bool:
        import time
        dl = time.time() + timeout_ms / 1000.0
        while time.time() < dl:
            for sel in selectors:
                try:
                    loc = page.locator(sel)
                    if await loc.count() > 0 and await loc.first.is_visible():
                        return True
                except Exception:
                    continue
            try:
                await page.wait_for_timeout(300)
            except Exception:
                pass
        return False

    def _variants_for(self, option: DateOption) -> List[str]:
        if option == DateOption.YESTERDAY:
            return ["昨天", "昨日", "Yesterday"]
        if option == DateOption.LAST_7_DAYS:
            return [
                "最近7天", "过去7天", "过去 7 天", "7天", "Last 7 days",
                "近7天", "近 7 天",
            ]
        if option == DateOption.LAST_28_DAYS:
            return [
                "最近28天", "过去28天", "28天", "Last 28 days",
                "近28天", "近 28 天",
            ]
        if option == DateOption.LAST_30_DAYS:
            return ["过去30天", "过去 30 天", "最近30天", "30天", "Last 30 days"]
        if option == DateOption.TODAY_REALTIME:
            return ["今日实时", "今天", "Today"]
        return [option.value]
    async def _all_roots(self, page: Any) -> list[Any]:
        """返回可交互的根集合：[page] + 所有层级 iframe（递归）。"""
        roots: list[Any] = []
        stack: list[Any] = [page]
        seen = set()
        while stack:
            cur = stack.pop()
            try:
                if id(cur) in seen:
                    continue
                seen.add(id(cur))
                roots.append(cur)
                # Page.frames / Frame.child_frames 兼容
                children = []
                for attr in ("frames", "child_frames"):
                    try:
                        v = list(getattr(cur, attr, []) or [])
                        if v:
                            children.extend(v)
                    except Exception:
                        pass
                if children:
                    stack.extend(children)
            except Exception:
                continue
        return roots

    async def _find_panel_root(self, page: Any) -> Optional[Any]:
        """在所有根上下文中定位已渲染的日期面板，返回对应 root。"""
        panel_hints = [
            ".theme-arco-picker-dropdown",
            ".arco-picker-dropdown",
            ".arco-picker-panel",
            ".theme-arco-picker-panel",
            ".arco-trigger-popup:has(.arco-picker-panel)",
            ".eds-date-selector-panel",
            ".eds-date-picker__dropdown",
            ".eds-dropdown__content:has(.eds-date-shortcut-item)",
            "[data-testid='time-selector-last-7-days']",
            "[data-testid='time-selector-last-28-days']",
            "div[role='tab']:has-text('\u81ea\u5b9a\u4e49')",
            "button:has-text('\u81ea\u5b9a\u4e49')",
        ]
        # 服务表现页（service-analytics）为 m4b 定制面板，这里补充其特有容器特征
        try:
            _url = page.url or ""
        except Exception:
            _url = ""
        if "service-analytics" in _url:
            panel_hints.extend([
                ".theme-m4b-date-picker-range-with-mode-shortcut-custom",
                "button.theme-m4b-date-picker-range-with-mode-shortcut-custom-btn",
            ])

        for r in await self._all_roots(page):
            for sel in panel_hints:
                try:
                    loc = r.locator(sel)
                    if await loc.count() > 0 and await loc.first.is_visible():
                        return r
                except Exception:
                    continue
        return None

    async def _is_panel_open(self, page: Any) -> bool:
        """在所有 root 中检查日期面板是否可见（包含 testId/自定义tab/常见面板类名）。"""
        tokens = [
            "[data-testid='time-selector-last-7-days']",
            "[data-testid='time-selector-last-28-days']",
            "button:has-text('自定义')",
            "div[role='tab']:has-text('自定义')",
            ".theme-arco-picker-dropdown",
            ".arco-picker-dropdown",
            ".arco-picker-panel",
            ".theme-arco-picker-panel",
            ".arco-trigger-popup:has(.arco-picker-panel)",
            ".eds-date-selector-panel",
            ".eds-date-picker__dropdown",
        ]
        # 服务表现页（service-analytics）额外判定：m4b 快捷容器/按钮可视即认为已打开
        try:
            _url2 = page.url or ""
        except Exception:
            _url2 = ""
        if "service-analytics" in _url2:
            tokens.extend([
                ".theme-m4b-date-picker-range-with-mode-shortcut-custom",
                "button.theme-m4b-date-picker-range-with-mode-shortcut-custom-btn",
            ])
        for r in await self._all_roots(page):
            for sel in tokens:
                try:
                    loc = r.locator(sel)
                    if await loc.count() > 0 and await loc.first.is_visible():
                        return True
                except Exception:
                    continue
        return False


    async def _fill_range_inputs(self, page: Any, start: date, end: date, root: Any | None = None) -> bool:
        """直接向范围输入框填充起止日期，并点击应用/确定。
        仅用于“最近30天”路径，以避免复杂面板点击。
        """
        try:
            f = root or self._find_panel_root(page) or self._first_frame(page) or page
            try:
                # 可选：切到“自定义”tab（若存在）
                for name in ("自定义", "Custom"):
                    try:
                        f.get_by_role("tab", name=name).click(timeout=600)
                        break
                    except Exception:
                        continue
            except Exception:
                pass
            inputs = f.locator(".theme-arco-picker-input-range input")
            if inputs and inputs.count() >= 2:
                fmt_candidates = ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"]
                for fmt in fmt_candidates:
                    try:
                        s_val = start.strftime(fmt)
                        e_val = end.strftime(fmt)
                        el0 = inputs.nth(0)
                        el0.click(timeout=800)
                        for key in ("Control+A", "Meta+A"):
                            try:
                                el0.press(key)
                            except Exception:
                                pass
                        el0.fill(s_val, timeout=1200)
                        el1 = inputs.nth(1)
                        el1.click(timeout=800)
                        for key in ("Control+A", "Meta+A"):
                            try:
                                el1.press(key)
                            except Exception:
                                pass
                        el1.fill(e_val, timeout=1200)
                        # 点击“确定/Apply/OK/完成”
                        for label in ["确定", "应用", "确认", "完成", "Apply", "OK", "Done"]:
                            try:
                                f.get_by_role("button", name=label).click(timeout=500)
                                break
                            except Exception:
                                continue
                        try:
                            page.wait_for_timeout(300)
                        except Exception:
                            pass
                        cur_s = inputs.nth(0).input_value()
                        cur_e = inputs.nth(1).input_value()
                        if cur_s and cur_e:
                            try:
                                if self.logger:
                                    self.logger.info(f"[TiktokDatePicker] input-fill success fmt={fmt} -> {cur_s} ~ {cur_e}")
                            except Exception:
                                pass
                            return True
                    except Exception:
                        continue
        except Exception:
            pass
        return False



    def _first_frame(self, page: Any):
        try:
            return page.frame_locator("iframe").first
        except Exception:
            return None

    async def _wait_analytics_ready(self, page: Any, *, timeout_ms: int = 12000) -> bool:
        """等待数据分析页面的日期控件容器渲染完成。
        - 在主文档与所有 iframe 内查找典型容器/触发器
        - 适配首次进入时 iframe 重载导致的短暂空窗
        """
        import time
        ddl = time.time() + timeout_ms / 1000.0
        hints = [
            "div.theme-arco-picker.theme-arco-picker-range",
            "div.arco-picker.arco-picker-range",
            ".theme-arco-picker",
            ".arco-picker",
            ".eds-date-picker-input",
            "[data-testid*='time-selector']",
            "[data-testid*='date']",
        ]
        while time.time() < ddl:
            try:
                # 重新获取 frames，兼容 iframe 刷新
                roots: list[Any] = [page]
                try:
                    roots += list(getattr(page, "frames", []))
                except Exception:
                    pass
                for r in roots:
                    for sel in hints:
                        try:
                            loc = r.locator(sel)
                            if loc.count() > 0 and loc.first.is_visible():
                                return True
                        except Exception:
                            continue
            except Exception:
                pass
            try:
                page.wait_for_timeout(300)
            except Exception:
                pass
        return False

    async def _try_quick_pick_without_panel(self, page: Any, option: DateOption) -> bool:
        """在未打开下拉面板的情况下，直接点击页面级快捷项（若存在）。"""
        targets = []
        if option == DateOption.LAST_7_DAYS:
            targets = [
                "[data-testid='time-selector-last-7-days']",
                "button:has-text('最近7天')",
                "text=最近7天",
                "button:has-text('近7天')",
                "button:has-text('近 7 天')",
                "div.theme-arco-typography:has-text('近7天')",
                "div.theme-arco-typography:has-text('近 7 天')",
                "text=近7天",
                "text=近 7 天",
            ]
        elif option == DateOption.LAST_28_DAYS:
            targets = [
                "[data-testid='time-selector-last-28-days']",
                "button:has-text('最近28天')",
                "text=最近28天",
                "button:has-text('近28天')",
                "button:has-text('近 28 天')",
                "div.theme-arco-typography:has-text('近28天')",
                "div.theme-arco-typography:has-text('近 28 天')",
                "text=近28天",
                "text=近 28 天",
            ]
        elif option == DateOption.YESTERDAY:
            targets = ["button:has-text('昨天')", "text=昨天"]
        elif option == DateOption.LAST_30_DAYS:
            targets = ["button:has-text('最近30天')", "text=最近30天"]
        else:
            targets = []

        if not targets:
            return False

        # 在主文档与所有 iframe 中尝试
        try:
            roots: list[Any] = [page]
            try:
                roots += list(getattr(page, "frames", []))
            except Exception:
                pass
            for r in roots:
                for sel in targets:
                    try:
                        loc = r.locator(sel)
                        if await loc.count() > 0 and await loc.first.is_visible():
                            await loc.first.click(timeout=1200)
                            try:
                                await page.wait_for_timeout(500)
                            except Exception:
                                pass
                            return True
                    except Exception:
                        continue
        except Exception:
            pass
        return False


    async def _open_panel(self, page: Any) -> bool:
        """Open the Arco date range picker panel with wait+retry and rich logging.
        - 优先点击 suffix 日历图标或第二个输入框
        - 在主文档与所有 iframe 中尝试
        - 点击后等待 dropdown/面板元素出现
        - 轮询重试约 2.5s，避免页面刚导航完尚未渲染
        """
        import time

        def all_contexts(p: Any) -> List[Any]:
            ctxs: List[Any] = [p]
            try:
                for fr in getattr(p, "frames", []):  # Page.frames -> List[Frame]
                    ctxs.append(fr)
            except Exception:
                pass
            return ctxs

        def log(msg: str) -> None:
            try:
                if self.logger:
                    self.logger.info(f"[TiktokDatePicker] {msg}")
                else:
                    print(f"[TiktokDatePicker] {msg}")
            except Exception:
                pass

        dropdown_hints = [
            ".theme-arco-picker-dropdown",
            ".arco-picker-dropdown",
            ".arco-picker-panel",
            ".theme-arco-picker-panel",
            ".arco-trigger-popup:has(.arco-picker-panel)",
            ".eds-date-selector-panel",
            ".eds-date-picker__dropdown",
        ]
        # 等待日期控件容器就绪（iframe 刷新时可能需要数秒）
        try:
            self._wait_analytics_ready(page, timeout_ms=6000)
        except Exception:
            pass


        # 先检测是否已经打开
        if self._is_panel_open(page):
            log("panel already open (pre-check)")
            return True

        deadline = time.time() + 9.0  # 轮询 9 秒（首次进入常有 iframe 刷新 + 慢网更稳）
        attempt = 0
        while time.time() < deadline:
            attempt += 1
            opened = False
            for idx, ctx in enumerate(all_contexts(page)):
                try:
                    # 容器限定（兼容 theme-arco 与 arco 两种类名前缀）
                    container = None
                    for cs in [
                        "div.theme-arco-picker.theme-arco-picker-range",
                        "div.arco-picker.arco-picker-range",
                        ".theme-arco-picker",
                        ".arco-picker",
                        ".eds-date-picker-input",
                    ]:
                        try:
                            loc = ctx.locator(cs)
                            if loc and loc.count() > 0 and loc.first.is_visible():
                                container = loc.first
                                break
                        except Exception:
                            continue
                    container = container or ctx
                    try:
                        container.scroll_into_view_if_needed(timeout=800)
                    except Exception:
                        pass
                    # 1) 优先点击日历图标（含 SVG/path）
                    choices = [
                        ".theme-arco-picker-suffix-icon",
                        "span.theme-arco-picker-suffix-icon svg",
                        "span.theme-arco-picker-suffix-icon svg path",
                        ".theme-arco-picker-input >> nth=1",
                        ".theme-arco-picker-input:last-child",
                        ".arco-picker-suffix-icon",
                        "span.arco-picker-suffix-icon svg",
                        "span.arco-picker-suffix-icon svg path",
                        ".arco-picker-input >> nth=1",
                        ".arco-picker-input:last-child",
                    ]
                    for sel in choices:
                        try:
                            el = container.locator(sel)
                            if el.count() > 0 and el.first.is_visible():
                                log(f"attempt#{attempt} ctx#{idx} click '{sel}'")
                                el.first.click(timeout=1200)
                                try:
                                    page.wait_for_timeout(300)
                                except Exception:
                                    pass
                                opened = True
                                break
                        except Exception as _:
                            continue
                        if opened and self._is_panel_open(page):
                            log("panel opened via container choices")
                            return True
                    # 容器未命中 -> 通用触发器
                    generic = [
                        ".theme-arco-picker-suffix-icon",
                        ".theme-arco-picker-input",
                        ".theme-arco-picker",
                        ".arco-picker-suffix-icon",
                        ".arco-picker-input",
                        ".arco-picker",
                        ".eds-date-picker-input",
                        ".eds-date-picker-input .eds-input__inner",
                        ".date-range-picker",
                        "div.bi-date-input",
                        "div.date-picker-trigger",
                        "[data-testid*='date']",
                        "[data-testid*='time']",
                    ]
                    if self._click_first(ctx, generic):
                        log(f"attempt#{attempt} ctx#{idx} clicked generic trigger")
                        try:
                            page.wait_for_timeout(300)
                        except Exception:
                            pass
                        if self._is_panel_open(page):
                            log("panel opened via generic trigger")
                            return True
                except Exception:
                    continue
            # 未打开则短暂等待后重试
            try:
                page.wait_for_timeout(200)
            except Exception:
                pass

        # 兜底：role=button 名称
        if self._click_role_button_by_names(page, ["最近7天", "最近28天", "昨天", "Today", "自定义", "近7天", "近 7 天", "近28天", "近 28 天"]):
            log("clicked by role=button fallback")
            if self._is_panel_open(page):
                return True

        # 最终确认
        if self._is_panel_open(page):
            log("panel detected after retries")
            return True
        log("open panel failed after retries")
        return False

    # -------- main --------
    async def run(self, page: Any, option: DateOption) -> DatePickResult:  # type: ignore[override]
        try:
            if self.logger:
                self.logger.info(f"[TiktokDatePicker] selecting: {option}")

            # 1) 打开日期面板（统一入口）
            if not await self._open_panel(page):
                # 页面或 iframe 刷新时，可能存在页级快捷项可直接生效；尝试一次无面板快捷选择
                if await self._try_quick_pick_without_panel(page, option):
                    return DatePickResult(success=True, option=option, message="ok(no-panel)")
                return DatePickResult(success=False, option=option, message="open date panel failed")

            # 2) 面板出现，定位面板 root（支持多层 iframe）
            panel_hints = [
                ".theme-arco-picker-dropdown",
                ".arco-picker-dropdown",
                ".arco-picker-panel",
                ".theme-arco-picker-panel",
                ".arco-trigger-popup:has(.arco-picker-panel)",
                ".eds-date-selector-panel",
                ".eds-date-picker__dropdown",
                ".eds-dropdown__content:has(.eds-date-shortcut-item)",
                "[data-testid='time-selector-last-7-days']",
                "[data-testid='time-selector-last-28-days']",
                "div[role='tab']:has-text('\u81ea\u5b9a\u4e49')",
                "button:has-text('\u81ea\u5b9a\u4e49')",
            ]
            # service-analytics: m4b 
            try:
                _urlp = page.url or ""
            except Exception:
                _urlp = ""
            if "service-analytics" in _urlp:
                panel_hints.extend([
                    ".theme-m4b-date-picker-range-with-mode-shortcut-custom",
                    "button.theme-m4b-date-picker-range-with-mode-shortcut-custom-btn",
                ])

            await self._wait_any_visible(page, panel_hints, timeout_ms=6000)
            panel_root = await self._find_panel_root(page) or page
            all_roots = await self._all_roots(page)

            # 昨天：在服务表现(service-analytics)页使用"自然日"单日选择；其他页面保留自定义同日起止。
            from datetime import date, timedelta
            if option == DateOption.YESTERDAY:
                y = date.today() - timedelta(days=1)
                try:
                    cur_url = page.url or ""
                except Exception:
                    cur_url = ""
                if "service-analytics" in cur_url:
                    ok = await self.select_natural_day(page, y)
                    return DatePickResult(success=ok, option=option, message=("natural-yesterday" if ok else "natural-yesterday-failed"))
                else:
                    ok = await self.select_custom_range(page, y, y)
                    return DatePickResult(success=ok, option=option, message=("custom-yesterday" if ok else "custom-yesterday-failed"))

            if option == DateOption.LAST_30_DAYS:
                end = date.today() - timedelta(days=1)
                start = end - timedelta(days=29)
                # 仅对"最近30天"使用直接输入框填充，避免复杂面板点击
                ok = await self._fill_range_inputs(page, start, end, panel_root)
                return DatePickResult(success=ok, option=option, message=("input-30d" if ok else "input-30d-failed"))


            # 3a) 特例：service-analytics 使用 m4b 快捷按钮（更精准）
            try:
                cur_url = ""
                try:
                    cur_url = page.url or ""
                except Exception:
                    cur_url = ""
                if "service-analytics" in cur_url:
                    texts = self._variants_for(option)
                    selectors = []
                    for t in texts:
                        selectors.extend([
                            # 精准：按钮 + 内部 typography 文案
                            f"button.theme-m4b-date-picker-range-with-mode-shortcut-custom-btn:has(div.theme-arco-typography:has-text('{t}'))",
                            # 兼容旧类名：theme-arco-btn 容器内含 typography
                            f"button.theme-arco-btn:has(div.theme-arco-typography:has-text('{t}'))",
                            # 宽松：仅 typography（仅在面板 root 内尝试）
                            f"div.theme-arco-typography:has-text('{t}')",
                        ])
                    if await self._click_first(panel_root, selectors, timeout=1800):
                        try:
                            await page.wait_for_timeout(600)
                        except Exception:
                            pass
                        return DatePickResult(success=True, option=option, message="ok")
            except Exception:
                pass

            # 3) testId 优先选择快捷项（在所有 root 中尝试）
            try:
                if option in (DateOption.LAST_7_DAYS, DateOption.LAST_28_DAYS):
                    testid = "time-selector-last-7-days" if option == DateOption.LAST_7_DAYS else "time-selector-last-28-days"
                    for r in all_roots:
                        try:
                            el = r.get_by_test_id(testid)
                            if el and await el.count() > 0 and await el.first.is_visible():
                                await el.first.click(timeout=2000)
                                try:
                                    await page.wait_for_timeout(600)
                                except Exception:
                                    pass
                                return DatePickResult(success=True, option=option, message="ok")
                        except Exception:
                            continue
            except Exception:
                pass

            # 4) 回退到文本/role 选择（在面板 root 与所有 root 上尝试）
            picked = False
            for text in self._variants_for(option):
                selectors_panel = [
                    f".eds-date-shortcut-item__text:has-text('{text}')",
                    f".eds-date-shortcut-item:has-text('{text}')",
                    f"li:has-text('{text}')",
                    f"span:has-text('{text}')",
                    f"button:has-text('{text}')",
                    f"div.theme-arco-typography:has-text('{text}')",
                    f"[role='tab']:has-text('{text}')",
                    f"[role='button']:has-text('{text}')",
                ]
                selectors_global = [
                    f".eds-date-shortcut-item__text:has-text('{text}')",
                    f".eds-date-shortcut-item:has-text('{text}')",
                    f"li:has-text('{text}')",
                    f"span:has-text('{text}')",
                    f"button:has-text('{text}')",
                    f"[role='tab']:has-text('{text}')",
                    f"[role='button']:has-text('{text}')",
                ]
                # 先在面板 root 试一次（允许点击 theme-arco-typography 等）
                if await self._click_first(panel_root, selectors_panel, timeout=1500):
                    picked = True
                    break
                # 再在所有 root 中兜底（避免点到面板外展示性文本）
                for r in all_roots:
                    if await self._click_first(r, selectors_global, timeout=1200):
                        picked = True
                        break
                if picked:
                    break
            if not picked:
                return DatePickResult(success=False, option=option, message="shortcut not found")

            try:
                await page.wait_for_timeout(800)
            except Exception:
                pass
            return DatePickResult(success=True, option=option, message="ok")
        except Exception as e:
            if self.logger:
                self.logger.error(f"[TiktokDatePicker] failed: {e}")
            return DatePickResult(success=False, option=option, message=str(e))

    # -------- extensions for custom/week index (for future use) --------
    async def select_custom_range(self, page: Any, start: date, end: date) -> bool:
        """
        切到“自定义”并选择起止日期（best-effort, 更稳健）。
        步骤：确保面板 -> 切到自定义(可选) -> 锁定左右月份容器 -> 点击起/止日期 -> 点击“确定/应用”。
        对齐 TikTok Arco 双月面板，优先在对应月份容器内定位日期，避免误点灰色日期。
        """
        try:
            def log(msg: str) -> None:
                try:
                    (self.logger.info if self.logger else print)(f"[TiktokDatePicker] custom-range: {msg}")
                except Exception:
                    pass

            # 1) 确保面板已打开
            if not self._open_panel(page):
                log("open panel failed")
                return False
            f = self._find_panel_root(page) or self._first_frame(page) or page

            # 1.1 兜底：在服务表现页且是“同一日”时，优先改走“自然日”路径，避免停留在“自定义”模式下点单日
            try:
                cur_url = ""
                try:
                    cur_url = page.url or ""
                except Exception:
                    cur_url = ""
                is_same_day = (start == end)
                if is_same_day and ("service-analytics" in cur_url):
                    try:
                        # 面板上必须存在 m4b 的 range-mode 才认为该策略可用
                        nat_btn = f.locator(
                            ".theme-m4b-date-picker-range-mode .theme-m4b-date-picker-range-mode-item[daterangekey='natural_day']"
                        )
                        if nat_btn and nat_btn.count() > 0 and nat_btn.first.is_visible():
                            if self.logger:
                                self.logger.info("[TiktokDatePicker] custom-range: redirect to select_natural_day(same-day on service-analytics)")
                            return self.select_natural_day(page, start)
                    except Exception:
                        pass
            except Exception:
                pass

            # 2) 切到“自定义”tab（若存在）
            try:
                f.get_by_role("tab", name="自定义").click(timeout=1200)
                log("switched to 自定义 tab")
            except Exception:
                try:
                    f.get_by_role("tab", name="Custom").click(timeout=1200)
                    log("switched to Custom tab")
                except Exception:
                    pass

            # 统一规范：将 end 归一化为“昨天”（避免选择到未统计的当天导致禁用/空数据）
            try:
                if end >= date.today():
                    end = date.today() - timedelta(days=1)
            except Exception:
                pass

            # 统一：优先采用面板对齐+点击；输入框仅作为最后兜底
            try:
                span = (end - start).days if (end and start) else None
            except Exception:
                span = None
            try:
                from datetime import timedelta as _td
                is_yesterday = (date.today() - _td(days=1)) == end
            except Exception:
                is_yesterday = False

            ym_start = (start.year, f"{start.month:02d}")
            ym_end = (end.year, f"{end.month:02d}")


            def month_header_texts(y: int, m2: str) -> list[str]:
                # 兼容多种标题格式："2025-09"、"2025 - 09"、"2025/09"、"2025.09"
                return [
                    f"{y}-{m2}",
                    f"{y} - {m2}",
                    f"{y}/{m2}",
                    f"{y}.{m2}",
                ]

            def month_container(y: int, m2: str, *, prefer_right: bool = False):
                # 依据 header 文本锁定该月份的面板容器（多格式容错）
                try:
                    for hdr in month_header_texts(y, m2):
                        try:
                            header = f.locator(
                                ".theme-arco-picker-panel:has(.theme-arco-picker-header-value:has-text('{}'))".format(hdr)
                            )
                            if header.count() > 0 and header.first.is_visible():
                                return header.first
                        except Exception:
                            continue
                except Exception:
                    pass
                # fallback: 若无法由 header 锁定，则在双面板中优先取左/右
                try:
                    panels = f.locator(".theme-arco-picker-panel")
                    if panels.count() >= 2:
                        return panels.nth(1 if prefer_right else 0)
                except Exception:
                    pass
                return f

            def click_day(container, day: int, *, require_enabled: bool = False) -> bool:
                selectors = []
                # 优先：只点击未禁用的日期单元格（防止点到灰禁用的右侧面板）
                if require_enabled:
                    selectors.append(
                        lambda: container.locator(
                            ".theme-arco-picker-cell:not(.theme-arco-picker-cell-disabled):has-text('{}')".format(day)
                        ).first
                    )
                    # 更贴近 DOM 的值节点（date-value），不少实现点击该节点也可选中
                    selectors.append(
                        lambda: container.locator(
                            ".theme-arco-picker-cell:not(.theme-arco-picker-cell-disabled) .theme-arco-picker-date-value:has-text('{}')".format(day)
                        ).first
                    )
                # 兜底：常规可交互元素（不强制未禁用）
                selectors.extend([
                    lambda: container.get_by_role("gridcell", name=str(day)).first,
                    lambda: container.get_by_role("button", name=str(day)).first,
                    lambda: container.locator(".theme-arco-picker-date-value:has-text('{}')".format(day)).first,
                    lambda: container.locator(".theme-arco-picker-cell:has-text('{}')".format(day)).first,
                ])
                for fn in selectors:
                    try:
                        el = fn()
                        if el and el.count() > 0 and el.is_visible():
                            # 如果检测到被禁用则跳过
                            try:
                                cls = el.get_attribute("class") or ""
                                if require_enabled and "picker-cell-disabled" in cls:
                                    continue
                            except Exception:
                                pass
                            try:
                                el.click(timeout=1500)
                            except Exception:
                                try:
                                    el.dblclick(timeout=1500)
                                except Exception:
                                    continue
                            return True
                    except Exception:
                        continue
                return False

            def month_visible(y: int, m2: str) -> bool:
                try:
                    for hdr in month_header_texts(y, m2):
                        try:
                            if f.locator(
                                ".theme-arco-picker-header-value:has-text('{}')".format(hdr)
                            ).first.is_visible():
                                return True
                        except Exception:
                            continue
                    return False
                except Exception:
                    return False

            def nav_next(count: int = 1) -> None:
                for _ in range(max(1, count)):
                    clicked = False
                    # 1) 官方类名（通常为月份箭头）
                    try:
                        f.locator(".theme-arco-picker-header-icon-btn-next").first.click(timeout=600)
                        clicked = True
                    except Exception:
                        pass
                    # 2) 操作区第3个按钮（›，月份右箭头），避免点击年份 »
                    if not clicked:
                        try:
                            ops = f.locator(".theme-arco-picker-header-operations button")
                            if ops.count() >= 3:
                                ops.nth(2).click(timeout=600)
                                clicked = True
                        except Exception:
                            pass
                    # 3) 语义按钮兜底（›）
                    if not clicked:
                        try:
                            f.get_by_role("button", name="›").click(timeout=600)
                            clicked = True
                        except Exception:
                            pass
                    # 4) header 内图标精确索引（第3个 ≈ ›），避免点击年份 »
                    if not clicked:
                        try:
                            hdr = f.locator(".theme-arco-picker-header, .theme-arco-picker-header-operations").first
                            if hdr and hdr.is_visible():
                                icons = hdr.locator("img, svg, i, span[role='img']").all()
                                if len(icons) >= 3:
                                    icons[2].click(timeout=600)
                                    clicked = True
                        except Exception:
                            pass

            def nav_prev(count: int = 1) -> None:
                for _ in range(max(1, count)):
                    clicked = False
                    # 1) 官方类名（通常为月份箭头）
                    try:
                        f.locator(".theme-arco-picker-header-icon-btn-prev").first.click(timeout=600)
                        clicked = True
                    except Exception:
                        pass
                    # 2) 操作区第2个按钮（‹，月份左箭头），避免点击年份 «
                    if not clicked:
                        try:
                            ops = f.locator(".theme-arco-picker-header-operations button")
                            if ops.count() >= 2:
                                ops.nth(1).click(timeout=600)
                                clicked = True
                        except Exception:
                            pass
                    # 3) 语义按钮兜底（‹）
                    if not clicked:
                        try:
                            f.get_by_role("button", name="‹").click(timeout=600)
                            clicked = True
                        except Exception:
                            pass
                    # 4) header 内图标精确索引（第2个 ≈ ‹），避免点击年份 «
                    if not clicked:
                        try:
                            hdr = f.locator(".theme-arco-picker-header, .theme-arco-picker-header-operations").first
                            if hdr and hdr.is_visible():
                                icons = hdr.locator("img, svg, i, span[role='img']").all()
                                if len(icons) >= 2:
                                    icons[1].click(timeout=600)
                                    clicked = True
                        except Exception:
                            pass


            # 兜底：直接向输入框填充起止日期（保留为最后一层，不影响首选点击流程）
            def try_fill_inputs() -> bool:
                try:
                    inputs = f.locator(".theme-arco-picker-input-range input")
                    if inputs.count() >= 2:
                        fmt_candidates = ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%b %d, %Y"]
                        for fmt in fmt_candidates:
                            try:
                                s_val = start.strftime(fmt)
                                e_val = end.strftime(fmt)
                                el0 = inputs.nth(0)
                                el0.click(timeout=800)
                                try:
                                    el0.press("Control+A")
                                except Exception:
                                    pass
                                try:
                                    el0.press("Meta+A")
                                except Exception:
                                    pass
                                el0.fill(s_val, timeout=1200)
                                el1 = inputs.nth(1)
                                el1.click(timeout=800)
                                try:
                                    el1.press("Control+A")
                                except Exception:
                                    pass
                                try:
                                    el1.press("Meta+A")
                                except Exception:
                                    pass
                                el1.fill(e_val, timeout=1200)
                                # 触发应用
                                for label in ["确定", "应用", "确认", "完成", "Apply", "OK", "Done"]:
                                    try:
                                        f.get_by_role("button", name=label).click(timeout=500)
                                        break
                                    except Exception:
                                        continue
                                try:
                                    page.wait_for_timeout(300)
                                except Exception:
                                    pass
                                cur_s = inputs.nth(0).input_value()
                                cur_e = inputs.nth(1).input_value()
                                if cur_s and cur_e:
                                    log(f"try-fill success fmt={fmt} -> {cur_s} ~ {cur_e}")
                                    return True
                            except Exception:
                                continue
                except Exception:
                    pass
                return False

            # 强制填充（移除 readonly 并触发事件）。优先用于“同日”选择，避免面板频繁重排导致闪烁。
            def force_fill_inputs_single_day() -> bool:
                try:
                    inputs = f.locator(".theme-arco-picker-input-range input")
                    if inputs.count() >= 2:
                        # 多种格式尝试，兼容英文/数字化显示
                        candidates = [
                            start.strftime("%Y-%m-%d"),
                            start.strftime("%Y/%m/%d"),
                            start.strftime("%Y.%m.%d"),
                            start.strftime("%b %d, %Y"),  # e.g., Aug 16, 2025
                        ]
                        for val in candidates:
                            try:
                                for i in range(2):
                                    el = inputs.nth(i)
                                    # 去掉 readonly，直接设置值并派发事件
                                    el.evaluate(
                                        "(e, v) => { e.removeAttribute('readonly'); e.focus(); e.value = v; e.dispatchEvent(new Event('input', {bubbles:true})); e.dispatchEvent(new Event('change', {bubbles:true})); }",
                                        val,
                                    )
                                # 点击应用/确定
                                for label in ["确定", "应用", "确认", "完成", "Apply", "OK", "Done"]:
                                    try:
                                        f.get_by_role("button", name=label).click(timeout=500)
                                        break
                                    except Exception:
                                        continue
                                try:
                                    page.wait_for_timeout(350)
                                except Exception:
                                    pass
                                # 读取一次实际展示值（可能会被本地化为 Sep 16, 2025 等，只要非空即认定成功）
                                cur_s = inputs.nth(0).input_value()
                                cur_e = inputs.nth(1).input_value()
                                if cur_s and cur_e:
                                    log(f"force-fill(single-day) success -> {cur_s} ~ {cur_e}")
                                    return True
                            except Exception:
                                continue
                except Exception:
                    pass
                return False

            # 新对齐器：根据“当前右侧标题”与目标截止月比较，决定 <- 或 ->，每步后校验
            def _parse_header_month(idx: int) -> tuple[int, int] | None:
                try:
                    import re
                    txt = panels.nth(idx).locator(".theme-arco-picker-header-value").first.inner_text(timeout=800)
                    s = (txt or "").replace("\xa0", " ")
                    m = re.search(r"(\d{4}).{0,3}(\d{1,2})", s)
                    if m:
                        return int(m.group(1)), int(m.group(2))
                except Exception:
                    pass
                return None

            def _cmp(a: tuple[int, int], b: tuple[int, int]) -> int:
                av, bv = a[0] * 12 + a[1], b[0] * 12 + b[1]
                return (av > bv) - (av < bv)

            def ensure_alignment(target_left: tuple[int, int], target_right: tuple[int, int], max_steps: int = 24) -> bool:
                stagnant = 0
                nochange = 0
                last_pair: tuple[tuple[int,int]|None, tuple[int,int]|None] | None = None
                for _ in range(max_steps):
                    cur_left = _parse_header_month(0)
                    cur_right = _parse_header_month(1)
                    if cur_left and cur_right and (cur_left == target_left and cur_right == target_right):
                        return True

                    # 决策方向：优先右侧对齐到截止月；无法识别则不点击，等待并重试
                    direction = None
                    if cur_right is not None:
                        cmp_r = _cmp(cur_right, target_right)
                        if cmp_r > 0:
                            direction = "prev"
                        elif cmp_r < 0:
                            direction = "next"
                    if direction is None and cur_left is not None:
                        cmp_l = _cmp(cur_left, target_left)
                        if cmp_l > 0:
                            direction = "prev"
                        elif cmp_l < 0:
                            direction = "next"

                    if direction is None:
                        try:
                            page.wait_for_timeout(120)
                        except Exception:
                            pass
                        stagnant += 1
                        if stagnant >= 5:
                            break
                        continue

                    prev_pair = (cur_left, cur_right)
                    if direction == "prev":
                        nav_prev()
                    else:
                        nav_next()
                    try:
                        page.wait_for_timeout(160)
                    except Exception:
                        pass

                    now_pair = (_parse_header_month(0), _parse_header_month(1))
                    if now_pair == prev_pair:
                        # 尝试反向一次
                        nochange += 1
                        if direction == "prev":
                            nav_next()
                        else:
                            nav_prev()
                        try:
                            page.wait_for_timeout(160)
                        except Exception:
                            pass
                        now_pair = (_parse_header_month(0), _parse_header_month(1))
                        if now_pair == prev_pair:
                            stagnant += 1
                        else:
                            stagnant = 0
                    else:
                        stagnant = 0

                    last_pair = now_pair
                    if stagnant >= 5:
                        break

                # 结束前再核验一次
                return _parse_header_month(0) == target_left and _parse_header_month(1) == target_right

            tgt_left = (start.year, start.month)
            tgt_right = (end.year, end.month)

            # 优先：同日范围用“强制填充”规避 UI 抽搐
            if start == end:
                if force_fill_inputs_single_day():
                    return True

            # 同月范围（含“昨天”等单日）：跳过强制双面板对齐，直接在可见月份容器内点击
            if ym_start != ym_end:
                if not ensure_alignment(tgt_left, tgt_right):
                    log(f"start month not visible after alignment: {(tgt_left[0], f'{tgt_left[1]:02d}')} | right={(tgt_right[0], f'{tgt_right[1]:02d}')} ")
                    # 兜底：直接填充输入框（最后一层）
                    if try_fill_inputs():
                        return True
                    return False

            # 4) 点击起/止日期（强制跨月时左=起始月，右=截止月）
            panels = f.locator(".theme-arco-picker-panel")

            def header_matches(idx: int, y: int, m2: str) -> bool:
                """更稳健地匹配面板标题月份，容忍 NBSP/窄空格/中英文格式。

                idx: 0=左面板, 1=右面板
                y: 年, m2: 'MM'
                """
                try:
                    import re

                    hdr = panels.nth(idx).locator(".theme-arco-picker-header-value").first
                    txt = hdr.inner_text(timeout=800)

                    def norm(s: str) -> str:
                        # 统一各种空白与分隔符，转成 y-m 的无空格格式
                        s = (s or "").replace("\xa0", " ").strip()
                        s = re.sub(r"[\u2000-\u200b\u202f]", "", s)  # 窄空格/零宽空格
                        s = s.replace("年", "-").replace("月", "")
                        s = s.replace("/", "-").replace(".", "-")
                        s = re.sub(r"\s*-\s*", "-", s)
                        s = re.sub(r"\s+", "", s)
                        return s

                    n_txt = norm(txt)
                    # 同时支持：2025-09 / 2025 - 09 / 2025/09 / 2025.09 / 2025年9月 / 2025年09月
                    patterns = month_header_texts(y, m2) + [f"{y}年{int(m2)}月", f"{y}年{m2}月"]
                    for t in patterns:
                        if norm(t) in n_txt:
                            return True
                except Exception:
                    return False
                return False

            # 起始日点击前，先显式激活“开始日期”输入框，避免控件仍处于“结束日期/快捷范围”模式
            try:
                page.get_by_role("textbox", name="开始日期").click(timeout=800)
            except Exception:
                try:
                    page.get_by_role("textbox", name="Start date").click(timeout=800)
                except Exception:
                    try:
                        f.locator(".theme-arco-picker-input-range input").nth(0).click(timeout=800)
                    except Exception:
                        pass
            # 起始日点击（优先选中目标月份容器）
            start_container = month_container(*ym_start)
            ok_start = click_day(start_container, start.day, require_enabled=True)
            if not ok_start:
                # 放宽限制再试一次（允许点击已选中的单元格 / date-value 节点）
                ok_start = click_day(start_container, start.day, require_enabled=False)
                if not ok_start:
                    try:
                        el = start_container.locator(
                            ".theme-arco-picker-date-value:has-text('{}')".format(start.day)
                        ).first
                        if el and el.count() > 0 and el.is_visible():
                            try:
                                el.click(timeout=1200)
                            except Exception:
                                el.dblclick(timeout=1200)
                            ok_start = True
                    except Exception:
                        pass
            if not ok_start:
                log(f"start day click failed: {start}")
                # Fallback: try direct input filling
                if try_fill_inputs():
                    return True
                return False

            if start == end or ym_start == ym_end:
                # 同日或同月：再次点击同面板/同月
                try:
                    page.wait_for_timeout(300)
                except Exception:
                    pass
                if not click_day(start_container, end.day, require_enabled=True):
                    # 有些实现需要先激活“结束日期”输入框，再点截止日
                    try:
                        page.get_by_role("textbox", name="结束日期").click(timeout=800)
                    except Exception:
                        try:
                            page.get_by_role("textbox", name="End date").click(timeout=800)
                        except Exception:
                            try:
                                f.locator(".theme-arco-picker-input-range input").nth(1).click(timeout=800)
                            except Exception:
                                pass
                    try:
                        page.wait_for_timeout(200)
                    except Exception:
                        pass
                    # 再次在当前容器尝试
                    ok2 = click_day(start_container, end.day, require_enabled=True)
                    if not ok2:
                        # 放宽限制再试一次（允许点击已选中的单元格 / 直接点击 date-value）
                        ok2 = click_day(start_container, end.day, require_enabled=False)
                        if not ok2:
                            try:
                                el = start_container.locator(
                                    ".theme-arco-picker-date-value:has-text('{}')".format(end.day)
                                ).first
                                if el and el.count() > 0 and el.is_visible():
                                    try:
                                        el.click(timeout=1200)
                                    except Exception:
                                        el.dblclick(timeout=1200)
                                    ok2 = True
                            except Exception:
                                ok2 = False
                    if not ok2:
                        # 兜底：尝试在另一侧面板点击
                        try:
                            alt = panels.nth(1) if start_container == panels.nth(0) else panels.nth(0)
                            if not click_day(alt, end.day, require_enabled=True):
                                raise Exception("alt panel click failed")
                        except Exception:
                            log("second click for same-month/day range failed")
                            if try_fill_inputs():
                                return True
                            return False
            else:
                # 先激活“结束日期”输入框，很多实现会以当前焦点决定右侧面板的可交互状态
                try:
                    page.get_by_role("textbox", name="End date").click(timeout=800)
                except Exception:
                    try:
                        page.get_by_role("textbox", name="结束日期").click(timeout=800)
                    except Exception:
                        try:
                            f.locator(".theme-arco-picker-input-range input").nth(1).click(timeout=800)
                        except Exception:
                            pass

                # 再校验对齐（防护：起始点击或聚焦后 UI 可能轻微重排）
                tgt_left = (start.year, start.month)
                tgt_right = (end.year, end.month)
                if not ensure_alignment(tgt_left, tgt_right):
                    try:
                        lh = panels.nth(0).locator(".theme-arco-picker-header-value").first.inner_text(timeout=400)
                        rh = panels.nth(1).locator(".theme-arco-picker-header-value").first.inner_text(timeout=400)
                        log(f"panels not aligned L={ym_start} R={ym_end} | headers=('{lh}' , '{rh}')")
                    except Exception:
                        log(f"panels not aligned L={ym_start} R={ym_end}")
                    if try_fill_inputs():
                        return True
                    return False

                # 明确在右侧“截止月”容器中点击截止日（先按 header 锁定容器，再点击）
                try:
                    end_container = month_container(*ym_end, prefer_right=True)
                    if not click_day(end_container, end.day, require_enabled=True):
                        raise Exception("end day click failed in header-locked container")
                except Exception:
                    # 兜底1：直接使用右侧面板
                    try:
                        end_container = panels.nth(1)
                        if not click_day(end_container, end.day, require_enabled=True):
                            raise Exception("end day click failed in right panel")
                    except Exception:
                        # 兜底2：全局按文本点击
                        tried = False
                        for scope in (f, page):
                            try:
                                scope.get_by_text(str(end.day), exact=True).first.click(timeout=1200)
                                tried = True
                                break
                            except Exception:
                                continue
                        if not tried:
                            log(f"end day click failed: {end}")
                            # 最终兜底：直接填充输入框
                            if try_fill_inputs():
                                return True
                            return False

            # 5) 点击确认按钮（若存在）
            for label in ["确定", "应用", "确认", "完成", "Apply", "OK", "Done"]:
                try:
                    f.get_by_role("button", name=label).click(timeout=500)
                    log(f"clicked confirm: {label}")
                    break
                except Exception:
                    continue

            try:
                page.wait_for_timeout(500)
            except Exception:
                pass
            try:
                inputs = f.locator(".theme-arco-picker-input-range input")
                if inputs.count() >= 2:
                    s_val = inputs.nth(0).input_value()
                    e_val = inputs.nth(1).input_value()
                    if not s_val or not e_val:
                        log("input values missing after selection")
                        return False
            except Exception:
                pass
            return True
        except Exception as _e:
            try:
                if self.logger:
                    self.logger.warning(f"[TiktokDatePicker] custom-range failed: {_e}")
            except Exception:
                pass
            return False

    async def select_week_index(self, page: Any, year: int, month: int, week_idx: int) -> bool:
        """
        某月第 N 周（周一~周日），内部转自定义区间。N 从 1 开始。
        """
        try:
            first = date(year, month, 1)
            # 本月第一个周一
            offset = (0 - first.weekday()) % 7  # 周一=0
            monday = first + timedelta(days=offset)
            start_d = monday + timedelta(days=7 * (week_idx - 1))
            end_d = start_d + timedelta(days=6)
            return self.select_custom_range(page, start_d, end_d)
        except Exception:
            return False

    async def select_natural_day(self, page: Any, target_day: date) -> bool:
        """服务表现页面的“自然日”单日选择。
        流程：打开面板 -> 点击“自然日”Tab -> 校验/对齐月份 -> 点击当月日历中的目标日期。
        只做 UI 操作，不写入输入框。
        """
        try:
            # 1) 确保日期面板已打开
            if not self._open_panel(page):
                return False

            f = self._find_panel_root(page) or self._first_frame(page) or page

            # 2) 切换到“自然日”模式（service-analytics 使用 m4b 分段按钮）。若无法成功切换，直接返回失败，避免在“自定义”下继续点击日期。
            def _log(msg: str) -> None:
                try:
                    (self.logger.info if self.logger else print)(f"[TiktokDatePicker] natural-day: {msg}")
                except Exception:
                    pass
            switched = False
            roots = [f]
            try:
                roots_ext = self._all_roots(page)
                for r in roots_ext:
                    if r not in roots:
                        roots.append(r)
            except Exception:
                pass

            # 2.1 精确属性定位（你提供的 DOM）
            for r in roots:
                try:
                    nat = r.locator(
                        ".theme-m4b-date-picker-range-mode .theme-m4b-date-picker-range-mode-item[daterangekey='natural_day']"
                    ).first
                    if nat and nat.count() > 0 and nat.is_visible():
                        cls = nat.get_attribute("class") or ""
                        _log(f"found m4b button, class='{cls}'")
                        if "theme-m4b-date-picker-range-mode-item-active" not in cls:
                            nat.click(timeout=1200)
                        for _ in range(10):
                            try:
                                cls = nat.get_attribute("class") or ""
                                if "theme-m4b-date-picker-range-mode-item-active" in cls:
                                    switched = True
                                    break
                            except Exception:
                                pass
                            try:
                                page.wait_for_timeout(120)
                            except Exception:
                                pass
                        if switched:
                            break
                except Exception:
                    continue

            # 2.2 文本/按钮兜底
            if not switched:
                for r in roots:
                    for sel in (
                        "div.theme-m4b-date-picker-range-mode-item:has-text('自然日')",
                        "button:has-text('自然日')",
                        "[role='button']:has-text('自然日')",
                    ):
                        try:
                            el = r.locator(sel).first
                            if el and el.count() > 0 and el.is_visible():
                                el.click(timeout=1000)
                                page.wait_for_timeout(150)
                                try:
                                    nat2 = r.locator(
                                        ".theme-m4b-date-picker-range-mode .theme-m4b-date-picker-range-mode-item[daterangekey='natural_day']"
                                    ).first
                                    cls2 = nat2.get_attribute("class") or ""
                                    if "theme-m4b-date-picker-range-mode-item-active" in cls2:
                                        switched = True
                                        break
                                except Exception:
                                    pass
                        except Exception:
                            continue
                    if switched:
                        break

            if not switched:
                _log("FAILED to switch to 自然日; abort to avoid using 自定义")
                return False

            # 3) 读取当前月份标题，并与目标月份对齐
            import re

            def parse_header_y_m() -> tuple[int, int] | None:
                try:
                    hdr = f.locator(".theme-arco-picker-header-value").first
                    if hdr and hdr.is_visible():
                        txt = (hdr.inner_text(timeout=800) or "").replace("\xa0", " ")
                        m = re.search(r"(\d{4}).{0,3}(\d{1,2})", txt)
                        if m:
                            return int(m.group(1)), int(m.group(2))
                except Exception:
                    pass
                return None

            def nav_prev_once() -> bool:
                for sel in (
                    ".theme-arco-picker-header-icon-btn-prev",
                    ".theme-arco-picker-header-operations button:nth-child(2)",  # ‹ 月份左箭头
                ):
                    try:
                        f.locator(sel).first.click(timeout=600)
                        return True
                    except Exception:
                        continue
                for nm in ("‹",):
                    try:
                        f.get_by_role("button", name=nm).click(timeout=600)
                        return True
                    except Exception:
                        continue
                return False

            def nav_next_once() -> bool:
                for sel in (
                    ".theme-arco-picker-header-icon-btn-next",
                    ".theme-arco-picker-header-operations button:nth-child(3)",  # › 月份右箭头
                ):
                    try:
                        f.locator(sel).first.click(timeout=600)
                        return True
                    except Exception:
                        continue
                for nm in ("›",):
                    try:
                        f.get_by_role("button", name=nm).click(timeout=600)
                        return True
                    except Exception:
                        continue
                return False

            def cmp_month(a: tuple[int, int], b: tuple[int, int]) -> int:
                av, bv = a[0] * 12 + a[1], b[0] * 12 + b[1]
                return (av > bv) - (av < bv)

            target_ym = (target_day.year, target_day.month)
            for _ in range(24):
                cur = parse_header_y_m()
                if cur is None:
                    try:
                        page.wait_for_timeout(200)
                    except Exception:
                        pass
                    continue
                if cur == target_ym:
                    break
                direction = cmp_month(cur, target_ym)
                if direction > 0:
                    nav_prev_once()
                elif direction < 0:
                    nav_next_once()
                try:
                    page.wait_for_timeout(160)
                except Exception:
                    pass
            # 再核验一次；打印更直观的月份确认日志
            cur = parse_header_y_m()
            def _ym_str(t: tuple[int,int] | None) -> str:
                try:
                    return f"{t[0]}-{t[1]:02d}" if t else "?"
                except Exception:
                    return "?"
            aligned = (cur == target_ym)
            _log(f"header_check current_header={_ym_str(cur)}, target={_ym_str(target_ym)}, aligned={aligned}")
            if not aligned:
                _log(f"header not matched (cur={cur}, target={target_ym}), fallback to global day search")

            # 4) 点击日期（优先选中未禁用单元格；双面板全量搜索）
            def click_in_container(container, day_val: int) -> bool:
                # 优先命中未禁用
                for sel in (
                    f".theme-arco-picker-cell:not(.theme-arco-picker-cell-disabled) .theme-arco-picker-date-value:has-text('{day_val}')",
                    f".theme-arco-picker-cell:not(.theme-arco-picker-cell-disabled):has-text('{day_val}')",
                ):
                    try:
                        el = container.locator(sel).first
                        if el and el.count() > 0 and el.is_visible():
                            el.click(timeout=1200)
                            return True
                    except Exception:
                        continue
                # 兜底：通用 gridcell/button/text
                for q in (
                    container.get_by_role("gridcell", name=str(day_val)).first,
                    container.get_by_role("button", name=str(day_val)).first,
                    container.get_by_text(str(day_val), exact=True).first,
                ):
                    try:
                        if q and q.count() > 0 and q.is_visible():
                            q.click(timeout=1200)
                            return True
                    except Exception:
                        continue
                return False

            day = target_day.day
            panels = f.locator(".theme-arco-picker-panel")
            clicked = False
            try:
                # 左 -> 右尝试
                if panels.count() > 0:
                    if click_in_container(panels.nth(0), day):
                        clicked = True
                    elif panels.count() >= 2 and click_in_container(panels.nth(1), day):
                        clicked = True
            except Exception:
                pass
            if not clicked:
                # 最终兜底：直接在面板根内搜索
                clicked = click_in_container(f, day)
            if not clicked:
                _log("FAILED to click target day in natural-day mode")
                return False

            # 5) 可选：点击“确定/应用/OK”（若存在即点一下）
            for label in ("确定", "应用", "确认", "完成", "Apply", "OK", "Done"):
                try:
                    f.get_by_role("button", name=label).click(timeout=400)
                    break
                except Exception:
                    continue
            try:
                page.wait_for_timeout(300)
            except Exception:
                pass
            return True
        except Exception:
            return False

