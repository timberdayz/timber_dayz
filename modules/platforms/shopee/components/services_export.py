"""
Shopee 服务表现（Services）导出组件

职责：
- 在同一数据域下，分别导出两个子类型：AI 助手(ai_assistant)、人工聊天(agent)
- 统一落盘到 temp/outputs/shopee/<account>/<shop>/services/<granularity>/
- 文件名以 variant 标识子类型：...__services.ai_assistant__manual.xlsx / ...__services.agent__manual.xlsx

说明：
- 默认导出全部子类型；可通过 ctx.config.get("services_subtype") 指定单个子类型
- 避免在导入阶段产生副作用；仅在 run 时执行浏览器动作
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
import json

from loguru import logger

from modules.components.base import ExecutionContext
from modules.components.export.base import ExportComponent, ExportMode, ExportResult, build_standard_output_root
from modules.platforms.shopee.components.services_config import ServicesSelectors
from modules.utils.path_sanitizer import build_output_path, build_filename


@dataclass
class _VariantSpec:
    key: str  # ai_assistant / agent
    path: str


class ShopeeServicesExport(ExportComponent):
    """Shopee 服务表现导出器

    兼容 3PF 与 SIP 店铺：
    - SIP 店铺不提供"服务表现"页，命中后应"跳过且不视为失败"。
    - 以页面要素与 404 URL 双重判定。
    """

    # Component metadata (v4.8.0)
    platform = "shopee"
    component_type = "export"
    data_domain = "services"

    def __init__(self, ctx: ExecutionContext, selectors: Optional[ServicesSelectors] = None) -> None:
        super().__init__(ctx)
        self.sel = selectors or ServicesSelectors()

    # --- Capability guards -------------------------------------------------
    def _is_sip_shop(self, page) -> bool:
        """判断是否为 SIP 附属店铺（保守、避免误杀）。
        仅基于明确的 SIP 徽标/提示做判断；不再以“侧边栏无服务表现入口”作为依据，
        因为深链接页面通常不包含侧边栏，容易误判。
        """
        try:
            candidates = [
                'text="SIP附属店铺"',
                'xpath=//*[contains(text(), "SIP附属店铺")]',
                'xpath=//*[contains(text(), "SIP") and contains(text(), "附属")]',
            ]
            for sel in candidates:
                try:
                    loc = page.locator(sel).first
                    if loc.count() > 0 and loc.is_visible():
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def _is_404_or_not_found(self, page) -> bool:
        """检测 404/无权限/不存在 页面（更全面）。"""
        try:
            url = page.url or ""
            url_lower = url.lower()
            if any(k in url_lower for k in ["/404", "no-permission", "no_permission", "permission-denied", "not-found"]):
                return True
            # 标题与正文特征
            try:
                title = (page.title() or "").lower()
            except Exception:
                title = ""
            try:
                body = (page.locator('body').inner_text() or "").lower()
            except Exception:
                body = ""
            indicators = [
                "404", "page not found", "not found", "页面不存在", "无法访问", "抱歉", "无权限", "没有权限", "permission denied",
            ]
            if any(ind in title for ind in indicators) or any(ind in body for ind in indicators):
                return True
        except Exception:
            pass
        return False

    def _await_404_if_any(self, page, timeout_ms: int = 3000) -> bool:
        """在短时间内反复检测是否进入404/无权限页，处理前端延迟跳转。
        返回 True 表示检测到不可用页面。"""
        try:
            deadline = datetime.now().timestamp() + max(0, int(timeout_ms)) / 1000.0
            while datetime.now().timestamp() < deadline:
                try:
                    if self._is_404_or_not_found(page):
                        return True
                except Exception:
                    pass
                try:
                    page.wait_for_timeout(200)
                except Exception:
                    pass
            # 结束前再检查一次
            try:
                return self._is_404_or_not_found(page)
            except Exception:
                return False
        except Exception:
            return False


    def _get_target_variants(self) -> List[_VariantSpec]:
        desired = (self.ctx.config or {}).get("services_subtype", "all").lower()
        variants: List[_VariantSpec] = []
        for p in self.sel.pages:
            key = p.get("key", "").lower()
            if desired in ("all", key):
                variants.append(_VariantSpec(key=key, path=p.get("path", "")))
        if not variants:
            for p in self.sel.pages:
                variants.append(_VariantSpec(key=p.get("key", "").lower(), path=p.get("path", "")))
        return variants

    def run(self, page, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
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

            successes: List[Path] = []
            failures: List[str] = []
            skipped: List[str] = []  # SIP 店或权限限制：功能不适用的变体

            for spec in self._get_target_variants():
                try:
                    target_url = self._build_target_url(spec)
                    if self.logger:
                        self.logger.info(f"[ShopeeServicesExport] 导航: {spec.key} -> {target_url}")
                    resp = page.goto(target_url, wait_until="domcontentloaded")
                    try:
                        # 若命中404页，尝试不同参数名的兜底（cnsc_shop_id -> shop_id）
                        if '/404' in (page.url or '') or (resp and getattr(resp, 'status', lambda:0)() == 404):
                            if self.logger:
                                self.logger.warning(f"[ShopeeServicesExport] 检测到404，尝试参数名兜底: {target_url}")
                            self._fallback_navigate_with_alt_params(page, spec)
                    except Exception:
                        pass

                    # 导航后快速守卫：短轮询确认是否 404/无权限，命中则立即跳过
                    try:
                        if self._await_404_if_any(page, timeout_ms=3000):
                            if self.logger:
                                self.logger.warning(f"[ShopeeServicesExport] 目标页不可用(404/无权限): {page.url}")
                            skipped.append(spec.key)
                            continue
                    except Exception:
                        pass

                    # 关弹窗，避免遮挡按钮
                    try:
                        self._close_notification_modal(page)
                    except Exception:
                        pass

                    # 探针：页面就绪
                    for probe in self.sel.data_ready_probes:
                        try:
                            if page.locator(probe).first.is_visible():
                                break
                        except Exception:
                            continue
                    page.wait_for_timeout(500)

                    # 二次能力守卫：SIP 店铺或 404/无入口 -> 跳过（不视为失败）
                    try:
                        if self._is_404_or_not_found(page) or self._is_sip_shop(page):
                            if self.logger:
                                self.logger.warning("[ShopeeServicesExport] 当前店铺不支持‘服务表现’（SIP/权限/404），已跳过")
                            skipped.append(spec.key)
                            continue
                    except Exception:
                        pass

                    # 时间范围：复用商品/流量表现的日期配方，按 granularity 自动选择
                    try:
                        from modules.components.date_picker.base import DateOption
                        from modules.platforms.shopee.components.date_picker import ShopeeDatePicker
                        opt = None
                        gran = (self.ctx.config or {}).get("granularity") or "day"
                        g = str(gran).lower()
                        if g in ("day", "daily", "d"):
                            opt = DateOption.YESTERDAY
                        elif g in ("weekly", "week", "w", "last_7_days"):
                            opt = DateOption.LAST_7_DAYS
                        elif g in ("monthly", "month", "m", "last_30_days"):
                            opt = DateOption.LAST_30_DAYS
                        if opt is not None:
                            if self.logger:
                                self.logger.info(f"[ShopeeServicesExport] 选择时间范围: {opt.value}")
                            _dp = ShopeeDatePicker(self.ctx)
                            _res = _dp.run(page, opt)
                            page.wait_for_timeout(600)
                            # 若基于配方的日期选择失败，则使用轻量通用逻辑兜底
                            try:
                                ok = bool(getattr(_res, 'success', False))
                            except Exception:
                                ok = False
                            if not ok:
                                variants = []
                                if opt == DateOption.YESTERDAY:
                                    variants = ["昨天", "昨日", "Yesterday"]
                                elif opt == DateOption.LAST_7_DAYS:
                                    variants = ["过去7天", "过去 7 天", "最近7天", "Last 7 days", "7天"]
                                elif opt == DateOption.LAST_30_DAYS:
                                    variants = ["过去30天", "过去 30 天", "最近30天", "Last 30 days", "30天"]
                                if variants:
                                    if self.logger:
                                        self.logger.info(f"[ShopeeServicesExport] 日期配方未命中，启用轻量兜底: {variants}")
                                    self._pick_date_light(page, variants)
                                    page.wait_for_timeout(400)
                    except Exception:
                        pass

                    # 点击导出
                    clicked = False
                    skip_wait = False  # AI助手为点击即下载：成功后跳过后续等待
                    for btn in self.sel.export_buttons:
                        try:
                            loc = page.locator(btn)
                            cand = loc.first
                            if cand.count() > 0 and cand.is_visible():
                                # 显式屏蔽“聊天记录/Transcript”类按钮（避免误点 track-transcript-button）
                                try:
                                    cls = (cand.get_attribute("class") or "")
                                    txt = (cand.inner_text() or "")
                                    if ("track-transcript" in cls) or ("聊天记录" in txt) or ("Transcript" in txt):
                                        if self.logger:
                                            self.logger.debug("[ShopeeServicesExport] 跳过非导出按钮(聊天记录/Transcript)")
                                        continue
                                except Exception:
                                    pass

                                if self.logger:
                                    self.logger.info(f"[ShopeeServicesExport] 点击导出按钮: {btn}")
                                if spec.key == "ai_assistant":
                                    # AI助手：点击即下载，围绕点击监听下载事件（30s 超时）+ 文件系统兜底
                                    from datetime import datetime as _dt
                                    import time

                                    cfg = self.ctx.config or {}
                                    gran = cfg.get("granularity") or "manual"
                                    start_date = cfg.get("start_date")
                                    end_date = cfg.get("end_date")

                                    # 获取路径配置选项
                                    from modules.core.config import get_config_value
                                    include_shop_id = get_config_value('data_collection', 'path_options.include_shop_id', True)
                                    shop_id = (self.ctx.config or {}).get("shop_id")

                                    out_root = build_standard_output_root(
                                        self.ctx,
                                        data_type="services",
                                        granularity=gran,
                                        subtype=spec.key,
                                    )
                                    out_root.mkdir(parents=True, exist_ok=True)

                                    # 记录点击前的下载目录文件列表（用于文件系统兜底）
                                    try:
                                        downloads_dir = out_root
                                        pre_files = set(downloads_dir.glob("*")) if downloads_dir.exists() else set()
                                    except Exception:
                                        pre_files = set()

                                    download_success = False
                                    target = None

                                    # 尝试 expect_download 监听（短超时）。若未立即开始下载，则进入统一轮询+重试机制。
                                    try:
                                        with page.expect_download(timeout=5000) as dl_info:
                                            cand.click()
                                        download = dl_info.value

                                        tmp_name = download.suggested_filename or f"services_{spec.key}.xlsx"
                                        tmp_path = out_root / tmp_name
                                        download.save_as(str(tmp_path))

                                        ts = _dt.now().strftime("%Y%m%d_%H%M%S")
                                        filename = build_filename(
                                            ts=ts,
                                            account_label=account_label,
                                            shop_name=shop_name,
                                            data_type=f"services.{spec.key}",
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

                                        # 写入导出元数据清单（便于后续入库/追溯）
                                        try:
                                            self._write_manifest(target, spec.key, cfg, account_label, shop_name)
                                        except Exception:
                                            pass

                                        if self.logger:
                                            getattr(self.logger, "success", self.logger.info)(f"[ShopeeServicesExport] 下载完成(UI): {target}")
                                        download_success = True

                                    except Exception as e:
                                        # 未能在5s内直接触发下载：通常因平台1分钟限制或异步生成。改为进入统一轮询+重试。
                                        if self.logger:
                                            self.logger.info(f"[ShopeeServicesExport] 未检测到立即下载，进入统一轮询+重试机制: {e}")
                                        # 标记已点击，交由后续 wait-loop 处理“最新记录就绪”与“30s重试导出”
                                        clicked = True
                                        skip_wait = False
                                        break

                                    if download_success and target:
                                        successes.append(target)
                                        try:
                                            print(f"\n[OK] 导出成功: {target}")
                                        except Exception:
                                            pass
                                        skip_wait = True
                                        clicked = True
                                        break

                                    # 若走到此处，说明未成功；继续尝试其他选择器
                                else:
                                    cand.click()
                                    clicked = True
                                    break
                        except Exception:
                            continue
                    if not clicked:
                        # 补救：尝试在“更多/.../下拉菜单”中寻找导出项
                        try:
                            menu_triggers = [
                                '.ant-dropdown-trigger',
                                'button:has-text("更多")',
                                'button:has([class*="more"])',
                                '.anticon-more',
                                'button[aria-label="更多"]',
                                'button:has-text("More")',
                            ]
                            opened = False
                            for trig in menu_triggers:
                                try:
                                    t = page.locator(trig).first
                                    if t.count() > 0 and t.is_visible():
                                        if self.logger:
                                            self.logger.info(f"[ShopeeServicesExport] 打开更多菜单: {trig}")
                                        t.click()
                                        page.wait_for_timeout(300)
                                        opened = True
                                        break
                                except Exception:
                                    continue
                            if opened:
                                menu_export = [
                                    'text="导出数据"', 'text="导出"', 'text="Export"', 'text="Export Data"',
                                ]
                                for me in menu_export:
                                    try:
                                        m = page.locator(me).first
                                        if m.count() > 0 and m.is_visible():
                                            if self.logger:
                                                self.logger.info(f"[ShopeeServicesExport] 点击菜单中的导出项: {me}")
                                            m.click()
                                            clicked = True
                                            break
                                    except Exception:
                                        continue
                        except Exception:
                            pass

                    if not clicked:
                        failures.append(spec.key)
                        continue

                    if skip_wait:
                        # AI助手已在点击时完成下载，跳过后续等待逻辑
                        continue

                    # 导出后，若出现“生成报告/立即生成”等按钮，先点击以生成导出任务
                    try:
                        self._maybe_generate_report(page)
                    except Exception:
                        pass

                    if self.logger:
                        self.logger.info("[ShopeeServicesExport] 已触发导出，等待生成/下载入口出现...")

                    # 导出后轮询下载入口（按配置的回退间隔与重试次数），并每5秒输出心跳日志
                    downloaded = False
                    start_ts = datetime.now().timestamp()
                    from modules.core.config import get_config_value as _cfg
                    backoff_sec = int(_cfg('data_collection', 'download.export_retry_backoff', 30))
                    max_retries = int(_cfg('data_collection', 'download.export_retry_count', 3))
                    deadline = start_ts + backoff_sec
                    next_beat = 5
                    export_retries = 0

                    while not downloaded and datetime.now().timestamp() < deadline:
                        # 每轮尝试前，先短暂等待
                        page.wait_for_timeout(1500)
                        # 心跳日志（每5秒一次）
                        try:
                            elapsed = int(datetime.now().timestamp() - start_ts)
                            if elapsed >= next_beat:
                                remain = int(max(0, deadline - datetime.now().timestamp()))
                                if self.logger:
                                    self.logger.info(f"[ShopeeServicesExport] 仍在等待下载入口... ({elapsed}/30s，剩余{remain}s)")
                                next_beat += 5
                        except Exception:
                            pass
                        # 若有弹窗弹出，尝试关闭
                        try:
                            self._close_notification_modal(page)
                        except Exception:
                            pass

                            # 达到回退间隔仍未就绪 -> 重试点击“导出数据”，并续期等待窗口
                            try:
                                elapsed_retry = int(datetime.now().timestamp() - start_ts)
                                # 满足下一次重试触发条件（间隔 backoff_sec），且未超过最大重试次数
                                if (export_retries < max_retries) and (elapsed_retry >= (export_retries + 1) * backoff_sec):
                                    if self.logger:
                                        self.logger.info(f"[ShopeeServicesExport] 第{export_retries + 1}次重试点击导出（间隔{backoff_sec}s）")
                                    for btn in self.sel.export_buttons:
                                        try:
                                            loc = page.locator(btn).first
                                            if loc.count() > 0 and loc.is_visible():
                                                try:
                                                    loc.click()
                                                    page.wait_for_timeout(300)
                                                except Exception:
                                                    pass
                                                try:
                                                    self._maybe_generate_report(page)
                                                except Exception:
                                                    pass
                                                export_retries += 1
                                                # 每次重试后重置等待窗口
                                                deadline = datetime.now().timestamp() + backoff_sec
                                                next_beat = 5
                                                break
                                        except Exception:
                                            continue
                            except Exception:
                                pass

                        # 等待最新导出记录变为可下载状态（短轮询，命中即优先点击最新一条）
                        from modules.core.config import get_config_value
                        wait_timeout = max(5, int(get_config_value('data_collection', 'download.wait_timeout', 30)))
                        preferred_loc = self._wait_for_latest_export_ready(page, spec.key, timeout=wait_timeout)

                        if preferred_loc:
                            if self.logger:
                                self.logger.info(f"[ShopeeServicesExport] 最新导出记录就绪 -> 优先点击下载")
                            # 统一输出目录（预先计算，支持 UI 监听与文件系统兜底）
                            cfg = self.ctx.config or {}
                            gran = cfg.get("granularity") or "manual"
                            start_date = cfg.get("start_date")
                            end_date = cfg.get("end_date")

                            # 获取路径配置选项
                            include_shop_id = get_config_value('data_collection', 'path_options.include_shop_id', True)
                            shop_id = (self.ctx.config or {}).get("shop_id")

                            out_root = build_standard_output_root(
                                self.ctx,
                                data_type="services",
                                granularity=gran,
                                subtype=spec.key,
                            )
                            out_root.mkdir(parents=True, exist_ok=True)

                            # 点击前快照现有文件（用于兜底识别）
                            try:
                                pre_files = set(out_root.glob("*"))
                            except Exception:
                                pre_files = set()

                            try:
                                with page.expect_download(timeout=60000) as dl_info:
                                    preferred_loc.click()
                                download = dl_info.value

                                tmp_name = download.suggested_filename or f"services_{spec.key}.xlsx"
                                tmp_path = out_root / tmp_name
                                download.save_as(str(tmp_path))

                                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                                filename = build_filename(
                                    ts=ts,
                                    account_label=account_label,
                                    shop_name=shop_name,
                                    data_type=f"services.{spec.key}",
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

                                # 写入导出元数据清单（便于后续入库/追溯）
                                try:
                                    self._write_manifest(target, spec.key, cfg, account_label, shop_name)
                                except Exception:
                                    pass

                                if self.logger:
                                    getattr(self.logger, "success", self.logger.info)(f"[ShopeeServicesExport] 下载完成(UI): {target}")
                                successes.append(target)
                                downloaded = True
                                break
                            except Exception as e:
                                # UI 监听未命中 -> 文件系统兜底（Agent页）
                                if self.logger:
                                    self.logger.info(f"[ShopeeServicesExport] UI下载监听超时，启用文件系统兜底(agent): {e}")
                                for _ in range(15):
                                    try:
                                        cur = set(out_root.glob("*"))
                                        new_files = cur - pre_files
                                        if new_files:
                                            newest = max(new_files, key=lambda f: f.stat().st_mtime)
                                            if newest.suffix.lower() in [".xlsx", ".xls", ".csv"]:
                                                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                                                filename = build_filename(
                                                    ts=ts,
                                                    account_label=account_label,
                                                    shop_name=shop_name,
                                                    data_type=f"services.{spec.key}",
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
                                                    shutil.copy2(newest, target)
                                                    try:
                                                        newest.unlink(missing_ok=True)
                                                    except Exception:
                                                        pass
                                                # 写入导出元数据清单（便于后续入库/追溯）
                                                try:
                                                    self._write_manifest(target, spec.key, cfg, account_label, shop_name)
                                                except Exception:
                                                    pass
                                                if self.logger:
                                                    getattr(self.logger, "success", self.logger.info)(f"[ShopeeServicesExport] 下载完成(文件系统兜底): {target}")
                                                successes.append(target)
                                                downloaded = True
                                                break
                                    except Exception:
                                        pass
                                    page.wait_for_timeout(1000)
                            if downloaded:
                                break

                        for btn in self.sel.download_buttons:
                            try:
                                loc = page.locator(btn)
                                if loc.count() > 0 and loc.first.is_visible():
                                    if self.logger:
                                        self.logger.info(f"[ShopeeServicesExport] 点击下载按钮: {btn}")
                                    # 统一输出目录（预先计算，支持 UI 监听与文件系统兜底）
                                    cfg = self.ctx.config or {}
                                    gran = cfg.get("granularity") or "manual"
                                    start_date = cfg.get("start_date")
                                    end_date = cfg.get("end_date")

                                    # 获取路径配置选项
                                    from modules.core.config import get_config_value
                                    include_shop_id = get_config_value('data_collection', 'path_options.include_shop_id', True)
                                    shop_id = (self.ctx.config or {}).get("shop_id")

                                    out_root = build_standard_output_root(
                                        self.ctx,
                                        data_type="services",
                                        granularity=gran,
                                        subtype=spec.key,
                                    )
                                    out_root.mkdir(parents=True, exist_ok=True)

                                    # 点击前快照现有文件（用于兜底识别）
                                    try:
                                        pre_files = set(out_root.glob("*"))
                                    except Exception:
                                        pre_files = set()

                                    try:
                                        with page.expect_download(timeout=60000) as dl_info:
                                            loc.first.click()
                                        download = dl_info.value

                                        tmp_name = download.suggested_filename or f"services_{spec.key}.xlsx"
                                        tmp_path = out_root / tmp_name
                                        download.save_as(str(tmp_path))

                                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                                        filename = build_filename(
                                            ts=ts,
                                            account_label=account_label,
                                            shop_name=shop_name,
                                            data_type=f"services.{spec.key}",
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

                                        # 写入导出元数据清单（便于后续入库/追溯）
                                        try:
                                            self._write_manifest(target, spec.key, cfg, account_label, shop_name)
                                        except Exception:
                                            pass

                                        if self.logger:
                                            getattr(self.logger, "success", self.logger.info)(f"[ShopeeServicesExport] 下载完成(UI): {target}")
                                        successes.append(target)
                                        downloaded = True
                                        break
                                    except Exception as e:
                                        # UI 监听未命中 -> 文件系统兜底（Agent页）
                                        if self.logger:
                                            self.logger.info(f"[ShopeeServicesExport] UI下载监听超时，启用文件系统兜底(agent): {e}")
                                        for _ in range(15):
                                            try:
                                                cur = set(out_root.glob("*"))
                                                new_files = cur - pre_files
                                                if new_files:
                                                    newest = max(new_files, key=lambda f: f.stat().st_mtime)
                                                    if newest.suffix.lower() in [".xlsx", ".xls", ".csv"]:
                                                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                                                        filename = build_filename(
                                                            ts=ts,
                                                            account_label=account_label,
                                                            shop_name=shop_name,
                                                            data_type=f"services.{spec.key}",
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
                                                            shutil.copy2(newest, target)
                                                            try:
                                                                newest.unlink(missing_ok=True)
                                                            except Exception:
                                                                pass
                                                        # 写入导出元数据清单（便于后续入库/追溯）
                                                        try:
                                                            self._write_manifest(target, spec.key, cfg, account_label, shop_name)
                                                        except Exception:
                                                            pass
                                                        if self.logger:
                                                            getattr(self.logger, "success", self.logger.info)(f"[ShopeeServicesExport] 下载完成(文件系统兜底): {target}")
                                                        successes.append(target)
                                                        downloaded = True
                                                        break
                                            except Exception:
                                                pass
                                            page.wait_for_timeout(1000)
                                        if downloaded:
                                            break
                            except Exception:
                                continue

                    if not downloaded:
                        ok, p = self._api_fallback(page, spec, account_label, shop_name)
                        if ok and p:
                            successes.append(p)
                        else:
                            failures.append(spec.key)

                except Exception as e:  # noqa: BLE001
                    if self.logger:
                        self.logger.error(f"[ShopeeServicesExport] 失败 variant={spec.key}: {e}")
                    failures.append(spec.key)

            if successes and not failures:
                return ExportResult(True, "全部成功(UI)", None, str(successes[-1]))
            if successes and failures:
                return ExportResult(True, f"部分成功，失败: {','.join(failures)}", None, str(successes[-1]))
            if (not successes) and (not failures) and skipped:
                # 典型场景：SIP 店铺不提供服务表现 -> 全部跳过
                return ExportResult(True, f"不适用(已跳过): {','.join(skipped)}")
            return ExportResult(False, "services 全部导出失败")
        except Exception as e:
            if self.logger:
                self.logger.error(f"[ShopeeServicesExport] 失败: {e}")
            return ExportResult(False, str(e))



    def _safe(self, s: Any) -> str:
        return "".join(c if (str(c).isalnum() or c in "._-") else "_" for c in str(s))

    def _latest_har_path(self) -> Optional[Path]:
        try:
            har_dir = Path("temp/har")
            if not har_dir.exists():
                return None
            files = sorted(har_dir.glob("*.har"), key=lambda p: p.stat().st_mtime, reverse=True)
            return files[0] if files else None
        except Exception:
            return None

    def _write_manifest(
        self,
        target: Path,
        subtype: str,
        cfg: Dict[str, Any],
        account_label: str,
        shop_name: str,
    ) -> None:
        """在导出文件旁生成元数据清单（.json），便于后续入库与追踪。"""
        try:
            meta = {
                "platform": self.ctx.platform,
                "account_label": account_label,
                "shop_name": shop_name,
                "shop_id": (self.ctx.config or {}).get("shop_id"),
                "region": (self.ctx.account or {}).get("region"),
                "data_type": "services",
                "subtype": subtype,
                "granularity": (cfg or {}).get("granularity"),
                "start_date": (cfg or {}).get("start_date"),
                "end_date": (cfg or {}).get("end_date"),
                "exported_at": datetime.now().isoformat(),
                "file_path": str(target),
            }
            manifest_path = Path(str(target) + ".json")
            manifest_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            # 元数据写入失败不影响主流程
            pass

    def _wait_for_latest_export_ready(self, page, subtype: str, timeout: Optional[int] = None) -> bool:
        """等待最新导出记录变为可下载状态，避免点击到旧记录"""
        try:
            # 从配置文件获取参数
            from modules.core.config import get_config_value
            if timeout is None:
                timeout = get_config_value('data_collection', 'download.wait_timeout', 30)
            retry_interval = get_config_value('data_collection', 'download.retry_interval', 2)
            heartbeat_sec = int(get_config_value('data_collection', 'download.heartbeat_interval', 3))

            if self.logger:
                self.logger.info(f"[ShopeeServicesExport] 等待最新导出记录就绪（超时:{timeout}s）...")

            start_time = datetime.now()
            deadline = start_time.timestamp() + timeout

            # 快速路径基础：记录当前页面“下载”按钮数量，用于检测新增记录出现
            download_buttons_all = page.locator('button:has-text("下载"), a:has-text("下载"), button:has-text("Download")')
            try:
                base_count = download_buttons_all.count()
            except Exception:
                base_count = 0
            last_probe = start_time.timestamp()

            while datetime.now().timestamp() < deadline:
                try:
                    # 查找导出记录列表/表格（针对Shopee界面优化）
                    export_list_selectors = [
                        # 优先尝试最新一行（first-child），以命中“最新报告”面板的顶部记录
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
                        # 备用选择器
                        '.export-history-table tbody tr:first-child',
                        '.download-history tbody tr:first-child',
                    ]

                    latest_row = None
                    for selector in export_list_selectors:
                        try:
                            rows = page.locator(selector)
                            if rows.count() > 0:
                                # 取第一行作为最新记录
                                latest_row = rows.first
                                if self.logger:
                                    self.logger.debug(f"[ShopeeServicesExport] 使用选择器找到记录: {selector}")
                                break
                        except Exception as e:
                            if self.logger:
                                self.logger.debug(f"[ShopeeServicesExport] 选择器失败 {selector}: {e}")
                            continue

                    # 如果没有找到，尝试更通用的方法
                    if not latest_row:
                        try:
                            # 查找包含"下载"按钮的任何元素
                            download_buttons = page.locator('button:has-text("下载"), a:has-text("下载")')
                            if download_buttons.count() > 0:
                                first_btn = download_buttons.first
                                # 尝试找到包含此按钮的行或容器（不做全局立即点击，避免点到历史记录）
                                possible_containers = ['tr', 'div[class*="item"]', 'div[class*="row"]', 'li']
                                for container in possible_containers:
                                    try:
                                        cand_row = first_btn.locator(f'xpath=ancestor::{container}[1]')
                                        if cand_row.count() > 0:
                                            latest_row = cand_row.first
                                            if self.logger:
                                                self.logger.debug(f"[ShopeeServicesExport] 通过按钮找到容器: {container}")
                                            break
                                    except Exception:
                                        continue
                        except Exception:
                            pass

                    # 快速路径：监控“下载”按钮数量增加 -> 新记录出现即返回顶部下载按钮
                    try:
                        cur_count = download_buttons_all.count()
                    except Exception:
                        cur_count = base_count
                    if cur_count > base_count:
                        base_count = cur_count
                        try:
                            btn_top = page.locator('table tbody tr:first-child button:has-text("下载"), tbody tr:first-child button:has-text("下载"), .latest-report .report-item:first-child :is(button,a):has-text("下载")')
                            if btn_top.count() > 0 and btn_top.first.is_visible() and btn_top.first.is_enabled():
                                if self.logger:
                                    self.logger.info("[ShopeeServicesExport] 发现新增下载记录，优先点击最新一条")
                                return btn_top.first
                        except Exception:
                            pass
                        if download_buttons_all.count() > 0:
                            return download_buttons_all.first

                    # 心跳探测：每 3s 再尝试一次顶部“下载”
                    now_ts = datetime.now().timestamp()
                    if now_ts - last_probe >= heartbeat_sec:
                        last_probe = now_ts
                        try:
                            btn_top = page.locator('table tbody tr:first-child button:has-text("下载"), tbody tr:first-child button:has-text("下载"), .latest-report .report-item:first-child :is(button,a):has-text("下载")')
                            if btn_top.count() > 0 and btn_top.first.is_visible() and btn_top.first.is_enabled():
                                return btn_top.first
                        except Exception:
                            pass


                    if latest_row:
                        # 检查状态文本（从配置文件获取状态指示词）
                        row_text = latest_row.text_content() or ""
                        status_indicators = get_config_value('data_collection', 'export_detection.processing_indicators', [
                            "执行中", "生成中", "队列中", "处理中", "导出中", "进行中",
                            "processing", "generating", "queued", "exporting", "in progress"
                        ])

                        # 如果包含执行状态，继续等待
                        if any(indicator.lower() in row_text.lower() for indicator in status_indicators):
                            if self.logger:
                                self.logger.info(f"[ShopeeServicesExport] 最新导出记录仍在处理中: {row_text[:50]}...")
                            # 更快轮询：不超过400ms，且不少于200ms（更灵敏）
                            page.wait_for_timeout(int(min(400, max(200, retry_interval * 1000))))
                            continue

                        # 检查是否有可点击的下载按钮
                        download_btn = latest_row.locator('button:has-text("下载"), a:has-text("下载"), button:has-text("Download")')
                        # 先短等待按钮出现，避免错过就绪瞬间
                        try:
                            from datetime import datetime as _now
                            remaining_ms = max(100, int((deadline - _now.now().timestamp()) * 1000))
                            download_btn.first.wait_for(state='visible', timeout=min(1500, remaining_ms))
                        except Exception:
                            pass
                        if download_btn.count() > 0:
                            # 进一步检查按钮是否可用（非禁用状态）
                            try:
                                first_btn = download_btn.first
                                if first_btn.is_enabled() and first_btn.is_visible():
                                    if self.logger:
                                        self.logger.info(f"[ShopeeServicesExport] 最新导出记录已就绪，可以下载")
                                    return first_btn
                            except Exception:
                                pass

                    page.wait_for_timeout(250)

                except Exception as e:
                    if self.logger:
                        self.logger.debug(f"[ShopeeServicesExport] 检查导出状态时出错: {e}")
                    page.wait_for_timeout(250)

            if self.logger:
                self.logger.warning(f"[ShopeeServicesExport] 等待最新导出记录就绪超时({timeout}s)")
            return False

        except Exception as e:
            if self.logger:
                self.logger.warning(f"[ShopeeServicesExport] 等待导出记录就绪失败: {e}")
            return False

    def _extract_params_from_har(self, har_path: Path, needle: str) -> tuple[Dict[str, Any], str]:
        params: Dict[str, Any] = {}
        method = "GET"
        try:
            data = json.loads(har_path.read_text(encoding="utf-8"))
            entries = (data.get("log", {}) or {}).get("entries", [])
            for entry in reversed(entries):
                req = entry.get("request", {})
                url = req.get("url", "")
                if needle in url:
                    method = (req.get("method") or "GET").upper()
                    # 优先请求体
                    post = req.get("postData") or {}
                    txt = post.get("text")
                    if txt:
                        try:
                            if txt.strip().startswith("{"):
                                body = json.loads(txt)
                            else:
                                body = {}
                                for part in txt.split("&"):
                                    if "=" in part:
                                        k, v = part.split("=", 1)
                                        body[k] = v
                            for k in ("start_ts", "end_ts", "start_time", "end_time", "period", "cnsc_shop_id"):
                                if k in body and body[k] is not None:
                                    params[k] = body[k]
                        except Exception:
                            pass
                    # 查询串兜底
                    for q in req.get("queryString", []) or []:
                        name = q.get("name")
                        if name in ("start_ts", "end_ts", "start_time", "end_time", "period", "cnsc_shop_id"):
                            params[name] = q.get("value")
                    # 找到一条即可
                    break
        except Exception:
            pass
        return params, method

    def _api_fallback(self, page, spec: _VariantSpec, account_label: str, shop_name: str) -> tuple[bool, Optional[Path]]:
        try:
            # 1) 端点映射
            key = spec.key
            base = self.sel.base_url.rstrip("/")
            mapping = {
                "ai_assistant": "/api/mydata/cnsc/shop/v2/chat/chatbot/export/",
                "agent": "/api/mydata/cnsc/shop/v1/chat/dashboard/export/",
            }
            if key not in mapping:
                return False, None
            export_url = f"{base}{mapping[key]}"
            needle = mapping[key].rstrip("/")  # 用于HAR匹配

            # 2) 参数来源：HAR -> ctx.config -> 兜底
            params = {}
            har_method = "GET"
            har_path = self._latest_har_path()
            if har_path:
                har_params, har_method = self._extract_params_from_har(har_path, needle)
                params.update(har_params)

            cfg = self.ctx.config or {}
            shop_id = cfg.get("shop_id") or (self.ctx.account or {}).get("shop_id")
            if shop_id and not params.get("cnsc_shop_id"):
                params["cnsc_shop_id"] = shop_id

            def _to_ts(d: Optional[str]) -> Optional[int]:
                if not d:
                    return None
                try:
                    return int(datetime.strptime(d, "%Y-%m-%d").timestamp())
                except Exception:
                    return None

            # 从配置补齐缺失时间
            if not params.get("start_ts") and cfg.get("start_date"):
                params["start_ts"] = _to_ts(cfg.get("start_date"))
            if not params.get("end_ts") and cfg.get("end_date"):
                params["end_ts"] = _to_ts(cfg.get("end_date"))

            # 同义键补齐（start_ts/start_time, end_ts/end_time）
            if params.get("start_ts") is not None and not params.get("start_time"):
                params["start_time"] = params["start_ts"]
            if params.get("end_ts") is not None and not params.get("end_time"):
                params["end_time"] = params["end_ts"]
            if params.get("start_time") is not None and not params.get("start_ts"):
                params["start_ts"] = params["start_time"]
            if params.get("end_time") is not None and not params.get("end_ts"):
                params["end_ts"] = params["end_time"]

            # period 默认：按选择范围推断
            if not params.get("period"):
                gran_sel = (cfg.get("granularity") or "").lower()
                if gran_sel == "day":
                    params["period"] = "yesterday"
                elif gran_sel == "weekly":
                    params["period"] = "last_7_days"
                elif gran_sel == "monthly":
                    params["period"] = "last_30_days"
                else:
                    params["period"] = "yesterday"

            # 清理 None
            params = {k: v for k, v in params.items() if v is not None}

            # 3) 触发浏览器内下载
            gran = cfg.get("granularity") or "manual"
            # 获取路径配置选项
            from modules.core.config import get_config_value
            include_shop_id = get_config_value('data_collection', 'path_options.include_shop_id', False)
            shop_id = (self.ctx.config or {}).get("shop_id")

            out_root = build_standard_output_root(
                self.ctx,
                data_type="services",
                granularity=gran,
            )
            out_root.mkdir(parents=True, exist_ok=True)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            tmp_name = f"services_{key}.xlsx"

            script = """
            async (data) => {
              try {
                const { url, method, payloadOrQuery, filename } = data || {};
                let finalUrl = url;
                const init = { credentials: 'include' };
                if ((method || 'GET').toUpperCase() === 'GET') {
                  const qs = new URLSearchParams(payloadOrQuery || {}).toString();
                  if (qs) finalUrl = url + (url.includes('?') ? '&' : '?') + qs;
                  init.method = 'GET';
                } else {
                  init.method = 'POST';
                  init.headers = { 'content-type': 'application/json' };
                  init.body = JSON.stringify(payloadOrQuery || {});
                }
                const res = await fetch(finalUrl, init);
                const ct = res.headers.get('content-type') || '';
                if (ct.includes('application/json')) {
                  // 尝试直接下载字段（若存在）
                  try {
                    const j = await res.json();
                    const link = j?.data?.download_link || j?.download_link || j?.url;
                    if (link) {
                      const a = document.createElement('a');
                      a.href = link; a.download = filename || 'export.xlsx'; document.body.appendChild(a); a.click(); a.remove();
                      return { mode: 'link', link };
                    }
                  } catch (e) { /* 忽略 */ }
                }
                // 退化为二进制下载
                const blob = await res.blob();
                const a = document.createElement('a');
                const u = URL.createObjectURL(blob);
                a.href = u; a.download = filename || 'export.xlsx'; document.body.appendChild(a); a.click(); a.remove();
                setTimeout(() => URL.revokeObjectURL(u), 8000);
                return { mode: 'blob' };
              } catch (e) {
                return { mode: 'error', error: String(e) };
              }
            }
            """

            with page.expect_download(timeout=90000) as dl_info:
                page.evaluate(script, {"url": export_url, "method": har_method, "payloadOrQuery": params, "filename": tmp_name})
            download = dl_info.value

            # 4) 统一重命名
            target = out_root / build_filename(
                ts=ts,
                account_label=account_label,
                shop_name=shop_name,
                data_type=f"services.{key}",
                granularity=gran,
                start_date=cfg.get("start_date"),
                end_date=cfg.get("end_date"),
                suffix=".xlsx",
            )
            tmp_path = out_root / (download.suggested_filename or tmp_name)
            download.save_as(str(tmp_path))
            try:
                tmp_path.rename(target)
            except Exception:
                import shutil
                shutil.copy2(tmp_path, target)
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass

            # 写入导出元数据清单（便于后续入库/追溯）
            try:
                self._write_manifest(target, key, cfg, account_label, shop_name)
            except Exception:
                pass

            if self.logger:
                getattr(self.logger, "success", self.logger.info)(f"[ShopeeServicesExport] 下载完成(API): {target}")
            return True, target
        except Exception as e:  # noqa: BLE001
            if self.logger:
                self.logger.warning(f"[ShopeeServicesExport] API fallback 失败 variant={spec.key}: {e}")
            return False, None
    def _fallback_navigate_with_alt_params(self, page, spec: _VariantSpec) -> None:
        """在出现 404 时，尝试替换不同的 shop_id 参数名重新导航。
        优先顺序：cnsc_shop_id -> shop_id -> 无参数。
        """
        try:
            base = self.sel.base_url.rstrip("/")
            path = spec.path if spec.path.startswith("/") else f"/{spec.path}"
            shop_id = (self.ctx.config or {}).get("shop_id") or (self.ctx.account or {}).get("shop_id")
            candidates = []
            if shop_id:
                candidates.extend([
                    f"{base}{path}?cnsc_shop_id={shop_id}",
                    f"{base}{path}?shop_id={shop_id}",
                ])
            candidates.append(f"{base}{path}")

            for url in candidates:
                if self.logger:
                    self.logger.info(f"[ShopeeServicesExport] 尝试备用URL: {url}")
                resp = page.goto(url, wait_until="domcontentloaded")
                try:
                    if '/404' not in (page.url or '') and not (resp and getattr(resp, 'status', lambda:0)() == 404):
                        if self.logger:
                            self.logger.info(f"[ShopeeServicesExport] 已切换至备用URL，404消失: {page.url}")
                        break
                except Exception:
                    continue
        except Exception:
            pass

    def _pick_date_light(self, page, target_texts: list[str]) -> bool:
        """轻量日期选择：通用开关/快捷项匹配，避免依赖产品页配方。
        返回 True/False 表示是否成功选择。
        """
        try:
            # 1) 打开面板
            openers = [
                ".eds-date-picker-input",
                ".eds-date-picker__input",
                ".ant-picker-input input",
                "div:has-text('统计时间')",
                "div:has-text('日期')",
                "[data-testid*='date']",
                ".date-range-picker",
            ]
            opened = False
            last = None
            for sel in openers:
                try:
                    el = page.locator(sel).first
                    if el.count() > 0 and el.is_visible():
                        el.click(); page.wait_for_timeout(250); opened = True; last = sel; break
                except Exception:
                    continue
            if not opened:
                return False

            # 2) 等待面板
            panel_selectors = [
                ".eds-date-selector-panel",
                ".eds-date-picker__dropdown",
                ".eds-dropdown__content:has(.eds-date-shortcut-item)",
                ".eds-date-range-panel",
                "div:has(.eds-date-shortcut-item__text)",
                "div:has-text('昨天')",
            ]
            panel = None
            for ps in panel_selectors:
                try:
                    loc = page.locator(ps).first
                    if loc.count() > 0:
                        try: loc.wait_for(state="visible", timeout=1500)
                        except Exception: pass
                        if loc.is_visible(): panel = loc; break
                except Exception:
                    continue
            if panel is None and last:
                try:
                    page.locator(last).first.click(); page.wait_for_timeout(400)
                except Exception:
                    pass
                for ps in panel_selectors:
                    try:
                        loc = page.locator(ps).first
                        if loc.count() > 0 and loc.is_visible():
                            panel = loc; break
                    except Exception:
                        continue
            if panel is None:
                return False

            # 3) 选择目标
            for txt in target_texts:
                selectors = [
                    f".eds-date-shortcut-item__text:has-text('{txt}')",
                    f".eds-date-shortcut-item:has-text('{txt}')",
                    f"li:has-text('{txt}')",
                    f"span:has-text('{txt}')",
                    f"button:has-text('{txt}')",
                    f"div:has-text('{txt}')",
                ]
                for sel in selectors:
                    try:
                        scope = panel.locator(sel).first if panel else page.locator(sel).first
                        if scope.count() > 0 and scope.is_visible():
                            scope.click(); page.wait_for_timeout(500)
                            return True
                    except Exception:
                        continue
            return False
        except Exception:
            return False


    def _build_page_url_by_key(self, key: str) -> str:
        """根据 pages 配置与当前 shop_id 生成目标页面 URL。"""
        try:
            page_item = next((p for p in self.sel.pages if p.get("key") == key), None)
            if not page_item:
                return ""
            base = self.sel.base_url.rstrip("/")
            path = page_item.get("path", "")
            if not path:
                return ""
            if not path.startswith("/"):
                path = "/" + path
            shop_id = (self.ctx.config or {}).get("shop_id") or (self.ctx.account or {}).get("shop_id")
            if shop_id:
                return f"{base}{path}?cnsc_shop_id={shop_id}"
            return f"{base}{path}"
        except Exception:
            return ""

            return False, None

    def _close_notification_modal(self, page) -> None:
        """尝试关闭常见的通知/公告弹窗，避免遮挡按钮。"""
        try:
            page.wait_for_timeout(300)
            close_selectors = [
                '.eds-modal__close', '.modal-close', '.close-btn', '.ant-modal-close', '.el-dialog__close',
                'button[aria-label="Close"]', 'button[aria-label="关闭"]',
                'button:has-text("关闭")', 'button:has-text("取消")', 'button:has-text("稍后再说")', 'button:has-text("我知道了")',
                '[class*="close"]:visible',
            ]
            for sel in close_selectors:
                try:
                    el = page.locator(sel).first
                    if el.count() > 0 and el.is_visible():
                        el.click()
                        page.wait_for_timeout(200)
                        break
                except Exception:
                    continue
        except Exception:
            pass

    def _maybe_generate_report(self, page) -> bool:
        """在导出记录抽屉/弹窗中自动点击“生成/立即生成/重新生成”。
        返回是否有点击动作。
        """
        try:
            page.wait_for_timeout(400)
            containers = [
                'div[role="dialog"]', '.ant-modal', '.ant-drawer', '.el-dialog', '.eds-dialog',
                '.ant-modal-root:visible',
            ]
            gen_btns = [
                'button:has-text("生成")', 'button:has-text("立即生成")', 'button:has-text("生成报告")',
                'button:has-text("重新生成")', 'a:has-text("生成")',
                'button:has-text("Generate")', 'button:has-text("Create")',
            ]

            for c in containers:
                try:
                    cont = page.locator(c).first
                    if cont.count() > 0 and cont.is_visible():
                        for g in gen_btns:
                            try:
                                btn = cont.locator(g).first
                                if btn.count() > 0 and btn.is_visible():
                                    if self.logger:
                                        self.logger.info(f"[ShopeeServicesExport] 点击生成按钮: {g}")
                                    btn.click()
                                    page.wait_for_timeout(500)
                                    return True
                            except Exception:
                                continue
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def _build_target_url(self, spec: _VariantSpec) -> str:
        base = self.sel.base_url.rstrip("/")
        path = spec.path if spec.path.startswith("/") else f"/{spec.path}"
        shop_id = (self.ctx.config or {}).get("shop_id") or (self.ctx.account or {}).get("shop_id")
        if shop_id:
            return f"{base}{path}?cnsc_shop_id={shop_id}"
        return f"{base}{path}"

