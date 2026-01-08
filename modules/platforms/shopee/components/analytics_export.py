from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
import json

from modules.components.base import ExecutionContext
from modules.components.export.base import ExportComponent, ExportResult, ExportMode, build_standard_output_root
from modules.platforms.shopee.components.analytics_config import AnalyticsSelectors
from modules.utils.path_sanitizer import safe_slug, build_output_path, build_filename


class ShopeeAnalyticsExport(ExportComponent):
    """Shopee 流量表现（Analytics）导出组件

    - 只依赖 analytics_config 中的 URL/选择器
    - 统一落盘到 temp/outputs/shopee/<账号>/<店铺>/traffic/<粒度>/
    - 优先 UI 导出（点击->等待->下载），后续可扩展 API 备选
    - 架构与 ShopeeProductsExport 保持一致
    """

    # Component metadata (v4.8.0)
    platform = "shopee"
    component_type = "export"
    data_domain = "analytics"

    def __init__(self, ctx: ExecutionContext, selectors: Optional[AnalyticsSelectors] = None) -> None:
        super().__init__(ctx)
        self.sel = selectors or AnalyticsSelectors()

    def _write_manifest(self, target: Path, cfg: dict, account_label: str, shop_name: str) -> None:
        """在导出文件旁生成元数据清单（.json），与服务表现保持一致字段"""
        try:
            from datetime import datetime
            meta = {
                "platform": self.ctx.platform,
                "account_label": account_label,
                "shop_name": shop_name,
                "shop_id": (self.ctx.config or {}).get("shop_id"),
                "region": (self.ctx.account or {}).get("region"),
                "data_type": "analytics",  # v4.10.0更新：统一使用analytics域，traffic域已废弃
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

    def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
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
                        if loc.count() > 0 and loc.first.is_visible():
                            if self.logger:
                                self.logger.info(f"[ShopeeAnalyticsExport] 关闭弹窗: {sel}")
                            loc.first.click()
                            page.wait_for_timeout(200)
                    except Exception:
                        continue
            except Exception:
                pass

            # 0.5) 日期选择：与单次/服务表现保持一致（基于 DatePicker 配方）
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
                    opt = DateOption.Last_30_DAYS if hasattr(DateOption, 'Last_30_DAYS') else DateOption.LAST_30_DAYS
                if opt is not None:
                    if self.logger:
                        self.logger.info(f"[ShopeeAnalyticsExport] 选择时间范围: {opt.value}")
                    _dp = ShopeeDatePicker(self.ctx)
                    _res = _dp.run(page, opt)
                    page.wait_for_timeout(600)
            except Exception:
                # 日期选择失败不阻断导出，后续依靠文件名区间校验兜底
                pass

            # 1) 确认页面加载完成（多探针并行检测）
            data_ready = False
            ready_probe = None
            for probe in self.sel.data_ready_probes:
                try:
                    if page.locator(probe).first.is_visible():
                        data_ready = True
                        ready_probe = probe
                        if self.logger:
                            self.logger.info(f"[ShopeeAnalyticsExport] 页面加载完成，探针: {probe}")
                        break
                except Exception:
                    continue

            if not data_ready:
                if self.logger:
                    self.logger.warning("[ShopeeAnalyticsExport] 未检测到数据就绪探针，继续执行")
                # 额外等待时间，给页面更多加载时间
                page.wait_for_timeout(2000)
            else:
                page.wait_for_timeout(500)

            # 2) 点击导出（增强日志与重试机制）
            clicked = False
            export_button_used = None

            if self.logger:
                self.logger.info(f"[ShopeeAnalyticsExport] 开始查找导出按钮，候选器数量: {len(self.sel.export_buttons)}")

            for btn in self.sel.export_buttons:
                try:
                    loc = page.locator(btn)
                    count = loc.count()
                    if count > 0:
                        if self.logger:
                            self.logger.info(f"[ShopeeAnalyticsExport] 找到 {count} 个匹配元素: {btn}")
                        if loc.first.is_visible():
                            if self.logger:
                                self.logger.info(f"[ShopeeAnalyticsExport] 点击导出按钮: {btn}")
                            loc.first.click()
                            clicked = True
                            export_button_used = btn
                            break
                        else:
                            if self.logger:
                                self.logger.debug(f"[ShopeeAnalyticsExport] 元素不可见: {btn}")
                except Exception as e:
                    if self.logger:
                        self.logger.debug(f"[ShopeeAnalyticsExport] 选择器失败: {btn}, 错误: {e}")
                    continue

            if not clicked:
                # 额外兜底：在所有 frame 中再次尝试；以及纯文本匹配
                try:
                    frames = getattr(page, 'frames', []) or []
                except Exception:
                    frames = []

                for fr in frames:
                    try:
                        for btn in self.sel.export_buttons:
                            try:
                                loc = fr.locator(btn)
                                if loc.count() > 0 and loc.first.is_visible():
                                    if self.logger:
                                        self.logger.info(f"[ShopeeAnalyticsExport] 在frame中点击导出按钮: {btn}")
                                    loc.first.click()
                                    clicked = True
                                    export_button_used = btn
                                    break
                            except Exception:
                                continue
                        if clicked:
                            break
                    except Exception:
                        continue

                # 纯文本兜底
                if not clicked:
                    try:
                        txt_loc = page.locator('text=导出数据')
                        if txt_loc.count() == 0:
                            txt_loc = page.locator('text=导出')
                        if txt_loc.count() > 0 and txt_loc.first.is_visible():
                            if self.logger:
                                self.logger.info("[ShopeeAnalyticsExport] 使用文本兜底点击导出")
                            txt_loc.first.click()
                            clicked = True
                            export_button_used = 'text=导出*'
                    except Exception:
                        pass

                if not clicked:
                    if self.logger:
                        self.logger.error("[ShopeeAnalyticsExport] 未找到可用的导出按钮")
                        # 调试截图
                        try:
                            from datetime import datetime
                            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                            screenshot_path = f"temp/development/debug_export_page_{ts}_{account_label}_{shop_name}.png"
                            page.screenshot(path=screenshot_path)
                            self.logger.info(f"[ShopeeAnalyticsExport] 已保存调试截图: {screenshot_path}")
                        except Exception:
                            pass
                    return ExportResult(False, "未找到导出按钮")

            # 等待导出处理，并检测下载完成
            if self.logger:
                self.logger.info(f"[ShopeeAnalyticsExport] 导出按钮已点击: {export_button_used}，等待处理...")

            # 统一输出目录（使用 build_output_path，支持 include_shop_id）
            data_type = "analytics"  # v4.10.0更新：统一使用analytics域，traffic域已废弃
            gran = cfg.get("granularity") or "manual"
            start_date = cfg.get("start_date")
            end_date = cfg.get("end_date")

            out_root = build_standard_output_root(self.ctx, data_type=data_type, granularity=gran)
            out_root.mkdir(parents=True, exist_ok=True)


            # 自适应超时参数与全局下载监听（提升一键/大范围场景稳定性）
            def _parse_days(sd, ed) -> int:
                try:
                    from datetime import datetime as _dt
                    if not sd or not ed:
                        return 0
                    return (_dt.strptime(str(ed), "%Y-%m-%d") - _dt.strptime(str(sd), "%Y-%m-%d")).days + 1
                except Exception:
                    return 0
            _days = _parse_days(start_date, end_date)
            _one_click = bool((self.ctx.config or {}).get("one_click"))
            _is_monthly = str(gran).lower() in {"monthly", "month", "m"}
            wait_button_sec = int((self.ctx.config or {}).get("download_wait_timeout_sec") or (180 if (_one_click or _days >= 28 or _is_monthly) else 30))
            retry_expect_ms = int((self.ctx.config or {}).get("export_retry_expect_ms") or (60000 if (_one_click or _days >= 28 or _is_monthly) else 30000))
            final_expect_ms = int((self.ctx.config or {}).get("export_final_expect_ms") or (180000 if (_one_click or _days >= 28 or _is_monthly) else 60000))
            fs_deadline_sec = int((self.ctx.config or {}).get("fs_poll_deadline_sec") or (120 if (_one_click or _days >= 28 or _is_monthly) else 60))

            _latest = {"dl": None}
            def _on_dl(ev):
                try:
                    _latest["dl"] = ev
                except Exception:
                    pass
            try:
                page.on("download", _on_dl)
            except Exception:
                pass
            try:
                page.context.on("download", _on_dl)
            except Exception:
                pass

            # 首选：围绕点击捕获下载事件（支持多次重试机制）
            from datetime import datetime
            import time, glob, os, shutil
            start_ts = time.time()

            # 尝试立即捕获下载（5s 短超时）
            download = None
            downloaded_file = None

            try:
                with page.expect_download(timeout=5000) as dl_info:
                    page.locator(export_button_used or self.sel.export_buttons[0]).first.click()
                download = dl_info.value
                if self.logger:
                    self.logger.info(f"[ShopeeAnalyticsExport] 立即下载成功")
            except Exception:
                if self.logger:
                    self.logger.info(f"[ShopeeAnalyticsExport] 未检测到立即下载，进入重试机制")

                # 读取重试配置：次数与间隔（默认3次，每次间隔30s）
                try:
                    from modules.core.config import get_config_value
                    max_retries = int(get_config_value('data_collection', 'download.export_retry_count', 3))
                    backoff_sec = int(get_config_value('data_collection', 'download.export_retry_backoff', 30))
                except Exception:
                    max_retries = 3
                    backoff_sec = 30

                # 若配置了下载目录，提前取出，供重试轮次之间的快速检测
                try:
                    downloads_path = (self.ctx.config or {}).get("downloads_path")
                except Exception:
                    downloads_path = None

                for retry_idx in range(1, max_retries + 1):
                    # 先快速检查是否已有新文件产生（避免已成功还继续重试）
                    try:
                        if downloads_path and os.path.isdir(downloads_path):
                            exts = (".xlsx", ".xls", ".csv")
                            candidates = [
                                Path(p) for p in glob.glob(os.path.join(downloads_path, "*"))
                                if os.path.splitext(p)[1].lower() in exts
                            ]
                            if candidates:
                                candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                                f = candidates[0]
                                if f.stat().st_mtime >= start_ts:
                                    downloaded_file = f
                                    break
                    except Exception:
                        pass

                    # 等待后重试，并在 expect_download 上下文内完成点击
                    page.wait_for_timeout(backoff_sec * 1000)
                    # 若全局监听已捕获下载，提前结束重试
                    if _latest.get("dl") is not None:
                        download = _latest.get("dl")
                        break
                    try:
                        with page.expect_download(timeout=retry_expect_ms) as dl_info:
                            page.locator(export_button_used or self.sel.export_buttons[0]).first.click()
                        download = dl_info.value
                        if self.logger:
                            self.logger.info(f"[ShopeeAnalyticsExport] 第{retry_idx}次重试点击导出按钮（间隔{backoff_sec}s）")
                        if download:
                            break
                    except Exception:
                        continue

            # 若仍未捕获到下载事件，参考“服务表现”流程：
            # 1) 尝试点击“生成/立即生成”
            # 2) 等待“下载”入口出现后优先点击最新一条
            if not download and not downloaded_file:
                try:
                    self._maybe_generate_report(page)
                except Exception:
                    pass
                try:
                    from modules.core.config import get_config_value as _cfg
                    base_wait = int(_cfg('data_collection', 'download.wait_timeout', 30))
                except Exception:
                    base_wait = 30
                wait_timeout = max(base_wait, wait_button_sec)
                preferred = self._wait_for_latest_download_button(page, timeout=wait_timeout)
                if preferred:
                    try:
                        from datetime import datetime as _dt
                        pre_files = set(out_root.glob("*")) if out_root.exists() else set()
                    except Exception:
                        pre_files = set()
                    try:
                        # 
                        if _latest.get("dl") is not None:
                            download = _latest.get("dl")
                        else:
                            with page.expect_download(timeout=final_expect_ms) as dl_info:
                                preferred.click()
                            download = dl_info.value
                    except Exception as e:
                        # UI监听未命中 -> 进行短时文件系统兜底（最多15秒，每秒检查一次）
                        for _ in range(15):
                            try:
                                cur = set(out_root.glob("*"))
                                new_files = [f for f in (cur - pre_files) if f.suffix.lower() in (".xlsx", ".xls", ".csv")]
                                if new_files:
                                    from pathlib import Path as _P
                                    downloaded_file = max(new_files, key=lambda f: f.stat().st_mtime)
                                    break
                            except Exception:
                                pass
                            page.wait_for_timeout(1000)

            if download:
                tmp_name = download.suggested_filename or f"{data_type}.xlsx"
                tmp_path = out_root / tmp_name
                download.save_as(str(tmp_path))

                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                # 使用统一文件命名函数
                filename = build_filename(
                    ts=ts,
                    account_label=account_label,
                    shop_name=shop_name,
                    data_type=data_type,
                    granularity=gran,
                    start_date=start_date,
                    end_date=end_date,
                    suffix=".xlsx"
                )
                target = out_root / filename
                try:
                    tmp_path.rename(target)
                except Exception:
                    shutil.copy2(tmp_path, target)
                    try:
                        tmp_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                # 写入导出元数据清单（与服务表现一致）
                try:
                    self._write_manifest(target, cfg, account_label, shop_name)
                except Exception:
                    pass
                if self.logger:
                    self.logger.info(f"下载完成(UI): {target}")
                print(f"\n[OK] 导出成功: {target}")
                return ExportResult(True, "下载完成(UI)", None, str(target))
            elif downloaded_file:
                try:
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = build_filename(
                        ts=ts,
                        account_label=account_label,
                        shop_name=shop_name,
                        data_type=data_type,
                        granularity=gran,
                        start_date=start_date,
                        end_date=end_date,
                        suffix=downloaded_file.suffix,
                    )
                    target = out_root / filename
                    try:
                        downloaded_file.rename(target)
                    except Exception:
                        shutil.copy2(downloaded_file, target)
                        try:
                            if downloaded_file.exists():
                                downloaded_file.unlink(missing_ok=True)
                        except Exception:
                            pass
                    try:
                        self._write_manifest(target, cfg, account_label, shop_name)
                    except Exception:
                        pass
                    if self.logger:
                        self.logger.info(f"下载完成(目录即时检测): {target}")
                    print(f"\n[OK] 导出成功: {target}")
                    return ExportResult(True, "下载完成(目录即时检测)", None, str(target))
                except Exception:
                    pass
            else:
                # 未捕获下载事件，进入目录轮询兜底
                if self.logger:
                    self.logger.info(f"[ShopeeAnalyticsExport] 未捕获下载事件，启用文件系统兜底")

            # 兜底：若配置了 downloads_path，则轮询检测是否有新文件产生
            downloads_path = None
            try:
                downloads_path = (self.ctx.config or {}).get("downloads_path")
            except Exception:
                downloads_path = None

            if downloads_path and os.path.isdir(downloads_path):
                exts = (".xlsx", ".xls", ".csv")
                deadline = start_ts + fs_deadline_sec
                newest_file = None
                while time.time() < deadline:
                    candidates = [
                        Path(p) for p in glob.glob(os.path.join(downloads_path, "*"))
                        if os.path.splitext(p)[1].lower() in exts
                    ]
                    if candidates:
                        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                        f = candidates[0]
                        if f.stat().st_mtime >= start_ts:
                            newest_file = f
                            break
                    time.sleep(1)
                if newest_file:
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    # 使用统一文件命名函数，保留原文件扩展名
                    filename = build_filename(
                        ts=ts,
                        account_label=account_label,
                        shop_name=shop_name,
                        data_type=data_type,
                        granularity=gran,
                        start_date=start_date,
                        end_date=end_date,
                        suffix=newest_file.suffix
                    )
                    target = out_root / filename
                    try:
                        shutil.move(str(newest_file), str(target))
                    except Exception:
                        shutil.copy2(str(newest_file), str(target))
                    # 写入导出元数据清单（与服务表现一致）
                    try:
                        self._write_manifest(target, cfg, account_label, shop_name)
                    except Exception:
                        pass
                    if self.logger:
                        self.logger.info(f"下载完成(目录监测): {target}")
                    return ExportResult(True, "下载完成(目录监测)", None, str(target))

            return ExportResult(False, "未捕获到下载事件，且未检测到新下载文件")

        except Exception as e:
            if self.logger:
                self.logger.error(f"[ShopeeAnalyticsExport] 失败: {e}")
            return ExportResult(False, str(e))


    def _maybe_generate_report(self, page) -> bool:
        """在导出记录抽屉/弹窗中自动点击“生成/立即生成/重新生成”。
        返回是否有点击动作。
        """
        try:
            candidates = [
                'button:has-text("生成")',
                'button:has-text("立即生成")',
                'button:has-text("重新生成")',
                'button:has-text("Generate")',
                'button:has-text("Regenerate")',
                'a:has-text("生成")',
                'a:has-text("Generate")',
            ]
            for sel in candidates:
                try:
                    loc = page.locator(sel)
                    if loc.count() > 0 and loc.first.is_enabled() and loc.first.is_visible():
                        if self.logger:
                            self.logger.info(f"[ShopeeAnalyticsExport] 点击生成按钮: {sel}")
                        loc.first.click()
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def _wait_for_latest_download_button(self, page, timeout: Optional[int] = None):
        """等待页面出现可点击的“下载”按钮，返回首选 Locator。
        逻辑与服务表现相近，但做了通用化精简。
        """
        try:
            from datetime import datetime
            from modules.core.config import get_config_value

            if timeout is None:
                timeout = int(get_config_value('data_collection', 'download.wait_timeout', 30))
            retry_interval = int(get_config_value('data_collection', 'download.retry_interval', 2))
            heartbeat_sec = int(get_config_value('data_collection', 'download.heartbeat_interval', 3))

            start_time = datetime.now()
            deadline = start_time.timestamp() + timeout
            last_beat = 0

            # 记录初始“下载”按钮数量，用于增量检测
            download_buttons_all = page.locator('button:has-text("下载"), a:has-text("下载"), button:has-text("Download")')
            try:
                base_count = download_buttons_all.count()
            except Exception:
                base_count = 0

            while datetime.now().timestamp() < deadline:
                try:
                    # 若出现新增“下载”按钮，优先取第一条
                    try:
                        cur_count = download_buttons_all.count()
                    except Exception:
                        cur_count = base_count
                    if cur_count > base_count:
                        base_count = cur_count
                        btn_top = download_buttons_all.first
                        if btn_top.is_visible() and btn_top.is_enabled():
                            if self.logger:
                                self.logger.info("[ShopeeAnalyticsExport] 发现新增下载入口，优先点击最新一条")
                            return btn_top

                    # 心跳探测：每 heartbeat_sec 再尝试一次
                    now_ts = datetime.now().timestamp()
                    if now_ts - last_beat >= heartbeat_sec:
                        last_beat = now_ts
                        btn = download_buttons_all.first
                        if btn and btn.is_visible() and btn.is_enabled():
                            return btn

                    # 文本状态检测（处理中 -> 继续等待）
                    try:
                        status_text = page.text_content('body') or ''
                        indicators = get_config_value('data_collection', 'export_detection.processing_indicators', [
                            '执行中', '生成中', '队列中', '处理中', '导出中', '进行中',
                            'processing', 'generating', 'queued', 'exporting', 'in progress',
                        ])
                        if any(ind.lower() in status_text.lower() for ind in indicators):
                            page.wait_for_timeout(int(min(400, max(200, retry_interval * 1000))))
                            continue
                    except Exception:
                        pass

                except Exception:
                    page.wait_for_timeout(250)

            if self.logger:
                self.logger.warning(f"[ShopeeAnalyticsExport] 等待下载入口超时({timeout}s)")
            return False
        except Exception:
            return False
