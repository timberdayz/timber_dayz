#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shopee Playwright 安全导出器
===========================

- 在浏览器上下文内发起请求与下载，规避裸 requests 风险
- 支持列出账号下所有店铺（实时拉取）
- 支持“商品表现-按周”导出：export -> report_id -> download_link -> 等待下载
- 统一分类输出路径：temp/outputs/<platform>/<account>/<shop_name>/<data_type>/<granularity>/
  文件命名：YYYYMMDD_HHMMSS__<account>__<shop>__<data_type>__<granularity>__<start>_<end>.xlsx
- 日期控件探测与分析
"""
from __future__ import annotations

import json
import re
import time
import glob
import os
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page

from modules.utils.logger import get_logger
from modules.utils.path_sanitizer import build_output_path, build_filename
from modules.core.config import get_config_value

logger = get_logger(__name__)


@dataclass
class Shop:
    id: str
    name: str
    region: str = ""


class ShopeePlaywrightExporter:
    def __init__(self, playwright):
        from modules.utils.persistent_browser_manager import PersistentBrowserManager

        # 兼容两种传参：
        # 1) Playwright 实例 -> 创建新的 PersistentBrowserManager
        # 2) PersistentBrowserManager 实例 -> 直接复用，避免重复初始化（减少“初始化会话管理器”日志）
        if hasattr(playwright, 'get_or_create_persistent_context') and hasattr(playwright, 'playwright'):
            # 视为 PersistentBrowserManager
            self.pb = playwright
            self.playwright = playwright.playwright
        else:
            self.playwright = playwright
            self.pb = PersistentBrowserManager(playwright)
        self.base = "https://seller.shopee.cn"

    def _open_account_page(self, account: Dict, download_path: str = None):
        platform = account.get("platform", "shopee").lower()
        # 标准化持久化上下文Key：优先使用 label/用户名，确保与“自动登录流程修正”一致
        account_key = (
            account.get("store_name")
            or account.get("username")
            or str(account.get("account_id") or "account")
        )

        # 如果指定了下载路径，设置浏览器下载目录
        extra_options = {}
        if download_path:
            extra_options = {
                "accept_downloads": True,
                "downloads_path": download_path,
            }
            logger.info(f"设置下载目录: {download_path}")

        ctx = self.pb.get_or_create_persistent_context(platform, str(account_key), account, **extra_options)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        login_url = account.get("login_url") or f"{self.base}/?cnsc_shop_id="
        logger.info(f"导航到账号入口: {login_url}")
        page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
        # 轻等待渲染
        page.wait_for_timeout(1200)

        # 优先等待可能的会话重定向（已登录将从 /account/signin 跳到 /portal）
        try:
            from time import sleep
            for _ in range(8):  # ~4.8s 宽限
                url_now = (page.url or "").lower()
                if ("/account/signin" not in url_now) and ("/login" not in url_now):
                    logger.info("检测到已登录会话，跳过自动登录")
                    return ctx, page, platform, str(account_key)
                sleep(0.6)
        except Exception:
            pass

        # 确保已登录（若仍在登录页则自动尝试登录一次）
        try:
            flags = {}
            try:
                flags = (account.get("login_flags") or {}) if isinstance(account, dict) else {}
            except Exception:
                flags = {}
            use_enhanced = bool(flags.get("use_enhanced_login", True))
            if use_enhanced:
                # 走“[BOT] 自动登录流程修正”同源实现，获取更强的自适应与详尽日志
                try:
                    from modules.utils.enhanced_recording_wizard import EnhancedRecordingWizard
                    _wiz = EnhancedRecordingWizard()
                    _wiz._perform_enhanced_auto_login(page, account, "Shopee")
                except Exception as we:
                    logger.debug(f"增强登录委托失败，回退 LoginService: {we}")
                    from modules.services.platform_login_service import LoginService as _LS
                    _LS().ensure_logged_in("shopee", page, account)
            else:
                from modules.services.platform_login_service import LoginService as _LS
                _LS().ensure_logged_in("shopee", page, account)
        except Exception as e:
            logger.debug(f"登录状态检查/自动登录跳过: {e}")
        return ctx, page, platform, str(account_key)

    def _is_on_login_page(self, page) -> bool:
        """更严格地判断是否为登录页，避免把首页误判为登录页。"""
        try:
            url = page.url or ''
            if 'account/signin' in url:
                return True

            def _visible(selector: str) -> bool:
                try:
                    loc = page.locator(selector)
                    return loc.count() > 0 and loc.first.is_visible()
                except Exception:
                    return False

            has_user = _visible('input[name="loginKey"], input[name="username"], input[placeholder*="邮箱"], input[placeholder*="手机"]')
            has_pass = _visible('input[type="password"], input[name="password"]')
            has_submit = _visible('button:has-text("登录"), button:has-text("登入")')

            # 需要同时命中账号与密码输入框；提交按钮可选
            if has_user and has_pass:
                return True
        except Exception:
            pass
        return False

    def _ensure_shopee_logged_in(self, page, account: Dict) -> None:
        """若检测到登录页，尝试使用账户信息自动登录一次，并在需要时进入验证码流程。"""
        try:
            if not self._is_on_login_page(page):
                return

            username = account.get('Username') or account.get('username') or account.get('email')
            password = account.get('Password') or account.get('password')
            if not username or not password:
                logger.warning('检测到未登录，但账号未提供用户名/密码，无法自动登录')
                return

            logger.info('[LOCK] 检测到登录页，尝试自动登录...')
            # 填写用户名
            for sel in ['input[name="loginKey"]', 'input[name="username"]', 'input[placeholder*="邮箱"]', 'input[placeholder*="手机"]', 'input[type="text"]']:
                try:
                    el = page.locator(sel)
                    if el.count() > 0 and el.first.is_visible():
                        el.first.fill(username)
                        break
                except Exception:
                    continue
            # 填写密码
            for sel in ['input[type="password"]', 'input[name="password"]']:
                try:
                    el = page.locator(sel)
                    if el.count() > 0 and el.first.is_visible():
                        el.first.fill(password)
                        break
                except Exception:
                    continue
            # 勾选“记住我”复选框（如果存在）—强化版：多策略点击 + 状态校验
            try:
                def _is_checked() -> bool:
                    try:
                        box = page.locator('input[type="checkbox"]').first
                        if box.count() > 0:
                            try:
                                return box.is_checked()
                            except Exception:
                                val = box.get_attribute('value') or ''
                                return val.strip().lower() in ['true', '1', 'on']
                    except Exception:
                        return False
                    return False

                if not _is_checked():
                    tried = False
                    for csel in [
                        'input.eds-checkbox__input[type="checkbox"]',
                        'label:has-text("记住我") input[type="checkbox"]',
                        'input[type="checkbox"]',
                    ]:
                        try:
                            loc = page.locator(csel).first
                            if loc.count() > 0 and loc.is_visible():
                                try:
                                    loc.check(force=True)  # type: ignore[attr-defined]
                                except Exception:
                                    loc.click(force=True)
                                tried = True
                                logger.info('[OK] 已尝试直接勾选“记住我”复选框')
                                break
                        except Exception:
                            continue

                    if not _is_checked():
                        try:
                            lab = page.get_by_text('记住我')  # type: ignore[attr-defined]
                            if lab and lab.count() > 0:
                                lab.first.click(force=True)
                                tried = True
                                logger.info('[OK] 通过文本点击触发“记住我”')
                        except Exception:
                            pass

                    if not _is_checked():
                        try:
                            frm = page.locator('form').first
                            if frm and frm.count() > 0:
                                try:
                                    frm.get_by_role('img').first.click()  # type: ignore[attr-defined]
                                    tried = True
                                except Exception:
                                    try:
                                        frm.locator('span').first.click()
                                        tried = True
                                    except Exception:
                                        pass
                        except Exception:
                            pass

                    if _is_checked():
                        logger.success('[OK] “记住我”已处于勾选状态')
                    else:
                        if tried:
                            logger.warning('[WARN] 已尝试点击“记住我”，但状态未改变，继续登录（不阻塞）')
                        else:
                            logger.debug('[i] 未找到“记住我”元素，跳过勾选步骤')
                else:
                    logger.info('[i] “记住我”已是勾选状态')
            except Exception:
                logger.debug('勾选“记住我”过程忽略异常')

            # 点击登录
            for sel in ['button:has-text("登录")', 'button:has-text("登入")', '.ant-btn-primary', '.btn-primary']:
                try:
                    btn = page.locator(sel)
                    if btn.count() > 0 and btn.first.is_visible():
                        btn.first.click()
                        break
                except Exception:
                    continue

            # 等待跳转或cookie生效
            page.wait_for_timeout(2500)

            # 若仍在登录页，进一步检测是否出现验证码弹窗并尝试自动处理
            if self._is_on_login_page(page):
                def _has_verification_modal_anywhere() -> bool:
                    selectors = [
                        '.phone-verify-container',
                        '[data-testid*="verify"]',
                        '[data-testid*="verification"]',
                        'div:has-text("验证手机号")',
                        'div:has-text("验证电话号码")',
                        'div:has-text("手机验证")',
                        'div:has-text("发送至邮箱")',
                        'div:has-text("发送至电话")',
                        'div:has-text("发送至手机")',
                        'div:has-text("输入验证码")',
                        'div:has-text("Verification")',
                        'div:has-text("OTP")',
                        'button:has-text("发送至电话")',
                        'button:has-text("发送至手机")',
                        'button:has-text("手机验证")',
                        'input[placeholder*="验证码"]',
                    ]
                    try:
                        # 当前页面
                        for _sel in selectors:
                            try:
                                loc = page.locator(_sel)
                                if loc.count() > 0 and loc.first.is_visible():
                                    return True
                            except Exception:
                                continue
                        # 所有frame
                        for fr in page.frames:
                            for _sel in selectors:
                                try:
                                    loc = fr.locator(_sel)
                                    if loc.count() > 0 and loc.first.is_visible():
                                        return True
                                except Exception:
                                    continue
                    except Exception:
                        pass
                    return False

                try:
                    # 使用更稳健的智能验证码处理器V2（覆盖“验证电话号码”页面等场景）
                    from modules.utils.smart_verification_handler_v2 import SmartVerificationHandlerV2

                    if _has_verification_modal_anywhere():
                        logger.info('[LOCK] 检测到验证码弹窗，启动验证码处理流程...')
                    else:
                        logger.info('[LOCK] 未显式检测到验证码弹窗，但仍停留在登录页，尝试走验证码处理兜底...')

                    handler = SmartVerificationHandlerV2(page, account)
                    handled = handler.handle_verification()
                    page.wait_for_timeout(2000)

                    if not self._is_on_login_page(page):
                        logger.info('[OK] 自动登录+验证码处理完成（检测通过）')
                        return

                    if handled:
                        logger.warning('验证码流程结束，但仍停留在登录页，后续步骤可能需要人工确认')
                    else:
                        logger.warning('验证码处理失败，可能需要人工介入')
                except Exception as ve:
                    logger.warning(f'验证码处理过程中出现异常: {ve}')
            else:
                logger.info('[OK] 自动登录完成（检测通过）')
        except Exception as e:
            logger.debug(f'_ensure_shopee_logged_in 异常: {e}')

    def list_shops(self, account: Dict) -> List[Shop]:
        """实时拉取账号下店铺列表（在页面上下文发起 fetch）。"""
        ctx, page, platform, account_id = self._open_account_page(account)
        # 多个区域尝试，增加重试和详细日志
        regions = ["sg", "br", "tw", "my", "th", "ph", "id", "mx", "cl", "co", "pl", "es"]
        shops: Dict[str, Shop] = {}
        successful_regions = []

        for region in regions:
            for retry in range(2):  # 每个区域重试2次
                try:
                    js = """
                    (async (region) => {
                      const u = new URL('/api/cnsc/selleraccount/get_merchant_shop_list/', location.origin);
                      u.searchParams.set('page_index','1');
                      u.searchParams.set('page_size','50');
                      u.searchParams.set('region', region);
                      u.searchParams.set('auth_codes','["access_my_product"]');
                      const resp = await fetch(u.toString(), { credentials: 'include' });
                      if (!resp.ok) return { error: `HTTP ${resp.status}` };
                      return await resp.json();
                    })
                    """
                    data = page.evaluate(js, region)

                    if not data:
                        logger.debug(f"区域 {region} 返回空数据 (重试 {retry+1}/2)")
                        continue

                    if isinstance(data, dict) and data.get("error"):
                        logger.debug(f"区域 {region} API错误: {data.get('error')} (重试 {retry+1}/2)")
                        continue

                    if isinstance(data, dict) and data.get("code") not in (0, 200):
                        logger.debug(f"区域 {region} 返回错误码: {data.get('code')} (重试 {retry+1}/2)")
                        continue

                    items = (
                        data.get("data", {}).get("shops")
                        or data.get("data", {}).get("list")
                        or data.get("data", {}).get("items")
                        or []
                    )

                    region_shops = 0
                    for it in items:
                        shop_id = str(it.get("shop_id") or it.get("cnsc_shop_id") or it.get("id") or "")
                        name = it.get("shop_name") or it.get("name") or it.get("label") or shop_id
                        if shop_id and shop_id not in shops:
                            shops[shop_id] = Shop(id=shop_id, name=name, region=region)
                            region_shops += 1

                    if region_shops > 0:
                        logger.debug(f"区域 {region} 发现 {region_shops} 个店铺")
                        successful_regions.append(region)
                    break  # 成功则跳出重试循环

                except Exception as e:
                    logger.debug(f"拉取区域 {region} 店铺失败 (重试 {retry+1}/2): {e}")
                    if retry == 1:  # 最后一次重试也失败
                        continue

        logger.info(f"共发现店铺 {len(shops)} 个，成功区域: {successful_regions}")
        return list(shops.values())

    def export_traffic_overview(
        self,
        account: Dict,
        shop: Shop,
        start_date: str,
        end_date: str,
        *,
        account_label: str,
        output_root: Path,
        enable_diagnostics: bool = False,
        enable_compare_diagnostics: bool = False,
        enable_recording_mode: bool = False,
    ) -> Tuple[bool, str, Optional[Path]]:
        """导出Shopee流量表现数据

        Args:
            account: 账号信息
            shop: 店铺信息
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            account_label: 账号标签
            output_root: 输出根目录
            enable_diagnostics: 启用诊断模式
            enable_compare_diagnostics: 启用对比诊断
            enable_recording_mode: 启用录制模式

        Returns:
            (成功标志, 消息, 文件路径)
        """
        ctx, page, platform, account_id = self._open_account_page(account)

        # 统一目录 + 文件名
        # 统一粒度规则：根据起止日期计算 daily/weekly/monthly
        gran = self._calculate_granularity(start_date, end_date)
        data_type = "traffic"
        include_shop_id = get_config_value('data_collection', 'path_options.include_shop_id', False)
        out_dir = build_output_path(
            root=output_root,
            platform=platform,
            account_label=account_label,
            shop_name=shop.name,
            data_type=data_type,
            granularity=gran,
            shop_id=getattr(shop, 'id', None),
            include_shop_id=include_shop_id,
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = build_filename(
            ts=ts,
            account_label=account_label,
            shop_name=shop.name,
            data_type=data_type,
            granularity=gran,
            start_date=start_date,
            end_date=end_date,
            suffix=".xlsx",
        )
        target_path = out_dir / filename

        # 诊断目录
        diag_dir = out_dir / ".diag"
        if enable_diagnostics or enable_compare_diagnostics or enable_recording_mode:
            diag_dir.mkdir(exist_ok=True)

        try:
            # 导航到流量表现页面
            traffic_url = f"https://seller.shopee.cn/datacenter/traffic/overview?cnsc_shop_id={shop.id}"
            logger.info(f"导航到流量表现页面: {traffic_url}")
            page.goto(traffic_url, wait_until="domcontentloaded", timeout=60000)

            # 检查并关闭可能的通知弹窗
            self._close_notification_modal(page)

            # 等待页面加载完成
            page.wait_for_timeout(2000)

            # 根据时间范围选择合适的选项
            time_option = self._determine_traffic_time_option(start_date, end_date)
            logger.info(f"[TARGET] 流量表现时间选择: {time_option}")

            # 执行时间选择（如需要）并进行校验
            if time_option != "昨天":
                if not self._execute_traffic_time_selection(page, time_option, diag_dir, enable_recording_mode):
                    return False, f"时间选择失败: {time_option}", None
                page.wait_for_timeout(800)
                if not self._verify_traffic_time_selection(page, start_date, end_date, time_option):
                    logger.info("[WAIT] 时间未生效，重试一次时间选择...")
                    if not self._execute_traffic_time_selection(page, time_option, diag_dir, enable_recording_mode):
                        return False, f"时间选择失败(重试): {time_option}", None
                    page.wait_for_timeout(800)
                    if not self._verify_traffic_time_selection(page, start_date, end_date, time_option):
                        return False, "时间选择未生效，请检查页面或稍后重试", None
            else:
                logger.info("[OK] 页面默认为'昨天'，跳过时间选择操作")

            # 等待数据加载
            page.wait_for_timeout(1500)

            # 直接围绕“导出数据”动作捕获下载事件（流量表现：点击即下载）
            with page.expect_download(timeout=120000) as dl_info:
                success, message = self._execute_traffic_export(page, diag_dir, enable_recording_mode)
                if not success:
                    return False, f"导出操作失败: {message}", None
            download = dl_info.value
            suggested = target_path.parent / download.suggested_filename
            download.save_as(str(suggested))
            if suggested != target_path:
                try:
                    suggested.rename(target_path)
                except Exception:
                    import shutil
                    shutil.move(str(suggested), str(target_path))
            download_path = target_path

            logger.info(f"[OK] 流量表现数据导出成功: {download_path}")
            return True, f"导出成功，文件保存至: {download_path}", download_path

        except Exception as e:
            logger.error(f"流量表现导出异常: {e}")
            return False, f"导出异常: {e}", None
        finally:
            # 上下文由批量编排器在账号级统一关闭；此处不再关闭以便同账号后续数据域复用
            pass

    def _determine_traffic_time_option(self, start_date: str, end_date: str) -> str:
        """根据日期范围确定流量表现的时间选项

        流量表现页面只有3个选项：昨天、过去7天、过去30天
        """
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            today = datetime.now().date()
            yesterday = today - timedelta(days=1)

            # 如果是昨天
            if start.date() == yesterday and end.date() == yesterday:
                return "昨天"

            # 如果是过去7天范围
            week_start = today - timedelta(days=7)
            if abs((start.date() - week_start).days) <= 1 and abs((end.date() - yesterday).days) <= 1:
                return "过去7天"

            # 如果是过去30天范围
            month_start = today - timedelta(days=30)
            if abs((start.date() - month_start).days) <= 1 and abs((end.date() - yesterday).days) <= 1:
                return "过去30天"

            # 默认使用昨天
            logger.warning(f"日期范围 {start_date}~{end_date} 不匹配标准选项，使用默认'昨天'")
            return "昨天"

        except Exception as e:
            logger.error(f"日期解析失败: {e}")
            return "昨天"

    def _execute_traffic_time_selection(self, page, time_option: str, diag_dir: Path, enable_recording_mode: bool) -> bool:
        """执行流量表现页面的时间选择"""
        try:
            logger.info(f"[ACTION] 开始流量表现时间选择，目标选项: {time_option}")

            # 使用配方执行器
            from modules.services.recipe_executor import RecipeExecutor
            executor = RecipeExecutor()

            # 执行时间选择配方
            success = executor.execute_traffic_date_recipe(page, time_option)
            if success:
                logger.info(f"[OK] 时间选择成功: {time_option}")
                return True
            else:
                logger.error(f"[FAIL] 时间选择失败: {time_option}")
                return False

        except Exception as e:
            logger.error(f"时间选择异常: {e}")
            return False

    def _verify_traffic_time_selection(self, page, start_date: str, end_date: str, time_option: str) -> bool:
        """校验流量表现页面的时间是否已按预期生效。

        优先从UI读取毫秒时间戳并与期望的 start/end 比较；失败则回退到文本关键字判断。
        """
        try:
            # 优先：解析 UI 时间范围（毫秒，右开区间）
            try:
                start_ms, end_ms = self._read_week_from_ui(page)
            except Exception:
                start_ms, end_ms = None, None
            if start_ms and end_ms:
                from datetime import datetime as dt, timezone, timedelta
                tz = timezone(timedelta(hours=8))  # 统一到 +08 仅用于日期比较
                s = dt.fromtimestamp(start_ms / 1000, tz).date().isoformat()
                e = (dt.fromtimestamp(end_ms / 1000, tz) - timedelta(days=1)).date().isoformat()
                if s == start_date and e == end_date:
                    logger.info("[OK] 时间范围校验通过(UI)")
                    return True

            # 回退：基于时间显示文本做关键字校验
            info = (self._read_time_display(page) or {})
            val = (info.get("value") or info.get("text") or "").strip()
            if time_option == "昨天" and ("昨天" in val or "Yesterday" in val):
                logger.info("[OK] 时间范围校验通过(文本=昨天)")
                return True
            if "7" in time_option and any(k in val for k in ["过去7", "近7", "Last 7", "7天", "7 Days", "7D"]):
                logger.info("[OK] 时间范围校验通过(文本=过去7天)")
                return True
            if "30" in time_option and any(k in val for k in ["过去30", "近30", "Last 30", "30天", "30 Days", "30D"]):
                logger.info("[OK] 时间范围校验通过(文本=过去30天)")
                return True

            logger.warning(f"时间范围校验未通过，显示='{val}'，期望={start_date}~{end_date}({time_option})")
            return False
        except Exception as e:
            logger.warning(f"时间范围校验异常: {e}")
            return False

    def _execute_traffic_export(self, page, diag_dir: Path, enable_recording_mode: bool) -> Tuple[bool, str]:
        """执行流量表现页面的导出操作"""
        try:
            logger.info("[ACTION] 开始流量表现数据导出...")

            # 查找导出按钮
            export_selectors = [
                'button:has-text("导出")',
                'button:has-text("下载")',
                '[data-testid*="export"]',
                '.export-btn',
                '.download-btn'
            ]

            export_clicked = False
            for selector in export_selectors:
                try:
                    element = page.locator(selector).first
                    if element.count() > 0 and element.is_visible():
                        logger.info(f"[TARGET] 点击导出按钮: {selector}")
                        element.click()
                        export_clicked = True
                        break
                except Exception as e:
                    logger.debug(f"导出按钮尝试失败 {selector}: {e}")
                    continue

            if not export_clicked:
                return False, "未找到可用的导出按钮"

            # 等待导出处理
            page.wait_for_timeout(2000)

            logger.info("[OK] 导出操作执行成功")
            return True, "导出操作成功"

        except Exception as e:
            logger.error(f"导出操作异常: {e}")
            return False, f"导出异常: {e}"

    def export_products_weekly_pure(
        self,
        page,  # 已经设置好的page对象
        shop: Shop,
        start_date: str,
        end_date: str,
        *,
        account_label: str,
        output_root: Path,
        enable_diagnostics: bool = False,
        enable_compare_diagnostics: bool = False,
        enable_recording_mode: bool = False,
        enable_auto_regenerate: bool = True,  # 纯导出默认启用自动重生
        enable_api_fallback: bool = False,    # API备选默认禁用（避免timestamp error）
        metrics: Optional[List[str]] = None,
    ) -> Tuple[bool, str, Optional[Path]]:
        """纯导出方法：跳过登录/导航/日期设置，直接执行导出。

        适用于组件化路径，假设page已经在正确的页面且时间已设置。
        """
        # 默认指标列表
        if metrics is None:
            metrics = [
                "销量", "销售额", "商品页访问量", "加购量",
                "点击率", "转化率", "订单买家数", "曝光量"
            ]

        # 动态计算粒度
        gran = self._calculate_granularity(start_date, end_date)
        data_type = "products"
        include_shop_id = get_config_value('data_collection', 'path_options.include_shop_id', False)
        out_dir = build_output_path(
            root=output_root,
            platform="shopee",
            account_label=account_label,
            shop_name=shop.name,
            data_type=data_type,
            granularity=gran,
            shop_id=getattr(shop, 'id', None),
            include_shop_id=include_shop_id,
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = build_filename(
            ts=ts,
            account_label=account_label,
            shop_name=shop.name,
            data_type=data_type,
            granularity=gran,
            start_date=start_date,
            end_date=end_date,
            suffix=".xlsx",
        )
        target_path = out_dir / filename

        try:
            # 跳过登录/导航/日期设置，直接执行导出流程
            logger.info("[TARGET] 纯导出模式：跳过登录/导航/日期设置，直接导出")

            # 诊断目录
            diag_dir = out_dir / ".diag"
            if enable_diagnostics or enable_compare_diagnostics or enable_recording_mode:
                diag_dir.mkdir(exist_ok=True)

            # 检查并关闭可能的通知弹窗
            self._close_notification_modal(page)

            # 先尝试“页面交互式导出”（点击页面上的导出/下载按钮并捕获下载）
            try:
                ok, ui_msg = self._export_via_ui(
                    page,
                    target_path,
                    diag_dir=diag_dir if (enable_diagnostics or enable_compare_diagnostics or enable_recording_mode) else None,
                    ts=ts,
                    capture_network=(enable_diagnostics or enable_compare_diagnostics or enable_recording_mode),
                    enable_auto_regenerate=enable_auto_regenerate,
                )
                if ok:
                    # 验证文件是否真的存在
                    if target_path.exists() and target_path.stat().st_size > 0:
                        # 写入导出元数据清单（与组件化导出保持一致）
                        try:
                            from datetime import datetime as _dt
                            import json as _json
                            manifest = {
                                "platform": "shopee",
                                "account_label": account_label,
                                "shop_name": getattr(shop, 'name', None),
                                "shop_id": getattr(shop, 'id', None),
                                "region": getattr(shop, 'region', None),
                                "data_type": data_type,
                                "granularity": gran,
                                "start_date": start_date,
                                "end_date": end_date,
                                "exported_at": _dt.now().isoformat(),
                                "file_path": str(target_path),
                            }
                            manifest_path = Path(str(target_path) + ".json")
                            manifest_path.write_text(_json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                        except Exception:
                            pass
                        return True, ui_msg, target_path
                    else:
                        logger.warning(f"[WARN] UI导出返回成功但文件不存在: {target_path}")
                        # 继续尝试API方案
            except Exception as e:
                logger.debug(f"UI导出流程未成功，回退到API方案: {e}")

            # API备选路径（可配置开关，默认禁用避免timestamp error）
            if not enable_api_fallback:
                logger.info("[NO] API备选已禁用，导出失败")
                return False, "UI导出失败且API备选已禁用", None

            logger.info("[RETRY] 启用API备选路径...")
            # 在浏览器上下文内发起 export -> 轮询 report -> 生成下载链接
            export_url = f"{self.base}/api/mydata/cnsc/shop/v2/product/performance/export/"
            download_api = f"{self.base}/api/v3/settings/download_report/"

            # 指标勾选已禁用：导出获取全量数据
            logger.info("[DATA] 跳过指标勾选（导出获取全量数据）")

            # 优先使用UI读取到的秒级时间戳；若UI不可用，回退到入参计算（严格 +08:00，右开区间）
            try:
                ui_start_ms, ui_end_ms = self._read_week_from_ui(page)
                start_ts = ui_start_ms // 1000 if ui_start_ms else None
                end_ts = ui_end_ms // 1000 if ui_end_ms else None
            except Exception:
                start_ts = None
                end_ts = None

            if not start_ts or not end_ts:
                # 回退：根据入参计算时间戳（+08:00，右开区间）
                try:
                    from datetime import datetime as dt, timedelta, timezone
                    tz = timezone(timedelta(hours=8))
                    sd = dt.strptime(start_date, "%Y-%m-%d").replace(tzinfo=tz)
                    ed = dt.strptime(end_date, "%Y-%m-%d").replace(tzinfo=tz)
                    start_ts = int(sd.timestamp())
                    end_ts = int((ed + timedelta(days=1)).timestamp())  # 右开区间
                    logger.info(f"时间戳回退计算: start_ts={start_ts}, end_ts={end_ts}")
                except Exception as te:
                    logger.error(f"时间戳计算失败: {te}")
                    return False, f"时间戳计算失败: {te}", None

            # 启用网络请求监听（诊断模式）
            network_requests = []
            if enable_diagnostics:
                def handle_request(request):
                    if 'export' in request.url or 'download' in request.url:
                        network_requests.append({
                            "url": request.url,
                            "method": request.method,
                            "headers": dict(request.headers),
                            "post_data": request.post_data,
                        })
                try:
                    page.on("request", handle_request)
                except Exception:
                    pass

            # 构造导出脚本
            script_export = """
            async ({export_url, download_api, shop_id, start_ts, end_ts}) => {
              const p = new URL(export_url);
              p.searchParams.set('start_ts', String(start_ts));
              p.searchParams.set('end_ts', String(end_ts));
              p.searchParams.set('period', 'week');
              p.searchParams.set('sort_by', '');
              p.searchParams.set('cnsc_shop_id', shop_id);

              // 发起请求
              const r = await fetch(p.toString(), { credentials:'include' });
              if (!r.ok) throw new Error('export http ' + r.status);
              const ct = (r.headers.get('content-type')||'').toLowerCase();
              const cd = r.headers.get('content-disposition') || '';
              const filename = (cd.match(/filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i) || []).slice(1).find(Boolean) || '';

              // 分支1：JSON流程（返回 report_id，需轮询）
              if (ct.includes('application/json')) {
                const j = await r.json();
                if (!(j && (j.code===0 || j.code===200))) throw new Error('export code ' + JSON.stringify(j));
                const report_id = j?.data?.report_id;
                if (!report_id) throw new Error('no report_id');
                // 轮询查询状态
                const wait = (ms)=>new Promise(res=>setTimeout(res,ms));
                for (let i=0;i<30;i++) {
                  const d = new URL(download_api);
                  d.searchParams.set('report_id', String(report_id));
                  d.searchParams.set('cnsc_shop_id', shop_id);
                  const dr = await fetch(d.toString(), { credentials:'include' });
                  if (dr.ok) {
                    const dj = await dr.json();
                    if (dj && (dj.code===0 || dj.code===200)) {
                      const info = dj.data || {};
                      if (info.status === 2 && info.download_link) {
                        return { mode: 'report', report_id, download_link: info.download_link };
                      }
                      if (info.status === 3) throw new Error('report failed');
                    }
                  }
                  await wait(5000);
                }
                throw new Error('report timeout');
              }

              // 分支2：非JSON（可能直接返回Excel/CSV等），改用直接下载模式
              if (ct.includes('application/octet-stream') || ct.includes('application/vnd') || ct.includes('excel') || cd.toLowerCase().includes('attachment')) {
                return { mode: 'direct', direct_url: p.toString(), content_type: ct, filename };
              }

              // 其他未知类型，返回文本诊断并走 direct_url 兜底
              const text = await r.text().catch(()=>'' );
              return { mode: 'unknown', direct_url: p.toString(), content_type: ct, filename, preview: (text||'').slice(0,200) };
            }
            """

            # 尝试导出，如果失败则自动重试一次（调整时间戳格式）
            export_attempts = []

            try:
                params = {
                    "export_url": export_url,
                    "download_api": download_api,
                    "shop_id": shop.id,
                    "start_ts": start_ts,
                    "end_ts": end_ts,
                }
                export_attempts.append({"attempt": 1, "params": params.copy()})

                result = page.evaluate(script_export, params)
                mode = result.get("mode")
                if mode == 'report':
                    download_link = result.get("download_link")
                    logger.info(f"报告生成成功，准备下载: {download_link}")
                else:
                    download_link = None
                    logger.info(f"导出返回非JSON（{result.get('content_type')}），将尝试直接下载模式")
            except Exception as e:
                # 如果走非JSON分支（直接下载），记录尝试参数头信息（仅第一轮）
                try:
                    export_attempts[-1]["result_head"] = {k: result.get(k) for k in ["mode","content_type","filename","preview"] if k in result}
                except Exception:
                    pass

                logger.warning(f"第一次导出失败: {e}")

                # 自动重试：尝试毫秒时间戳
                try:
                    logger.info("自动重试：时间戳容错回退...")
                    start_ts_fallback = start_ts * 1000
                    end_ts_fallback = end_ts * 1000

                    retry_params = {
                        "export_url": export_url,
                        "download_api": download_api,
                        "shop_id": shop.id,
                        "start_ts": start_ts_fallback,
                        "end_ts": end_ts_fallback,
                    }
                    export_attempts.append({"attempt": 2, "params": retry_params.copy(), "retry_reason": str(e)})

                    result = page.evaluate(script_export, retry_params)
                    mode = result.get("mode")
                    if mode == 'report':
                        download_link = result.get("download_link")
                        logger.info(f"重试成功，报告生成，准备下载: {download_link}")
                    else:
                        download_link = None
                        logger.info(f"重试返回非JSON（{result.get('content_type')}），将尝试直接下载模式")
                except Exception as retry_e:
                    logger.error(f"重试也失败: {retry_e}")
                    # 保存导出尝试记录用于诊断
                    if enable_diagnostics or enable_compare_diagnostics:
                        attempts_file = diag_dir / f"{ts}_export_attempts.json"
                        attempts_file.write_text(
                            json.dumps(export_attempts, ensure_ascii=False, indent=2),
                            encoding="utf-8"
                        )
                    return False, f"导出失败（已重试）: {retry_e}", None

            # 下载逻辑：优先使用 download_link；否则尝试直接下载模式
            try:
                if download_link:
                    # 正常报告下载
                    with page.expect_download(timeout=120000) as dl_info:
                        page.evaluate(
                            "(url)=>{ const a=document.createElement('a'); a.href=url; a.download=''; document.body.appendChild(a); a.click(); }",
                            download_link,
                        )
                    download = dl_info.value
                    download.save_as(str(target_path))
                else:
                    # 直接下载模式：在页面上下文触发 fetch(blob) 并触发下载
                    with page.expect_download(timeout=120000) as dl_info:
                        page.evaluate(
                            "(url)=>{ fetch(url, {credentials:'include'}).then(r=>r.blob()).then(b=>{ const blobUrl=URL.createObjectURL(b); const a=document.createElement('a'); a.href=blobUrl; a.download='export.xlsx'; document.body.appendChild(a); a.click(); setTimeout(()=>URL.revokeObjectURL(blobUrl), 5000); }); }",
                            result.get("direct_url") or result.get("download_link") or export_url,
                        )
                    download = dl_info.value
                    download.save_as(str(target_path))

                size = target_path.stat().st_size if target_path.exists() else 0
                meta = {
                    "platform": "shopee",
                    "account": account_label,
                    "shop_name": shop.name,
                    "shop_id": shop.id,
                    "data_type": data_type,
                    "granularity": gran,
                    "start_date": start_date,
                    "end_date": end_date,
                    "created_at": ts,
                    "report_id": result.get("report_id"),
                    "download_link": download_link or result.get("direct_url"),
                    "file_path": str(target_path),
                    "file_size": size,
                    "mode": result.get("mode"),
                    "content_type": result.get("content_type"),
                }
                try:
                    (out_dir / f"{ts}_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
                # 统一：在目标文件旁写入标准化 manifest（与批量/组件化一致）
                try:
                    from datetime import datetime as _dt
                    import json as _json
                    adj_manifest = {
                        "platform": "shopee",
                        "account_label": account_label,
                        "shop_name": getattr(shop, 'name', None),
                        "shop_id": getattr(shop, 'id', None),
                        "region": getattr(shop, 'region', None),
                        "data_type": data_type,
                        "granularity": gran,
                        "start_date": start_date,
                        "end_date": end_date,
                        "exported_at": _dt.now().isoformat(),
                        "file_path": str(target_path),
                    }
                    (Path(str(target_path) + ".json")).write_text(_json.dumps(adj_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass


                logger.success(f"下载完成: {target_path} ({size:,} bytes)")
                return True, "下载完成", target_path
            except Exception as e:
                logger.error(f"下载失败: {e}")
                return False, f"下载失败: {e}", None

        except Exception as e:
            logger.error(f"纯导出异常: {e}")
            return False, f"纯导出异常: {e}", None

    def _prepare_export_context(
        self,
        account: Dict,
        shop: Shop,
        start_date: str,
        end_date: str,
        download_path: str = None,
    ) -> Tuple[bool, str, Optional[object], Optional[object]]:
        """准备导出上下文：登录 -> 导航 -> 日期设置。

        Args:
            download_path: 可选的下载目录路径

        Returns:
            (success, message, page_or_none, ctx_or_none)
        """
        try:
            # 打开账号页面（设置下载目录）
            ctx, page, platform, account_id = self._open_account_page(account, download_path)

            # 导航到商品表现页面
            self._navigate_to_product_performance(page, shop)

            # 设置时间范围
            self._set_date_range(page, start_date, end_date)

            return True, "准备完成", page, ctx

        except Exception as e:
            logger.error(f"准备导出上下文异常: {e}")
            return False, f"准备导出上下文异常: {e}", None, None

    def export_products_weekly(
        self,
        account: Dict,
        shop: Shop,
        start_date: str,
        end_date: str,
        *,
        account_label: str,
        output_root: Path,
        enable_diagnostics: bool = False,
        enable_compare_diagnostics: bool = False,
        enable_recording_mode: bool = False,
        enable_auto_regenerate: bool = False,
        enable_api_fallback: bool = False,    # API备选默认禁用
        metrics: Optional[List[str]] = None,
    ) -> Tuple[bool, str, Optional[Path]]:
        """在浏览器上下文内执行导出并等待下载。

        Args:
            metrics: 要勾选的指标列表，如 ["销量", "销售额", "商品页访问量", "加购量"]
                    如果为None，将使用默认指标列表
        """
        # 默认指标列表（基于你截图中看到的指标）
        if metrics is None:
            metrics = [
                "销量", "销售额", "商品页访问量", "加购量",
                "点击率", "转化率", "订单买家数", "曝光量"
            ]

        # 统一目录
        gran = self._calculate_granularity(start_date, end_date)
        data_type = "products"
        platform = "shopee"  # 硬编码平台名
        include_shop_id = get_config_value('data_collection', 'path_options.include_shop_id', False)
        out_dir = build_output_path(
            root=output_root,
            platform=platform,
            account_label=account_label,
            shop_name=shop.name,
            data_type=data_type,
            granularity=gran,
            shop_id=getattr(shop, 'id', None),
            include_shop_id=include_shop_id,
        )
        out_dir.mkdir(parents=True, exist_ok=True)

        # 准备步骤：登录 -> 导航 -> 日期设置（设置下载目录）
        success, msg, page, ctx = self._prepare_export_context(
            account, shop, start_date, end_date, str(out_dir)
        )
        if not success:
            return False, msg, None

        # 文件名与目标路径
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = build_filename(
            ts=ts,
            account_label=account_label,
            shop_name=shop.name,
            data_type=data_type,
            granularity=gran,
            start_date=start_date,
            end_date=end_date,
            suffix=".xlsx",
        )
        target_path = out_dir / filename

        # 诊断目录
        diag_dir = out_dir / ".diag"
        if enable_diagnostics or enable_compare_diagnostics or enable_recording_mode:
            diag_dir.mkdir(exist_ok=True)
            if not enable_compare_diagnostics and not enable_recording_mode:
                self._capture_time_controls_snapshot(page, out_dir, ts)

        # 导航到商品表现页面并设置周度
        recipe_automation_success = False  # 初始化配方自动化成功标记
        try:
            self._navigate_to_product_performance(page, shop.id)

            # 检查并关闭可能的通知弹窗
            self._close_notification_modal(page)

            # 录制模式：启用tracing、注入监听器、打开Inspector
            if enable_recording_mode:
                logger.info("[ACTION] 启动录制模式...")

                # 启动tracing
                trace_path = diag_dir / f"{ts}_recording_trace.zip"
                try:
                    ctx.tracing.start(screenshots=True, snapshots=True, sources=True)
                    logger.info(f"[VID] Playwright tracing已启动，将保存到: {trace_path}")
                except Exception as e:
                    logger.warning(f"启动tracing失败: {e}")

                # 安装日期控件监听器到所有frames
                self._install_recording_monitors(page)

                # 显示录制指引并立即打开Inspector
                print("\n[TARGET] 录制模式已启动：")
                print("1. 页面已导航到商品表现页面")
                print("2. 日期控件监听器已安装（支持iframe）")
                print("3. 正在打开Playwright Inspector...")
                print("4. 请在页面上手动操作日期选择（包括iframe内的控件）")
                print("5. 完成操作后在Inspector中点击'Resume'继续")
                print("6. 系统将自动生成录制配方和trace文件")

                # 立即打开Inspector进行录制
                logger.info("[SEARCH] 打开Playwright Inspector进行录制...")
                page.pause()

                # 录制完成后的处理
                logger.info("[DATA] 录制完成，正在生成配方...")
                self.generate_date_picker_recipe(page, diag_dir, ts)

                # 停止tracing
                try:
                    ctx.tracing.stop(path=str(trace_path))
                    logger.info(f"[OK] Tracing已保存: {trace_path}")
                except Exception as e:
                    logger.warning(f"停止tracing失败: {e}")

                # 不执行自动时间设置，因为用户已手动操作
                logger.info("[TARGET] 录制模式：跳过自动时间设置（用户已手动操作）")

            # 对比诊断模式：先保存 before 快照
            elif enable_compare_diagnostics:
                # 日期控件探测
                logger.info("[SEARCH] 执行日期控件探测...")
                date_picker_info = self.inspect_date_picker(page)
                self.install_date_picker_monitor(page)

                # before 快照
                self._save_compare_snapshot(page, diag_dir, ts, "before")
                # 安装 MutationObserver，捕捉之后的DOM变化
                try:
                    self._install_mutation_observer(page)
                except Exception as _:
                    pass
                print("\n[TOOL] 对比诊断模式：")
                print("请手动完成以下操作：")
                print("1. 切换到'按周'模式")
                print("2. 设置日期范围为 2025-08-25 ~ 2025-08-31")
                print("3. 点击'选择指标'按钮")
                print("4. 勾选你需要的指标（如：销量、销售额、商品页访问量等）")
                print("5. 确认所有设置")
                input("\n完成上述操作后，按回车键继续...")

                # 尝试打开一次“选择指标”浮层，便于 after 快照捕获
                try:
                    self._open_metric_selector(page)
                except Exception:
                    pass

                # 获取日期控件交互事件
                events = self.get_date_picker_events(page)
                if events:
                    logger.info(f"[DATA] 捕获到 {len(events)} 个日期控件交互事件")
                    for event in events[-3:]:  # 显示最后3个事件
                        logger.info(f"  {event['type']}: {event.get('details', {})}")

                # 保存 after 快照
                self._save_compare_snapshot(page, diag_dir, ts, "after")
                # 导出 Mutation 变化
                try:
                    self._dump_mutations(page, diag_dir, ts)
                except Exception as _:
                    pass
                # 生成对比
                self._generate_comparison_report(diag_dir, ts)
                # 生成日期控件操作配方
                self.generate_date_picker_recipe(page, diag_dir, ts)
            else:
                # 标准模式：尝试使用录制配方，失败则回退到传统方法
                recipe_success = self._try_recipe_automation(page, start_date, end_date)
                if not recipe_success:
                    logger.info("[LIST] 配方自动化失败，回退到传统时间设置方法")
                    self._set_weekly_timerange(page, start_date, end_date)
                else:
                    # 配方自动化成功，设置标记跳过后续日期控件探测
                    recipe_automation_success = True
        except Exception as e:
            logger.error(f"设置页面周度失败: {e}")
            # 回退为快捷项：过去7天
            try:
                self._set_quick_timerange(page, label='过去7')
            except Exception:
                pass
            return False, f"设置页面周度失败: {e}", None

        # 若仍显示“今日实时”，回退为快捷项设置“过去7天”
        # 注释：移除弃用的按周设置检查逻辑，现在使用配方自动化
        # try:
        #     info = self.inspect_date_picker(page)
        #     if info and info.get('activeShortcut') in ("今日实时", "Today", "今天"):
        #         logger.warning("按周设置可能未生效，回退为快捷项：过去7天")
        #         self._set_quick_timerange(page, label='过去7')
        # except Exception:
        #     pass

        # 增强诊断（如果启用）
        if enable_diagnostics:
            self._enhanced_diagnostics(page, diag_dir)

        # 指标勾选应当发生在导出之前（标准模式）
        # 在标准模式下也执行日期控件探测（但配方自动化成功时跳过）
        if not enable_compare_diagnostics and not enable_recording_mode and not recipe_automation_success:
            logger.info("[SEARCH] 执行日期控件探测...")
            self.inspect_date_picker(page)
        # 指标勾选已禁用：导出获取全量数据
        logger.info("[DATA] 标准模式：跳过指标勾选（导出获取全量数据）")

        # 先尝试“页面交互式导出”（点击页面上的导出/下载按钮并捕获下载）
        try:
            if enable_diagnostics or enable_compare_diagnostics or enable_recording_mode:
                try:
                    pre_net = diag_dir / f"{ts}_pre_net.json"
                    self._capture_network_snapshot(page, duration_ms=8000, out_file=pre_net)
                except Exception as ne:
                    logger.debug(f"预抓取网络快照失败: {ne}")

            ok, ui_msg = self._export_via_ui(
                page,
                target_path,
                diag_dir=diag_dir,
                ts=ts,
                capture_network=(enable_diagnostics or enable_compare_diagnostics or enable_recording_mode),
                enable_auto_regenerate=enable_auto_regenerate,
            )
            if ok:
                return True, ui_msg, target_path
        except Exception as e:
            logger.debug(f"UI导出流程未成功，回退到API方案: {e}")

        # API备选路径（可配置开关，默认禁用避免timestamp error）
        if not enable_api_fallback:
            logger.info("[NO] API备选已禁用，导出失败")
            return False, "UI导出失败且API备选已禁用", None

        logger.info("[RETRY] 启用API备选路径...")
        # 在浏览器上下文内发起 export -> 轮询 report -> 生成下载链接
        export_url = f"{self.base}/api/mydata/cnsc/shop/v2/product/performance/export/"
        download_api = f"{self.base}/api/v3/settings/download_report/"

        # 指标勾选已禁用：导出获取全量数据
        logger.info("[DATA] 跳过指标勾选（导出获取全量数据）")
        if False:  # 指标勾选已禁用
            try:
                self._select_metrics(page, metrics)
                # 勾选后尝试点击“确定/应用/完成”类按钮确保设置生效
                try:
                    self._confirm_metrics_selection(page)
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"指标勾选失败（将继续导出）: {e}")

        # 优先使用UI读取到的秒级时间戳；若UI不可用，回退到入参计算（严格 +08:00，右开区间）
        try:
            ui_start_ms, ui_end_ms = self._read_week_from_ui(page)
            start_ts_ui = ui_start_ms // 1000 if ui_start_ms else None
            end_ts_ui = ui_end_ms // 1000 if ui_end_ms else None
        except Exception as e:
            start_ts_ui, end_ts_ui = None, None
            logger.warning(f"从UI读取时间失败: {e}")

        def to_ts_start_tz(d: str) -> int:
            from datetime import timezone, timedelta
            tz = timezone(timedelta(hours=8))
            dt = datetime.strptime(d, "%Y-%m-%d").replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=tz)
            return int(dt.timestamp())
        def to_ts_end_tz(d: str) -> int:
            from datetime import timezone, timedelta
            tz = timezone(timedelta(hours=8))
            dt = datetime.strptime(d, "%Y-%m-%d").replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=tz)
            dt = dt + timedelta(days=1)
            return int(dt.timestamp())

        if start_ts_ui and end_ts_ui:
            start_ts, end_ts = start_ts_ui, end_ts_ui
            logger.info(f"使用时间戳(秒): start_ts={start_ts}, end_ts={end_ts} （来源=UI）")
        else:
            start_ts, end_ts = to_ts_start_tz(start_date), to_ts_end_tz(end_date)
            logger.info(f"使用时间戳(秒): start_ts={start_ts}, end_ts={end_ts} （来源=目标周度，UI={start_ts_ui},{end_ts_ui}）")

        # 启用网络请求监听（诊断模式）
        network_requests = []
        if enable_diagnostics:
            def handle_request(request):
                if 'export' in request.url or 'download' in request.url:
                    network_requests.append({
                        "url": request.url,
                        "method": request.method,
                        "headers": dict(request.headers),
                        "post_data": request.post_data
                    })
            page.on("request", handle_request)

        # 时间戳容错回退策略
        start_ts_fallback = start_ts
        end_ts_fallback = end_ts

        logger.info("发起导出请求（页面上下文）...")
        script_export = """
        async ({export_url, download_api, shop_id, start_ts, end_ts}) => {
          const p = new URL(export_url);
          p.searchParams.set('start_ts', String(start_ts));
          p.searchParams.set('end_ts', String(end_ts));
          p.searchParams.set('period', 'week');
          p.searchParams.set('sort_by', '');
          p.searchParams.set('cnsc_shop_id', shop_id);

          // 发起请求
          const r = await fetch(p.toString(), { credentials:'include' });
          if (!r.ok) throw new Error('export http ' + r.status);
          const ct = (r.headers.get('content-type')||'').toLowerCase();
          const cd = r.headers.get('content-disposition') || '';
          const filename = (cd.match(/filename\\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i) || []).slice(1).find(Boolean) || '';

          // 分支1：JSON流程（返回 report_id，需轮询）
          if (ct.includes('application/json')) {
            const j = await r.json();
            if (!(j && (j.code===0 || j.code===200))) throw new Error('export code ' + JSON.stringify(j));
            const report_id = j?.data?.report_id;
            if (!report_id) throw new Error('no report_id');
            // 轮询查询状态
            const wait = (ms)=>new Promise(res=>setTimeout(res,ms));
            for (let i=0;i<30;i++) {
              const d = new URL(download_api);
              d.searchParams.set('report_id', String(report_id));
              d.searchParams.set('cnsc_shop_id', shop_id);
              const dr = await fetch(d.toString(), { credentials:'include' });
              if (dr.ok) {
                const dj = await dr.json();
                if (dj && (dj.code===0 || dj.code===200)) {
                  const info = dj.data || {};
                  if (info.status === 2 && info.download_link) {
                    return { mode: 'report', report_id, download_link: info.download_link };
                  }
                  if (info.status === 3) throw new Error('report failed');
                }
              }
              await wait(5000);
            }
            throw new Error('report timeout');
          }

          // 分支2：非JSON（可能直接返回Excel/CSV等），改用直接下载模式
          if (ct.includes('application/octet-stream') || ct.includes('application/vnd') || ct.includes('excel') || cd.toLowerCase().includes('attachment')) {
            return { mode: 'direct', direct_url: p.toString(), content_type: ct, filename };
          }

          // 其他未知类型，返回文本诊断并走 direct_url 兜底
          const text = await r.text().catch(()=>'');
          return { mode: 'unknown', direct_url: p.toString(), content_type: ct, filename, preview: (text||'').slice(0,200) };
        }
        """

        # 尝试导出，如果失败则自动重试一次（调整时间戳格式）
        export_attempts = []

        try:
            params = {
                "export_url": export_url,
                "download_api": download_api,
                "shop_id": shop.id,
                "start_ts": start_ts,
                "end_ts": end_ts,
            }
            export_attempts.append({"attempt": 1, "params": params.copy()})

            result = page.evaluate(script_export, params)
            mode = result.get("mode")
            if mode == 'report':
                download_link = result.get("download_link")
                logger.info(f"报告生成成功，准备下载: {download_link}")
            else:
                download_link = None
                logger.info(f"导出返回非JSON（{result.get('content_type')}），将尝试直接下载模式")
        except Exception as e:
            # 如果走非JSON分支（直接下载），记录尝试参数头信息（仅第一轮）
            try:
                export_attempts[-1]["result_head"] = {k: result.get(k) for k in ["mode","content_type","filename","preview"] if k in result}
            except Exception:
                pass

            logger.warning(f"第一次导出失败: {e}")

            # 自动重试：尝试毫秒时间戳
            try:
                logger.info("自动重试：时间戳容错回退...")

                # 时间戳回退策略：严格 +08:00 对齐，end_ts 安全钳制
                from datetime import timezone, timedelta
                tz_plus8 = timezone(timedelta(hours=8))

                # 将 start_ts 对齐到当天 00:00 +08:00
                start_dt = datetime.fromtimestamp(start_ts, tz=tz_plus8)
                start_aligned = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                start_ts_fallback = int(start_aligned.timestamp())

                # end_ts 钳制：不超过昨天 23:59:59 +08:00
                now_plus8 = datetime.now(tz=tz_plus8)
                yesterday_end = (now_plus8 - timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0)
                end_ts_max = int(yesterday_end.timestamp())
                end_ts_fallback = min(end_ts, end_ts_max)

                logger.info(f"回退时间戳: start={start_ts_fallback}, end={end_ts_fallback}")

                retry_params = {
                    "export_url": export_url,
                    "download_api": download_api,
                    "shop_id": shop.id,
                    "start_ts": start_ts_fallback,
                    "end_ts": end_ts_fallback,
                }
                export_attempts.append({"attempt": 2, "params": retry_params.copy(), "retry_reason": str(e)})

                result = page.evaluate(script_export, retry_params)
                mode = result.get("mode")
                if mode == 'report':
                    download_link = result.get("download_link")
                    logger.info(f"重试成功，报告生成，准备下载: {download_link}")
                else:
                    download_link = None
                    logger.info(f"重试返回非JSON（{result.get('content_type')}），将尝试直接下载模式")
            except Exception as retry_e:
                logger.error(f"重试也失败: {retry_e}")

                # 保存导出尝试记录用于诊断
                if enable_diagnostics or enable_compare_diagnostics:
                    attempts_file = diag_dir / f"{ts}_export_attempts.json"
                    attempts_file.write_text(
                        json.dumps(export_attempts, ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )
                return False, f"导出失败（已重试）: {retry_e}", None
        # 下载逻辑：优先使用 download_link；否则尝试直接下载模式
        try:
            if download_link:
                # 正常报告下载
                with page.expect_download(timeout=120000) as dl_info:
                    page.evaluate(
                        "(url)=>{ const a=document.createElement('a'); a.href=url; a.download=''; document.body.appendChild(a); a.click(); }",
                        download_link,
                    )
                download = dl_info.value
                download.save_as(str(target_path))
            else:
                # 直接下载模式：在页面上下文触发 fetch(blob) 并触发下载
                with page.expect_download(timeout=120000) as dl_info:
                    page.evaluate(
                        "(url)=>{ fetch(url, {credentials:'include'}).then(r=>r.blob()).then(b=>{ const blobUrl=URL.createObjectURL(b); const a=document.createElement('a'); a.href=blobUrl; a.download='export.xlsx'; document.body.appendChild(a); a.click(); setTimeout(()=>URL.revokeObjectURL(blobUrl), 5000); }); }",
                        result.get("direct_url") or result.get("download_link") or export_url,
                    )
                download = dl_info.value
                download.save_as(str(target_path))

            size = target_path.stat().st_size if target_path.exists() else 0
            meta = {
                "platform": platform,
                "account": account_label,
                "shop_id": shop.id,
                "shop_name": shop.name,
                "data_type": data_type,
                "granularity": gran,

                "start_date": start_date,
                "end_date": end_date,
                "created_at": ts,
                "report_id": result.get("report_id"),
                "download_link": download_link or result.get("direct_url"),
                "file_path": str(target_path),
                "file_size": size,
                "mode": result.get("mode"),
                "content_type": result.get("content_type"),
            }
            (target_path.with_suffix(target_path.suffix + ".meta.json")).write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            if enable_diagnostics and network_requests:
                network_file = diag_dir / f"{ts}_network_requests.json"
                network_file.write_text(
                    json.dumps(network_requests, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                logger.info(f"网络请求信息已保存: {network_file}")

            logger.success(f"下载完成: {target_path} ({size:,} bytes)")
            return True, "下载完成", target_path
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return False, f"下载失败: {e}", None




    def _open_date_picker(self, page) -> bool:
        """打开日期选择器弹出层。
        基于DOM差异：
        - 未打开：class="bi-date-input track-click-open-time-selector"
        - 已打开：class="bi-date-input bi-date-input__focus track-click-open-time-selector"
        """
        try:
            container_selectors = [

                '.bi-date-input.track-click-open-time-selector',
                '.track-click-open-time-selector.bi-date-input',
                '.track-click-open-time-selector .bi-date-input',
                'div.track-click-open-time-selector',
                'div:has(.bi-date-input-icon):has-text("统计时间")',
                'div.bi-date-input',
                'div:has(span.title:has-text("统计时间"))',
                'div:has(span.value)',
                '[class*="bi-date-input"][class*="track-click-open-time-selector"]',
                '.bi-date-input:has(span.title:has-text("统计时间"))',
                '.bi-date-input__suffix',
                '.bi-date-input-icon',
                'span.value',
                'text=今日实时',
                'text=Today',
            ]

            def is_open() -> bool:
                # 1) 根据 focus class 判断（包括容器祖先）
                try:
                    if page.locator('.bi-date-input.bi-date-input__focus.track-click-open-time-selector, .bi-date-input.bi-date-input__focus').count() > 0:
                        return True
                except Exception:
                    pass
                for s in container_selectors:
                    try:
                        loc = page.locator(s)
                        if loc.count() > 0:
                            parent = loc.first.locator('xpath=ancestor-or-self::div[contains(@class,"bi-date-input")]').first
                            if parent and (parent.get_attribute('class') or '').find('bi-date-input__focus') >= 0:
                                return True
                    except Exception:
                        continue
                # 2) 弹层内容出现也视为已打开
                if page.locator('.eds-date-shortcut-item, .bi-date-shortcuts li, .eds-date-picker, .bi-date-picker').count() > 0:
                    return True
                # 3) 聚焦态通过ARIA/role也可能可见
                try:
                    role_popup = page.get_by_role('dialog')
                    if role_popup.count() > 0 and role_popup.first.is_visible():
                        return True
                except Exception:
                    pass
                return False

            # 已经打开
            if is_open():
                return True

            # 优先尝试配方复刻（如果存在）
            try:
                # 从当前URL提取shop_id
                current_url = page.url
                shop_id_match = re.search(r'cnsc_shop_id=(\d+)', current_url)
                if shop_id_match:
                    shop_id = shop_id_match.group(1)
                    recipe = self.load_date_picker_recipe(shop_id)
                    if recipe:
                        logger.info("[ACTION] 尝试使用配方复刻打开日期控件")
                        if self.replay_date_picker_recipe(page, recipe):
                            page.wait_for_timeout(500)
                            if is_open():
                                logger.info("已打开日期选择器: 配方复刻成功")
                                return True
            except Exception as e:
                logger.debug(f"配方复刻失败: {e}")

            # 若未打开，使用强制打开一次（JS+坐标）
            try:
                if self._force_open_date_picker(page):
                    page.wait_for_timeout(300)
                    if is_open():
                        logger.info("已打开日期选择器: 强制打开成功")
                        return True
            except Exception:
                pass

            # 多轮尝试点击容器/图标/坐标
            for _ in range(3):
                clicked = False
                for sel in container_selectors:
                    try:
                        loc = page.locator(sel)
                        if loc.count() > 0 and loc.first.is_visible():
                            el = loc.first
                            try:
                                before = el.get_attribute('class') or ''
                                logger.debug(f'日期容器[{sel}] before class="{before}"')
                            except Exception:
                                pass

                            # 确保在视口内并悬停
                            try:
                                el.scroll_into_view_if_needed()
                                el.hover()
                            except Exception:
                                pass

                            # 1) 常规点击 + 等待
                            try:
                                el.click(force=True)
                                clicked = True
                                page.wait_for_timeout(300)
                                # 显式等待焦点或弹层可见
                                try:
                                    page.wait_for_selector('.bi-date-input.bi-date-input__focus.track-click-open-time-selector, .eds-date-picker, .bi-date-picker, [role="dialog"]', state='visible', timeout=1200)
                                except Exception:
                                    pass
                                if is_open():
                                    logger.info(f"已打开日期选择器: 通过点击 {sel}")
                                    return True
                                # 额外点击 span.value 文本
                                try:
                                    val = el.locator('span.value')
                                    if val.count() > 0 and val.first.is_visible():
                                        val.first.click()
                                        page.wait_for_timeout(200)
                                        if is_open():
                                            logger.info("已打开日期选择器: 点击 span.value")
                                            return True
                                except Exception:
                                    pass
                                # 回车键尝试打开
                                try:
                                    el.focus()
                                    el.press('Enter')
                                    page.wait_for_timeout(200)
                                    if is_open():
                                        logger.info("已打开日期选择器: Enter 键")
                                        return True
                                except Exception:
                                    pass
                            except Exception:
                                pass

                            # 2) 双击尝试
                            try:
                                el.dblclick()
                                page.wait_for_timeout(300)
                                if is_open():
                                    logger.info(f"已打开日期选择器: 双击 {sel}")
                                    return True
                            except Exception:
                                pass

                            # 3) 点击内部图标/后缀
                            try:
                                icon = el.locator('.bi-date-input-icon, .bi-date-input__suffix')
                                if icon.count() > 0 and icon.first.is_visible():
                                    icon.first.click(force=True)
                                    page.wait_for_timeout(300)
                                    if is_open():
                                        logger.info(f"已打开日期选择器: 点击图标 {sel}")
                                        return True
                            except Exception:
                                pass

                            # 4) 坐标点击兜底
                            try:
                                box = el.bounding_box()
                                if box:
                                    page.mouse.move(box['x'] + box['width']/2, box['y'] + box['height']/2)
                                    page.mouse.down()
                                    page.mouse.up()
                                    page.wait_for_timeout(300)
                                    if is_open():
                                        logger.info(f"已打开日期选择器: 坐标点击 {sel}")
                                        return True
                            except Exception:
                                pass

                            # 5) JS 强制点击
                            try:
                                page.evaluate("(sel)=>{const el=document.querySelector(sel); if(el){el.click(); el.dispatchEvent(new MouseEvent('click',{bubbles:true}))}}", sel)
                                page.wait_for_timeout(300)
                                if is_open():
                                    logger.info(f"已打开日期选择器: JS 点击 {sel}")
                                    return True
                            except Exception:
                                pass
                    except Exception:
                        continue

                if not clicked:
                    # 兜底：点击“统计时间”文本或图标
                    try:
                        t = page.locator('text=统计时间')
                        if t.count() > 0 and t.first.is_visible():
                            t.first.scroll_into_view_if_needed()
                            t.first.hover()
                            t.first.click(force=True)
                            page.wait_for_timeout(300)
                            if is_open():
                                logger.info('已打开日期选择器: 点击统计时间文本')
                                return True
                    except Exception:
                        pass
                    try:
                        ico = page.locator('.bi-date-input-icon')
                        if ico.count() > 0 and ico.first.is_visible():
                            try:
                                ico.first.scroll_into_view_if_needed()
                                ico.first.hover()
                                ico.first.click(force=True)
                                page.wait_for_timeout(300)
                                if is_open():
                                    logger.info('已打开日期选择器: 点击页面级图标')
                                    return True
                            except Exception:
                                pass
                    except Exception:
                        pass

                logger.warning('多次尝试后仍未能打开日期选择器')
                return False
        except Exception as e:
            logger.error(f'打开日期选择器失败: {e}')
            return False

    def _force_open_date_picker(self, page) -> bool:
        """使用JS+坐标的强制打开方式，直接作用于 .bi-date-input 容器。
        返回 True 表示推测已打开（随后由 is_open 二次校验）。"""
        try:
            # 1) 等待时间显示元素出现
            try:
                page.wait_for_selector('span.value, .bi-date-input', state='attached', timeout=2000)
            except Exception:
                pass

            # 2) 用 JS 找到容器并尝试滚动与点击
            script = """
            () => {
                const res = { ok: false, x: null, y: null, w: null, h: null, used: null };
                let container = document.querySelector('.bi-date-input.track-click-open-time-selector');
                if (!container) {
                    const val = document.querySelector('span.value');
                    if (val) container = val.closest('.bi-date-input');
                }
                if (!container) container = document.querySelector('.bi-date-input');
                if (!container) return res;

                const rect = container.getBoundingClientRect();
                const topOffset = Math.max(0, rect.top - 160);
                window.scrollTo({ top: window.scrollY + topOffset, behavior: 'instant' });

                // 直接触发 click 事件
                try {
                    container.click();
                    container.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                    res.ok = true;
                    res.x = rect.left + rect.width / 2;
                    res.y = rect.top + rect.height / 2;
                    res.w = rect.width; res.h = rect.height; res.used = 'element.click';
                    return res;
                } catch (e) {}

                // 退化方案：点击图标/后缀
                const ico = container.querySelector('.bi-date-input-icon, .bi-date-input__suffix');
                if (ico) {
                    try { ico.click(); res.ok = true; res.used = 'icon.click'; } catch(e){}
                }

                res.x = rect.left + rect.width / 2;
                res.y = rect.top + rect.height / 2;
                res.w = rect.width; res.h = rect.height; res.used = res.used || 'coords';
                return res;
            }
            """
            info = page.evaluate(script)
            if info:
                try:
                    # 3) 如果需要，用坐标再点一次
                    if info.get('used') == 'coords' or not self._read_time_display(page):
                        x = float(info.get('x') or 0.0)
                        y = float(info.get('y') or 0.0)
                        if x and y:
                            page.mouse.move(x, y)
                            page.mouse.down()
                            page.mouse.up()
                except Exception:
                    pass
            page.wait_for_timeout(350)
            return True
        except Exception as e:
            logger.warning(f"_force_open_date_picker 失败: {e}")
            return False


    def _read_time_display(self, page) -> Dict[str, str]:
        """读取页面时间控件的显示文本（label/value）。"""
        try:
            script = """
            () => {
                const res = { label: null, value: null, text: null };
                const candidates = Array.from(document.querySelectorAll(
                    '.bi-date-input.track-click-open-time-selector, .bi-date-input'
                ));
                for (const el of candidates) {
                    const title = el.querySelector('.title')?.textContent?.trim();
                    const label = el.querySelector('.label')?.textContent?.trim() || null;
                    const value = el.querySelector('.value')?.textContent?.trim() || null;
                    const text = el.textContent?.trim() || null;
                    if (title?.includes('统计时间') || label || value) {
                        return { label, value, text };
                    }
                }
                // fallback: 全局搜索包含“统计时间”的元素
                const all = Array.from(document.querySelectorAll('*'));
                const node = all.find(n => (n.textContent || '').includes('统计时间'));
                if (node) {
                    const el = node.closest('.bi-date-input') || node.parentElement;
                    if (el) {
                        const label = el.querySelector('.label')?.textContent?.trim() || null;
                        const value = el.querySelector('.value')?.textContent?.trim() || null;
                        const text = el.textContent?.trim() || null;
                        return { label, value, text };
                    }
                }
                return res;
            }
            """;
            return page.evaluate(script)
        except Exception:
            return {"label": None, "value": None, "text": None}

    def _wait_time_display_change(self, page, prev_text: str | None, timeout_ms: int = 6000) -> bool:
        """等待时间控件显示文本发生变化。
        返回 True 表示文本更新且不再是“今日实时/Today/今天”。
        """
        try:
            checks = 0
            while checks * 300 < timeout_ms:
                info = self._read_time_display(page)
                cur = info.get('value') or info.get('label') or info.get('text') or ''
                if cur and cur != prev_text and ('今日实时' not in cur) and ('Today' not in cur) and ('今天' not in cur):
                    return True
                page.wait_for_timeout(300)
                checks += 1
        except Exception:
            pass
        return False

    def _set_quick_timerange(self, page, label: str = '过去7') -> bool:
        """通过快捷项设置时间范围，例如：过去7天/过去30天。
        label: 关键字，支持 '过去7' / '过去30' / 'Last 7' / 'Last 30' / '近7' / '近30'
        """
        try:
            # 读取之前的时间显示
            prev = (self._read_time_display(page) or {}).get('value')

            opened = self._open_date_picker(page)
            if not opened:
                logger.warning("未能打开日期选择器，将尝试直接查找快捷项。")

            candidates = [
                f'.eds-date-shortcut-item:has-text("{label}")',
                f'.bi-date-shortcuts li:has-text("{label}")',
            ]
            # 多语言候选
            synonyms = []
            if '7' in label:
                synonyms = ['过去7', 'Last 7', '近7', '7 天', '7天']
            elif '30' in label:
                synonyms = ['过去30', 'Last 30', '近30', '30 天', '30天']
            for s in synonyms:
                candidates.append(f'.eds-date-shortcut-item:has-text("{s}")')
                candidates.append(f'.bi-date-shortcuts li:has-text("{s}")')

            clicked = False
            for sel in candidates:
                try:
                    loc = page.locator(sel)
                    if loc.count() > 0 and loc.first.is_visible():
                        loc.first.click()
                        logger.info(f"点击快捷项: {sel}")
                        clicked = True
                        break
                except Exception:
                    continue

            if not clicked:
                logger.warning(f"未找到快捷项: {label}")
                return False

            # 可能需要点击确定/应用
            for ok_sel in ['button:has-text("确定")', 'button:has-text("应用")', '.ant-modal .ant-btn-primary', '.el-dialog .el-button--primary']:
                try:
                    ok = page.locator(ok_sel)
                    if ok.count() > 0 and ok.first.is_visible():
                        ok.first.click()
                        logger.info(f"点击快捷项确认按钮: {ok_sel}")
                        break
                except Exception:
                    continue

            # 等待时间显示发生变化（不再是“今日实时”）
            if self._wait_time_display_change(page, prev):
                logger.info("快捷项生效：时间显示已变化")
                return True

            # 若未能通过显示文本判断，回退到探测器判断
            try:
                info = self.inspect_date_picker(page)
                active = (info or {}).get('activeShortcut')
                if active and ('7' in label and ('7' in active or '7 ' in active)):
                    return True
                if active and ('30' in label and ('30' in active or '30 ' in active)):
                    return True
            except Exception:
                pass

            # 兜底：认为已点击，返回 True，让后续网络参数校验来保证
            return True
        except Exception as e:
            logger.error(f"快捷时间设置失败: {e}")
            return False


    def _navigate_to_product_performance(self, page, shop_id: str):
        """导航到商品表现页面"""
        perf_url = f"{self.base}/datacenter/product/performance?cnsc_shop_id={shop_id}"
        logger.info(f"导航到商品表现页面: {perf_url}")
        page.goto(perf_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)  # 等待页面渲染

    def _close_notification_modal(self, page):
        """检查并关闭可能的通知弹窗"""
        try:
            logger.info("[SEARCH] 检查是否有通知弹窗需要关闭...")

            # 等待页面稳定
            page.wait_for_timeout(1000)

            # 多种可能的弹窗关闭按钮选择器
            close_selectors = [
                # 您提供的具体选择器
                'i.eds-icon.eds-modal__close',
                'i[data-v-ef5019c0][data-v-25a12b69].eds-icon.eds-modal__close',

                # 通用的弹窗关闭选择器
                '.eds-modal__close',
                '.modal-close',
                '.close-btn',
                'button[aria-label="Close"]',
                'button[aria-label="关闭"]',
                '.ant-modal-close',
                '.el-dialog__close',

                # SVG关闭图标
                'svg[viewBox="0 0 16 16"] path[fill-rule="evenodd"]',

                # 通用关闭按钮文本
                'button:has-text("关闭")',
                'button:has-text("取消")',
                'button:has-text("稍后再说")',
                'button:has-text("我知道了")',

                # X形状的关闭按钮
                '[class*="close"]:visible',
                '[class*="dismiss"]:visible'
            ]

            modal_closed = False
            for selector in close_selectors:
                try:
                    # 检查元素是否存在且可见
                    element = page.locator(selector).first
                    if element.count() > 0 and element.is_visible():
                        logger.info(f"[TARGET] 发现通知弹窗，点击关闭按钮: {selector}")
                        element.click()
                        page.wait_for_timeout(500)  # 等待弹窗关闭动画
                        modal_closed = True
                        break
                except Exception as e:
                    logger.debug(f"尝试关闭选择器失败 {selector}: {e}")
                    continue

            if modal_closed:
                logger.info("[OK] 通知弹窗已关闭")
                page.wait_for_timeout(1000)  # 等待页面稳定
            else:
                logger.debug("[NOTE] 未发现需要关闭的通知弹窗")

        except Exception as e:
            logger.debug(f"检查通知弹窗失败: {e}")
            # 不抛出异常，继续后续操作

    def _set_weekly_timerange(self, page, start_date: str, end_date: str):
        """设置页面为按周模式并选择目标周度"""
        try:
            # 0. 打开日期控件
            if not self._open_date_picker(page):
                logger.warning("未能打开日期选择器，将直接尝试点击‘按周’标签")

            # 1. 切换到按周模式
            logger.info("切换到按周模式...")

            # 尝试多种可能的"按周"选择器（在弹层内）
            week_selectors = [
                '.eds-date-shortcut-item:has-text("按周")',
                '.bi-date-shortcuts li:has-text("按周")',
                'text="按周"',
                '[data-testid*="week"]',
                '.time-range-selector [role="radio"]:has-text("周")',
                '.period-selector button:has-text("周")',
                'button:has-text("按周")',
                'label:has-text("按周")',
            ]

            week_clicked = False
            for selector in week_selectors:
                try:
                    if page.locator(selector).count() > 0:
                        page.locator(selector).first.click()
                        week_clicked = True
                        logger.info(f"成功点击按周选择器: {selector}")
                        break
                except Exception:
                    continue

            if not week_clicked:
                logger.warning("未找到按周选择器，尝试继续...")

            page.wait_for_timeout(1500)

            # 2. 设置日期范围（如果有日期选择器）
            logger.info(f"设置日期范围: {start_date} ~ {end_date}")

            # 尝试设置开始日期
            start_selectors = [
                'input[placeholder*="开始"]',
                'input[placeholder*="起始"]',
                'input[name*="start"]',
                '.date-picker input:first-child',
                '.time-range input:first-child',
            ]

            for selector in start_selectors:
                try:
                    if page.locator(selector).count() > 0:
                        page.locator(selector).first.fill(start_date)
                        logger.info(f"设置开始日期: {selector}")
                        break
                except Exception:
                    continue

            # 尝试设置结束日期
            end_selectors = [
                'input[placeholder*="结束"]',
                'input[placeholder*="截止"]',
                'input[name*="end"]',
                '.date-picker input:last-child',
                '.time-range input:last-child',
            ]

            for selector in end_selectors:
                try:
                    if page.locator(selector).count() > 0:
                        page.locator(selector).first.fill(end_date)
                        logger.info(f"设置结束日期: {selector}")
                        break
                except Exception:
                    continue

            page.wait_for_timeout(1000)

            # 3. 确认/应用设置
            confirm_selectors = [
                'button:has-text("确定")',
                'button:has-text("应用")',
                'button:has-text("查询")',
                '.date-picker button[type="submit"]',
            ]

            for selector in confirm_selectors:
                try:
                    if page.locator(selector).count() > 0:
                        page.locator(selector).first.click()
                        logger.info(f"点击确认按钮: {selector}")
                        break
                except Exception:
                    continue

            page.wait_for_timeout(2000)  # 等待页面更新
            logger.info("周度设置完成")

        except Exception as e:
            logger.error(f"设置周度失败: {e}")
            raise

    def _capture_time_controls_snapshot(self, page, out_dir: Path, timestamp: str):
        """捕获时间控件快照用于诊断"""
        try:
            diag_dir = out_dir / ".diag"
            diag_dir.mkdir(parents=True, exist_ok=True)

            # 捕获时间控件区域的HTML
            time_selectors = [
                '.time-range-selector',
                '.date-picker',
                '.period-selector',
                '[class*="time"]',
                '[class*="date"]',
                '[class*="period"]',
            ]

            snapshot = {
                "timestamp": timestamp,
                "url": page.url,
                "time_controls": {}
            }

            for i, selector in enumerate(time_selectors):
                try:
                    elements = page.locator(selector)
                    if elements.count() > 0:
                        element = elements.first
                        snapshot["time_controls"][f"selector_{i}"] = {
                            "selector": selector,
                            "count": elements.count(),
                            "html": element.inner_html(),
                            "text": element.inner_text(),
                            "outer_html": element.evaluate("el => el.outerHTML")
                        }
                except Exception as e:
                    snapshot["time_controls"][f"selector_{i}_error"] = str(e)

            # 保存快照
            snapshot_file = diag_dir / f"{timestamp}_time_controls.json"
            snapshot_file.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"时间控件快照已保存: {snapshot_file}")

        except Exception as e:
            logger.warning(f"捕获时间控件快照失败: {e}")

    def _enhanced_diagnostics(self, page: "Page", diag_dir: Path) -> None:
        """增强诊断：保存页面HTML、截图、时间控件、指标勾选项、网络请求等"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # 1. 全页HTML和截图
            html_file = diag_dir / f"{timestamp}_page.html"
            screenshot_file = diag_dir / f"{timestamp}_page.png"

            html_file.write_text(page.content(), encoding="utf-8")
            page.screenshot(path=str(screenshot_file), full_page=True)
            logger.info(f"页面HTML和截图已保存: {html_file}, {screenshot_file}")

            # 2. 时间控件详细信息
            time_info = self._extract_time_controls(page)
            time_file = diag_dir / f"{timestamp}_time_controls_enhanced.json"
            time_file.write_text(json.dumps(time_info, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"时间控件详细信息已保存: {time_file}")

            # 3. 指标勾选项清单
            metrics_info = self._extract_metrics_checkboxes(page)
            metrics_file = diag_dir / f"{timestamp}_metrics_checkboxes.json"
            metrics_file.write_text(json.dumps(metrics_info, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"指标勾选项清单已保存: {metrics_file}")

            # 4. 可访问性树快照
            try:
                accessibility_tree = page.accessibility.snapshot()
                accessibility_file = diag_dir / f"{timestamp}_accessibility.json"
                accessibility_file.write_text(json.dumps(accessibility_tree, ensure_ascii=False, indent=2), encoding="utf-8")
                logger.info(f"可访问性树已保存: {accessibility_file}")
            except Exception as e:
                logger.warning(f"可访问性树快照失败: {e}")

        except Exception as e:
            logger.error(f"增强诊断失败: {e}")

    def _extract_time_controls(self, page: "Page") -> Dict:
        """提取时间控件的详细信息"""
        time_info = {
            "timestamp": datetime.now().isoformat(),
            "url": page.url,
            "time_selectors": {}
        }

        # 常见的时间选择器
        selectors = [
            'span.value',  # 你提供的时间显示元素
            '[data-v-2aefd622].value',
            '.date-range-picker span',
            '.time-range span',
            '.date-picker-input',
            'input[placeholder*="时间"]',
            'input[placeholder*="日期"]',
        ]

        for selector in selectors:
            try:
                elements = page.locator(selector).all()
                for i, element in enumerate(elements):
                    if element.is_visible():
                        info = {
                            "selector": selector,
                            "index": i,
                            "text_content": element.text_content(),
                            "inner_text": element.inner_text(),
                            "outer_html": element.get_attribute("outerHTML"),
                            "bounding_box": element.bounding_box(),
                            "attributes": {}
                        }

                        # 获取所有属性
                        try:
                            attrs = page.evaluate("""
                                (element) => {
                                    const attrs = {};
                                    for (let attr of element.attributes) {
                                        attrs[attr.name] = attr.value;
                                    }
                                    return attrs;
                                }
                            """, element.element_handle())
                            info["attributes"] = attrs
                        except:
                            pass

                        key = f"{selector}_{i}"
                        time_info["time_selectors"][key] = info

            except Exception as e:
                logger.debug(f"时间选择器 {selector} 提取失败: {e}")

        return time_info

    def _extract_metrics_checkboxes(self, page: "Page") -> Dict:
        """提取指标勾选项的详细信息"""
        metrics_info = {
            "timestamp": datetime.now().isoformat(),
            "url": page.url,
            "checkboxes": {},
            "labels": {},
            "multi_selector_items": {},
            "table_headers": []
        }

        try:
            # 方法1: 通过checkbox角色查找
            checkboxes = page.get_by_role("checkbox").all()
            for i, checkbox in enumerate(checkboxes):
                if checkbox.is_visible():
                    try:
                        info = {
                            "index": i,
                            "checked": checkbox.is_checked(),
                            "text": checkbox.text_content(),
                            "inner_text": checkbox.inner_text(),
                            "bounding_box": checkbox.bounding_box(),
                            "locator_info": str(checkbox)
                        }

                        # 尝试获取关联的label文本
                        try:
                            # 查找父级或兄弟元素中的文本
                            parent = checkbox.locator("..")
                            parent_text = parent.text_content()
                            if parent_text and parent_text.strip():
                                info["parent_text"] = parent_text.strip()
                        except:
                            pass

                        metrics_info["checkboxes"][f"checkbox_{i}"] = info
                    except Exception as e:
                        logger.debug(f"checkbox {i} 信息提取失败: {e}")

        except Exception as e:
            logger.debug(f"checkbox角色查找失败: {e}")

        try:
            # 方法2: 通过input[type="checkbox"]查找
            checkbox_inputs = page.locator('input[type="checkbox"]').all()
            for i, checkbox in enumerate(checkbox_inputs):
                if checkbox.is_visible():
                    try:
                        info = {
                            "index": i,
                            "checked": checkbox.is_checked(),
                            "value": checkbox.get_attribute("value"),
                            "name": checkbox.get_attribute("name"),
                            "id": checkbox.get_attribute("id"),
                            "bounding_box": checkbox.bounding_box()
                        }

                        # 查找关联的label
                        checkbox_id = checkbox.get_attribute("id")
                        if checkbox_id:
                            try:
                                label = page.locator(f'label[for="{checkbox_id}"]')
                                if label.is_visible():
                                    info["label_text"] = label.text_content()
                            except:
                                pass

                        metrics_info["labels"][f"input_checkbox_{i}"] = info
                    except Exception as e:
                        logger.debug(f"input checkbox {i} 信息提取失败: {e}")

        except Exception as e:
            logger.debug(f"input checkbox查找失败: {e}")

        # 方法3: 专门采集 multi-selector 指标项（针对 Shopee 自定义组件）
        try:
            multi_items = page.locator('li.multi-selector__item').all()
            for i, item in enumerate(multi_items):
                if item.is_visible():
                    try:
                        # 获取标题文本
                        title_element = item.locator('.title').first
                        title_text = title_element.text_content() if title_element.count() > 0 else ""

                        # 获取 class 属性，判断是否选中
                        class_attr = item.get_attribute("class") or ""
                        is_selected = "selected" in class_attr

                        info = {
                            "index": i,
                            "title": title_text.strip() if title_text else "",
                            "class": class_attr,
                            "selected": is_selected,
                            "bounding_box": item.bounding_box(),
                            "outer_html": item.evaluate("el => el.outerHTML")[:500] if item.count() > 0 else ""
                        }

                        metrics_info["multi_selector_items"][f"item_{i}"] = info

                    except Exception as e:
                        logger.debug(f"multi-selector item {i} 信息提取失败: {e}")
        except Exception as e:
            logger.debug(f"multi-selector 查找失败: {e}")
        # 方法4: 采集表格表头（作为已选指标的替代信号）
        try:
            header_cells = page.locator('table thead th .title, table thead th [class*="title"]').all()
            headers = []
            for cell in header_cells:
                try:
                    text = (cell.text_content() or '').strip()
                    if text:
                        headers.append(text)
                except:
                    pass
            metrics_info["table_headers"] = headers
        except Exception as e:
            logger.debug(f"表头提取失败: {e}")

        return metrics_info

    def _read_week_from_ui(self, page: "Page") -> Tuple[Optional[int], Optional[int]]:
        """从页面UI读取周度时间范围，返回毫秒时间戳"""
        try:
            # 查找时间显示元素
            time_selectors = [
                'span.value',
                '[data-v-2aefd622].value',
                '.date-range-picker span',
                '.time-range span'
            ]

            date_text = None
            for selector in time_selectors:
                try:
                    element = page.locator(selector).first
                    if element.is_visible():
                        text = element.text_content()
                        # 支持范围格式和单日格式
                        if text and 'GMT' in text and (('-' in text) or ('/' in text) or ('-' in text)):
                            date_text = text
                            logger.info(f"从UI读取到时间范围: {date_text}")
                            break
                except:
                    continue

            if not date_text:
                logger.warning("未能从UI读取到时间范围")
                return None, None

            # 解析格式: 支持多种格式
            # 1. 范围格式: "11-08-2025 - 17-08-2025 (GMT+08)" 或 "23/08/2025 - 29/08/2025 (GMT-03)"
            # 2. 单日格式: "29/08/2025 (GMT-03)" 或 "29-08-2025 (GMT+08)"
            patterns = [
                # 范围格式
                (r'(\d{2}-\d{2}-\d{4})\s*-\s*(\d{2}-\d{2}-\d{4})\s*\(GMT([+-]\d{2})\)', "%d-%m-%Y", "range"),
                (r'(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})\s*\(GMT([+-]\d{2})\)', "%d/%m/%Y", "range"),
                # 单日格式
                (r'(\d{2}/\d{2}/\d{4})\s*\(GMT([+-]\d{2})\)', "%d/%m/%Y", "single"),
                (r'(\d{2}-\d{2}-\d{4})\s*\(GMT([+-]\d{2})\)', "%d-%m-%Y", "single")
            ]

            match = None
            date_format = None
            pattern_type = None
            for pattern, fmt, ptype in patterns:
                match = re.search(pattern, date_text)
                if match:
                    date_format = fmt
                    pattern_type = ptype
                    break

            if not match:
                logger.warning(f"时间格式不匹配: {date_text}")
                return None, None

            # 根据模式类型处理匹配结果
            if pattern_type == "range":
                start_str, end_str, tz_offset = match.groups()
            else:  # single
                start_str, tz_offset = match.groups()
                end_str = start_str  # 单日格式，开始和结束是同一天

            # 解析日期，使用匹配的格式
            start_date = datetime.strptime(start_str, date_format)
            end_date = datetime.strptime(end_str, date_format)

            # 年份验证：确保年份合理（不修正，只记录）
            current_year = datetime.now().year
            if abs(start_date.year - current_year) > 1:
                logger.warning(f"检测到异常年份 {start_date.year}，当前年份 {current_year}")
            else:
                logger.debug(f"年份正常: {start_date.year}")

            # 创建时区对象，支持正负时区偏移 GMT+08 或 GMT-03
            from datetime import timezone, timedelta
            tz_hours = int(tz_offset)  # tz_offset 已经包含正负号
            tz = timezone(timedelta(hours=tz_hours))

            # 设置为当天00:00:00，并应用时区
            start_dt = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            start_dt = start_dt.replace(tzinfo=tz)

            # 结束时间设为下一天00:00:00（右开区间）
            end_dt = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_dt = end_dt + timedelta(days=1)  # 下一天
            end_dt = end_dt.replace(tzinfo=tz)

            # 转换为毫秒时间戳
            start_ts_ms = int(start_dt.timestamp() * 1000)
            end_ts_ms = int(end_dt.timestamp() * 1000)

            logger.info(f"解析时间范围: {start_dt} ~ {end_dt}")
            logger.info(f"毫秒时间戳: start_ts={start_ts_ms}, end_ts={end_ts_ms}")

            return start_ts_ms, end_ts_ms

        except Exception as e:
            logger.error(f"从UI读取时间范围失败: {e}")
            return None, None

    def _select_metrics(self, page: "Page", metrics: List[str]) -> None:
        """指标勾选已禁用：导出获取全量数据"""
        logger.info("[DATA] 指标勾选已禁用：导出获取全量数据")
        return

        # 确保“选择指标”区域已打开并可见
        try:
            self._open_metric_selector(page)
        except Exception:
            pass
        page.wait_for_timeout(500)

        for metric in metrics:
            try:
                # 将期望指标名映射为页面上的真实标题（同义词/相似度容错）
                target_text = self._match_metric_title(page, metric) or metric
                if target_text != metric:
                    logger.info(f"指标名映射: '{metric}' -> '{target_text}'")

                # 尝试滚动到指标区域，避免元素不可见
                try:
                    page.locator('li.multi-selector__item').first.scroll_into_view_if_needed(timeout=1000)
                except Exception:
                    pass

                # 方法1: 通过 has= 子定位器匹配 .title 文本（Playwright 正确用法）
                try:
                    items = page.locator('li.multi-selector__item')
                    item = items.filter(has=page.locator('.title', has_text=target_text)).first

                    if item.count() > 0 and item.is_visible():
                        class_attr = item.get_attribute("class") or ""
                        if "selected" not in class_attr:
                            checkbox_area = item.locator('.checkbox').first
                            if checkbox_area.count() > 0:
                                checkbox_area.click()
                            else:
                                item.click()
                            # 等待选中状态更新（最多3秒）
                            try:
                                page.wait_for_function(
                                    "el => el && el.classList.contains('selected')",
                                    arg=item.element_handle(),
                                    timeout=3000,
                                )
                                logger.info(f"[OK] 已勾选指标: {target_text}")
                            except Exception:
                                logger.info(f"[OK] 点击指标: {target_text} (状态待确认)")
                        else:
                            logger.info(f"[OK] 指标已勾选: {target_text}")
                        continue
                except Exception as e:
                    logger.debug(f"multi-selector 方法失败 {metric}: {e}")

                # 方法2: 模糊文本匹配 + 祖先容器点击 + 等待
                try:
                    title_locator = page.locator('.title').filter(has_text=re.compile(re.escape(target_text), re.IGNORECASE))
                    if title_locator.count() > 0:
                        parent_li = title_locator.first.locator('xpath=ancestor::li[contains(@class,"multi-selector__item")][1]')
                        if parent_li.count() > 0 and parent_li.is_visible():
                            class_attr = parent_li.get_attribute("class") or ""
                            if "selected" not in class_attr:
                                parent_li.click()
                                try:
                                    page.wait_for_function(
                                        "el => el && el.classList.contains('selected')",
                                        arg=parent_li.element_handle(),
                                        timeout=3000,
                                    )
                                except Exception:
                                    pass
                                logger.info(f"[OK] 通过模糊匹配勾选: {target_text}")
                            else:
                                logger.info(f"[OK] 模糊匹配指标已勾选: {target_text}")
                            continue
                except Exception as e:
                    logger.debug(f"模糊匹配方法失败 {metric}: {e}")

                # 方法3: 通用文本点击 + 祖先容器
                try:
                    label = page.get_by_text(target_text, exact=False).first
                    if label and label.is_visible():
                        container = label.locator("xpath=ancestor::*[self::li or self::label or self::div][contains(@class, 'selector') or contains(@class, 'item')][1]")
                        if container.count() > 0:
                            container.scroll_into_view_if_needed(timeout=1000)
                            container.click()
                            logger.info(f"[OK] 通过文本容器点击: {target_text}")
                            continue
                        label.click()
                        logger.info(f"[OK] 通过文本点击: {target_text}")
                        continue
                except Exception as e:
                    logger.debug(f"文本点击方法失败 {metric}: {e}")

            except Exception as e:
                logger.warning(f"[WARN] 勾选指标失败 {metric}: {e}")

    def _confirm_metrics_selection(self, page: "Page") -> None:
        """在指标选择面板内点击“确定/完成/应用”之类的按钮，确保勾选生效。"""
        selectors = [
            'button:has-text("确定")',
            'button:has-text("完成")',
            'button:has-text("应用")',
            'button:has-text("保存")',
            '.el-dialog .el-button--primary',
            '.ant-modal .ant-btn-primary',
        ]
        for sel in selectors:
            try:
                btn = page.locator(sel)
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click()
                    logger.info(f"点击指标面板确认按钮: {sel}")
                    page.wait_for_timeout(500)
                    return
            except Exception:
                continue
        # 如果没有确认按钮，尝试点击面板外区域关闭
        try:
            page.mouse.click(10, 10)
        except Exception:
            pass



    def _normalize_text(self, s: str) -> str:
        """规范化中文指标文案：去空格、统一括号、去标点、转小写。"""
        s = (s or "").strip()
        s = s.replace("（", "(").replace("）", ")")
        s = re.sub(r"\s+", "", s)
        s = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", s)
        return s.lower()

    def _match_metric_title(self, page, target: str) -> Optional[str]:
        """在页面的 multi-selector 标题中为目标词寻找最优匹配（规范化 + 同义词 + 相似度）。"""
        try:
            import difflib
        except Exception:
            difflib = None

        synonyms: Dict[str, List[str]] = {
            "商品页访问量": ["商品页面访问量", "商品访问量", "商品页面访问人数", "商品页访问人数"],
            "销售额": ["销售额（已付款订单）", "GMV", "销售额(商品)", "总销售额", "销售额(已付款订单)", "销售额(已付款)", "销售额-已付款"],
            "销量": ["销量", "销售量", "件数（已付款订单）", "订单件数", "已付款件数", "成交件数"],
            "加购量": ["加购量", "加入购物车数", "件数 (加入购物车）", "加入购物车件数", "加购件数"],
            "点击率": ["点击率", "CTR", "点击率%"],
            "转化率": ["转化率", "CVR", "转化率%"],
            "订单买家数": ["订单买家数", "买家数（已付款订单）", "下单买家数", "已付款买家数"],
            "曝光量": ["曝光量", "展现量", "曝光人数", "搜索曝光量", "搜索曝光"],
        }

        target_norm = self._normalize_text(target)

        titles_locator = page.locator('li.multi-selector__item .title')
        n = titles_locator.count()
        titles: List[str] = []
        titles_norm: Dict[str, str] = {}
        for i in range(min(n, 200)):
            try:
                t = (titles_locator.nth(i).inner_text() or '').strip()
                if t:
                    titles.append(t)
                    titles_norm[t] = self._normalize_text(t)
            except Exception:
                continue

        if not titles:
            logger.debug("未在页面上发现 multi-selector 标题列表")
            return None

        for t in titles:
            tn = titles_norm.get(t, "")
            if target_norm == tn or (target_norm and target_norm in tn):
                return t

        for alt in synonyms.get(target, []):
            an = self._normalize_text(alt)
            for t in titles:
                tn = titles_norm.get(t, "")
                if an == tn or (an and an in tn):
                    return t

        if difflib is not None:
            best_text, best_ratio = None, 0.0
            for t in titles:
                r = difflib.SequenceMatcher(None, target_norm, titles_norm.get(t, "")).ratio()
                if r > best_ratio:
                    best_text, best_ratio = t, r
            if best_text and best_ratio >= 0.6:
                logger.info(f"使用相似度匹配 '{target}' -> '{best_text}' (ratio={best_ratio:.2f})")
                return best_text

        logger.debug(f"未找到与 '{target}' 匹配的标题，候选有: {titles[:10]}")
        return None


    def inspect_date_picker(self, page: "Page") -> Dict:
        """日期控件探测器：分析页面上的日期选择控件类型与状态"""
        try:
            logger.info("[SEARCH] 开始日期控件探测...")

            # 注入探测脚本
            script = """
            () => {
                const result = {
                    hasShortcuts: false,
                    hasInputs: false,
                    hasCalendar: false,
                    shortcuts: [],
                    activeShortcut: null,
                    selectedRange: null,
                    controlType: 'unknown'
                };

                // 1. 检测快捷按钮
                const shortcuts = document.querySelectorAll('.eds-date-shortcut-item, .bi-date-shortcuts li');
                if (shortcuts.length > 0) {
                    result.hasShortcuts = true;
                    shortcuts.forEach(item => {
                        const text = item.querySelector('.eds-date-shortcut-item__text')?.textContent?.trim() ||
                                   item.textContent?.trim();
                        if (text) {
                            result.shortcuts.push(text);
                            if (item.classList.contains('active')) {
                                result.activeShortcut = text;
                            }
                        }
                    });
                }

                // 2. 检测输入框
                const inputs = document.querySelectorAll('.eds-date-picker input[type="text"], .bi-date-picker input[type="text"]');
                result.hasInputs = inputs.length > 0;

                // 3. 检测日历表格
                const calendar = document.querySelector('.eds-date-table, .eds-month-table, .eds-year-table');
                result.hasCalendar = !!calendar;

                // 4. 检测选中范围（周选择）
                const selectedCells = document.querySelectorAll('.week-selection, .range-start, .range-end, .selected');
                if (selectedCells.length > 0) {
                    const startCell = document.querySelector('.range-start, .selected');
                    const endCell = document.querySelector('.range-end');
                    if (startCell) {
                        const startText = startCell.textContent?.trim();
                        const endText = endCell?.textContent?.trim() || startText;
                        result.selectedRange = `${startText} ~ ${endText}`;
                    }
                }

                // 5. 判断控件类型
                if (result.hasShortcuts && result.hasCalendar && !result.hasInputs) {
                    result.controlType = 'shortcut_calendar';
                } else if (result.hasShortcuts && result.hasInputs) {
                    result.controlType = 'hybrid';
                } else if (result.hasInputs && !result.hasShortcuts) {
                    result.controlType = 'input_only';
                } else if (result.hasShortcuts && !result.hasCalendar) {
                    result.controlType = 'shortcut_only';
                }

                return result;
            }
            """

            result = page.evaluate(script)

            # 格式化输出
            logger.info("[DATA] 日期控件探测结果:")
            logger.info(f"  控件类型: {result['controlType']}")
            logger.info(f"  快捷按钮: {'[OK]' if result['hasShortcuts'] else '[FAIL]'}")
            logger.info(f"  输入框: {'[OK]' if result['hasInputs'] else '[FAIL]'}")
            logger.info(f"  日历表格: {'[OK]' if result['hasCalendar'] else '[FAIL]'}")

            if result['shortcuts']:
                logger.info(f"  可用快捷项: {result['shortcuts']}")
            if result['activeShortcut']:
                logger.info(f"  当前激活: {result['activeShortcut']}")
            if result['selectedRange']:
                logger.info(f"  选中范围: {result['selectedRange']}")

            return result

        except Exception as e:
            logger.error(f"日期控件探测失败: {e}")
            return {"controlType": "error", "error": str(e)}

    def install_date_picker_monitor(self, page_or_frame) -> None:
        """安装日期控件交互监听器（增强版：录制复刻用）

        Args:
            page_or_frame: Page或Frame对象，支持主页面和iframe
        """
        try:
            script = """
            () => {
                // 避免重复安装
                if (window.__date_picker_monitor_installed__) return;
                window.__date_picker_monitor_installed__ = true;
                window.__date_picker_events__ = [];

                // 生成元素的多重定位特征
                function generateSelectors(element) {
                    const selectors = [];

                    // 1. 文本内容（优先级最高）
                    const text = element.textContent?.trim();
                    if (text && text.length < 50) {
                        selectors.push({type: 'text', value: text, priority: 1});
                    }

                    // 2. CSS 选择器组合
                    const tagName = element.tagName.toLowerCase();
                    const classes = Array.from(element.classList);
                    if (classes.length > 0) {
                        selectors.push({type: 'css', value: `${tagName}.${classes.join('.')}`, priority: 2});
                        // 关键类名单独提取
                        const keyClasses = classes.filter(c =>
                            c.includes('date') || c.includes('time') || c.includes('shortcut') ||
                            c.includes('picker') || c.includes('input') || c.includes('value')
                        );
                        if (keyClasses.length > 0) {
                            selectors.push({type: 'css', value: `.${keyClasses.join('.')}`, priority: 1.5});
                        }
                    }

                    // 3. 属性选择器
                    for (const attr of element.attributes) {
                        if (attr.name.startsWith('data-') || attr.name === 'role') {
                            selectors.push({type: 'css', value: `[${attr.name}="${attr.value}"]`, priority: 3});
                        }
                    }

                    // 4. 结构化定位（相对于容器）
                    const dateContainer = element.closest('.bi-date-input, .eds-date-picker, .bi-date-picker');
                    if (dateContainer) {
                        const containerClasses = Array.from(dateContainer.classList);
                        if (containerClasses.length > 0) {
                            selectors.push({
                                type: 'css',
                                value: `.${containerClasses.join('.')} ${tagName}${classes.length ? '.' + classes.join('.') : ''}`,
                                priority: 2.5
                            });
                        }
                    }

                    // 5. 兜底：标签+位置
                    const siblings = Array.from(element.parentElement?.children || []);
                    const index = siblings.indexOf(element);
                    if (index >= 0) {
                        selectors.push({type: 'css', value: `${tagName}:nth-child(${index + 1})`, priority: 4});
                    }

                    return selectors.sort((a, b) => a.priority - b.priority);
                }

                // 监听点击事件
                document.addEventListener('click', (e) => {
                    const target = e.target;
                    let eventType = 'unknown_click';
                    let details = {
                        selectors: generateSelectors(target),
                        boundingBox: target.getBoundingClientRect(),
                        timestamp: Date.now()
                    };

                    // 判断点击的元素类型
                    if (target.closest('.eds-date-shortcut-item, .bi-date-shortcuts li')) {
                        eventType = 'shortcut_click';
                        details.text = target.textContent?.trim();
                        details.element = target.closest('.eds-date-shortcut-item, .bi-date-shortcuts li').className;
                        details.action = 'select_shortcut';
                    } else if (target.closest('.bi-date-input, .eds-date-picker')) {
                        eventType = 'date_container_click';
                        details.text = target.textContent?.trim();
                        details.classes = target.className;
                        details.action = 'open_picker';
                    } else if (target.closest('.eds-date-table__cell')) {
                        eventType = 'calendar_cell_click';
                        details.text = target.textContent?.trim();
                        details.classes = target.className;
                        details.action = 'select_date';
                    } else if (target.closest('input[type="text"]')) {
                        eventType = 'input_click';
                        details.value = target.value;
                        details.action = 'focus_input';
                    }

                    if (eventType !== 'unknown_click') {
                        window.__date_picker_events__.push({
                            type: eventType,
                            timestamp: Date.now(),
                            details: details
                        });
                        console.log('[DatePicker Recorder]', eventType, details);
                    }
                }, true);

                console.log('[DatePicker Recorder] 增强监听器已安装');
            }
            """
            page_or_frame.evaluate(script)
            # 获取页面/frame的URL用于日志
            try:
                url = page_or_frame.url
                frame_info = f" (URL: {url[:50]}...)" if len(url) > 50 else f" (URL: {url})"
            except:
                frame_info = ""
            logger.info(f"[TARGET] 日期控件录制监听器已安装{frame_info}")

        except Exception as e:
            logger.error(f"安装日期控件监听器失败: {e}")

    def _install_recording_monitors(self, page: "Page") -> None:
        """为录制模式安装全局监听器（支持iframe）"""
        try:
            logger.info("[TARGET] 安装录制模式监听器（支持iframe）...")

            # 为主页面安装监听器
            self.install_date_picker_monitor(page)

            # 为所有现有frames安装监听器
            for frame in page.frames:
                try:
                    if frame != page.main_frame:
                        self.install_date_picker_monitor(frame)
                        logger.debug(f"已为frame安装监听器: {frame.url}")
                except Exception as e:
                    logger.debug(f"为frame安装监听器失败: {e}")

            # 监听新frame的加载
            def handle_frame_attached(frame):
                try:
                    # 延迟安装，避免frame还未完全加载
                    def delayed_install():
                        try:
                            # 等待frame加载完成
                            frame.wait_for_load_state("domcontentloaded", timeout=3000)
                            # 再次检查frame是否仍然有效
                            if not frame.is_detached():
                                self.install_date_picker_monitor(frame)
                                logger.debug(f"新frame已安装监听器: {frame.url}")
                        except Exception as e:
                            logger.debug(f"为新frame安装监听器失败: {e}")

                    # 使用页面的evaluate来延迟执行
                    page.evaluate("() => setTimeout(() => {}, 100)")
                    delayed_install()
                except Exception as e:
                    logger.debug(f"处理新frame失败: {e}")

            page.on("frameattached", handle_frame_attached)
            logger.info("[OK] 录制监听器安装完成（包括iframe支持）")

        except Exception as e:
            logger.error(f"安装录制监听器失败: {e}")

    def _try_recipe_automation(self, page, start_date: str, end_date: str) -> bool:
        """尝试使用录制配方进行自动化操作"""
        try:
            from modules.services.recipe_executor import RecipeExecutor

            # 根据日期范围推断目标选项
            target_option = self._infer_target_option(start_date, end_date)

            executor = RecipeExecutor()
            success = executor.execute_date_picker_recipe(page, target_option=target_option)

            if success:
                logger.info(f"[ACTION] 配方自动化成功：已选择 {target_option}")
                return True
            else:
                logger.warning("[LIST] 配方自动化失败")
                return False

        except Exception as e:
            logger.warning(f"配方自动化异常: {e}")
            return False

    def _infer_target_option(self, start_date: str, end_date: str) -> str:
        """根据日期范围推断目标选项"""
        try:
            from datetime import datetime, timedelta

            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
            days_diff = (end - start).days + 1  # 包含结束日期

            # 根据天数差异推断选项
            if days_diff == 1:
                # 检查是否是昨天
                yesterday = datetime.now() - timedelta(days=1)
                if start.date() == yesterday.date():
                    return "昨天"
                else:
                    return "今日实时"
            elif days_diff <= 8:  # 7-8天都认为是过去7天
                return "过去7 天"
            elif days_diff <= 31:  # 29-31天都认为是过去30天
                return "过去30 天"
            else:
                # 超过31天，默认使用过去30天
                logger.warning(f"日期范围 {days_diff} 天超出常用范围，使用过去30天")
                return "过去30 天"

        except Exception as e:
            logger.warning(f"日期推断失败: {e}，使用默认选项")
            return "过去7 天"

    def generate_date_picker_recipe(self, page: "Page", diag_dir: Path, timestamp: str) -> None:
        """从监听事件生成日期控件操作配方"""
        try:
            events = self.get_date_picker_events(page)
            if not events:
                logger.info("无日期控件交互事件，跳过配方生成")
                return

            # 过滤并排序事件
            valid_events = []
            for event in events:
                if event.get('type') in ['date_container_click', 'shortcut_click']:
                    valid_events.append(event)

            if not valid_events:
                logger.info("无有效的日期控件操作事件")
                return

            # 按时间排序
            valid_events.sort(key=lambda x: x.get('timestamp', 0))

            # 生成配方
            recipe = {
                "page_key": "datacenter/product/performance",
                "generated_at": timestamp,
                "url_pattern": "*/datacenter/product/performance*",
                "steps": []
            }

            for i, event in enumerate(valid_events):
                details = event.get('details', {})
                action = details.get('action', 'click')

                step = {
                    "step_id": i + 1,
                    "action": action,
                    "description": f"{action}: {details.get('text', 'unknown')}",
                    "candidates": []
                }

                # 提取候选选择器
                selectors = details.get('selectors', [])
                for sel in selectors[:5]:  # 取前5个最优选择器
                    candidate = {
                        "type": sel['type'],
                        "value": sel['value'],
                        "priority": sel['priority']
                    }
                    step["candidates"].append(candidate)

                # 添加兜底选择器
                text = details.get('text', '').strip()
                if text:
                    step["candidates"].append({
                        "type": "text",
                        "value": text,
                        "priority": 1
                    })

                recipe["steps"].append(step)

            # 保存配方
            recipe_dir = diag_dir / "recipes"
            recipe_dir.mkdir(parents=True, exist_ok=True)
            recipe_file = recipe_dir / "date_picker.json"

            recipe_file.write_text(
                json.dumps(recipe, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

            logger.info(f"[NOTE] 日期控件操作配方已生成: {recipe_file}")
            logger.info(f"   包含 {len(recipe['steps'])} 个操作步骤")

        except Exception as e:
            logger.error(f"生成日期控件配方失败: {e}")

    def get_date_picker_events(self, page: "Page") -> List[Dict]:
        """获取日期控件交互事件记录"""
        try:
            events = page.evaluate("() => window.__date_picker_events__ || []")
            return events
        except Exception as e:
            logger.error(f"获取日期控件事件失败: {e}")
            return []

    def load_date_picker_recipe(self, shop_id: str | None = None) -> Dict | None:
        """加载日期控件操作配方（shop_id 仅为兼容保留，不参与路径匹配）"""
        try:
            # 递归搜索最近生成的配方文件（避免路径依赖账号/店铺名）
            pattern = os.path.join('temp', 'outputs', 'shopee', '**', 'products', 'weekly', '.diag', 'recipes', 'date_picker.json')
            candidates = glob.glob(pattern, recursive=True)
            if not candidates:
                logger.debug("未找到日期控件配方文件")
                return None

            latest_path = max(candidates, key=lambda p: os.path.getmtime(p))
            recipe_text = Path(latest_path).read_text(encoding="utf-8")
            recipe = json.loads(recipe_text)
            logger.info(f"[BOOK] 已加载日期控件配方: {latest_path}")
            return recipe

        except Exception as e:
            logger.error(f"加载日期控件配方失败: {e}")
            return None

    def replay_date_picker_recipe(self, page: "Page", recipe: Dict) -> bool:
        """复刻执行日期控件操作配方"""
        try:
            steps = recipe.get("steps", [])
            if not steps:
                logger.warning("配方中无操作步骤")
                return False

            logger.info(f"[ACTION] 开始复刻日期控件操作，共 {len(steps)} 个步骤")

            for step in steps:
                step_id = step.get("step_id", 0)
                action = step.get("action", "click")
                description = step.get("description", "unknown")
                candidates = step.get("candidates", [])

                logger.info(f"  步骤 {step_id}: {description}")

                success = False
                for candidate in candidates:
                    try:
                        selector_type = candidate.get("type", "css")
                        selector_value = candidate.get("value", "")

                        if not selector_value:
                            continue

                        # 根据选择器类型定位元素
                        if selector_type == "text":
                            locator = page.locator(f'text="{selector_value}"')
                        elif selector_type == "css":
                            locator = page.locator(selector_value)
                        else:
                            continue

                        # 检查元素是否存在且可见
                        if locator.count() == 0:
                            continue

                        element = locator.first
                        if not element.is_visible():
                            continue

                        # 执行操作
                        try:
                            element.scroll_into_view_if_needed()
                            element.hover()

                            if action in ["click", "open_picker", "select_shortcut", "select_date"]:
                                element.click(force=True)
                            elif action == "focus_input":
                                element.focus()
                            else:
                                element.click(force=True)

                            page.wait_for_timeout(300)
                            success = True
                            logger.info(f"    [OK] 成功: {selector_type}='{selector_value}'")
                            break

                        except Exception as e:
                            logger.debug(f"    操作失败: {selector_type}='{selector_value}' - {e}")
                            continue

                    except Exception as e:
                        logger.debug(f"    定位失败: {candidate} - {e}")
                        continue

                if not success:
                    logger.warning(f"  步骤 {step_id} 执行失败，尝试继续")

            logger.info("[ACTION] 配方复刻执行完成")
            return True

        except Exception as e:
            logger.error(f"复刻执行配方失败: {e}")
            return False

    def _save_compare_snapshot(self, page: "Page", diag_dir: Path, timestamp: str, phase: str) -> None:
        """保存对比诊断快照（before/after）"""
        try:
            # 1. 页面HTML和截图
            html_file = diag_dir / f"{timestamp}_{phase}_page.html"
            screenshot_file = diag_dir / f"{timestamp}_{phase}_page.png"

            html_file.write_text(page.content(), encoding="utf-8")
            page.screenshot(path=str(screenshot_file), full_page=True)
            logger.info(f"{phase} 快照：页面HTML和截图已保存")

            # 2. 时间控件详细信息
            time_info = self._extract_time_controls(page)
            time_file = diag_dir / f"{timestamp}_{phase}_time_controls_enhanced.json"
            time_file.write_text(json.dumps(time_info, ensure_ascii=False, indent=2), encoding="utf-8")

            # 3. 指标勾选项清单
            metrics_info = self._extract_metrics_checkboxes(page)
            metrics_file = diag_dir / f"{timestamp}_{phase}_metrics_checkboxes.json"
            metrics_file.write_text(json.dumps(metrics_info, ensure_ascii=False, indent=2), encoding="utf-8")

            # 4. 可访问性树快照
            try:
                accessibility_tree = page.accessibility.snapshot()
                accessibility_file = diag_dir / f"{timestamp}_{phase}_accessibility.json"
                accessibility_file.write_text(json.dumps(accessibility_tree, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                logger.warning(f"{phase} 可访问性树快照失败: {e}")

            logger.info(f"[OK] {phase} 快照保存完成")

        except Exception as e:
            logger.error(f"{phase} 快照保存失败: {e}")

    def _generate_comparison_report(self, diag_dir: Path, timestamp: str) -> None:
        """生成对比报告"""
        try:
            before_time_file = diag_dir / f"{timestamp}_before_time_controls_enhanced.json"
            after_time_file = diag_dir / f"{timestamp}_after_time_controls_enhanced.json"
            before_metrics_file = diag_dir / f"{timestamp}_before_metrics_checkboxes.json"
            after_metrics_file = diag_dir / f"{timestamp}_after_metrics_checkboxes.json"

            diff_report = {
                "timestamp": timestamp,
                "comparison_type": "before_vs_after",
                "time_controls_diff": {},
                "metrics_diff": {},
                "summary": {}
            }

            # 对比时间控件
            if before_time_file.exists() and after_time_file.exists():
                before_time = json.loads(before_time_file.read_text(encoding="utf-8"))
                after_time = json.loads(after_time_file.read_text(encoding="utf-8"))

                # 提取时间显示文本的变化
                before_texts = []
                after_texts = []

                for key, info in before_time.get("time_selectors", {}).items():
                    if info.get("text_content"):
                        before_texts.append(info["text_content"])

                for key, info in after_time.get("time_selectors", {}).items():
                    if info.get("text_content"):
                        after_texts.append(info["text_content"])

                diff_report["time_controls_diff"] = {
                    "before_texts": before_texts,
                    "after_texts": after_texts,
                    "changed": before_texts != after_texts
                }

            # 对比指标勾选
            if before_metrics_file.exists() and after_metrics_file.exists():
                before_metrics = json.loads(before_metrics_file.read_text(encoding="utf-8"))
                after_metrics = json.loads(after_metrics_file.read_text(encoding="utf-8"))

                # 统计勾选状态变化（传统 checkbox）
                before_checked = []
                after_checked = []

                for key, info in before_metrics.get("checkboxes", {}).items():
                    if info.get("checked"):
                        before_checked.append(info.get("text", key))

                for key, info in after_metrics.get("checkboxes", {}).items():
                    if info.get("checked"):
                        after_checked.append(info.get("text", key))

                # 表头列（作为已选指标的替代信号）
                before_headers = before_metrics.get("table_headers", [])
                after_headers = after_metrics.get("table_headers", [])

                # 统计 multi-selector 状态变化
                before_selected = []
                after_selected = []

                for key, info in before_metrics.get("multi_selector_items", {}).items():
                    if info.get("selected"):
                        before_selected.append(info.get("title", key))

                for key, info in after_metrics.get("multi_selector_items", {}).items():
                    if info.get("selected"):
                        after_selected.append(info.get("title", key))

                diff_report["metrics_diff"] = {
                    "before_checked": before_checked,
                    "after_checked": after_checked,
                    "newly_checked": list(set(after_checked) - set(before_checked)),
                    "unchecked": list(set(before_checked) - set(after_checked)),
                    "before_selected": before_selected,
                    "after_selected": after_selected,
                    "newly_selected": list(set(after_selected) - set(before_selected)),
                    "newly_unselected": list(set(before_selected) - set(after_selected)),
                    "before_headers": before_headers,
                    "after_headers": after_headers,
                    "new_headers": list(set(after_headers) - set(before_headers)),
                    "removed_headers": list(set(before_headers) - set(after_headers))
                }

            # 生成摘要
            metrics_changed = (
                len(diff_report["metrics_diff"].get("newly_checked", [])) > 0 or
                len(diff_report["metrics_diff"].get("unchecked", [])) > 0 or
                len(diff_report["metrics_diff"].get("newly_selected", [])) > 0 or
                len(diff_report["metrics_diff"].get("newly_unselected", [])) > 0
            )

            diff_report["summary"] = {
                "time_changed": diff_report["time_controls_diff"].get("changed", False),
                "metrics_changed": metrics_changed,
                "multi_selector_changed": len(diff_report["metrics_diff"].get("newly_selected", [])) > 0 or len(diff_report["metrics_diff"].get("newly_unselected", [])) > 0,
                "total_changes": sum([
                    diff_report["time_controls_diff"].get("changed", False),
                    metrics_changed
                ])
            }

            # 保存对比报告
            diff_file = diag_dir / f"{timestamp}_diff.json"
            diff_file.write_text(json.dumps(diff_report, ensure_ascii=False, indent=2), encoding="utf-8")

            logger.info(f"[DATA] 对比报告已生成: {diff_file}")
            logger.info(f"[CHART] 变化摘要: 时间控件{'已变化' if diff_report['summary']['time_changed'] else '未变化'}, "
                       f"指标勾选{'已变化' if diff_report['summary']['metrics_changed'] else '未变化'}, "
                       f"多选器{'已变化' if diff_report['summary']['multi_selector_changed'] else '未变化'}")

            # 生成日期控件操作配方（在对比诊断结束时）
            try:
                # 需要从调用方传入 page 对象，这里先占位
                # self.generate_date_picker_recipe(page, diag_dir, timestamp)
                pass
            except Exception as e:
                logger.error(f"生成配方时出错: {e}")

        except Exception as e:
            logger.error(f"生成对比报告失败: {e}")

    def _install_mutation_observer(self, page: "Page") -> None:
        """安装 DOM 变化监听器，捕捉页面元素属性和子节点变化"""
        script = """
        () => {
          if (window.__x_mutations_installed__) return;
          window.__x_mutations_installed__ = true;
          window.__x_mutations__ = [];

          const observer = new MutationObserver((mutations) => {
            for (const m of mutations) {
              const rec = {
                type: m.type,
                target: m.target && m.target.outerHTML ? m.target.outerHTML.slice(0, 500) : (m.target?.nodeName || ''),
                attributeName: m.attributeName || null,
                addedNodes: Array.from(m.addedNodes || []).map(n => (n.outerHTML||n.nodeName||'')).slice(0,5),
                removedNodes: Array.from(m.removedNodes || []).map(n => (n.outerHTML||n.nodeName||'')).slice(0,5),
                oldValue: m.oldValue || null,
                timestamp: Date.now()
              };
              try {
                window.__x_mutations__.push(rec);
                // 限制数组大小，避免内存溢出
                if (window.__x_mutations__.length > 1000) {
                  window.__x_mutations__ = window.__x_mutations__.slice(-500);
                }
              } catch(e) {}
            }
          });

          observer.observe(document.body, {
            attributes: true,
            childList: true,
            subtree: true,
            characterData: false,
            attributeOldValue: true
          });

          window.__x_mutation_observer__ = observer;
          console.log('[PUZZLE] DOM MutationObserver 已安装');
        }
        """
        page.evaluate(script)
        logger.info("[PUZZLE] DOM变化监听器已安装")

    def _dump_mutations(self, page: "Page", diag_dir: Path, timestamp: str) -> None:
        """导出 DOM 变化记录"""
        try:
            data = page.evaluate("() => (window.__x_mutations__||[])")

            # 过滤出有意义的变化（重点关注 class 属性变化和 multi-selector 相关）
            filtered_mutations = []
            for mutation in data if isinstance(data, list) else []:
                # 保留所有 attributeName=class 的变化
                if mutation.get("attributeName") == "class":
                    filtered_mutations.append(mutation)
                # 保留包含 multi-selector 的元素变化
                elif "multi-selector" in str(mutation.get("target", "")):
                    filtered_mutations.append(mutation)
                # 保留新增/删除节点的变化
                elif mutation.get("addedNodes") or mutation.get("removedNodes"):
                    filtered_mutations.append(mutation)

            out = {
                "timestamp": timestamp,
                "total_mutations": len(data) if isinstance(data, list) else 0,
                "filtered_count": len(filtered_mutations),
                "mutations": filtered_mutations[:500],  # 最多保留500条
                "filter_criteria": [
                    "attributeName == 'class'",
                    "target contains 'multi-selector'",
                    "has addedNodes or removedNodes"
                ]
            }

            mutations_file = diag_dir / f"{timestamp}_mutations.json"
            mutations_file.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

            logger.info(f"[PUZZLE] DOM变化记录已保存: {mutations_file}")
            logger.info(f"[DATA] 变化统计: 总计{out['total_mutations']}条, 过滤后{out['filtered_count']}条")

        except Exception as e:
            logger.error(f"导出DOM变化记录失败: {e}")

    def _export_via_ui(
        self,
        page: "Page",
        target_path: Path,
        *,
        diag_dir: Optional[Path] = None,
        ts: Optional[str] = None,
        capture_network: bool = False,
        enable_auto_regenerate: bool = False,
    ) -> Tuple[bool, str]:
        """通过页面按钮执行导出并自动下载；可选抓取网络快照。

        - 自动点击"导出数据"按钮
        - 自动点击弹窗中的"下载"按钮（多语言兼容）
        - 如果 capture_network=True，则在点击后抓取约30秒网络请求，保存为 <ts>_post_net.json
        - 若已提供 pre_net.json，会生成 net_diff.json（新增请求、导出相关URL、请求体摘要）
        """
        try:
            # 可能的导出按钮选择器
            export_btn_selectors = [
                'button:has-text("导出数据")',
                'button:has-text("导出")',
                'button:has-text("下载")',
                'button:has-text("导出报表")',
                '[data-testid*="export"]',
                '.export-btn',
                '.download-btn',
            ]

            # 视窗滚动到你提供的指标区域 XPath，避免按钮不可见
            try:
                xpath_panel = '/html/body/div[1]/div[2]/div[2]/div[2]/div/div/div/div[2]/div/section/div/div/div[5]/div[3]'
                panel = page.locator(f'xpath={xpath_panel}')
                if panel.count() > 0:
                    panel.first.scroll_into_view_if_needed(timeout=2000)
                    page.wait_for_timeout(300)
            except Exception:
                pass

            # 尝试点击导出/下载
            clicked = False
            for sel in export_btn_selectors:
                try:
                    loc = page.locator(sel)
                    if loc.count() > 0 and loc.first.is_visible():
                        loc.first.click()
                        clicked = True
                        logger.info(f"点击导出按钮: {sel}")
                        break
                except Exception:
                    continue

            if not clicked:
                try:
                    btn = page.get_by_role("button", name=re.compile("导出|下载", re.IGNORECASE))
                    if btn.count() > 0 and btn.first.is_visible():
                        btn.first.click()
                        clicked = True
                        logger.info("通过按钮角色点击导出/下载")
                except Exception:
                    pass

            if not clicked:
                return False, "未找到导出/下载按钮"

            # 等待导出弹窗出现并自动点击最新一条“未下载”的报告
            page.wait_for_timeout(2000)  # 等待弹窗加载

            download_clicked = False

            # 等待"进行中"状态变为"下载"
            self._wait_for_download_ready(page)

            try:
                # 1) 优先点击第一条“未下载”的下载按钮（不包含“已下载”文案）
                # 列表结构大致为：行(包含报告名) + 操作列(按钮或“已下载”文本)
                report_rows = page.locator('div[role="dialog"] .ant-table-row, .el-dialog .el-table__row, .report-list .row, .latest-report .row')
                if report_rows.count() > 0:
                    # 遍历前5行，找到不含“已下载”的行
                    limit = min(5, report_rows.count())
                    for i in range(limit):
                        row = report_rows.nth(i)
                        txt = row.inner_text(timeout=1000).lower()
                        if ("已下载" not in txt) and ("downloaded" not in txt):
                            # 点击该行中的下载按钮
                            btn = row.locator('button:has-text("下载"), button:has-text("Download"), button:has-text("下載")')
                            if btn.count() > 0 and btn.first.is_visible():
                                # 点击时等待下载事件，避免错过事件
                                with page.expect_download(timeout=20000) as dl_info:
                                    btn.first.click()
                                download = dl_info.value

                                # 获取下载的文件名并保存到目标路径
                                suggested_filename = download.suggested_filename
                                tmp_path = target_path.parent / suggested_filename
                                download.save_as(str(tmp_path))
                                if tmp_path != target_path:
                                    try:
                                        tmp_path.rename(target_path)
                                    except Exception:
                                        try:
                                            import shutil
                                            shutil.copy2(tmp_path, target_path)
                                            tmp_path.unlink(missing_ok=True)
                                        except Exception:
                                            pass

                                size = target_path.stat().st_size if target_path.exists() else 0
                                logger.success(f"下载完成(UI): {target_path} ({size:,} bytes)")
                                return True, "下载完成(UI)"
            except Exception:
                pass

            # 2) 兜底：按通用选择器点击第一个下载按钮
            if not download_clicked:
                candidates = [
                    'button:has-text("下载")',
                    'button:has-text("Download")',
                    'button:has-text("下載")',
                    'a:has-text("下载")',
                    'a:has-text("Download")',
                    '.download-btn',
                    '[data-testid*="download"]',
                ]
                for sel in candidates:
                    try:
                        loc = page.locator(sel)
                        if loc.count() > 0 and loc.first.is_visible():
                            # 点击时等待下载事件
                            with page.expect_download(timeout=20000) as dl_info:
                                loc.first.click()
                            download = dl_info.value

                            suggested_filename = download.suggested_filename
                            tmp_path = target_path.parent / suggested_filename
                            download.save_as(str(tmp_path))
                            if tmp_path != target_path:
                                try:
                                    tmp_path.rename(target_path)
                                except Exception:
                                    try:
                                        import shutil
                                        shutil.copy2(tmp_path, target_path)
                                        tmp_path.unlink(missing_ok=True)
                                    except Exception:
                                        pass

                            size = target_path.stat().st_size if target_path.exists() else 0
                            logger.success(f"下载完成(UI): {target_path} ({size:,} bytes)")
                            return True, "下载完成(UI)"
                    except Exception:
                        continue

            if not download_clicked:
                logger.warning("未找到可点击的下载按钮，将等待自动下载")

            # 可选：点击导出后抓 post 网络快照
            if capture_network and diag_dir and ts:
                try:
                    post_net = diag_dir / f"{ts}_post_net.json"
                    self._capture_network_snapshot(page, duration_ms=30000, out_file=post_net)
                    pre_net = diag_dir / f"{ts}_pre_net.json"
                    if pre_net.exists():
                        self._diff_network_files(pre_net, post_net, diag_dir / f"{ts}_net_diff.json")
                    # 成功后打印前5条可疑请求
                    try:
                        diff_path = diag_dir / f"{ts}_net_diff.json"
                        if diff_path.exists():
                            summary = json.loads(diff_path.read_text(encoding='utf-8'))
                            interesting = summary.get('interesting', [])[:5]
                            if interesting:
                                logger.info("网络差异(前5条可疑)：")
                                for i, it in enumerate(interesting, 1):
                                    url = it.get('url', '')
                                    method = it.get('method', '')
                                    post = it.get('post', '')
                                    logger.info(f"[{i}] {method} {url} | post={post}")
                    except Exception as pe:
                        logger.debug(f"打印网络差异摘要失败: {pe}")
                except Exception as ne:
                    logger.debug(f"抓取/对比网络快照失败: {ne}")

            # 若没有可点击的下载且开启自动重生，尝试生成新报告
            if enable_auto_regenerate and not download_clicked:
                try:
                    regen_candidates = [
                        'button:has-text("导出数据")',
                        'button:has-text("重新生成")',
                        'a:has-text("导出数据")',
                    ]
                    clicked_regen = False
                    for sel in regen_candidates:
                        loc = page.locator(sel)
                        if loc.count() > 0 and loc.first.is_visible():
                            loc.first.click()
                            clicked_regen = True
                            logger.info(f"触发重新生成: {sel}")
                            break
                    if clicked_regen:
                        # 等待进行中->下载
                        self._wait_for_download_ready(page, max_wait_seconds=90)
                        # 尝试再次点击并等待下载
                        rows = page.locator('div[role="dialog"] .ant-table-row, .el-dialog .el-table__row')
                        if rows.count() > 0:
                            btn = rows.first.locator('button:has-text("下载"), button:has-text("Download")')
                            if btn.count() > 0 and btn.first.is_visible():
                                with page.expect_download(timeout=30000) as dl_info:
                                    btn.first.click()
                                download = dl_info.value
                                suggested_filename = download.suggested_filename
                                tmp_path = target_path.parent / suggested_filename
                                download.save_as(str(tmp_path))
                                if tmp_path != target_path:
                                    try:
                                        tmp_path.rename(target_path)
                                    except Exception:
                                        import shutil
                                        shutil.copy2(tmp_path, target_path)
                                        try:
                                            tmp_path.unlink(missing_ok=True)
                                        except Exception:
                                            pass
                                size = target_path.stat().st_size if target_path.exists() else 0
                                logger.success(f"下载完成(UI): {target_path} ({size:,} bytes)")
                                return True, "下载完成(UI)"
                except Exception as re:
                    logger.debug(f"自动重新生成失败: {re}")

            # 检查是否有"这是您还没下载的报告"提示
            try:
                no_download_text = page.locator('text="这是您还没下载的报告"')
                if no_download_text.count() > 0 and no_download_text.first.is_visible():
                    logger.warning("[WARN] 检测到'这是您还没下载的报告'，可能需要重新生成报告")
                    return False, "没有可下载的报告，请重新生成"
            except Exception:
                pass

            # 捕获下载（直接下载到指定目录）
            try:
                # 先短暂等待触发下载
                page.wait_for_timeout(1500)

                # 1) 优先等待UI下载事件（使用上下文级别监听，避免跨页/iframe丢失）
                with page.context.expect_download(timeout=20000) as dl_info:  # 20秒
                    pass
                download = dl_info.value

                # 获取下载的文件名
                suggested_filename = download.suggested_filename
                download_path = target_path.parent / suggested_filename

                # 保存到临时位置，然后重命名为目标文件名
                download.save_as(str(download_path))

                if download_path != target_path:
                    download_path.rename(target_path)

                size = target_path.stat().st_size if target_path.exists() else 0
                logger.success(f"下载完成(UI): {target_path} ({size:,} bytes)")
                return True, "下载完成(UI)"

            except Exception as download_error:
                logger.warning(f"下载等待超时或失败: {download_error}")

                # 2) 兜底：检查目标目录是否有新文件
                success, message = self._check_alternative_download(page, target_path)
                if success:
                    return True, message

                # 如果开启自动重生，已经在上文尝试过；此处走最终失败路径
                logger.error("[FAIL] 下载失败，文件未生成")
                return False, f"下载失败: {download_error}"
        except Exception as e:
            logger.debug(f"UI导出失败: {e}")
            return False, f"UI导出失败: {e}"

    def _capture_network_snapshot(self, page: "Page", duration_ms: int, out_file: Path) -> None:
        """在Python侧短时间捕捉网络请求（response 事件），保存到 JSON。

        保存字段：时间戳、方法、URL、状态、内容类型、部分请求体/响应体（最多200字）。
        """
        try:
            events: List[Dict] = []

            def _on_response(res):
                try:
                    req = res.request
                    url = getattr(req, "url", lambda: "")()
                    method = getattr(req, "method", lambda: "")()
                    post = getattr(req, "post_data", lambda: None)() or ""
                    status = res.status
                    headers = res.headers
                    ct = (headers.get("content-type", "") or "").lower()
                    preview = ""
                    try:
                        # text() 可能较慢，截断到200字符
                        preview = (res.text() or "")[:200]
                    except Exception:
                        pass
                    events.append({
                        "t": int(time.time() * 1000),
                        "method": method,
                        "url": url,
                        "status": status,
                        "content_type": ct,
                        "post": (post or "")[:200],
                        "preview": preview,
                    })
                except Exception:
                    pass

            page.on("response", _on_response)
            try:
                page.wait_for_timeout(duration_ms)
            finally:
                try:
                    page.off("response", _on_response)
                except Exception:
                    pass

            out_file.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"网络快照已保存: {out_file}")
        except Exception as e:
            logger.debug(f"网络快照失败: {e}")

    def _diff_network_files(self, pre_path: Path, post_path: Path, out_path: Path) -> None:
        """对比两份网络快照，生成差异摘要。"""
        try:
            pre = json.loads(pre_path.read_text(encoding='utf-8')) if pre_path.exists() else []
            post = json.loads(post_path.read_text(encoding='utf-8')) if post_path.exists() else []

            pre_urls = {item.get('url') for item in pre}
            added = [item for item in post if item.get('url') not in pre_urls]

            # 重点标记包含导出/下载/metrics/column 等关键词的请求
            keywords = ['export', 'download', 'report', 'metric', 'column', 'performance']
            interesting = [it for it in added if any(k in (it.get('url','')) for k in keywords)]

            out = {
                'pre_count': len(pre),
                'post_count': len(post),
                'added_count': len(added),
                'added_samples': added[:20],
                'interesting': interesting[:20],
            }
            out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
            logger.info(f"网络差异报告已保存: {out_path}")
        except Exception as e:
            logger.debug(f"网络差异对比失败: {e}")


    def _open_metric_selector(self, page: "Page") -> None:
        """尝试打开指标选择面板"""
        try:
            # 方法1: 通过按钮角色查找
            btn = page.get_by_role("button", name=re.compile("选择指标|选择列|指标", re.IGNORECASE))
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                page.wait_for_timeout(1000)  # 等待面板加载
                logger.info("[OK] 通过按钮角色打开指标选择面板")
                return
        except Exception as e:
            logger.debug(f"按钮角色方法失败: {e}")

        try:
            # 方法2: 通过文本查找
            text_btn = page.get_by_text(re.compile("选择指标|选择列|指标", re.IGNORECASE)).first
            if text_btn and text_btn.is_visible():
                text_btn.click()
                page.wait_for_timeout(1000)
                logger.info("[OK] 通过文本查找打开指标选择面板")
                return
        except Exception as e:
            logger.debug(f"文本查找方法失败: {e}")

        try:
            # 方法3: 查找可能的选择器按钮
            selectors = [
                'button:has-text("选择指标")',
                'button:has-text("矩形 选择指标")',
                'button:has-text("选择列")',
                'button:has-text("指标")',
                '.metric-selector-btn',
                '.column-selector',
                '[data-testid*="metric"]',
                '[data-testid*="column"]'
            ]

            for selector in selectors:
                try:
                    element = page.locator(selector).first
                    if element.count() > 0 and element.is_visible():
                        element.click()
                        page.wait_for_timeout(1000)
                        logger.info(f"[OK] 通过选择器打开指标面板: {selector}")
                        return
                except:
                    continue

        except Exception as e:
            logger.debug(f"选择器方法失败: {e}")

        logger.warning("[WARN] 未能自动打开指标选择面板，请确保手动操作时面板已打开")

    def _wait_for_download_ready(self, page, max_wait_seconds: int = 60) -> bool:
        """
        等待下载按钮从"进行中"状态变为"下载"状态

        Args:
            page: Playwright页面对象
            max_wait_seconds: 最大等待时间（秒）

        Returns:
            bool: 是否成功等待到下载就绪
        """
        try:
            import time

            logger.info("[WAIT] 等待导出完成，监控状态变化...")

            start_time = time.time()
            check_interval = 2  # 每2秒检查一次

            while time.time() - start_time < max_wait_seconds:
                try:
                    # 查找所有可能的状态指示器
                    status_selectors = [
                        'text="进行中"',
                        'text="Processing"',
                        'text="正在生成"',
                        'text="Generating"',
                        '.processing',
                        '.generating',
                        '[data-status="processing"]'
                    ]

                    # 检查是否还有"进行中"状态
                    has_processing = False
                    for selector in status_selectors:
                        try:
                            elements = page.locator(selector)
                            if elements.count() > 0:
                                # 检查元素是否可见
                                for i in range(elements.count()):
                                    if elements.nth(i).is_visible():
                                        has_processing = True
                                        break
                                if has_processing:
                                    break
                        except Exception:
                            continue

                    if not has_processing:
                        # 检查是否有可用的下载按钮
                        download_selectors = [
                            'button:has-text("下载")',
                            'button:has-text("Download")',
                            'a:has-text("下载")',
                            'a:has-text("Download")'
                        ]

                        for selector in download_selectors:
                            try:
                                elements = page.locator(selector)
                                if elements.count() > 0 and elements.first.is_visible():
                                    logger.info("[OK] 导出完成，下载按钮已就绪")
                                    return True
                            except Exception:
                                continue

                    # 显示等待进度
                    elapsed = int(time.time() - start_time)
                    logger.info(f"[WAIT] 等待导出完成... ({elapsed}s/{max_wait_seconds}s)")

                    time.sleep(check_interval)

                except Exception as e:
                    logger.debug(f"状态检查异常: {e}")
                    time.sleep(check_interval)

            logger.warning(f"[WARN] 等待超时 ({max_wait_seconds}s)，继续尝试下载")
            return False

        except Exception as e:
            logger.error(f"等待下载就绪失败: {e}")
            return False

    def _wait_for_download(self, page, target_path: Path, timeout: int = 60) -> tuple[bool, Optional[Path]]:
        """
        等待下载完成并保存到目标路径。
        先监听 UI 下载事件，失败则检查常见下载目录作为兜底。
        """
        try:
            with page.expect_download(timeout=timeout * 1000) as dl_info:
                pass
            download = dl_info.value
            suggested = target_path.parent / download.suggested_filename
            download.save_as(str(suggested))
            if suggested != target_path:
                try:
                    suggested.rename(target_path)
                except Exception:
                    import shutil
                    shutil.move(str(suggested), str(target_path))
            return True, target_path
        except Exception as e:
            logger.warning(f"等待下载事件失败，尝试兜底检查: {e}")
            ok, msg = self._check_alternative_download(page, target_path)
            if ok:
                return True, target_path
            return False, None

    def _check_alternative_download(self, page, target_path: Path) -> Tuple[bool, str]:
        """检查备用下载方式"""
        try:
            import time
            from pathlib import Path

            logger.info("[SEARCH] 检查是否有其他下载方式...")

            # 0. 首先检查目标文件是否已经存在（可能已经下载完成）
            if target_path.exists() and target_path.stat().st_size > 0:
                size = target_path.stat().st_size
                logger.success(f"[OK] 目标文件已存在: {target_path} ({size:,} bytes)")
                return True, f"文件已存在: {size:,} bytes)"

            # 1. 检查多个可能的下载目录
            possible_download_dirs = [
                Path.home() / "Downloads",
                Path.home() / "下载",
                Path("C:/Users") / Path.home().name / "Downloads",
                Path("C:/Users") / Path.home().name / "下载",
                # 新增：Playwright持久化默认下载目录
                Path("profiles") / "shopee" / "**" / "Default" / "Downloads",
            ]

            from glob import glob
            for downloads_dir in possible_download_dirs:
                try:
                    # 支持通配 profiles/shopee/**/Default/Downloads
                    candidate_paths = []
                    if "**" in str(downloads_dir):
                        candidate_paths = [Path(p) for p in glob(str(downloads_dir))]
                    else:
                        candidate_paths = [downloads_dir]

                    for d in candidate_paths:
                        if not d.exists():
                            continue
                        logger.debug(f"检查下载目录: {d}")
                        xlsx_files = list(d.glob("*.xlsx"))
                        if xlsx_files:
                            latest_file = max(xlsx_files, key=lambda f: f.stat().st_mtime)
                            if time.time() - latest_file.stat().st_mtime < 600:
                                try:
                                    target_path.parent.mkdir(parents=True, exist_ok=True)
                                    if target_path.exists():
                                        backup_path = target_path.with_suffix(f".backup_{int(time.time())}.xlsx")
                                        target_path.rename(backup_path)
                                        logger.info(f"备份已存在文件: {backup_path}")
                                    # 优先移动
                                    try:
                                        latest_file.rename(target_path)
                                    except Exception:
                                        import shutil
                                        shutil.copy2(latest_file, target_path)
                                    size = target_path.stat().st_size
                                    logger.success(f"[OK] 从下载目录获取文件: {target_path} ({size:,} bytes)")
                                    return True, f"从下载目录获取文件: {size:,} bytes"
                                except Exception as e:
                                    logger.warning(f"处理下载目录文件失败: {e}")
                except Exception:
                    continue

            # 2. 检查页面是否有直接下载链接
            try:
                download_links = page.locator('a[href*=".xlsx"], a[download*=".xlsx"]')
                if download_links.count() > 0:
                    link = download_links.first
                    if link.is_visible():
                        href = link.get_attribute('href')
                        if href:
                            logger.info(f"[LINK] 发现直接下载链接: {href}")
                            # 这里可以添加直接下载逻辑
                            return False, "发现下载链接但未实现直接下载"
            except Exception:
                pass

            # 3. 检查页面是否显示"已下载"或类似状态
            try:
                download_status_selectors = [
                    'text="已下载"',
                    'text="Downloaded"',
                    'text="下载完成"',
                    '[class*="download"][class*="success"]',
                    '[class*="download"][class*="complete"]'
                ]

                for selector in download_status_selectors:
                    try:
                        elements = page.locator(selector)
                        if elements.count() > 0 and elements.first.is_visible():
                            logger.info(f"[TARGET] 检测到下载状态指示: {selector}")

                            # 如果页面显示已下载，再次尝试查找文件（可能需要更多时间）
                            logger.info("[WAIT] 页面显示已下载，等待文件出现...")
                            for wait_attempt in range(6):  # 等待最多30秒
                                time.sleep(5)

                                # 重新检查所有下载目录
                                for downloads_dir in possible_download_dirs:
                                    if not downloads_dir.exists():
                                        continue
                                    xlsx_files = list(downloads_dir.glob("*.xlsx"))
                                    if xlsx_files:
                                        latest_file = max(xlsx_files, key=lambda f: f.stat().st_mtime)
                                        if time.time() - latest_file.stat().st_mtime < 600:  # 10分钟内
                                            try:
                                                import shutil
                                                target_path.parent.mkdir(parents=True, exist_ok=True)
                                                shutil.copy2(latest_file, target_path)
                                                size = target_path.stat().st_size
                                                logger.success(f"[OK] 延迟获取到文件: {target_path} ({size:,} bytes)")
                                                return True, f"延迟获取文件成功: {size:,} bytes"
                                            except Exception as e:
                                                logger.debug(f"延迟获取文件失败: {e}")

                                logger.info(f"[WAIT] 等待文件出现... ({(wait_attempt+1)*5}s/30s)")

                            logger.warning("[WARN] 页面显示已下载但30秒内未获取到文件")
                            return False, "页面显示已下载但文件获取超时"
                    except Exception:
                        continue
            except Exception:
                pass

            logger.warning("[FAIL] 未找到可用的下载方式")
            return False, "下载失败，未找到文件"

        except Exception as e:
            logger.error(f"检查备用下载失败: {e}")
            return False, f"检查备用下载失败: {e}"

    def _calculate_granularity(self, start_date: str, end_date: str) -> str:
        """根据日期范围动态计算粒度"""
        try:
            from datetime import datetime
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            days = (end - start).days + 1

            if days == 1:
                return "daily"
            elif 2 <= days <= 7:
                return "weekly"
            elif 8 <= days <= 31:
                return "monthly"
            elif 32 <= days <= 93:
                return "quarterly"
            else:
                return "custom"
        except Exception as e:
            logger.warning(f"计算粒度失败: {e}，使用默认值")
            return "weekly"


def _safe_slug(s: str) -> str:
    try:
        from modules.utils.path_sanitizer import safe_slug as _ss
        return _ss(s)
    except Exception:
        return "".join(c if (c.isalnum() or c in "-_.") else "_" for c in (s or "")).strip("._") or "unknown"

