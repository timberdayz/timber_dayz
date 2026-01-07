from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional
import json

from modules.components.base import ExecutionContext
from modules.components.export.base import ExportComponent, ExportResult, ExportMode, build_standard_output_root
from modules.platforms.shopee.components.products_config import ProductsSelectors
from modules.utils.path_sanitizer import safe_slug, build_output_path, build_filename


class ShopeeProductsExport(ExportComponent):
    """Shopee 商品表现（Products）导出组件

    - 只依赖 products_config 中的 URL/选择器
    - 统一落盘到 temp/outputs/shopee/<账号>/<店铺>/products/<粒度>/
    - 优先 UI 导出（点击→等待→下载），后续可扩展 API 备选
    """

    # Component metadata
    platform = "shopee"
    component_type = "export"
    data_domain = "products"

    def __init__(self, ctx: ExecutionContext, selectors: Optional[ProductsSelectors] = None) -> None:
        super().__init__(ctx)
        self.sel = selectors or ProductsSelectors()

    def _write_manifest(self, target: Path, cfg: dict, account_label: str, shop_name: str) -> None:
        """
        在导出文件旁生成元数据清单（.json），与服务表现保持一致字段
        """
        try:
            from datetime import datetime
            meta = {
                "platform": self.ctx.platform,
                "account_label": account_label,
                "shop_name": shop_name,
                "shop_id": (self.ctx.config or {}).get("shop_id"),
                "region": (self.ctx.account or {}).get("region"),
                "data_type": "products",
                "granularity": (cfg or {}).get("granularity"),
                "start_date": (cfg or {}).get("start_date"),
                "end_date": (cfg or {}).get("end_date"),
                "exported_at": datetime.now().isoformat(),
                "file_path": str(target),
            }
            manifest_path = Path(str(target) + ".json")
            manifest_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        try:
            account = self.ctx.account
            cfg = self.ctx.config or {}
            # 店铺命名优先级：菜单显示名 > 账号里显式的display/menu字段 > store_name > 配置里的shop_name
            shop_name = (
                account.get("menu_display_name")
                or account.get("menu_name")
                or account.get("selected_shop_name")
                or account.get("display_shop_name")
                or account.get("display_name")
                or account.get("store_name")
                or cfg.get("shop_name")
                or "unknown_shop"
            )
            # 账号标签仍保持 label 优先，回退到 store_name/username，避免路径大范围变化
            account_label = account.get("label") or account.get("store_name") or account.get("username", "unknown")

            # 0) 轻量弹窗关闭（若存在）
            try:
                for sel in getattr(self.sel, 'popup_close_buttons', []) or []:
                    try:
                        loc = page.locator(sel)
                        if await loc.count() > 0 and await loc.first.is_visible():
                            if self.logger:
                                self.logger.info(f"[ShopeeProductsExport] 关闭弹窗: {sel}")
                            await loc.first.click()
                            await page.wait_for_timeout(200)
                    except Exception:
                        continue
            except Exception:
                pass

            # 0.5) 日期选择：与组件化/服务表现保持一致（基于 DatePicker 配方）
            try:
                gran_for_pick = (cfg.get("granularity") or "").lower()
                from modules.components.date_picker.base import DateOption
                from modules.platforms.shopee.components.date_picker import ShopeeDatePicker
                opt = None
                if gran_for_pick in ("day", "daily", "d"):
                    opt = DateOption.YESTERDAY
                elif gran_for_pick in ("weekly", "week", "w", "last_7_days"):
                    opt = DateOption.LAST_7_DAYS
                elif gran_for_pick in ("monthly", "month", "m", "last_30_days"):
                    opt = DateOption.LAST_30_DAYS
                if opt is not None:
                    if self.logger:
                        self.logger.info(f"[ShopeeProductsExport] 选择时间范围: {opt.value}")
                    _dp = ShopeeDatePicker(self.ctx)
                    _res = await _dp.run(page, opt)
                    await page.wait_for_timeout(600)
            except Exception:
                # 日期选择失败不阻断导出，后续依靠文件名区间校验兜底
                pass

            # 1) 确认页面加载完成（探针）
            for probe in self.sel.data_ready_probes:
                try:
                    if await page.locator(probe).first.is_visible():
                        break
                except Exception:
                    continue
            await page.wait_for_timeout(500)

            # 2) 点击导出
            clicked = False
            for btn in self.sel.export_buttons:
                try:
                    loc = page.locator(btn)
                    if await loc.count() > 0 and await loc.first.is_visible():
                        if self.logger:
                            self.logger.info(f"[ShopeeProductsExport] 点击导出按钮: {btn}")
                        await loc.first.click()
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                return ExportResult(False, None, "未找到导出按钮")

            await page.wait_for_timeout(1000)

            # 3) 触发后等待“最新导出记录”就绪，优先下载最新，避免点到历史记录
            from modules.core.config import get_config_value

            # 可选：若出现"生成报告/立即生成"等按钮，尝试点击以开始生成
            try:
                await self._maybe_generate_report(page)
            except Exception:
                pass

            if self.logger:
                self.logger.info("[ShopeeProductsExport] 已触发导出，等待生成/下载入口出现...")

            # 统一输出目录（预先计算，支持 UI 监听与文件系统兜底）
            gran = cfg.get("granularity") or "manual"
            start_date = cfg.get("start_date")
            end_date = cfg.get("end_date")
            out_root = build_standard_output_root(self.ctx, data_type="products", granularity=gran)
            out_root.mkdir(parents=True, exist_ok=True)

            # 记录点击前的下载目录文件列表（用于文件系统兜底）
            try:
                pre_files = set(out_root.glob("*"))
            except Exception:
                pre_files = set()

            # 等待"最新记录"变为可下载
            wait_timeout = int(get_config_value('data_collection', 'download.wait_timeout', 30))
            preferred_btn = await self._wait_for_latest_export_ready(page, timeout=wait_timeout)

            # 4) 下载：优先点击"最新记录"的下载按钮（UI监听60s）
            if preferred_btn:
                try:
                    from datetime import datetime as _dt
                    async with page.expect_download(timeout=60000) as dl_info:
                        await preferred_btn.click()
                    download = dl_info.value

                    tmp_name = download.suggested_filename or "products.xlsx"
                    tmp_path = out_root / tmp_name
                    await download.save_as(str(tmp_path))

                    from datetime import datetime
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = build_filename(
                        ts=ts,
                        account_label=account_label,
                        shop_name=shop_name,
                        data_type="products",
                        granularity=gran,
                        start_date=start_date,
                        end_date=end_date,
                        suffix=tmp_path.suffix,
                    )
                    target = out_root / filename
                    try:
                        tmp_path.rename(target)
                    except Exception:
                        import shutil
                        shutil.copy2(tmp_path, target)
                        try:
                            tmp_path.unlink(missing_ok=True)
                        except Exception:
                            pass

                    try:
                        self._write_manifest(target, cfg, account_label, shop_name)
                    except Exception:
                        pass
                    if self.logger:
                        self.logger.info(f"下载完成(UI): {target}")
                    print(f"\n[OK] 导出成功: {target}")
                    return ExportResult(True, "下载完成(UI)", None, str(target))
                except Exception as e:
                    # UI监听未命中 → 文件系统兜底
                    if self.logger:
                        self.logger.info(f"[ShopeeProductsExport] UI下载监听超时，启用文件系统兜底: {e}")

            # 4.1 兜底一：尝试直接点击页面上可见的"下载"按钮（与服务表现一致）
            try:
                from modules.core.config import get_config_value as _cfg
                for btn_sel in self.sel.download_buttons:
                    try:
                        loc = page.locator(btn_sel)
                        if await loc.count() > 0 and await loc.first.is_visible():
                            if self.logger:
                                self.logger.info(f"[ShopeeProductsExport] 点击下载按钮: {btn_sel}")

                            # 点击并监听下载
                            async with page.expect_download(timeout=60000) as dl_info:
                                await loc.first.click()
                            download = dl_info.value

                            tmp_name = download.suggested_filename or "products.xlsx"
                            tmp_path = out_root / tmp_name
                            await download.save_as(str(tmp_path))

                            from datetime import datetime as _dt
                            ts = _dt.now().strftime("%Y%m%d_%H%M%S")
                            filename = build_filename(
                                ts=ts,
                                account_label=account_label,
                                shop_name=shop_name,
                                data_type="products",
                                granularity=gran,
                                start_date=start_date,
                                end_date=end_date,
                                suffix=tmp_path.suffix,
                            )
                            target = out_root / filename
                            try:
                                tmp_path.rename(target)
                            except Exception:
                                import shutil as _sh
                                _sh.copy2(tmp_path, target)
                                try:
                                    tmp_path.unlink(missing_ok=True)
                                except Exception:
                                    pass

                            try:
                                self._write_manifest(target, cfg, account_label, shop_name)
                            except Exception:
                                pass
                            if self.logger:
                                self.logger.info(f"下载完成(UI-兜底): {target}")
                            return ExportResult(True, "下载完成(UI-兜底)", None, str(target))
                    except Exception:
                        continue
            except Exception:
                pass

            # 5) 兜底：若未拿到"最新记录"或 UI监听失败，轮询文件系统是否有新文件产生
            retry_interval = int(get_config_value('data_collection', 'download.retry_interval', 2))
            for _ in range(max(1, wait_timeout // max(1, retry_interval))):
                try:
                    cur = set(out_root.glob("*"))
                    new_files = cur - pre_files
                    if new_files:
                        newest = sorted(new_files, key=lambda p: p.stat().st_mtime)[-1]
                        # 统一重命名
                        from datetime import datetime
                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = build_filename(
                            ts=ts,
                            account_label=account_label,
                            shop_name=shop_name,
                            data_type="products",
                            granularity=gran,
                            start_date=start_date,
                            end_date=end_date,
                            suffix=newest.suffix,
                        )
                        target = out_root / filename
                        try:
                            newest.rename(target)
                        except Exception:
                            import shutil
                            shutil.copy2(str(newest), str(target))
                        try:
                            self._write_manifest(target, cfg, account_label, shop_name)
                        except Exception:
                            pass
                        if self.logger:
                            self.logger.info(f"下载完成(目录监测): {target}")
                        return ExportResult(True, "下载完成(目录监测)", None, str(target))
                except Exception:
                    pass
                await page.wait_for_timeout(int(max(500, retry_interval * 1000)))

            return ExportResult(False, "未捕获到下载事件，且未检测到新下载文件")

        except Exception as e:
            if self.logger:
                self.logger.error(f"[ShopeeProductsExport] 失败: {e}")
            return ExportResult(False, None, str(e))


    async def _maybe_generate_report(self, page: Any) -> None:
        """尝试点击"生成报告/立即生成/生成"按钮以启动生成（若存在）。"""
        try:
            candidates = [
                "button:has-text('生成')",
                "button:has-text('立即生成')",
                "button:has-text('生成报告')",
                "[role='button']:has-text('生成')",
                "[role='button']:has-text('立即生成')",
            ]
            for sel in candidates:
                try:
                    loc = page.locator(sel)
                    if await loc.count() > 0 and await loc.first.is_visible():
                        await loc.first.click()
                        await page.wait_for_timeout(300)
                        break
                except Exception:
                    continue
        except Exception:
            pass

    async def _wait_for_latest_export_ready(self, page: Any, timeout: Optional[int] = None):
        """等待最新导出记录就绪，返回“下载”按钮的 locator；超时返回 False。

        逻辑与服务表现保持一致思想：
        - 优先定位“最新记录”的行（包含 下载 按钮的最近一条记录）
        - 行内若显示“进行中/生成中”等字样，视为未就绪
        - 行内“下载”按钮可见且可用时，返回其 locator
        """
        try:
            from datetime import datetime
            from modules.core.config import get_config_value
            if timeout is None:
                timeout = int(get_config_value('data_collection', 'download.wait_timeout', 30))
            retry_interval = int(get_config_value('data_collection', 'download.retry_interval', 2))

            if self.logger:
                self.logger.info(f"[ShopeeProductsExport] 等待最新导出记录就绪（超时:{timeout}s）...")

            deadline = datetime.now().timestamp() + timeout
            # 快速路径1：记录当前页面中"下载"按钮数量，用于检测新条目出现
            download_buttons_all = page.locator('button:has-text("下载"), a:has-text("下载"), button:has-text("Download")')
            try:
                base_count = await download_buttons_all.count()
            except Exception:
                base_count = 0
            last_probe = datetime.now().timestamp()

            while datetime.now().timestamp() < deadline:
                latest_row = None
                # 可能的记录选择器（包含下载按钮的记录）
                row_selectors = [
                    # 优先尝试最新一行（first-child），以命中"最新报告"面板的顶部记录
                    '.latest-report .report-item:first-child',
                    '.report-list .report-item:first-child',
                    '.download-list .download-item:first-child',
                    'table tbody tr:first-child',
                    'tbody tr:first-child',
                    # 其次再尝试包含下载按钮的容器（用于反向定位）
                    'table tbody tr:has(button:has-text("下载"))',
                    'tbody tr:has(button:has-text("下载"))',
                    '[class*="report"]:has(button:has-text("下载"))',
                    '[class*="download"]:has(button:has-text("下载"))',
                    '.export-history-table tbody tr:first-child',
                    '.download-history tbody tr:first-child',
                ]
                try:
                    for rs in row_selectors:
                        try:
                            rows = page.locator(rs)
                            if await rows.count() > 0:
                                latest_row = rows.first
                                break
                        except Exception:
                            continue

                    # 快速路径：监控"下载"按钮数量的增加 → 出现新记录后立即返回顶部下载按钮
                    try:
                        cur_count = await download_buttons_all.count()
                    except Exception:
                        cur_count = base_count
                    if cur_count > base_count:
                        base_count = cur_count
                        try:
                            btn_top = page.locator('table tbody tr:first-child button:has-text("下载"), tbody tr:first-child button:has-text("下载"), .latest-report .report-item:first-child :is(button,a):has-text("下载")')
                            if await btn_top.count() > 0 and await btn_top.first.is_visible() and await btn_top.first.is_enabled():
                                if self.logger:
                                    self.logger.info("[ShopeeProductsExport] 发现新增下载记录，优先点击最新一条")
                                return btn_top.first
                        except Exception:
                            pass
                        # 若未定位到顶部，退化为直接返回任一下载按钮
                        if await download_buttons_all.count() > 0:
                            return download_buttons_all.first

                    # 心跳探测：每 3s 再尝试一次顶部"下载"
                    now_ts = datetime.now().timestamp()
                    if now_ts - last_probe >= 3:
                        last_probe = now_ts
                        try:
                            btn_top = page.locator('table tbody tr:first-child button:has-text("下载"), tbody tr:first-child button:has-text("下载"), .latest-report .report-item:first-child :is(button,a):has-text("下载")')
                            if await btn_top.count() > 0 and await btn_top.first.is_visible() and await btn_top.first.is_enabled():
                                return btn_top.first
                        except Exception:
                            pass

                    if latest_row:
                        # 检查是否"进行中/生成中"
                        try:
                            row_text = await latest_row.inner_text(timeout=1000)
                        except Exception:
                            row_text = ""
                        text_lower = (row_text or "").lower()
                        if any(k in text_lower for k in ["进行中", "生成中", "processing", "generating"]):
                            await page.wait_for_timeout(int(min(400, max(200, retry_interval * 1000))))
                            continue

                        # 检查是否有可点击的下载按钮（先短等待按钮出现，再判断）
                        try:
                            btn = latest_row.locator('button:has-text("下载"), a:has-text("下载"), button:has-text("Download")')
                            try:
                                from datetime import datetime as _now
                                remaining_ms = max(100, int((deadline - _now.now().timestamp()) * 1000))
                                await btn.first.wait_for(state="visible", timeout=min(1500, remaining_ms))
                            except Exception:
                                pass
                            if await btn.count() > 0:
                                first_btn = btn.first
                                if await first_btn.is_visible() and await first_btn.is_enabled():
                                    if self.logger:
                                        self.logger.info("[ShopeeProductsExport] 最新导出记录已就绪，可以下载")
                                    return first_btn
                        except Exception:
                            pass
                    else:
                        # Fallback：未能识别最新记录容器，尝试从任意"下载"按钮反向定位所在行/容器
                        try:
                            download_buttons = page.locator('button:has-text("下载"), a:has-text("下载")')
                            if await download_buttons.count() > 0:
                                first_btn = download_buttons.first
                                possible_containers = ['tr', 'div[class*="item"]', 'div[class*="row"]', 'li']
                                for container in possible_containers:
                                    try:
                                        cand_row = first_btn.locator(f'xpath=ancestor::{container}[1]')
                                        if await cand_row.count() > 0:
                                            latest_row = cand_row.first
                                            if self.logger:
                                                self.logger.debug(f"[ShopeeProductsExport] 通过按钮找到容器: {container}")
                                            break
                                    except Exception:
                                        continue
                                if latest_row:
                                    try:
                                        btn = latest_row.locator('button:has-text("下载"), a:has-text("下载"), button:has-text("Download")')
                                        if await btn.count() > 0 and await btn.first.is_visible() and await btn.first.is_enabled():
                                            return btn.first
                                    except Exception:
                                        pass
                        except Exception:
                            pass

                    await page.wait_for_timeout(250)
                except Exception:
                    await page.wait_for_timeout(250)

            if self.logger:
                self.logger.warning(f"[ShopeeProductsExport] 等待最新导出记录就绪超时({timeout}s)")
            return False
        except Exception:
            if self.logger:
                self.logger.warning("[ShopeeProductsExport] 等待导出记录就绪失败（已忽略）")
            return False
