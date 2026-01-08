#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据采集中心应用

集成所有数据采集功能，包括：
- Playwright录制/调试模式
- 数据采集运行
- Shopee多账号专属采集
- Amazon数据采集
- 妙手ERP数据同步
- 采集统计
- 采集器配置
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from modules.core.base_app import BaseApplication
from modules.core.logger import get_logger

logger = get_logger(__name__)

class CollectionCenterApp(BaseApplication):
    """数据采集中心应用"""

    # 类级元数据 - 供注册器读取，避免实例化副作用
    NAME = "数据采集中心"
    VERSION = "1.0.0"
    DESCRIPTION = "多平台数据采集，支持Shopee、Amazon、妙手ERP等平台"

    def __init__(self):
        """初始化数据采集中心应用"""
        super().__init__()  # 调用父类初始化

        self.name = "数据采集中心"
        self.version = "1.0.0"
        self.description = "多平台数据采集，支持Shopee、Amazon、妙手ERP等平台"
        self.author = "跨境电商ERP团队"

        # 统计数据
        self.run_count = 0
        self.success_count = 0
        self.error_count = 0

        # 处理器惰性初始化标志
        self._handlers_initialized = False
        self.recording_handler = None
        self.data_handler = None
        self.shopee_handler = None
        self.stats_handler = None
        self.config_handler = None

    def _ensure_handlers_initialized(self):
        """确保处理器已初始化（惰性初始化）"""
        if not self._handlers_initialized:
            self._init_handlers()
            self._handlers_initialized = True

    def _init_handlers(self):
        """初始化处理器"""
        try:
            from .handlers import (
                RecordingWizardHandler,
                DataCollectionHandler,
                ShopeeCollectionHandler,
                CollectionStatsHandler,
                CollectionConfigHandler
            )

            self.recording_handler = RecordingWizardHandler()
            self.data_handler = DataCollectionHandler()
            self.shopee_handler = ShopeeCollectionHandler()
            self.stats_handler = CollectionStatsHandler()
            self.config_handler = CollectionConfigHandler()

            logger.info("数据采集中心处理器初始化完成")
        except Exception as e:
            logger.error(f"处理器初始化失败: {e}")
            # 设置空处理器避免错误
            self.recording_handler = None
            self.data_handler = None
            self.shopee_handler = None
            self.stats_handler = None
            self.config_handler = None

    def _persist_shops_and_prepare_dirs(self, platform: str, account_label: str, shops: list) -> None:
        """
        将发现到的店铺实时写入数据库，并为每个店铺创建规范化输出目录。
        """
        from pathlib import Path
        from models.database import DatabaseManager

        def _sanitize(name: str) -> str:
            import re
            s = re.sub(r"[\\/:*?\"<>|]+", "_", str(name).strip())
            return s[:120]

        # 1) 入库（去重更新）
        db = DatabaseManager()
        payload = [{"id": getattr(s, 'id', None), "name": getattr(s, 'name', None), "region": getattr(s, 'region', '')} for s in shops]
        try:
            db.upsert_shops(platform, account_label, payload)
        except Exception as e:
            logger.warning(f"写入店铺到数据库失败: {e}")

        # 2) 目录初始化：新架构下不在“发现店铺”阶段创建任何输出目录，避免产生非规范旧路径。
        #    目录由各导出组件在落盘时使用 build_output_path 统一创建（含 include_shop_id 策略）。
        return

    def run(self) -> bool:
        """运行数据采集中心应用"""
        try:
            self._ensure_handlers_initialized()
            logger.info("启动 数据采集中心")
            self.run_count += 1

            while True:
                if not self._show_collection_menu():
                    break

            self.success_count += 1
            logger.info("数据采集中心运行完成")
            return True

        except KeyboardInterrupt:
            print("\n\n[HI] 用户取消操作")
            return True
        except Exception as e:
            self.error_count += 1
            logger.error(f"数据采集中心运行失败: {e}")
            print(f"[FAIL] 运行失败: {e}")
            return False

    def _show_collection_menu(self):
        """显示采集中心菜单"""
        try:
            # 显示状态信息
            self._show_status_info()

            print("\n[START] 数据采集中心 - 功能菜单")
            print("-" * 40)
            print("1. [DATA]  数据采集录制")
            print("2. [START]  数据采集运行")

            print("6. [TARGET] 统一采集管理界面")
            print("7. [DATA] 查看采集统计")
            print("8. [GEAR]  采集器配置")
            print("9. [CLEAN] 录制/诊断归档维护 (DRY-RUN)")

            print("0. [BACK] 返回主菜单")

            choice = input("\n请选择操作 (0-9): ").strip()

            if choice == "1":
                self._run_collection_recording_menu()
            elif choice == "2":
                self._run_data_collection()

            elif choice == "6":
                self._run_collection_management_ui()
            elif choice == "7":
                self._show_collection_statistics()
            elif choice == "8":
                self._show_collector_configuration()

            elif choice == "9":
                self._run_recording_maintenance()
            elif choice == "0":
                return False
            else:
                print("[FAIL] 无效选择，请重新输入")
                input("按回车键继续...")

            return True

        except Exception as e:
            logger.error(f"显示采集菜单失败: {e}")
            print(f"[FAIL] 菜单显示失败: {e}")
            input("按回车键继续...")
            return True

    def _run_recording_maintenance(self):
        """执行录制与诊断文件归档（DRY-RUN）"""
        print("\n[CLEAN] 录制/诊断归档维护 (DRY-RUN)")
        print("=" * 40)
        try:
            from modules.utils.recording_maintenance import RecordingMaintenance
            tool = RecordingMaintenance()
            tool.enforce()
            print("\n[OK] 维护计划已输出到终端日志。默认 DRY-RUN，不会移动文件。\n- 支持 CLI: python modules/utils/recording_maintenance.py --platform shopee --keep 15 --apply\n- 配置项: collection.maintenance.* 可控制默认行为")
        except Exception as e:
            print(f"[FAIL] 归档维护执行失败: {e}")
        input("按回车键返回...")

    def _show_status_info(self):
        """显示状态信息"""
        print("\n" + "=" * 50)
        print(f"[START] {self.name} v{self.version}")
        print("=" * 50)
        print(f"[LIST] {self.description}")

        # 显示运行状态
        if self._is_running:
            runtime = time.time() - (self._startup_time or time.time())
            print(f"[GREEN] 状态: 运行中")
            print(f"[DATA] 历史运行: {self.run_count} 次")
            if self.run_count > 0:
                success_rate = (self.success_count / self.run_count) * 100
                print(f"[OK] 成功率: {success_rate:.1f}%")
        else:
            print(f"[WHITE] 状态: 未运行")

        print("=" * 50)

    def _run_recording_wizard(self):
        """运行录制向导"""
        print("\n[TOOLS]  Playwright录制/调试模式")
        print("=" * 40)
        print("[LIST] 功能说明: 使用Playwright录制用户操作，生成采集脚本")
        print("[TIP] 提示: 这将打开浏览器供您录制操作")

        try:
            print("\n[START] 启动Playwright录制模式...")

            if self.recording_handler:
                self.recording_handler.run_recording_wizard()
            else:
                print("[FAIL] 录制处理器未初始化")
                print("[TIP] 录制功能开发中，将从原系统迁移")
            input("按回车键返回...")
        except Exception as e:
            logger.error(f"录制模式启动失败: {e}")
            print(f"[FAIL] 启动失败: {e}")
            input("按回车键继续...")


    def _run_collection_recording_menu(self):
        """数据采集录制（回滚至旧版四项菜单：登录录制/自动登录修正/数据采集录制/完整流程）。"""
        print("\n[DATA] 数据采集录制")
        print("=" * 40)
        try:
            from .handlers import RecordingWizardHandler
            RecordingWizardHandler().run_recording_wizard()
            return
        except Exception as e:
            logger.error(f"旧版录制向导启动失败：{e}")
            print("[WARN] 旧版录制向导异常，尝试备用增强向导...")
            # 备用：增强向导（仅当旧版异常时兜底）
            try:
                from modules.utils.enhanced_recording_wizard import EnhancedRecordingWizard
                EnhancedRecordingWizard().run_wizard()
                return
            except Exception as e2:
                logger.error(f"备用增强向导也失败：{e2}")
                print("[FAIL] 录制功能暂不可用，请稍后再试。")
            print("请选择要录制的数据类型：")
            print("  1. 订单数据采集")
            print("  2. 商品数据采集")
            print("  3. 客流数据采集")
            print("  4. 财务数据采集")
            print("  5. 服务数据采集（AI助手/人工聊天）")
            print("  0. 返回上级菜单")
            dtype_choice = input("\n请选择 (0-5): ").strip()
            if dtype_choice == "0":
                return
            dtype_map = {"1": "orders", "2": "products", "3": "analytics", "4": "finance", "5": "services"}
            dtype_key = dtype_map.get(dtype_choice)
            if not dtype_key:
                print("[FAIL] 无效选择"); input("按回车键返回..."); return
            print("\n[TARGET] 选择录制方式：")
            print("  1. [LOCK] 登录流程录制")
            print("  2. [BOT] 自动登录流程修正")
            print("  3. [DATA] 数据采集录制")
            print("  4. [RETRY] 完整流程录制")
            print("  0. 返回上级菜单")
            mode_choice = input("\n请选择 (0-4): ").strip()
            if mode_choice == "0":
                return
            mode_map = {"1": "login", "2": "login_auto", "3": "collection", "4": "complete"}
            mode_key = mode_map.get(mode_choice)
            if not mode_key:
                print("[FAIL] 无效选择"); input("按回车键返回..."); return
            if not self._handlers_initialized:
                self._init_handlers()
            if not self.recording_handler:
                raise RuntimeError("录制处理器未初始化")
            self.recording_handler.run_legacy_recording_flow(dtype_key=dtype_key, preset_type=mode_key)
        input("按回车键返回...")

    def _run_data_collection(self):
        """运行数据采集"""
        while True:
            print("\n[START]  数据采集运行")
            print("=" * 40)
            print("[LIST] 选择采集任务类型:")
            print("1. [DATA] 运行录制脚本")
            print("2. [RETRY] 批量数据采集")
            print("0. [BACK] 返回上级菜单")

            choice = input("\n请选择操作 (0-2): ").strip()

            if choice == "1":
                self._run_recorded_scripts()
            elif choice == "2":
                self._run_batch_collection()
            elif choice == "0":
                break
            else:
                print("[FAIL] 无效选择，请重新输入")
                input("按回车键继续...")

    def _run_shopee_weekly_export(self):
        """运行 Shopee 商品周度导出"""
        print("\n[SHOP]  Shopee 商品周度导出 (API)")
        print("=" * 50)
        print("[LIST] 功能: 基于 HAR 解析的参数化导出")
        print("[NEW] 特性: 直连 API, 自动轮询下载, 支持多周度")

        try:
            # 输入店铺ID
            shop_id = input("\n请输入店铺ID (cnsc_shop_id): ").strip()
            if not shop_id:
                print("[FAIL] 店铺ID不能为空")
                input("按回车键返回...")
                return

            # 选择时间范围（适配Shopee控件实际能力）
            print("\n[DATE] 选择时间范围:")
            print("1. 今日实时")
            print("2. 昨天")
            print("3. 过去7天（推荐）")
            print("4. 过去30天")

            time_choice = input("请选择 (1-4): ").strip()

            from modules.services.shopee_exporter import ShopeeExporter
            from datetime import datetime, timedelta

            if time_choice == "1":
                # 今日实时
                today = datetime.now().strftime("%Y-%m-%d")
                start_date = today
                end_date = today
            elif time_choice == "2":
                # 昨天
                yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                start_date = yesterday
                end_date = yesterday
            elif time_choice == "3":
                # 过去7天
                end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")  # 昨天作为结束
                start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            elif time_choice == "4":
                # 过去30天
                end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")  # 昨天作为结束
                start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            else:
                print("[FAIL] 无效选择，使用默认：过去7天")
                end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

            print(f"\n[DATA] 导出参数:")
            print(f"   店铺ID: {shop_id}")
            print(f"   日期范围: {start_date} ~ {end_date}")

            confirm = input("\n确认开始导出? (y/n): ").strip().lower()
            if confirm not in ['y', 'yes', '是']:
                return

            # 创建导出器并执行
            exporter = ShopeeExporter.from_persistent_session("shopee", "shopee新加坡3C店")

            print("\n[START] 开始导出...")
            success, message, file_path = exporter.export_product_performance_weekly(
                shop_id=shop_id,
                start_date=start_date,
                end_date=end_date
            )

            if success:
                print(f"\n[OK] 导出成功!")
                print(f"[DIR] 文件路径: {file_path}")
                print(f"[NOTE] 说明: {message}")
            else:
                print(f"\n[FAIL] 导出失败: {message}")

        except Exception as e:
            logger.error(f"Shopee 导出异常: {e}")
            print(f"[FAIL] 导出异常: {e}")

        input("\n按回车键返回...")

    def _run_recorded_scripts(self):
        """运行录制脚本（选择数据类型后执行）"""
        print("\n[DATA] 运行录制脚本")
        print("=" * 40)
        print("[TIP] 请选择数据类型以运行相应的录制脚本：")
        print("  1. 订单数据采集")
        print("  2. 商品数据采集")
        print("  3. 客流数据采集")
        print("  4. 财务数据采集")
        print("  5. 服务数据采集（AI助手/人工聊天）")
        print("  0. 返回上级菜单")

        choice = input("\n请选择 (0-5): ").strip()
        if choice == "0":
            return
        elif choice == "1":
            self._run_orders_recorded_menu()
        elif choice == "2":
            self._run_products_recorded_menu()
        elif choice == "3":
            self._run_analytics_collection_menu()
        elif choice == "4":
            self._run_finance_recorded_menu()
        elif choice == "5":
            self._run_services_recorded_menu()
        else:
            print("[FAIL] 无效选择")
            input("按回车键返回...")
    def _run_orders_recorded_menu(self):
        """订单数据采集 - 录制脚本菜单"""
        while True:
            print("\n[RECEIPT] 订单数据采集 - 录制脚本")
            print("=" * 40)
            print("  1. 运行最新订单采集脚本")
            print("  2. [BRAIN] 妙手ERP 订单表现数据导出（组件化）")

            print("  c. [EDIT]  快速修改组件配置（orders_config.py）")
            print("  m. 管理稳定版脚本（查看/设置/取消）")
            print("  0. 返回上级菜单")
            choice = input("\n请选择 (0-2/c/m): ").strip()
            if choice == "0":
                break
            elif choice == "1":
                self._run_recorded_scripts_by_type("orders")
            elif choice == "2":
                self._run_miaoshou_orders_componentized()
            elif choice.lower() == "c":
                self._quick_edit_config("orders")
            elif choice.lower() == "m":
                self._manage_stable_scripts_menu("orders")
            else:
                print("[FAIL] 无效选择"); input("按回车键返回...")

    def _run_finance_recorded_menu(self):
        """财务数据采集 - 录制脚本菜单"""
        while True:
            print("\n[MONEY] 财务数据采集 - 录制脚本")
            print("=" * 40)
            print("  1. 运行最新财务采集脚本")
            print("  2. [BRAIN] 妙手ERP 财务表现数据导出（组件化）")

            print("  c. [EDIT]  快速修改组件配置（finance_config.py）")
            print("  m. 管理稳定版脚本（查看/设置/取消）")
            print("  0. 返回上级菜单")
            choice = input("\n请选择 (0-2/c/m): ").strip()
            if choice == "0":
                break
            elif choice == "1":
                self._run_recorded_scripts_by_type("finance")
            elif choice == "2":
                self._run_miaoshou_finance_componentized()
            elif choice.lower() == "c":
                self._quick_edit_config("finance")
            elif choice.lower() == "m":
                self._manage_stable_scripts_menu("finance")
            else:
                print("[FAIL] 无效选择"); input("按回车键返回...")

    def _run_services_recorded_menu(self):
        """服务数据采集 - 录制脚本菜单"""
        while True:
            print("\n[BELL] 服务数据采集 - 录制脚本")
            print("=" * 40)
            print("  1. 运行最新服务采集脚本（AI助手/人工聊天）")
            print("  2. [BELL] Shopee 服务表现数据导出（组件化优先 - 已增强）")
            print("  3. [MUSIC] TikTok 服务表现数据导出（组件化 - 深链接->时间->导出）")
            print("  4. [BRAIN] 妙手ERP 服务表现数据导出（组件化）")

            print("  c. [EDIT]  快速修改组件配置（services_config.py）")
            print("  m. 管理稳定版脚本（查看/设置/取消）")
            print("  0. 返回上级菜单")
            choice = input("\n请选择 (0-4/c/m): ").strip()
            if choice == "0":
                break
            elif choice == "1":
                self._run_recorded_scripts_by_type("services")
            elif choice == "2":
                self._run_componentized_one_click_export()
            elif choice == "3":
                self._run_tiktok_services_componentized()
            elif choice == "4":
                self._run_miaoshou_services_componentized()
            elif choice.lower() == "c":
                self._quick_edit_config("services")
            elif choice.lower() == "m":
                self._manage_stable_scripts_menu("services")
            else:
                print("[FAIL] 无效选择"); input("按回车键返回...")


    def _run_products_recorded_menu(self):
        """商品数据采集 - 录制脚本菜单"""
        while True:
            print("\n[PKG] 商品数据采集 - 录制脚本")
            print("=" * 40)
            print("  1. [SHOP]  Shopee 商品表现数据导出 (录制脚本)")
            print("  2. [START] 运行最新商品采集脚本（选择平台：Shopee/TikTok）")
            print("  3. [MUSIC] TikTok 商品表现数据导出（组件化 - 深链接->时间->导出）")
            print("  4. [TOOLKIT] 妙手ERP 商品表现数据导出（组件化）")
            print("  c. [EDIT]  快速修改组件配置（products_config.py）")
            print("  m. 管理稳定版脚本（查看/设置/取消）")
            print("  0. 返回上级菜单")
            choice = input("\n请选择 (0-4/c/m): ").strip()
            if choice == "0":
                break
            elif choice == "1":
                # Shopee 专用组件化导出（稳定可靠）
                self._run_shopee_product_performance_export()
            elif choice == "2":
                # 统一回放入口（已支持跨平台与持久化会话）
                self._run_recorded_scripts_by_type("products")
            elif choice == "3":
                # 新增：TikTok 组件化导出（对齐 Shopee 深链接->时间->导出 流程）
                self._run_tiktok_products_componentized()
            elif choice == "4":
                self._run_miaoshou_products_componentized()
            elif choice.lower() == "c":
                self._quick_edit_config("products")
            elif choice.lower() == "m":
                self._manage_stable_scripts_menu("products")
            else:
                print("[FAIL] 无效选择")
                input("按回车键返回...")


    def _run_tiktok_products_componentized(self):
        """TikTok 商品表现数据导出（组件化）

        对齐 Shopee 的流程：选账号 -> 选择店铺/区域 -> 选择时间 -> 深链接导航 -> 导出下载。
        使用平台适配器 + 组件：Navigation + DatePicker + Exporter。
        """
        try:
            print("\n[MUSIC] TikTok 商品表现数据导出（组件化）")
            print("=" * 40)
            print("[LIST] 流程：选账号 -> 选择店铺/区域 -> 选择时间 -> 深链接导航 -> 导出下载")

            # 步骤0：选择账号
            sel = self._select_account_unified("tiktok")
            if not sel:
                return
            account, account_label = sel

            # 步骤1：选择时间范围（与 DateOption/TimePolicy 对齐）
            print("\n[DATE] 选择时间范围:")
            print("  1. 最近7天（默认）    2. 最近28天    3. 昨天")
            tch = input("请选择 (1-3): ").strip() or "1"

            from modules.components.date_picker.base import DateOption
            from modules.services.time_policy import RollingDaysPolicy, CustomRangePolicy
            from datetime import datetime, timedelta

            if tch == "2":
                date_opt = DateOption.LAST_28_DAYS
                granularity = "monthly"
                days = 28
                time_policy = RollingDaysPolicy(28)
            elif tch == "3":
                date_opt = DateOption.YESTERDAY
                granularity = "daily"
                days = 1
                _end = (datetime.now() - timedelta(days=1)).date()
                time_policy = CustomRangePolicy(_end, _end)
            else:
                date_opt = DateOption.LAST_7_DAYS
                granularity = "weekly"
                days = 7
                time_policy = RollingDaysPolicy(7)

            # 步骤2：执行组件化流程
            from playwright.sync_api import sync_playwright
            from modules.utils.persistent_browser_manager import PersistentBrowserManager
            from modules.components.base import ExecutionContext
            from modules.services.platform_adapter import get_adapter
            from modules.components.navigation.base import TargetPage

            with sync_playwright() as p:
                print("[LOC] 步骤1: 获取页面对象...")
                pb = PersistentBrowserManager(p)
                account_id = (
                    account.get("store_name")
                    or account.get("username")
                    or str(account.get("account_id") or "account")
                )
                ctx = pb.get_or_create_persistent_context("tiktok", str(account_id), account)
                page = ctx.pages[0] if getattr(ctx, "pages", None) else ctx.new_page()
                try:
                    print("[LOC] 步骤2: 构造执行上下文...")
                    exec_ctx = ExecutionContext(
                        platform="tiktok",
                        account=account,
                        config={
                            "granularity": granularity,
                            # 区域/店铺在登录后由 URL 识别，随后覆盖
                        },
                        logger=get_logger(__name__),
                    )
                    adapter = get_adapter("tiktok", exec_ctx)

                    print("[LOC] 步骤3: 确保已登录...")
                    try:
                        login_comp = adapter.login()
                        login_comp.run(page)
                    except Exception:
                        pass

                    # 步骤3：发现店铺/区域并选择（优先自动发现，其次人工回退）
                    region_to_use = None
                    try:
                        sel_comp = adapter.shop_selector()
                        sel_res = sel_comp.run(page)
                        print(f"[LOC] 店铺选择结果: success={sel_res.success}, region={sel_res.region}, shop={sel_res.shop_name}, code={sel_res.shop_code}")
                        if sel_res.success and sel_res.region:
                            region_to_use = sel_res.region
                    except Exception as _se:
                        print(f"[WARN] 店铺选择组件异常: {_se}")

                    if not region_to_use:
                        # URL 检测 + 人工确认覆盖
                        detected_region = None
                        try:
                            from urllib.parse import urlparse, parse_qs
                            parsed = urlparse(str(page.url))
                            q = parse_qs(parsed.query)
                            cur = q.get("shop_region", [None])[0]
                            if cur:
                                detected_region = str(cur).upper()
                        except Exception:
                            pass
                        default_region = detected_region or account.get("shop_region") or account.get("region") or "SG"
                        hint = input(f"[SHOP] 步骤3: 选择店铺/区域（检测到: {default_region}，回车确认或输入区域代码覆盖）: ").strip().upper()
                        region_to_use = hint or default_region

                    exec_ctx.config["shop_region"] = region_to_use
                    exec_ctx.config["days"] = days

                    # 同步计算展示日期（与文件命名/manifest 对齐）
                    try:
                        from datetime import datetime, timedelta
                        end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                        if days == 1:
                            start_date = end_date
                        else:
                            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
                        exec_ctx.config["start_date"] = start_date
                        exec_ctx.config["end_date"] = end_date
                    except Exception:
                        pass

                    print("[LOC] 步骤4: 执行导航组件...")
                    try:
                        nav = adapter.navigation()
                        nav_res = nav.run(page, TargetPage.PRODUCTS_PERFORMANCE)
                        print(f"[LOC] 导航结果: success={nav_res.success}, url={nav_res.url}, message={nav_res.message}")
                    except Exception as _ne:
                        print(f"[WARN] 导航组件异常: {_ne}，尝试兜底深链接...")
                        try:
                            from modules.platforms.tiktok.components.products_config import ProductsSelectors
                            sel_cfg = ProductsSelectors()
                            url = f"{sel_cfg.BASE_URL}{sel_cfg.PRODUCTS_PERFORMANCE_PATH}?shop_region={region_to_use}"
                            try:
                                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                            except Exception:
                                page.goto(url, wait_until="load", timeout=60000)
                        except Exception:
                            pass

                    # 步骤5: 如果 URL 已包含时间参数，则跳过 DatePicker 点击
                    try:
                        cur_url = str(page.url)
                        ok = True
                        if ("timeRange=" in cur_url) or ("shortcut=" in cur_url):
                            print("[LOC] 步骤5: 已包含时间参数，跳过日期选择组件")
                        else:
                            print("[LOC] 步骤5: 执行统一时间策略 (TikTok)...")
                            from modules.services.time_policy import apply_time_policy_tiktok
                            ok, msg = apply_time_policy_tiktok(page, adapter, time_policy)
                            print(f"[LOC] 时间策略结果: success={ok}, message={msg}")
                            page.wait_for_timeout(600)
                        if not ok:
                            print("[FAIL] 日期选择失败，已取消导出。")
                            return
                    except Exception as _de:
                        print(f"[WARN] 日期选择组件异常: {_de}")
                        print("[FAIL] 日期选择异常，已取消导出。")
                        return

                    print("[TARGET] 组件化路径完成，开始纯导出...")
                    exporter = adapter.exporter()
                    res = exporter.run(page)
                    if res.success:
                        # 导出组件已打印标准化落盘路径
                        pass
                    else:
                        print("\n[FAIL] 导出失败")
                        if getattr(res, "error", None):
                            print(f"原因: {res.error}")
                        elif getattr(res, "message", None):
                            print(f"信息: {res.message}")
                finally:
                    try:
                        pb.save_context_state(ctx, "tiktok", str(account_id))
                    except Exception:
                        pass
                    try:
                        pb.close_context("tiktok", str(account_id))
                    except Exception:
                        pass

            input("\n[OK] 执行完成，按回车键返回...")
        except Exception as e:
            logger.error(f"TikTok 组件化导出失败: {e}")
            print(f"[FAIL] 执行异常: {e}")
            input("按回车键返回...")

    def _run_tiktok_traffic_componentized(self):
        """TikTok 流量表现数据导出（组件化）

        设计对齐 TikTok 商品表现与 Shopee 流量表现组件化流程：
        选账号 -> 选择店铺/区域 -> 选择时间 -> 深链接导航 -> 导出下载。
        使用统一组件链：Navigation + DatePicker + Exporter。
        """
        try:
            print("\n[MUSIC] TikTok 流量表现数据导出（组件化）")
            print("=" * 40)
            print("[LIST] 流程：选账号 -> 选择店铺/区域 -> 选择时间 -> 深链接导航 -> 导出下载")

            # 步骤0：选择账号
            sel = self._select_account_unified("tiktok")
            if not sel:
                return
            account, account_label = sel

            # 步骤1：选择时间范围（与 DateOption/TimePolicy 对齐）
            print("\n[DATE] 选择时间范围:")
            print("  1. 最近7天（默认）    2. 最近28天    3. 昨天")
            tch = input("请选择 (1-3): ").strip() or "1"

            from modules.components.date_picker.base import DateOption
            from modules.services.time_policy import RollingDaysPolicy, CustomRangePolicy
            from datetime import datetime, timedelta

            if tch == "2":
                date_opt = DateOption.LAST_28_DAYS
                granularity = "monthly"
                days = 28
                time_policy = RollingDaysPolicy(28)
            elif tch == "3":
                date_opt = DateOption.YESTERDAY
                granularity = "daily"
                days = 1
                _end = (datetime.now() - timedelta(days=1)).date()
                time_policy = CustomRangePolicy(_end, _end)
            else:
                date_opt = DateOption.LAST_7_DAYS
                granularity = "weekly"
                days = 7
                time_policy = RollingDaysPolicy(7)

            # 步骤2：执行组件化流程
            from playwright.sync_api import sync_playwright
            from modules.utils.persistent_browser_manager import PersistentBrowserManager
            from modules.components.base import ExecutionContext
            from modules.services.platform_adapter import get_adapter
            from modules.components.navigation.base import TargetPage

            with sync_playwright() as p:
                print("[LOC] 步骤1: 获取页面对象...")
                pb = PersistentBrowserManager(p)
                account_id = (
                    account.get("store_name")
                    or account.get("username")
                    or str(account.get("account_id") or "account")
                )
                ctx = pb.get_or_create_persistent_context("tiktok", str(account_id), account)
                page = ctx.pages[0] if getattr(ctx, "pages", None) else ctx.new_page()
                try:
                    print("[LOC] 步骤2: 构造执行上下文...")
                    exec_ctx = ExecutionContext(
                        platform="tiktok",
                        account=account,
                        config={
                            "granularity": granularity,
                            # 重要：流量表现页不允许在深链中携带时间，否则导出按钮可能不出现
                            "nav_with_timerange": False,
                        },
                        logger=get_logger(__name__),
                    )
                    adapter = get_adapter("tiktok", exec_ctx)

                    print("[LOC] 步骤3: 确保已登录...")
                    try:
                        adapter.login().run(page)
                    except Exception:
                        pass

                    # 步骤3：发现店铺/区域并选择
                    region_to_use = None
                    try:
                        sel_comp = adapter.shop_selector()
                        sel_res = sel_comp.run(page)
                        print(f"[LOC] 店铺选择结果: success={sel_res.success}, region={sel_res.region}, shop={sel_res.shop_name}, code={sel_res.shop_code}")
                        if sel_res.success and sel_res.region:
                            region_to_use = sel_res.region
                    except Exception as _se:
                        print(f"[WARN] 店铺选择组件异常: {_se}")

                    if not region_to_use:
                        # URL 检测 + 人工确认覆盖
                        detected_region = None
                        try:
                            from urllib.parse import urlparse, parse_qs
                            parsed = urlparse(str(page.url))
                            q = parse_qs(parsed.query)
                            cur = q.get("shop_region", [None])[0]
                            if cur:
                                detected_region = str(cur).upper()
                        except Exception:
                            pass
                        default_region = detected_region or account.get("shop_region") or account.get("region") or "SG"
                        hint = input(f"[SHOP] 步骤3: 选择店铺/区域（检测到: {default_region}，回车确认或输入区域代码覆盖）: ").strip().upper()
                        region_to_use = hint or default_region

                    exec_ctx.config["shop_region"] = region_to_use
                    exec_ctx.config["days"] = days

                    # 同步计算展示日期（与文件命名/manifest 对齐）
                    try:
                        from datetime import datetime, timedelta
                        end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                        if days == 1:
                            start_date = end_date
                        else:
                            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
                        exec_ctx.config["start_date"] = start_date
                        exec_ctx.config["end_date"] = end_date
                    except Exception:
                        pass

                    print("[LOC] 步骤4: 执行导航组件...")
                    try:
                        nav = adapter.navigation()
                        nav_res = nav.run(page, TargetPage.TRAFFIC_OVERVIEW)
                        print(f"[LOC] 导航结果: success={nav_res.success}, url={nav_res.url}, message={nav_res.message}")
                    except Exception as _ne:
                        print(f"[WARN] 导航组件异常: {_ne}，尝试兜底深链接...")
                        try:
                            from modules.platforms.tiktok.components.analytics_config import AnalyticsSelectors
                            sel_cfg = AnalyticsSelectors()
                            url = f"{sel_cfg.BASE_URL}{sel_cfg.TRAFFIC_PATH}?shop_region={region_to_use}"
                            try:
                                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                            except Exception:
                                page.goto(url, wait_until="load", timeout=60000)
                        except Exception:
                            pass

                    # 步骤5: 如果 URL 已包含时间参数，则跳过 DatePicker
                    try:
                        cur_url = str(page.url)
                        ok = True
                        if ("timeRange=" in cur_url) or ("shortcut=" in cur_url):
                            print("[LOC] 步骤5: 已包含时间参数，跳过日期选择组件")
                        else:
                            print("[LOC] 步骤5: 执行日期选择组件...")
                            from modules.services.time_policy import apply_time_policy_tiktok
                            ok, msg = apply_time_policy_tiktok(page, adapter, time_policy)
                            print(f"[LOC] 时间策略结果: success={ok}, message={msg}")
                            page.wait_for_timeout(600)
                        if not ok:
                            print("[FAIL] 日期选择失败，已取消导出。")
                            return
                    except Exception as _de:
                        print(f"[WARN] 日期选择组件异常: {_de}")
                        print("[FAIL] 日期选择异常，已取消导出。")
                        return

                    print("[TARGET] 组件化路径完成，开始纯导出...")
                    res = adapter.exporter().run(page)
                    if res.success:
                        pass  # 导出组件已打印标准化落盘路径
                    else:
                        print("\n[FAIL] 导出失败")
                        if getattr(res, "error", None):
                            print(f"原因: {res.error}")
                        elif getattr(res, "message", None):
                            print(f"信息: {res.message}")
                finally:
                    try:
                        pb.save_context_state(ctx, "tiktok", str(account_id))
                    except Exception:
                        pass
                    try:
                        pb.close_context("tiktok", str(account_id))
                    except Exception:
                        pass

            input("\n[OK] 执行完成，按回车键返回...")
        except Exception as e:
            logger.error(f"TikTok 流量表现组件化导出失败: {e}")
            print(f"[FAIL] 执行异常: {e}")
            input("按回车键返回...")


    def _run_tiktok_services_componentized(self):
        """TikTok 服务表现数据导出（组件化）

        流程与 TikTok 流量表现一致：
        选账号 -> 选择店铺/区域 -> 选择时间（昨天/近7天/近28天）-> 深链接导航 -> 导出下载。
        使用统一组件链：Navigation + DatePicker + Exporter。
        注意：TikTok 的 iframe 日期控件不允许输入填充，必须走面板对齐+点击。
        """
        try:
            print("\n[MUSIC] TikTok 服务表现数据导出（组件化）")
            print("=" * 40)
            print("[LIST] 流程：选账号 -> 选择店铺/区域 -> 选择时间 -> 深链接导航 -> 导出下载")

            # 步骤0：选择账号
            sel = self._select_account_unified("tiktok")
            if not sel:
                return
            account, account_label = sel

            # 步骤1：选择时间范围
            print("\n[DATE] 选择时间范围:")
            print("  1. 最近7天（默认）    2. 最近28天    3. 昨天")
            tch = input("请选择 (1-3): ").strip() or "1"

            from modules.components.date_picker.base import DateOption
            from modules.services.time_policy import RollingDaysPolicy, CustomRangePolicy
            from datetime import datetime, timedelta

            if tch == "2":
                date_opt = DateOption.LAST_28_DAYS
                granularity = "monthly"
                days = 28
                time_policy = RollingDaysPolicy(28)
            elif tch == "3":
                date_opt = DateOption.YESTERDAY
                granularity = "daily"
                days = 1
                _end = (datetime.now() - timedelta(days=1)).date()
                time_policy = CustomRangePolicy(_end, _end)
            else:
                date_opt = DateOption.LAST_7_DAYS
                granularity = "weekly"
                days = 7
                time_policy = RollingDaysPolicy(7)

            # 步骤2：执行组件化流程
            from playwright.sync_api import sync_playwright
            from modules.utils.persistent_browser_manager import PersistentBrowserManager
            from modules.components.base import ExecutionContext
            from modules.services.platform_adapter import get_adapter
            from modules.components.navigation.base import TargetPage
            from modules.core.logger import get_logger as _get_logger

            with sync_playwright() as p:
                print("[LOC] 步骤1: 获取页面对象...")
                pb = PersistentBrowserManager(p)
                account_id = (
                    account.get("store_name")
                    or account.get("username")
                    or str(account.get("account_id") or "account")
                )
                ctx = pb.get_or_create_persistent_context("tiktok", str(account_id), account)
                page = ctx.pages[0] if getattr(ctx, "pages", None) else ctx.new_page()

                try:
                    try:
                        print("[LOC] 步骤2: 构造执行上下文...")
                        exec_ctx = ExecutionContext(
                            platform="tiktok",
                            account=account,
                            config={
                                "granularity": granularity,
                                # 与流量表现一致：深链不带时间，统一用 DatePicker 选择
                                "nav_with_timerange": False,
                            },
                            logger=_get_logger(__name__),
                        )
                        adapter = get_adapter("tiktok", exec_ctx)

                        print("[LOC] 步骤3: 确保已登录...")
                        try:
                            adapter.login().run(page)
                        except Exception:
                            pass

                        # 步骤3：发现店铺/区域并选择（与流量一致）
                        region_to_use = None
                        try:
                            sel_comp = adapter.shop_selector()
                            sel_res = sel_comp.run(page)
                            print(f"[LOC] 店铺选择结果: success={sel_res.success}, region={sel_res.region}, shop={sel_res.shop_name}, code={sel_res.shop_code}")
                            if sel_res.success and sel_res.region:
                                region_to_use = sel_res.region
                        except Exception as _se:
                            print(f"[WARN] 店铺选择组件异常: {_se}")
                        if not region_to_use:
                            try:
                                from urllib.parse import urlparse, parse_qs
                                parsed = urlparse(str(page.url))
                                q = parse_qs(parsed.query)
                                cur = q.get("shop_region", [None])[0]
                                if cur:
                                    region_to_use = str(cur).upper()
                            except Exception:
                                pass
                            if not region_to_use:
                                region_to_use = account.get("shop_region") or account.get("region") or "SG"

                        exec_ctx.config["shop_region"] = region_to_use

                        # 同步计算展示日期（与文件命名/manifest 对齐）
                        try:
                            from datetime import datetime, timedelta
                            end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                            if days == 1:
                                start_date = end_date
                            else:
                                start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
                            exec_ctx.config["start_date"] = start_date
                            exec_ctx.config["end_date"] = end_date
                            exec_ctx.config["days"] = days
                        except Exception:
                            pass

                        print("[LOC] 步骤4: 执行导航组件...")
                        try:
                            nav = adapter.navigation()
                            nav_res = nav.run(page, TargetPage.SERVICE_ANALYTICS)
                            print(f"[LOC] 导航结果: success={nav_res.success}, url={nav_res.url}, message={nav_res.message}")
                        except Exception as _ne:
                            print(f"[WARN] 导航组件异常: {_ne}")

                        print("[LOC] 步骤5: 执行日期选择组件...")
                        try:
                            from modules.services.time_policy import apply_time_policy_tiktok
                            ok, msg = apply_time_policy_tiktok(page, adapter, time_policy)
                            print(f"[LOC] 时间策略结果: success={ok}, message={msg}")
                            page.wait_for_timeout(600)
                            if not ok:
                                print("[FAIL] 日期选择失败，已取消导出。")
                                return
                        except Exception as _de:
                            print(f"[WARN] 日期选择组件异常: {_de}")
                            print("[FAIL] 日期选择异常，已取消导出。")
                            return

                        print("[TARGET] 组件化路径完成，开始纯导出...")
                        res = adapter.exporter().run(page)
                        if res.success:
                            pass
                        else:
                            print("\n[FAIL] 导出失败")
                            if getattr(res, "message", None):
                                print(f"信息: {res.message}")

                        input("\n[OK] 执行完成，按回车键返回...")
                    except Exception as _e:
                        print(f"[FAIL] 执行异常: {_e}")
                        input("按回车键返回...")
                except Exception as _outer_e:
                    print(f"[WARN] 组件化流程异常: {_outer_e}")

        except Exception as e:
            logger.error(f"TikTok 服务表现组件化导出失败: {e}")
            print(f"[FAIL] 执行异常: {e}")
            input("按回车键返回...")

    def _miaoshou_time_prompt(self):
        """妙手ERP时间选择：支持一键预设覆盖，默认提供三档选择。
        返回 (DateOption, granularity)
        """
        from modules.components.date_picker.base import DateOption
        try:
            preset = getattr(self, "_one_click_preset", None)
            if isinstance(preset, dict) and preset.get("start_date") and preset.get("end_date"):
                from datetime import datetime
                sd = datetime.strptime(str(preset["start_date"]), "%Y-%m-%d").date()
                ed = datetime.strptime(str(preset["end_date"]), "%Y-%m-%d").date()
                days = (ed - sd).days + 1
                if days <= 1:
                    return DateOption.YESTERDAY, "daily"
                elif days <= 7:
                    return DateOption.LAST_7_DAYS, "weekly"
                else:
                    # 妙手ERP最大建议28天
                    return DateOption.LAST_28_DAYS, "monthly"
        except Exception:
            pass
        print("\n[DATE] 选择时间范围:")
        print("  1. 最近7天（默认）    2. 最近30天    3. 昨天")
        tch = input("请选择 (1-3): ").strip() or "1"
        if tch == "2":
            return DateOption.LAST_28_DAYS, "monthly"
        elif tch == "3":
            return DateOption.YESTERDAY, "daily"
        else:
            return DateOption.LAST_7_DAYS, "weekly"

    def _run_miaoshou_products_componentized(self):
        try:
            print("\n[BRAIN] 妙手ERP 商品表现数据导出（组件化）"); print("=" * 40)
            sel = self._select_account_unified("miaoshou")
            if not sel: return
            account, account_label = sel
            date_opt, granularity = self._miaoshou_time_prompt()
            from playwright.sync_api import sync_playwright
            from modules.utils.persistent_browser_manager import PersistentBrowserManager
            from modules.components.base import ExecutionContext
            from modules.services.platform_adapter import get_adapter
            from modules.components.navigation.base import TargetPage
            with sync_playwright() as p:
                pb = PersistentBrowserManager(p)
                acct_id = account.get("store_name") or account.get("username") or str(account.get("account_id") or "account")
                ctx = pb.get_or_create_persistent_context("miaoshou", str(acct_id), account)
                page = ctx.pages[0] if getattr(ctx, "pages", None) else ctx.new_page()
                exec_ctx = ExecutionContext(platform="miaoshou", account=account, config={"granularity": granularity, "data_domain": "products"}, logger=get_logger(__name__))
                adapter = get_adapter("miaoshou", exec_ctx)
                try:
                    adapter.login().run(page)
                except Exception:
                    pass

                print("[LOC] 步骤1: 导航到商品表现页面（深链接优先）...")
                nav = adapter.navigation().run(page, TargetPage.PRODUCTS_PERFORMANCE)
                try:
                    print(f"[LOC] 导航结果: success={getattr(nav,'success',None)}, url={getattr(nav,'url',None)}, message={getattr(nav,'message',None)}")
                except Exception:
                    pass
                if not getattr(nav, 'success', False):
                    print(f"[WARN] 导航提示: {getattr(nav,'message','')}，尝试继续")

                # [LOC] 步骤1.5: 观察并关闭通知弹窗（6s），避免遮挡日期/导出按钮
                try:
                    from modules.platforms.miaoshou.components.overlay_guard import OverlayGuard
                    OverlayGuard().run(page, label="[LOC] 步骤1.5: 观察并关闭通知弹窗（6s）...")
                except Exception:
                    pass

                # [LOC] 步骤2: 选择时间范围...（仓库清单无时间维度，本步骤暂时跳过，但保留选项用于命名/粒度配置）
                print("[LOC] 步骤2: 选择时间范围...（跳过：商品表现=仓库清单无时间维度）")
                # 保留 date_opt/granularity 用于文件命名与后续配置，但不在页面上执行日期选择
                # try:
                #     adapter.date_picker().run(page, date_opt)
                # except Exception as _e:
                #     print(f"[WARN] 日期策略异常: {_e}")

                print("[LOC] 步骤3: 开始执行导出组件...")
                # 步骤3/4 在导出组件中输出（点击导出 -> 等待下载并保存）
                res = adapter.exporter().run(page)
                if not res.success: print(f"[FAIL] 导出失败: {res.message}")
            input("\n按回车键返回...")
        except Exception as e:
            print(f"[FAIL] 执行异常: {e}")
            input("按回车键返回...")

    def _run_miaoshou_traffic_componentized(self):
        try:
            print("\n[BRAIN] 妙手ERP 流量表现数据导出（组件化）"); print("=" * 40)
            sel = self._select_account_unified("miaoshou")
            if not sel: return
            account, account_label = sel
            date_opt, granularity = self._miaoshou_time_prompt()
            from playwright.sync_api import sync_playwright
            from modules.utils.persistent_browser_manager import PersistentBrowserManager
            from modules.components.base import ExecutionContext
            from modules.services.platform_adapter import get_adapter
            from modules.components.navigation.base import TargetPage
            with sync_playwright() as p:
                pb = PersistentBrowserManager(p)
                acct_id = account.get("store_name") or account.get("username") or str(account.get("account_id") or "account")
                ctx = pb.get_or_create_persistent_context("miaoshou", str(acct_id), account)
                page = ctx.pages[0] if getattr(ctx, "pages", None) else ctx.new_page()
                exec_ctx = ExecutionContext(platform="miaoshou", account=account, config={"granularity": granularity, "data_domain": "traffic"}, logger=get_logger(__name__))
                adapter = get_adapter("miaoshou", exec_ctx)
                try: adapter.login().run(page)
                except Exception: pass
                nav = adapter.navigation().run(page, TargetPage.TRAFFIC_OVERVIEW)
                if not getattr(nav, 'success', False): print(f"[WARN] 导航提示: {getattr(nav,'message','')}，尝试继续")
                # 步骤1.5：关闭导航后的公告弹窗
                try:
                    from modules.platforms.miaoshou.components.overlay_guard import OverlayGuard
                    OverlayGuard().run(page, label="[LOC] 步骤1.5: 观察并关闭通知弹窗（6s）...")
                except Exception:
                    pass
                try: adapter.date_picker().run(page, date_opt)
                except Exception: pass
                res = adapter.exporter().run(page)
                if not res.success: print(f"[FAIL] 导出失败: {res.message}")
            input("\n按回车键返回...")
        except Exception as e:
            print(f"[FAIL] 执行异常: {e}")
            input("按回车键返回...")

    def _run_miaoshou_services_componentized(self):
        try:
            print("\n[BRAIN] 妙手ERP 服务表现数据导出（组件化）"); print("=" * 40)
            sel = self._select_account_unified("miaoshou")
            if not sel: return
            account, account_label = sel
            date_opt, granularity = self._miaoshou_time_prompt()
            from playwright.sync_api import sync_playwright
            from modules.utils.persistent_browser_manager import PersistentBrowserManager
            from modules.components.base import ExecutionContext
            from modules.services.platform_adapter import get_adapter
            from modules.components.navigation.base import TargetPage
            with sync_playwright() as p:
                pb = PersistentBrowserManager(p)
                acct_id = account.get("store_name") or account.get("username") or str(account.get("account_id") or "account")
                ctx = pb.get_or_create_persistent_context("miaoshou", str(acct_id), account)
                page = ctx.pages[0] if getattr(ctx, "pages", None) else ctx.new_page()
                exec_ctx = ExecutionContext(platform="miaoshou", account=account, config={"granularity": granularity, "data_domain": "services"}, logger=get_logger(__name__))
                adapter = get_adapter("miaoshou", exec_ctx)
                try: adapter.login().run(page)
                except Exception: pass
                nav = adapter.navigation().run(page, TargetPage.SERVICE_ANALYTICS)
                if not getattr(nav, 'success', False): print(f"[WARN] 导航提示: {getattr(nav,'message','')}，尝试继续")
                try:
                    from modules.platforms.miaoshou.components.overlay_guard import OverlayGuard
                    OverlayGuard().run(page, label="[LOC] 步骤1.5: 观察并关闭通知弹窗（6s）...")
                except Exception:
                    pass
                try: adapter.date_picker().run(page, date_opt)
                except Exception: pass
                res = adapter.exporter().run(page)
                if not res.success: print(f"[FAIL] 导出失败: {res.message}")
            input("\n按回车键返回...")
        except Exception as e:
            print(f"[FAIL] 执行异常: {e}")
            input("按回车键返回...")

    def _run_miaoshou_orders_componentized(self):
        try:
            print("\n[BRAIN] 妙手ERP 订单表现数据导出（组件化）"); print("=" * 40)
            sel = self._select_account_unified("miaoshou")
            if not sel: return
            account, account_label = sel
            date_opt, granularity = self._miaoshou_time_prompt()
            # 子类型选择（默认：同时导出 Shopee + TikTok）
            print("\n请选择子类型：1) shopee  2) tiktok  3) 两者（默认）")
            sub_in = input("请输入 1/2/3（回车=3）: ").strip()
            if sub_in == "1":
                subtypes = ["shopee"]
            elif sub_in == "2":
                subtypes = ["tiktok"]
            else:
                subtypes = ["shopee", "tiktok"]

            from playwright.sync_api import sync_playwright
            from modules.utils.persistent_browser_manager import PersistentBrowserManager
            from modules.components.base import ExecutionContext
            from modules.services.platform_adapter import get_adapter
            from modules.components.navigation.base import TargetPage
            with sync_playwright() as p:
                pb = PersistentBrowserManager(p)
                acct_id = account.get("store_name") or account.get("username") or str(account.get("account_id") or "account")
                ctx = pb.get_or_create_persistent_context("miaoshou", str(acct_id), account)
                page = ctx.pages[0] if getattr(ctx, "pages", None) else ctx.new_page()
                # 先登录一次（若已登录会自动跳过），避免在每个子类型循环中重复尝试登录导致卡顿/识别异常
                try:
                    _exec0 = ExecutionContext(platform="miaoshou", account=account, config={"granularity": granularity}, logger=get_logger(__name__))
                    _adapter0 = get_adapter("miaoshou", _exec0)
                    _adapter0.login().run(page)
                except Exception:
                    pass
                for sub in subtypes:
                    # 为规整落盘命名显式注入 shop_name（避免出现 unknown_shop）
                    _shop_name = account.get("store_name") or account.get("menu_display_name") or account.get("display_name") or account.get("username") or str(account.get("account_id") or "unknown_shop")
                    exec_ctx = ExecutionContext(
                        platform="miaoshou",
                        account=account,
                        config={
                            "granularity": granularity,
                            "data_domain": "orders",
                            "orders_subtype": sub,
                            "shop_name": _shop_name,
                        },
                        logger=get_logger(__name__),
                    )
                    adapter = get_adapter("miaoshou", exec_ctx)
                    nav = adapter.navigation().run(page, TargetPage.ORDERS)
                    if not getattr(nav, 'success', False): print(f"[WARN] 导航提示: {getattr(nav,'message','')}，尝试继续")
                    try:
                        from modules.platforms.miaoshou.components.overlay_guard import OverlayGuard
                        OverlayGuard().run(page, label="[LOC] 步骤1.5: 观察并关闭通知弹窗（6s）...")
                    except Exception:
                        pass
                    # 订单表现：此处仅写入配置，不在此时操作页面；具体输入由导出器按顺序执行（状态->时间->搜索）
                    try: adapter.date_picker().run(page, date_opt, apply_to_page=False)
                    except Exception: pass
                    print(f"\n[START] 开始导出子类型: {sub}")

                    res = adapter.exporter().run(page)
                    if res.success:
                        # 统一规范输出：导出成功 + 文件地址
                        print(f"\n[OK] 导出成功: {res.file_path or ''}")
                        try:
                            from pathlib import Path as _P
                            _p = _P(res.file_path or "")
                            if _p:
                                print(f"[FOLDER] 输出目录: {_p.parent}")
                                try:
                                    _url = f"file:///{str(_p).replace('\\', '/')}"
                                    print(f"[LINK] 文件链接: {_url}")
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    else:
                        print(f"[FAIL] 导出失败({sub}): {res.message}")
            input("\n按回车键返回...")
        except Exception as e:
            print(f"[FAIL] 执行异常: {e}")
            input("按回车键返回...")

    def _run_miaoshou_finance_componentized(self):
        try:
            print("\n[BRAIN] 妙手ERP 财务表现数据导出（组件化）"); print("=" * 40)
            sel = self._select_account_unified("miaoshou")
            if not sel: return
            account, account_label = sel
            # 财务一般按月/最近30天；仍提供三档
            date_opt, granularity = self._miaoshou_time_prompt()
            from playwright.sync_api import sync_playwright
            from modules.utils.persistent_browser_manager import PersistentBrowserManager
            from modules.components.base import ExecutionContext
            from modules.services.platform_adapter import get_adapter
            from modules.components.navigation.base import TargetPage
            with sync_playwright() as p:
                pb = PersistentBrowserManager(p)
                acct_id = account.get("store_name") or account.get("username") or str(account.get("account_id") or "account")
                ctx = pb.get_or_create_persistent_context("miaoshou", str(acct_id), account)
                page = ctx.pages[0] if getattr(ctx, "pages", None) else ctx.new_page()
                exec_ctx = ExecutionContext(platform="miaoshou", account=account, config={"granularity": granularity, "data_domain": "finance"}, logger=get_logger(__name__))
                adapter = get_adapter("miaoshou", exec_ctx)
                try: adapter.login().run(page)
                except Exception: pass
                nav = adapter.navigation().run(page, TargetPage.FINANCE)
                if not getattr(nav, 'success', False): print(f"[WARN] 导航提示: {getattr(nav,'message','')}，尝试继续")
                try:
                    from modules.platforms.miaoshou.components.overlay_guard import OverlayGuard
                    OverlayGuard().run(page, label="[LOC] 步骤1.5: 观察并关闭通知弹窗（6s）...")
                except Exception:
                    pass
                try: adapter.date_picker().run(page, date_opt)
                except Exception: pass
                res = adapter.exporter().run(page)
                if not res.success: print(f"[FAIL] 导出失败: {res.message}")
            input("\n按回车键返回...")
        except Exception as e:
            print(f"[FAIL] 执行异常: {e}")
            input("按回车键返回...")

    def _run_miaoshou_platform_wide_batch(self):
        """妙手ERP 平台批量采集（五大数据类型：products/traffic/services/orders/finance）。"""
        try:
            print("\n[BRAIN] 妙手ERP 批量采集"); print("=" * 40)
            # 选择数据域（默认仅商品表现+订单表现）；支持一键预设覆盖
            preset_domains = getattr(self, "_one_click_domains", None)
            if preset_domains:
                domains = list(preset_domains)
            else:
                print("\n[DATA] 选择数据域（可多选）：")
                print("1. 商品表现  2. 流量表现  3. 服务表现  4. 订单表现  5. 财务表现")
                dom_in = input("请输入选择的数字，用逗号分隔 (默认: 1,4): ").strip()
                # 兼容中文逗号/空格
                dom_in = dom_in.replace('，', ',').replace(' ', '')
                idx_map = {"1":"products","2":"traffic","3":"services","4":"orders","5":"finance"}
                default_keys = ["1","4"]
                keys = dom_in.split(',') if dom_in else default_keys
                domains = [idx_map[k] for k in keys if k in idx_map]
            # 时间范围
            date_opt, granularity = self._miaoshou_time_prompt()
            # 账户清单（与单次入口一致的模糊匹配：platform包含任一同义词 即视为妙手ERP）
            from modules.utils.account_manager import AccountManager
            am = AccountManager()
            all_accounts = am.load_accounts().get('accounts', [])
            _tokens = ['miaoshou', 'miaoshou_erp', 'miaoshou erp', 'erp', '妙手']
            accounts = [
                a for a in all_accounts
                if a.get('enabled', True)
                and a.get('login_url')
                and any(tok in ((a.get('platform', '') or '').lower()) for tok in _tokens)
            ]
            if not accounts:
                print("[FAIL] 未找到启用的 妙手ERP 账号"); input("按回车键返回..."); return
            # 执行
            from playwright.sync_api import sync_playwright
            from modules.utils.persistent_browser_manager import PersistentBrowserManager
            from modules.components.base import ExecutionContext
            from modules.services.platform_adapter import get_adapter
            from modules.components.navigation.base import TargetPage
            from modules.core.logger import get_logger
            total, ok, fail = 0, 0, 0
            skip = 0
            skip_reasons = {}
            tgt_map = {
                'products': TargetPage.PRODUCTS_PERFORMANCE,
                'traffic': TargetPage.TRAFFIC_OVERVIEW,
                'services': TargetPage.SERVICE_ANALYTICS,
                'orders': TargetPage.ORDERS,
                'finance': TargetPage.FINANCE,
            }
            # 平台内聚的域执行助手（仅供妙手ERP批量使用，不影响其他平台）
            def _run_domain(page, adapter, domain_key: str, date_opt):
                try:
                    # 将当前域写入执行上下文，便于组件读取（确保config存在）
                    try:
                        if getattr(adapter, 'exec_ctx', None) is not None:
                            if getattr(adapter.exec_ctx, 'config', None) is None:
                                adapter.exec_ctx.config = {}
                            adapter.exec_ctx.config["data_domain"] = domain_key
                    except Exception:
                        pass

                    # 订单表现：按平台子类型循环（Shopee + TikTok），Lazada 暂不处理
                    if str(domain_key) == "orders":
                        try:
                            from modules.components.export.base import ExportResult  # 仅用于封装汇总结果
                        except Exception:
                            ExportResult = None  # type: ignore
                        subtypes = ["shopee", "tiktok"]
                        all_ok = True
                        err_msgs: list[str] = []
                        for sub in subtypes:
                            # 为导航与导出写入首选子类型
                            try:
                                if getattr(adapter, 'exec_ctx', None) is not None:
                                    if getattr(adapter.exec_ctx, 'config', None) is None:
                                        adapter.exec_ctx.config = {}
                                    adapter.exec_ctx.config["orders_subtype"] = sub
                            except Exception:
                                pass
                            # 导航至对应平台的订单页
                            nav = adapter.navigation().run(page, tgt_map[domain_key])
                            if not getattr(nav, 'success', False):
                                try:
                                    print(f"    [WARN] 导航({sub})提示: {getattr(nav,'message','')}")
                                except Exception:
                                    pass

                            # 平台切换确认与重试日志：最多2轮（点击标签->深链），放在导航之后、日期选择之前
                            try:
                                from urllib.parse import urlparse, parse_qs
                                expect = str(sub).lower()
                                for attempt in range(1, 3):
                                    cur_url = str(getattr(page, "url", ""))
                                    cur_pf = (parse_qs(urlparse(cur_url).query).get("platform") or [None])[0]
                                    cur_pf_norm = str(cur_pf or "").lower()
                                    print(f"    [SwitchPlatform] attempt={attempt} expect={expect} current={cur_pf_norm or '-'}")
                                    if cur_pf_norm == expect:
                                        print("    [SwitchPlatform] OK: 平台已匹配")
                                        break
                                    # 1) 先尝试点击平台标签
                                    try:
                                        label = ("TikTok" if expect == "tiktok" else ("Shopee" if expect == "shopee" else str(sub)))
                                        page.get_by_text(label, exact=False).first.click(timeout=1500)
                                        page.wait_for_timeout(300)
                                        print(f"    [SwitchPlatform] 点击平台标签: {label}")
                                    except Exception:
                                        pass
                                    # 若点击无效或仍不一致，则显式深链
                                    cur_url = str(getattr(page, "url", ""))
                                    cur_pf = (parse_qs(urlparse(cur_url).query).get("platform") or [None])[0]
                                    cur_pf_norm = str(cur_pf or "").lower()
                                    if cur_pf_norm != expect:
                                        try:
                                            from modules.platforms.miaoshou.components.orders_config import OrdersSelectors as _OS
                                            osel = _OS()
                                            deep_url = f"{osel.base_url}{osel.deep_link_template.format(platform=expect)}"
                                            page.goto(deep_url, wait_until="domcontentloaded", timeout=40000)
                                            print(f"    [SwitchPlatform] 深链跳转: {deep_url}")
                                        except Exception:
                                            pass
                                    # 小等待后下一轮判断
                                    page.wait_for_timeout(300)
                            except Exception:
                                pass

                            # 日期选择（每个子类型均应用同一时间范围）
                            try:
                                adapter.date_picker().run(page, date_opt)
                            except Exception:
                                pass
                            # 执行导出
                            res = adapter.exporter().run(page)
                            if getattr(res, 'success', False):
                                # 一键/批量：收集文件路径
                                try:
                                    fp = getattr(res, 'file_path', None)
                                    files = getattr(self, "_one_click_files", None)
                                    if fp and isinstance(files, list):
                                        files.append(str(fp))
                                except Exception:
                                    pass
                            else:
                                all_ok = False
                                try:
                                    err_msgs.append(f"{sub}:{getattr(res,'message','fail')}")
                                except Exception:
                                    err_msgs.append(f"{sub}:fail")
                        # 汇总返回
                        if ExportResult:
                            return ExportResult(success=all_ok, file_path="", message=("; ".join(err_msgs) if err_msgs else "ok"))  # type: ignore
                        else:
                            class _R:  # 退化占位
                                def __init__(self, ok, msg):
                                    self.success = ok; self.message = msg
                            return _R(all_ok, "; ".join(err_msgs) if err_msgs else "ok")

                    # 非订单域：单次导航->导出
                    # 导航至目标页
                    nav = adapter.navigation().run(page, tgt_map[domain_key])
                    if not getattr(nav, 'success', False):
                        try:
                            print(f"    [WARN] 导航提示: {getattr(nav,'message','')}")
                        except Exception:
                            pass
                    # 日期选择（若组件自行处理或URL含参会自动忽略）
                    try:
                        # 妙手ERP的“商品表现”= 仓库清单，无时间维度；一律不改页面时间
                        if str(domain_key) != "products":
                            adapter.date_picker().run(page, date_opt)
                    except Exception:
                        pass
                    # 执行导出
                    return adapter.exporter().run(page)
                except Exception as _ex:
                    try:
                        print(f"    [FAIL] 域执行异常: {_ex}")
                    except Exception:
                        pass
                    return None


            with sync_playwright() as p:
                for account in accounts:
                    account_label = account.get("label") or account.get("store_name") or account.get("username") or str(account.get("account_id") or "account")
                    print(f"\n[USER] 账号: {account_label} [miaoshou]")
                    pb = PersistentBrowserManager(p)
                    ctx = pb.get_or_create_persistent_context("miaoshou", str(account_label), account)
                    page = ctx.pages[0] if getattr(ctx, "pages", None) else ctx.new_page()
                    # 构造上下文
                    exec_ctx = ExecutionContext(platform="miaoshou", account=account, config={"granularity": granularity}, logger=get_logger(__name__))
                    adapter = get_adapter("miaoshou", exec_ctx)
                    try:
                        adapter.login().run(page)
                    except Exception:
                        pass
                    # 执行每个域
                    for d in domains:
                        total += 1
                        print(f"  [DATA] 执行: {d}")
                        try:
                            res = _run_domain(page, adapter, d, date_opt)
                            if res:
                                msg = str(getattr(res, 'message', '') or '')
                                if res.success and msg.lower().startswith('skip:'):
                                    skip += 1
                                    reason = msg[5:].strip() or 'unspecified'
                                    skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
                                    print(f"    [NEXT] 跳过: {msg}")
                                    if getattr(self, "_one_click_collector", None) is not None:
                                        try:
                                            self._one_click_collector.append({
                                                "platform": "miaoshou",
                                                "account": account_label,
                                                "shop": account_label,  # 妙手无店铺粒度，使用账号作区分
                                                "domain": d,
                                                "status": "skip",
                                                "message": msg,
                                            })
                                        except Exception:
                                            pass
                                elif res.success:
                                    ok += 1; print("    [OK] 成功")
                                    # 收集成功文件路径（如有）
                                    try:
                                        fp = getattr(res, 'file_path', None)
                                        files = getattr(self, "_one_click_files", None)
                                        if fp and isinstance(files, list):
                                            files.append(str(fp))
                                    except Exception:
                                        pass
                                    if getattr(self, "_one_click_collector", None) is not None:
                                        try:
                                            self._one_click_collector.append({
                                                "platform": "miaoshou",
                                                "account": account_label,
                                                "shop": account_label,
                                                "domain": d,
                                                "status": "success",
                                                "message": "",
                                            })
                                        except Exception:
                                            pass
                                else:
                                    fail += 1; print(f"    [FAIL] 失败: {msg}")
                                    if getattr(self, "_one_click_collector", None) is not None:
                                        try:
                                            self._one_click_collector.append({
                                                "platform": "miaoshou",
                                                "account": account_label,
                                                "shop": account_label,
                                                "domain": d,
                                                "status": "fail",
                                                "message": msg,
                                            })
                                        except Exception:
                                            pass
                            else:
                                fail += 1; print("    [FAIL] 失败: no result")
                                if getattr(self, "_one_click_collector", None) is not None:
                                    try:
                                        self._one_click_collector.append({
                                            "platform": "miaoshou",
                                            "account": account_label,
                                            "shop": account_label,
                                            "domain": d,
                                            "status": "fail",
                                            "message": "no result",
                                        })
                                    except Exception:
                                        pass
                        except Exception as ex:
                            fail += 1; print(f"    [FAIL] 异常: {ex}")
                            if getattr(self, "_one_click_collector", None) is not None:
                                try:
                                    self._one_click_collector.append({
                                        "platform": "miaoshou",
                                        "account": account_label,
                                        "shop": account_label,
                                        "domain": d,
                                        "status": "error",
                                        "message": str(ex),
                                    })
                                except Exception:
                                    pass
                    # 关闭上下文（防泄露）
                    try: pb.close_context("miaoshou", str(account_label))
                    except Exception: pass
            print("\n[DATA] 批量结果汇总：")
            print(f"   总任务: {total} | [OK] 成功: {ok} | [NEXT] 跳过: {skip} | [FAIL] 失败: {fail}")
            if skip:
                print("\n[NOTE] 跳过原因统计：")
                for r, c in skip_reasons.items():
                    print(f"   • {r}: {c}")
            try:
                from modules.utils.persistent_browser_manager import PersistentBrowserManager
                PersistentBrowserManager().close_all_contexts()
                print("\n[CLEAN] 已关闭所有浏览器上下文 (global cleanup)")
            except Exception:
                pass
            if not getattr(self, "_one_click_mode", False):
                input("\n按回车键返回...")
        except Exception as e:
            from modules.core.logger import get_logger
            get_logger(__name__).error(f"妙手ERP 批量采集异常: {e}")
            print(f"[FAIL] 执行异常: {e}")
            if not getattr(self, "_one_click_mode", False):
                input("按回车键返回...")




    def _run_tiktok_platform_wide_batch(self):
        """TikTok 平台批量采集（当前实现：商品/流量/服务表现）。

        流程：
        - 选择时间范围（昨天/近7天/近30天）
        - 遍历 TikTok 平台所有启用账号
        - 每账号登录一次，按 allowed_regions 迭代区域执行：导航->（可选）日期->导出
        - 导出命名与目录结构与单次流程一致（account_label_region[__shop_id]）
        """
        try:
            print("\n[MUSIC] TikTok 批量采集")
            print("=" * 40)

            # 选择数据域（可多选），与 Shopee 一致；支持一键预设覆盖
            from modules.components.navigation.base import TargetPage
            preset_domains = getattr(self, "_one_click_domains", None)
            if preset_domains:
                # 预设域名直接映射为执行清单
                exec_domains = []
                dm = {
                    "services": ("services", "服务表现", TargetPage.SERVICE_ANALYTICS),
                    "products": ("products", "商品表现", TargetPage.PRODUCTS_PERFORMANCE),
                    "traffic": ("traffic", "流量表现", TargetPage.TRAFFIC_OVERVIEW),
                    "orders": ("orders", "订单表现(未实现)", TargetPage.ORDERS),
                    "finance": ("finance", "财务表现(未实现)", TargetPage.FINANCE),
                }
                for k in preset_domains:
                    if k in dm:
                        exec_domains.append(dm[k])
            else:
                print("\n[DATA] 选择数据域（可多选）：")
                print("1. 服务表现 (services)")
                print("2. 商品表现 (products)")
                print("3. 流量表现 (traffic)")
                print("4. 订单表现 (orders)")
                print("5. 财务表现 (finance)")
                dom_in = input("请输入选择的数字，用逗号分隔 (如: 1,2,3 或 回车=默认商品+流量+服务): ").strip()
                if not dom_in:
                    dom_sel = {"1","2","3"}
                else:
                    dom_sel = {s.strip() for s in dom_in.split(',') if s.strip() in {"1","2","3","4","5"}}
                # 已实现：products/traffic/services；其余先跳过
                exec_domains = []  # (key, name, target)
                if "2" in dom_sel:
                    exec_domains.append(("products", "商品表现", TargetPage.PRODUCTS_PERFORMANCE))
                if "3" in dom_sel:
                    exec_domains.append(("traffic", "流量表现", TargetPage.TRAFFIC_OVERVIEW))
                if "1" in dom_sel:
                    exec_domains.append(("services", "服务表现", TargetPage.SERVICE_ANALYTICS))
                if "4" in dom_sel:
                    exec_domains.append(("orders", "订单表现(未实现)", TargetPage.ORDERS))
                if "5" in dom_sel:
                    exec_domains.append(("finance", "财务表现(未实现)", TargetPage.FINANCE))

            # 选择时间范围（含自定义映射）；支持一键预设覆盖
            from modules.components.date_picker.base import DateOption
            from modules.services.time_policy import RollingDaysPolicy, CustomRangePolicy
            from datetime import datetime, timedelta
            preset = getattr(self, "_one_click_preset", None)
            if isinstance(preset, dict) and preset.get("start_date") and preset.get("end_date"):
                try:
                    sd = datetime.strptime(str(preset["start_date"]), "%Y-%m-%d").date()
                    ed = datetime.strptime(str(preset["end_date"]), "%Y-%m-%d").date()
                    days = (ed - sd).days + 1
                    if days <= 1:
                        date_opt, granularity = DateOption.YESTERDAY, "daily"
                        time_policy = CustomRangePolicy(ed, ed)
                    elif days <= 7:
                        date_opt, granularity = DateOption.LAST_7_DAYS, "weekly"
                        time_policy = RollingDaysPolicy(7)
                    else:
                        # TikTok 最大28天，超出按28天处理
                        date_opt, granularity = DateOption.LAST_28_DAYS, "monthly"
                        time_policy = RollingDaysPolicy(28)
                except Exception:
                    date_opt = None  # 回退到交互式选择
            if not locals().get("date_opt"):
                print("\n[DATE] 选择时间范围:")
                print("  1. 最近7天（默认）    2. 最近28天    3. 昨天")
                tch = input("请选择 (1-3): ").strip() or "1"
                if tch == "2":
                    date_opt, granularity, days = DateOption.LAST_28_DAYS, "monthly", 28
                    time_policy = RollingDaysPolicy(28)
                elif tch == "3":
                    date_opt, granularity, days = DateOption.YESTERDAY, "daily", 1
                    _end = (datetime.now() - timedelta(days=1)).date()
                    time_policy = CustomRangePolicy(_end, _end)
                else:
                    date_opt, granularity, days = DateOption.LAST_7_DAYS, "weekly", 7
                    time_policy = RollingDaysPolicy(7)
                time_policy = RollingDaysPolicy(7)

            # 遍历 TikTok 启用账号
            from modules.utils.account_manager import AccountManager
            am = AccountManager()
            accounts = [
                a for a in am.load_accounts().get('accounts', [])
                if a.get('platform', '').lower() == 'tiktok' and a.get('enabled', True) and a.get('login_url')
            ]
            if not accounts:
                print("[FAIL] 未找到启用的 TikTok 账号")
                if not getattr(self, "_one_click_mode", False):
                    input("按回车键返回...")
                return

            from playwright.sync_api import sync_playwright
            from modules.utils.persistent_browser_manager import PersistentBrowserManager
            from modules.components.base import ExecutionContext
            from modules.services.platform_adapter import get_adapter
            from modules.components.navigation.base import TargetPage
            from modules.core.logger import get_logger

            total, ok, fail = 0, 0, 0
            skip = 0
            skip_reasons = {}

            with sync_playwright() as p:
                for account in accounts:
                    account_label = (
                        account.get("label")
                        or account.get("store_name")
                        or account.get("username")
                        or str(account.get("account_id") or "account")
                    )
                    print(f"\n[USER] 账号: {account_label}")

                    pb = PersistentBrowserManager(p)
                    ctx = pb.get_or_create_persistent_context("tiktok", str(account_label), account)
                    page = ctx.pages[0] if getattr(ctx, "pages", None) else ctx.new_page()

                    try:
                        # 构造执行上下文
                        exec_ctx = ExecutionContext(
                            platform="tiktok",
                            account=account,
                            config={
                                "granularity": granularity,
                            },
                            logger=get_logger(__name__),
                        )
                        # 将时间选择注入上下文（用于导航深链与文件命名）
                        from datetime import date, timedelta
                        _end = date.today()
                        _start = _end - timedelta(days=days)
                        # 自适应一键模式与超时配置
                        _one_click = bool(getattr(self, "_one_click_mode", False))
                        _gran = (granularity or "").lower()
                        _export_timeout_ms = 240000 if (_one_click or days >= 28 or _gran == "monthly") else 90000
                        exec_ctx.config.update({
                            "days": days,
                            "start_date": _start.strftime("%Y-%m-%d"),
                            "end_date": _end.strftime("%Y-%m-%d"),
                            # 与单次采集完全一致：所有范围均使用深链 timeRange（yesterday=last1days），随后若URL含时间直接跳过 DatePicker
                            "nav_with_timerange": True,
                            # 一键模式标记与导出等待超时（TikTok 导出组件使用）
                            "one_click": _one_click,
                            "export_timeout_ms": _export_timeout_ms,
                        })
                        adapter = get_adapter("tiktok", exec_ctx)

                        # 登录
                        try:
                            adapter.login().run(page)
                        except Exception:
                            pass
                        # 清理可能出现的空白/多余标签页，仅保留最后一个活动页
                        try:
                            pages = page.context.pages
                            if len(pages) > 1:
                                primary = pages[-1]
                                for _p in pages[:-1]:
                                    try:
                                        _p.close()
                                    except Exception:
                                        pass
                                page = primary
                        except Exception:
                            pass

                        # 区域列表：优先账号配置，其次默认
                        regions = account.get("allowed_regions") or ["MY", "PH", "SG"]
                        for region in regions:
                            # 逐数据域执行
                            for dom_key, dom_name, target in exec_domains:
                                # 暂未实现的数据域直接跳过（已实现：products/traffic/services）
                                if dom_key not in {"products", "traffic", "services"}:
                                    print(f"  [NEXT] 区域: {region} · {dom_name} 暂未实现，跳过")
                                    continue
                                total += 1
                                print(f"  [SHOP] 区域: {region} · {dom_name} -> 导航与导出")
                                try:
                                    # 写入区域到上下文
                                    exec_ctx.config["shop_region"] = region
                                    try:
                                        account_label_norm = account_label
                                    except Exception:
                                        account_label_norm = str(account_label)
                                    # 流量/服务 表现禁止在导航深链中携带时间参数，会导致导出按钮不出现
                                    exec_ctx.config["nav_with_timerange"] = (dom_key not in {"traffic", "services"})

                                    exec_ctx.config["shop_name"] = f"{account_label_norm}_{region.lower()}"
                                    exec_ctx.config["data_domain"] = dom_key

                                    # 导航
                                    nav = adapter.navigation()
                                    nav_res = nav.run(page, target)
                                    if not getattr(nav_res, 'success', False):
                                        print(f"    [WARN] 导航失败: {getattr(nav_res, 'message', 'unknown')}，尝试继续")

                                    # 日期：如 URL 已含 timeRange/shortcut 则跳过
                                    try:
                                        cur_url = str(page.url)
                                    except Exception:
                                        cur_url = ""
                                    if ("timeRange=" in cur_url) or ("shortcut=" in cur_url):
                                        print("    [CAL] 当前URL已包含时间参数，跳过日期选择组件")
                                    else:
                                        from modules.services.time_policy import apply_time_policy_tiktok
                                        ok, msg = apply_time_policy_tiktok(page, adapter, time_policy)
                                        if not ok:
                                            print(f"    [FAIL] 时间策略失败: {msg}")
                                            raise RuntimeError(msg)
                                        page.wait_for_timeout(600)

                                    # 导出
                                    res = adapter.exporter().run(page)
                                    if res:
                                        msg = getattr(res, 'message', '') or ''
                                        if getattr(res, 'success', False) and isinstance(msg, str) and msg.lower().startswith('skip:'):
                                            skip += 1
                                            reason = msg[5:].strip() or 'unspecified'
                                            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
                                            print(f"    [NEXT] 跳过: {msg}")
                                            if getattr(self, "_one_click_collector", None) is not None:
                                                try:
                                                    self._one_click_collector.append({
                                                        "platform": "tiktok",
                                                        "account": account_label,
                                                        "shop": f"{account_label}_{region.lower()}",
                                                        "domain": dom_key,
                                                        "status": "skip",
                                                        "message": msg,
                                                    })
                                                except Exception:
                                                    pass
                                        elif getattr(res, 'success', False):
                                            ok += 1  # 出口组件已打印成功信息，这里不重复输出
                                            if getattr(self, "_one_click_collector", None) is not None:
                                                try:
                                                    self._one_click_collector.append({
                                                        "platform": "tiktok",
                                                        "account": account_label,
                                                        "shop": f"{account_label}_{region.lower()}",
                                                        "domain": dom_key,
                                                        "status": "success",
                                                        "message": "",
                                                    })
                                                except Exception:
                                                    pass
                                        else:
                                            print(f"    [FAIL] 导出失败: {msg or '导出失败'}")
                                            fail += 1
                                            if getattr(self, "_one_click_collector", None) is not None:
                                                try:
                                                    self._one_click_collector.append({
                                                        "platform": "tiktok",
                                                        "account": account_label,
                                                        "shop": f"{account_label}_{region.lower()}",
                                                        "domain": dom_key,
                                                        "status": "fail",
                                                        "message": msg,
                                                    })
                                                except Exception:
                                                    pass
                                    else:
                                        print("    [FAIL] 导出失败: 导出结果为空")
                                        fail += 1
                                        if getattr(self, "_one_click_collector", None) is not None:
                                            try:
                                                self._one_click_collector.append({
                                                    "platform": "tiktok",
                                                    "account": account_label,
                                                    "shop": f"{account_label}_{region.lower()}",
                                                    "domain": dom_key,
                                                    "status": "fail",
                                                    "message": "empty result",
                                                })
                                            except Exception:
                                                pass
                                except Exception as ex:
                                    print(f"    [FAIL] 区域 {region} · {dom_name} 处理异常: {ex}")
                                    fail += 1
                                    if getattr(self, "_one_click_collector", None) is not None:
                                        try:
                                            self._one_click_collector.append({
                                                "platform": "tiktok",
                                                "account": account_label,
                                                "shop": f"{account_label}_{region.lower()}",
                                                "domain": dom_key,
                                                "status": "error",
                                                "message": str(ex),
                                            })
                                        except Exception:
                                            pass
                                finally:
                                    # 轻微冷却，避免频繁切区域/页面
                                    try:
                                        page.wait_for_timeout(500)
                                    except Exception:
                                        pass
                    finally:
                        try:
                            pb.save_context_state(ctx, "tiktok", str(account_label))
                        except Exception:
                            pass
                        try:
                            pb.close_context("tiktok", str(account_label))
                        except Exception:
                            pass

            # 汇总
            print("\n[DATA] 批量结果汇总：")
            print(f"   总任务: {total} | [OK] 成功: {ok} | [NEXT] 跳过: {skip} | [FAIL] 失败: {fail}")
            if skip:
                print("\n[NOTE] 跳过原因统计：")
                for r, c in skip_reasons.items():
                    print(f"   • {r}: {c}")
            try:
                PersistentBrowserManager().close_all_contexts()
                print("\n[CLEAN] 已关闭所有浏览器上下文 (global cleanup)")
            except Exception:
                pass
            if not getattr(self, "_one_click_mode", False):
                input("\n按回车键返回...")
        except Exception as e:
            from modules.core.logger import get_logger
            get_logger(__name__).error(f"TikTok 批量采集异常: {e}")
            print(f"[FAIL] 执行异常: {e}")
            if not getattr(self, "_one_click_mode", False):
                input("按回车键返回...")

    def _manage_stable_scripts_menu(self, dtype_key: str = "products"):
        """管理稳定版脚本（查看/设置/取消）"""
        from modules.utils.account_manager import AccountManager
        from modules.utils.recording_registry import (
            ensure_index, RecordingType, get_latest_login, get_latest_collection,
            get_stable_collection, mark_stable, clear_stable,
        )
        platform = "shopee"
        ensure_index(platform)

        sel = self._select_shopee_account_unified()
        if not sel:
            return
        account, account_label = sel

        while True:
            print("\n[SHIELD] 稳定版脚本管理")
            print("=" * 30)
            print(f"  1. 查看稳定版（{dtype_key}）")
            print(f"  2. 设置当前最新为稳定版（{dtype_key}）")
            print(f"  3. 取消稳定版（{dtype_key}）")
            print("  4. [LOCK] 管理登录脚本（查看/设置/取消）")
            print("  0. 返回上一级")
            ch = input("请选择 (0-4): ").strip()
            if ch == '0':
                break
            elif ch == '1':
                rtype = RecordingType(dtype_key)
                path = get_stable_collection(platform, account_label, rtype)
                print(f"当前稳定版: {path or '无'}")
                input("按回车键继续...")
            elif ch == '2':
                rtype = RecordingType(dtype_key)
                latest = get_latest_collection(platform, account_label, rtype)
                if not latest:
                    print("[FAIL] 未找到最新脚本"); input("按回车键继续..."); continue
                mark_stable(platform, account_label, 'collection', rtype, latest)
                print("[OK] 已设置为稳定版"); input("按回车键继续...")
            elif ch == '3':
                rtype = RecordingType(dtype_key)
                clear_stable(platform, account_label, 'collection', rtype)
                print("[OK] 已取消稳定版"); input("按回车键继续...")
            elif ch == '4':
                self._manage_login_scripts(platform, account_label)
            else:
                print("[FAIL] 无效选择"); input("按回车键继续...")


    def _run_product_performance_recorded(self):
        """运行‘Shopee 商品表现数据导出’录制脚本（优先选择 complete_products）"""
        from modules.utils.account_manager import AccountManager
        from modules.utils.recording_registry import ensure_index, plan_flow, RecordingType
        import re

        platform = "shopee"
        ensure_index(platform)

        sel = self._select_shopee_account_unified()
        if not sel:
            return
        account, account_label = sel

        # 先用 registry 规划一次
        rt = RecordingType("products")
        login_path, collect_path = plan_flow(platform, account_label, rt)

        # 优先使用 complete_products 脚本
        root = Path("temp/recordings") / platform
        latest_complete = None
        ts_re = re.compile(r"(\d{8}_\d{6})")
        pat_complete = re.compile(rf"^{re.escape(account_label)}_complete_products_\d{{8}}_\d{{6}}\.py$")
        if root.exists():
            for f in root.glob("*.py"):
                name = f.name
                if pat_complete.match(name):
                    m = ts_re.search(name)
                    ts = m.group(1) if m else ""
                    if latest_complete is None or ts > latest_complete[1]:
                        latest_complete = (str(f.as_posix()), ts)
        if latest_complete:
            collect_path = latest_complete[0]

        if not collect_path:
            print("[FAIL] 未找到‘商品表现数据导出’录制脚本，请先在‘数据采集录制 -> 商品数据采集’中录制。")
            input("按回车键返回..."); return

        print(f"\n[FILE] 将执行的脚本：\n  登录: {login_path or '（可选，未找到）'}\n  采集: {collect_path}")
        if input("\n确认开始执行? (y/n): ").strip().lower() not in ['y','yes','是']:
            return
        if login_path:
            self._exec_python_script(login_path)
        self._exec_python_script(collect_path)
        input("\n[OK] 执行完成，按回车键返回...")


    def _run_recorded_scripts_by_type(self, dtype: str):
        """按数据类型运行录制脚本（五类：orders/products/analytics/finance/services），支持多平台。"""
        from modules.utils.recording_registry import ensure_index, plan_flow, RecordingType

        # 选择平台（默认 Shopee，可切换 TikTok）
        print("\n[WEB] 选择平台：")
        print("  1. Shopee    2. TikTok    0. 返回")
        pch = input("请选择 (1-2/0): ").strip() or "1"
        if pch == "0":
            return
        platform = "shopee" if pch == "1" else "tiktok"

        ensure_index(platform)

        # 选择账号（通用入口）
        sel = self._select_account_unified(platform)
        if not sel:
            return
        account, account_label = sel

        # 获取脚本路径（旧版回放策略：先执行登录脚本，再执行采集脚本）
        rt = RecordingType(dtype)
        login_path, collect_path = plan_flow(platform, account_label, rt)
        if not collect_path:
            print("[FAIL] 未找到对应的数据采集录制脚本，请先在‘数据采集录制’中录制。")
            input("按回车键返回..."); return

        print(f"\n[FILE] 将执行的脚本：\n  平台: {platform}\n  登录: {login_path or '（可选，未找到）'}\n  采集: {collect_path}")
        if input("\n确认开始执行? (y/n): ").strip().lower() not in ['y','yes','是']:
            return

        # 旧版行为：独立执行脚本模块，不干预脚本内部浏览器/会话逻辑
        if login_path:
            self._exec_python_script(login_path)
        self._exec_python_script(collect_path)
        input("\n[OK] 执行完成，按回车键返回...")

    def _exec_python_script(self, path: str) -> None:
        """以独立模块方式加载并执行录制脚本的 main() 或 run()"""
        try:
            from importlib.util import spec_from_file_location, module_from_spec

            spec = spec_from_file_location("recording_script", path)
            mod = module_from_spec(spec)
            assert spec and spec.loader
            spec.loader.exec_module(mod)  # type: ignore
            if hasattr(mod, 'main'):
                print(f"[ACTION] 执行 main() 函数: {path}")
                mod.main()
            elif hasattr(mod, 'run'):
                print(f"[ACTION] 执行 run() 函数: {path}")
                mod.run()
            elif hasattr(mod, 'test_recording'):
                print(f"[ACTION] 执行 test_recording() 函数: {path}")
                mod.test_recording()
            else:
                print(f"[WARN] 脚本未定义 main()/run()/test_recording()，已完成加载: {path}")
        except Exception as e:
            logger.error(f"执行脚本失败 {path}: {e}")
            print(f"[FAIL] 执行脚本失败: {e}")

    def _check_session_health(self, account_label: str, platform: str) -> str:
        """检查会话健康状态

        Returns:
            str: "healthy" | "unhealthy" | "unknown"
        """
        try:
            # 检查持久化会话是否存在且有效
            from modules.utils.persistent_browser_manager import PersistentBrowserManager
            from modules.core.config import get_config_manager

            config = get_config_manager().get_config('simple_config')
            recording_config = config.get('recording', {})

            # 如果配置强制登录，直接返回不健康
            if recording_config.get('force_login_before_collection', False):
                return "unhealthy"

            # 检查会话文件是否存在
            session_manager = PersistentBrowserManager()
            session_key = f"{platform.lower()}/{account_label}"

            # 简单检查：会话目录是否存在且不为空
            session_dir = Path("data/sessions") / session_key
            if session_dir.exists() and any(session_dir.iterdir()):
                return "healthy"
            else:
                return "unhealthy"

        except Exception as e:
            logger.debug(f"会话健康检查失败: {e}")
            return "unknown"

    def _quick_record_login_script(self, account_label: str, platform: str):
        """快速录制登录脚本"""
        try:
            print("\n[START] 启动快速登录录制...")
            print("[TIP] 这将打开录制向导，选择'登录流程录制'即可")

            from modules.utils.enhanced_recording_wizard import EnhancedRecordingWizard
            wizard = EnhancedRecordingWizard()

            # 提示用户在向导中选择对应账号和登录录制
            print(f"[LIST] 请在向导中选择:")
            print(f"   平台: {platform}")
            print(f"   账号: {account_label}")
            print(f"   录制类型: [LOCK] 登录流程录制")

            wizard.run_wizard()

        except Exception as e:
            logger.error(f"快速录制登录脚本失败: {e}")
            print(f"[FAIL] 快速录制失败: {e}")
            print("[TIP] 请手动进入'数据采集录制'录制登录流程")

    def _exec_recording_with_persistent_page(self, path: str, account: Dict[str, Any], platform: str = "shopee") -> bool:
        """在持久化上下文中执行录制脚本的 run(page)（优先）。

        - 优先查找脚本中的 run(page) 并在同一持久化上下文中回放，避免脚本自行 new browser 导致会话割裂
        - 如无 run(page)，返回 False 让上层回退到 _exec_python_script()
        - 非 Shopee 平台走通用的 PersistentBrowserManager 路径
        """
        try:
            from importlib.util import spec_from_file_location, module_from_spec
            spec = spec_from_file_location("recording_script", path)
            mod = module_from_spec(spec)
            assert spec and spec.loader
            spec.loader.exec_module(mod)  # type: ignore

            if not hasattr(mod, "run"):
                # 无 run(page) 接口，交由上层回退
                return False

            from playwright.sync_api import sync_playwright
            if platform.lower() == "shopee":
                # Shopee 走现有导出器（集成更完善）
                from modules.services.shopee_playwright_exporter import ShopeePlaywrightExporter
                with sync_playwright() as p:
                    exp = ShopeePlaywrightExporter(p)
                    ctx, page, pf, account_id = exp._open_account_page(account)
                    try:
                        print(f"[ACTION] 在持久化会话中回放: {Path(path).name}")
                        mod.run(page)
                    finally:
                        try:
                            exp.pb.save_context_state(ctx, pf, account_id)
                        except Exception:
                            pass
                        try:
                            exp.pb.close_context(pf, str(account_id))
                        except Exception:
                            pass
                return True
            else:
                # 通用路径（例如 TikTok）：直接使用持久化上下文并打开 login_url
                from modules.utils.persistent_browser_manager import PersistentBrowserManager
                with sync_playwright() as p:
                    pb = PersistentBrowserManager(p)
                    account_id = account.get("store_name") or account.get("name") or account.get("username") or "account"
                    ctx = pb.get_or_create_persistent_context(platform, str(account_id), account)
                    page = ctx.new_page()
                    try:
                        login_url = account.get("login_url") or account.get("url")
                        if login_url:
                            try:
                                page.goto(login_url, wait_until="domcontentloaded", timeout=45000)
                            except Exception:
                                page.goto(login_url, wait_until="load", timeout=60000)
                        # 统一登录策略：优先调用“[BOT] 自动登录流程修正”，失败则回退 LoginService
                        try:
                            flags = (account.get('login_flags') or {}) if isinstance(account, dict) else {}
                        except Exception:
                            flags = {}
                        use_enhanced = bool(flags.get('use_enhanced_login', True))
                        try:
                            if use_enhanced:
                                from modules.utils.enhanced_recording_wizard import EnhancedRecordingWizard
                                print("\n[BOT] 使用增强版自动登录...")
                                EnhancedRecordingWizard()._perform_enhanced_auto_login(page, account, platform)
                            else:
                                from modules.services.platform_login_service import LoginService
                                LoginService().ensure_logged_in(platform, page, account)
                        except Exception as _le:
                            try:
                                from modules.services.platform_login_service import LoginService
                                print(f"[WARN] 增强登录失败，回退 LoginService: {_le}")
                                LoginService().ensure_logged_in(platform, page, account)
                            except Exception:
                                pass
                        print(f"[ACTION] 在持久化会话中回放: {Path(path).name}")
                        mod.run(page)
                    finally:
                        try:
                            pb.save_context_state(ctx, platform, str(account_id))
                        except Exception:
                            pass
                        try:
                            pb.close_context(platform, str(account_id))
                        except Exception:
                            pass
                return True
        except Exception as e:
            logger.error(f"持久化上下文回放失败 {path}: {e}")
            return False

    def _manage_login_scripts(self, platform: str, account_label: str):
        """管理登录脚本（查看/设置/取消）"""
        from modules.utils.recording_registry import (
            get_latest_login, mark_stable, clear_stable, reindex
        )

        while True:
            print("\n[LOCK] 登录脚本管理")
            print("=" * 30)
            print("  1. 查看当前稳定登录脚本")
            print("  2. 设置最新为稳定登录脚本")
            print("  3. 取消稳定登录脚本")
            print("  4. 快速录制新登录脚本")
            print("  0. 返回上一级")

            ch = input("请选择 (0-4): ").strip()
            if ch == '0':
                break
            elif ch == '1':
                # 查看稳定登录脚本
                from modules.utils.recording_registry import _load_registry
                registry = _load_registry()
                pnode = registry.get("platforms", {}).get(platform.lower(), {})
                anode = pnode.get("accounts", {}).get(account_label, {})
                login_node = anode.get("login", {})
                stable_path = login_node.get("stable", {}).get("path") if login_node.get("stable") else None
                latest_path = login_node.get("latest", {}).get("path") if login_node.get("latest") else None

                print(f"\n[LIST] 登录脚本状态:")
                print(f"   稳定版: {stable_path or '无'}")
                print(f"   最新版: {latest_path or '无'}")
                input("按回车键继续...")

            elif ch == '2':
                # 设置最新为稳定版
                latest = get_latest_login(platform, account_label)
                if not latest:
                    print("[FAIL] 未找到最新登录脚本")
                    print("[TIP] 请先录制登录脚本")
                    input("按回车键继续...")
                    continue

                mark_stable(platform, account_label, 'login', None, latest)
                print("[OK] 已设置为稳定登录脚本")
                input("按回车键继续...")

            elif ch == '3':
                # 取消稳定版
                clear_stable(platform, account_label, 'login', None)
                print("[OK] 已取消稳定登录脚本")
                input("按回车键继续...")

            elif ch == '4':
                # 快速录制新登录脚本
                self._quick_record_login_script(account_label, platform)
                break  # 录制完成后返回上级菜单

            else:
                print("[FAIL] 无效选择")
                input("按回车键继续...")

    def _run_batch_collection(self):
        """批量数据采集"""
        while True:
            print("\n[RETRY] 批量数据采集")
            print("=" * 40)
            print("1. [TOOLKIT] Shopee 批量采集")
            print("2. [MUSIC] TikTok 批量采集")
            print("3. [BRAIN] 妙手ERP 批量采集")
            print("4. [STORE] Amazon 批量采集（占位）")
            print("5. [COMPASS] 一键所有平台批量采集")
            print("0. [BACK] 返回上级菜单")
            choice = input("\n请选择 (0-5/0): ").strip()
            if choice == "0":
                break
            elif choice == "1":
                self._run_multi_domain_platform_wide_batch()
            elif choice == "2":
                self._run_tiktok_platform_wide_batch()
            elif choice == "3":
                self._run_miaoshou_platform_wide_batch()
            elif choice == "4":
                self._run_amazon_batch_placeholder()
            elif choice == "5":
                self._run_all_platforms_one_click_batch()
            else:
                print("[FAIL] 无效选择")
                input("按回车键继续...")


    def _run_generic_batch_flow(self):
        """
        通用批量流程（所有平台）- 骨架：
        选择或全平台 -> 选择或全数据类型 -> 选择或全账号，生成任务计划。
        当前为规划/预演模式，不执行实际采集，确保流程与统一规则正确。
        """
        try:
            print("\n[COMPASS] 一键所有平台批量采集")
            print("=" * 40)
            # 1) 选择平台或全平台
            print("\n[WEB] 选择平台：")
            print("  1. 全平台 (默认)")
            print("  2. shopee    3. amazon    4. tiktok    5. miaoshou")
            pch = input("请选择 (1-5): ").strip() or "1"
            all_map = {
                "2": ["shopee"], "3": ["amazon"], "4": ["tiktok"], "5": ["miaoshou"],
            }
            if pch == "1":
                platforms = ["shopee", "amazon", "tiktok", "miaoshou"]
            else:
                platforms = all_map.get(pch, ["shopee", "amazon", "tiktok", "miaoshou"])

            # 2) 选择数据类型（域）
            print("\n[PUZZLE] 选择数据类型：")
            print("  1. 全部    2. products  3. analytics  4. services  5. orders  6. finance")
            dch = input("请选择 (1-6，回车=已打通三类): ").strip()
            ready_domains = ["products", "analytics", "services"]
            all_domains = ["products", "analytics", "services", "orders", "finance"]
            if not dch:
                domains = ready_domains
            elif dch == "1":
                domains = all_domains
            else:
                idx_map = {"2": "products", "3": "analytics", "4": "services", "5": "orders", "6": "finance"}
                domains = [idx_map.get(dch)] if idx_map.get(dch) else ready_domains

            # 3) 选择账号范围
            print("\n[USERS] 账号范围：")
            print("  a. 全账号 (默认)    s. 选择单个账号")
            sch = (input("请选择 (a/s): ").strip() or "a").lower()

            from modules.utils.account_manager import AccountManager
            am = AccountManager()

            planned = []
            if sch == "a":
                all_acc = am.load_accounts().get('accounts', [])
                for pf in platforms:
                    pf_acc = [a for a in all_acc if (a.get('platform','') or '').lower() == pf and a.get('enabled', True) and a.get('login_url')]
                    for acc in pf_acc:
                        label = acc.get('store_name') or acc.get('username') or acc.get('label') or str(acc.get('account_id') or '')
                        for d in domains:
                            planned.append((pf, label, d))
            else:
                for pf in platforms:
                    sel = self._select_account_unified(pf)
                    if not sel:
                        continue
                    acc, label = sel
                    for d in domains:
                        planned.append((pf, label, d))

            # 4) 选择时间范围（与平台批量一致）
            from datetime import datetime, timedelta
            print("\n[DATE] 选择时间范围:")
            print("1. 昨天（默认）  2. 过去7天  3. 过去30天  4. 过去28天")
            w = input("请选择 (1-4): ").strip() or "1"
            if w == '1':
                end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                start_date = end_date
                granularity = "day"
            elif w == '2':
                end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
                granularity = "weekly"
            elif w == '3':
                end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                granularity = "monthly"
            elif w == '4':
                end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=28)).strftime("%Y-%m-%d")
                granularity = "range"
            else:
                end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                start_date = end_date
                granularity = "day"

            # 5) 构建账号清单（依选择模式）
            from modules.utils.account_manager import AccountManager
            am = AccountManager()
            selected_accounts_by_pf = {}
            if sch == "a":
                all_acc = am.load_accounts().get('accounts', [])
                for pf in platforms:
                    pf_acc = [a for a in all_acc if (a.get('platform','') or '').lower() == pf and a.get('enabled', True) and a.get('login_url')]
                    if pf_acc:
                        selected_accounts_by_pf[pf] = pf_acc
            else:
                for pf in platforms:
                    sel = self._select_account_unified(pf)
                    if sel:
                        selected_accounts_by_pf[pf] = [sel[0]]

            if not selected_accounts_by_pf:
                print("[FAIL] 未选择到任何有效账号（需启用且配置 login_url）")
                input("按回车键返回...")
                return

            # 6) 确认并执行
            print(f"\n[OK] 即将执行 批量采集 | 平台: {', '.join(platforms)} | 数据域: {', '.join(domains)}")
            print(f"   时间: {start_date} ~ {end_date} | 粒度: {granularity}")
            if input("确认开始? (y/n): ").strip().lower() not in ['y','yes','是']:
                return

            # 规范化域名，analytics -> traffic（与组件注册保持一致）
            norm_domains = ["traffic" if d == "analytics" else d for d in domains]

            total_tasks = 0; ok_count = 0; fail_count = 0
            results_by_domain = {d: {"ok": 0, "fail": 0} for d in norm_domains}

            # 限流与抖动配置（云端可调）
            from modules.core.config import get_config_value as _get
            jitter_range = _get('data_collection', 'execution.jitter_ms_range', [300, 1200])
            account_cooldown_ms = _get('data_collection', 'execution.account_cooldown_ms', 1500)
            shop_cooldown_ms = _get('data_collection', 'execution.shop_cooldown_ms', 800)
            domain_cooldown_ms = _get('data_collection', 'execution.domain_cooldown_ms', 400)
            max_concurrent_accounts = _get('data_collection', 'execution.max_concurrent_accounts', 1)

            import time, random
            def _delay(base_ms: int):
                try:
                    j = random.randint(int(jitter_range[0]), int(jitter_range[1])) if isinstance(jitter_range, (list, tuple)) and len(jitter_range) == 2 else 0
                except Exception:
                    j = 0
                time.sleep(max(0, (int(base_ms) + int(j))) / 1000.0)

            # 仅 Shopee 现已接通；其他平台占位提示
            from playwright.sync_api import sync_playwright
            from modules.services.shopee_playwright_exporter import ShopeePlaywrightExporter
            try:
                with sync_playwright() as p:
                    # Shopee 执行
                    if 'shopee' in selected_accounts_by_pf:
                        for account in selected_accounts_by_pf['shopee']:
                            account_label = account.get('store_name') or account.get('username') or str(account.get('account_id'))
                            print(f"\n[USER] 账号: {account_label} [shopee]")
                            exp = ShopeePlaywrightExporter(p)
                            shops = exp.list_shops(account)
                            if not shops:
                                print("  [WARN] 未拉取到店铺，跳过该账号")
                                continue
                            # Shopee 中仅执行已打通三类（products/traffic/services）
                            ready_norm = ["products", "traffic", "services"]
                            exec_norm = [d for d in norm_domains if d in ready_norm]
                            skipped_norm = [d for d in norm_domains if d not in ready_norm]
                            if skipped_norm:
                                print(f"  [NEXT] Shopee 未实现/占位，已跳过: {', '.join(skipped_norm)}")
                            for shop in shops:
                                print(f"  [SHOP] 店铺: {getattr(shop,'name','shop')} (id={getattr(shop,'id','')}, region={getattr(shop,'region','')})")
                                for d in exec_norm:
                                    _delay(domain_cooldown_ms)
                                    total_tasks += 1
                                    print(f"    [DATA] 执行: {d}")
                                    try:
                                        success = self._execute_single_domain_export(
                                            exp, account, shop, 'shopee', d,
                                            start_date, end_date, granularity, account_label
                                        )
                                        if success:
                                            ok_count += 1; results_by_domain[d]["ok"] += 1
                                            print("    [OK] 成功")
                                        else:
                                            fail_count += 1; results_by_domain[d]["fail"] += 1
                                            print("    [FAIL] 失败")
                                    except Exception as e:
                                        fail_count += 1; results_by_domain[d]["fail"] += 1
                                        print(f"    [FAIL] 异常: {e}")
                                _delay(shop_cooldown_ms)
                            # 账户级：统一通过PB关闭持久化上下文，避免后续复用到已关闭的上下文
                            try:
                                acct_key = str(account.get('store_name') or account.get('username') or account.get('account_id') or '')
                                if getattr(exp, 'pb', None) and acct_key:
                                    exp.pb.close_context('shopee', acct_key)
                                if getattr(exp, 'pb', None):
                                    exp.pb.close_all_contexts()
                                try:
                                    import time
                                    for _ in range(20):
                                        any_open = False
                                        try:
                                            if getattr(exp.pb, 'active_contexts', None) and len(exp.pb.active_contexts) > 0:
                                                any_open = True
                                            if getattr(exp.pb, '_fallback_browsers', None) and len(exp.pb._fallback_browsers) > 0:
                                                any_open = True
                                        except Exception:
                                            pass
                                        if not any_open:
                                            break
                                        time.sleep(0.25)
                                except Exception:
                                    pass

                            except Exception:
                                pass
                            _delay(account_cooldown_ms)

                    # 其他平台：使用最小骨架“真实执行”——为每个账号/域生成占位导出文件与 manifest
                    from modules.core.config import get_config_value as _get
                    from modules.utils.path_sanitizer import build_output_path, build_filename
                    from datetime import datetime as _dt
                    for pf in platforms:
                        if pf == 'shopee':
                            continue
                        if pf not in selected_accounts_by_pf:
                            continue
                        for account in selected_accounts_by_pf[pf]:
                            account_label = account.get('store_name') or account.get('username') or str(account.get('account_id'))
                            shop_name = account.get('display_shop_name') or account.get('store_name') or account_label
                            shop_id = account.get('shop_id') or account.get('cnsc_shop_id') or account.get('account_id')
                            for d in norm_domains:
                                total_tasks += 1
                                try:
                                    include_shop_id = _get('data_collection', 'path_options.include_shop_id', True)
                                    gran = granularity if granularity else 'manual'
                                    out_root = build_output_path(
                                        root='temp/outputs', platform=pf, account_label=account_label,
                                        shop_name=shop_name, data_type=d, granularity=gran, shop_id=shop_id,
                                        include_shop_id=include_shop_id,
                                    )
                                    out_root.mkdir(parents=True, exist_ok=True)
                                    ts = _dt.now().strftime('%Y%m%d_%H%M%S')
                                    filename = build_filename(
                                        ts=ts, account_label=account_label, shop_name=shop_name,
                                        data_type=d, granularity=gran, start_date=start_date,
                                        end_date=end_date, suffix='.placeholder'
                                    )
                                    target = out_root / filename
                                    # 写入占位文件与 manifest
                                    try:
                                        target.write_text('placeholder', encoding='utf-8')
                                    except Exception:
                                        pass
                                    try:
                                        import json
                                        manifest = {
                                            'platform': pf,
                                            'account_label': account_label,
                                            'shop_name': shop_name,
                                            'shop_id': shop_id,
                                            'data_type': d,
                                            'granularity': gran,
                                            'start_date': start_date,
                                            'end_date': end_date,
                                            'exported_at': _dt.now().isoformat(),
                                            'file_path': str(target),
                                            'note': 'skeleton output (no-op exporter)'
                                        }
                                        (out_root / (target.name + '.json')).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
                                    except Exception:
                                        pass
                                    ok_count += 1; results_by_domain[d]['ok'] += 1
                                    print(f"    [OK] {account_label} [{pf}] -> {d} 占位输出: {target}")
                                except Exception as _ex:
                                    fail_count += 1; results_by_domain[d]['fail'] += 1
                                    print(f"    [FAIL] {account_label} [{pf}] -> {d} 失败: {_ex}")

                # 结果汇总
                print("\n[DATA] 批量结果汇总：")
                print(f"   总任务: {total_tasks} | [OK] 成功: {ok_count} | [FAIL] 失败: {fail_count}")
                print("\n[CHART] 按数据域统计：")
                for d in norm_domains:
                    stats = results_by_domain[d]
                    print(f"   {d}: [OK] {stats['ok']} | [FAIL] {stats['fail']}")
                # 全局兜底关闭所有浏览器上下文，避免账号采集结束后残留
                try:
                    from modules.utils.persistent_browser_manager import PersistentBrowserManager
                    PersistentBrowserManager().close_all_contexts()
                    print("\n[CLEAN] 已关闭所有浏览器上下文 (global cleanup)")
                except Exception:
                    pass

                input("\n按回车键返回...")
            except Exception as _e:
                print(f"[FAIL] 通用批量执行异常: {_e}")
                input("按回车键返回...")
        except Exception as e:
            from modules.core.logger import get_logger
            get_logger(__name__).error(f"通用批量流程异常: {e}")

    def _run_amazon_batch_placeholder(self):
        """Amazon 批量采集占位入口（使用通用批量流程或等待适配器接入）。"""
        print("\n[i] Amazon 批量采集暂未接入平台适配器。")
        print("请使用 '一键所有平台批量采集' 并选择 Amazon，以便预演/计划任务；后续接入后将自动执行。")
        input("按回车键返回...")

    def _run_tiktok_batch_placeholder(self):
        """TikTok 批量采集占位入口（使用通用批量流程或等待适配器接入）。"""
        print("\n[i] TikTok 批量采集暂未接入平台适配器。")
        print("请使用 '一键所有平台批量采集' 并选择 TikTok，以便预演/计划任务；后续接入后将自动执行。")
        input("按回车键返回...")

    def _run_componentized_one_click_export(self):
        """通用的‘组件化一键导出’入口（平台无关设计，当前支持 Shopee）。

        流程：选择平台 -> 选择账号 -> 实时拉店铺 -> 选择店铺 -> 选择时间范围 -> 执行对应数据域的导出组件
        默认数据域为 services（服务表现，AI 助手 + 人工聊天，支持 UI->API 兜底）。
        """
        try:
            # 1) 平台选择（当前提供 Shopee，后续平台按配置自动出现）
            platforms = ["shopee"]
            print("\n[WEB] 可用平台：")
            for i, pf in enumerate(platforms, 1):
                print(f"  {i}. {pf}")
            ch = input("请选择平台 (默认1): ").strip() or "1"
            try:
                pidx = int(ch)
                platform = platforms[pidx - 1]
            except Exception:
                print("[FAIL] 选择无效"); input("按回车键返回..."); return

            # 2) 选择账号（统一入口）
            if platform != "shopee":
                print("[WARN] 暂不支持该平台的一键导出"); input("按回车键返回..."); return
            sel = self._select_shopee_account_unified()
            if not sel:
                return
            account, account_label = sel

            # 3) 实时拉取店铺 + 选择店铺
            from playwright.sync_api import sync_playwright
            if platform == "shopee":
                from modules.services.shopee_playwright_exporter import ShopeePlaywrightExporter
            else:
                print("[WARN] 暂不支持该平台的一键导出"); input("按回车键返回..."); return

            with sync_playwright() as p:
                exp = ShopeePlaywrightExporter(p)
                shops = exp.list_shops(account)
                if not shops:
                    print("[FAIL] 未拉取到店铺，请确认账号登录状态"); input("按回车键返回..."); return
                print("\n[SHOP] 选择店铺：")
                for i, s in enumerate(shops, 1):
                    print(f"  {i}. {getattr(s,'name', 'shop')} (id={getattr(s,'id', '')}, region={getattr(s,'region','')})")
                sidx = input("请选择店铺序号: ").strip()
                try:
                    sidx = int(sidx); shop = shops[sidx-1]
                except Exception:
                    print("[FAIL] 选择无效"); input("按回车键返回..."); return

                # 4) 选择时间范围（标准候选：昨天/过去7天/过去30天）
                from datetime import datetime, timedelta
                print("\n[DATE] 选择时间范围:")
                print("1. 昨天（默认）  2. 过去7天  3. 过去30天")
                w = input("请选择 (1-3): ").strip() or "1"
                if w == '1':
                    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                    start_date = yesterday; end_date = yesterday; granularity = "day"
                elif w == '2':
                    end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                    start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"); granularity = "weekly"
                elif w == '3':
                    end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"); granularity = "monthly"
                else:
                    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                    start_date = yesterday; end_date = yesterday; granularity = "day"

                # 子类型选择（默认：全部）
                print("\n子类型选择:")
                print("1. 全部 (默认)  2. AI助手  3. 人工聊天")
                st = input("请选择 (1-3): ").strip() or "1"
                services_subtype = "all"
                if st == "2":
                    services_subtype = "ai_assistant"
                elif st == "3":
                    services_subtype = "agent"

                # 5) 打开已登录页面（持久化会话），构造 adapter + 执行导出组件
                try:
                    ctx_exp, page_exp, platform_exp, account_id_exp = exp._open_account_page(account)
                except Exception as e:
                    print(f"[FAIL] 打开会话失败: {e}"); input("按回车键返回..."); return

                try:
                    from modules.components.base import ExecutionContext
                    from modules.services.platform_adapter import get_adapter
                    from modules.platforms.shopee.components.config_registry import ConfigRegistry, DataDomain
                    from modules.core.logger import get_logger as _get_logger

                    # 默认数据域：services（服务表现，AI助手+人工聊天）；后续可扩展为可选
                    domain = DataDomain.SERVICES
                    # 构造执行上下文
                    account_ctx = dict(account)
                    account_ctx['label'] = account_label
                    account_ctx['shop_id'] = getattr(shop, 'id', None)
                    account_ctx['selected_shop_name'] = getattr(shop, 'name', None)
                    _gran = exp._calculate_granularity(start_date, end_date) if hasattr(exp, '_calculate_granularity') else 'daily'
                    exec_ctx = ExecutionContext(
                        platform=platform,
                        account=account_ctx,
                        logger=_get_logger(__name__),
                        config={
                            "shop_id": getattr(shop, 'id', None),
                            "granularity": _gran,
                            "start_date": start_date,
                            "end_date": end_date,
                            "shop_name": getattr(shop, 'name', None),
                            "services_subtype": services_subtype,
                            # 默认导出全部子类型；如需仅导出某一子类型，可设置 "services_subtype": "ai_assistant"/"agent"
                        },
                    )

                    adapter = get_adapter(platform, exec_ctx)

                    # 动态获取导出组件类并执行
                    ExportCls = ConfigRegistry.get_export_component_class(domain)
                    exporter = ExportCls(exec_ctx)
                    print("\n[START] 开始执行：Shopee 服务表现（AI助手/人工聊天）")
                    result = exporter.run(page_exp)
                    if result.success:
                        print(f"\n[OK] 导出成功: {result.file_path or ''}")
                        print("[FOLDER] 输出目录已按规范生成（含统一文件命名）")
                    else:
                        print(f"\n[FAIL] 导出失败: {result.message}")
                finally:
                    try:
                        ctx_exp.close()
                    except Exception:
                        pass

                input("\n按回车键返回...")
        except Exception as e:
            from modules.core.logger import get_logger
            get_logger(__name__).error(f"一键导出流程异常: {e}")

    def _run_multi_domain_platform_wide_batch(self):
        """多数据域平台全量批量采集：一个平台的所有账号->所有店铺->多种数据类型。"""
        try:
            # 1) 平台选择（当前仅支持 Shopee）；支持一键预设直达
            preset = getattr(self, "_one_click_preset", None)
            if preset:
                platform = "shopee"
            else:
                platforms = ["shopee"]
                print("\n[WEB] 可用平台：")
                for i, pf in enumerate(platforms, 1):
                    print(f"  {i}. {pf}")
                ch = input("请选择平台 (默认1): ").strip() or "1"
                try:
                    platform = platforms[int(ch) - 1]
                except Exception:
                    print("[FAIL] 选择无效"); input("按回车键返回..."); return

            # 2) 数据域选择（多选）；支持一键预设覆盖
            preset_domains = getattr(self, "_one_click_domains", None)
            if preset_domains:
                domain_map = {
                    "services": ("services", "服务表现"),
                    "products": ("products", "商品表现"),
                    "traffic": ("traffic", "流量表现"),
                    "orders": ("orders", "订单表现"),
                    "finance": ("finance", "财务表现"),
                }
                selected_domains = [domain_map[k] for k in preset_domains if k in domain_map]
            else:
                print("\n[DATA] 选择数据域（可多选）：")
                print("1. 服务表现 (services)")
                print("2. 商品表现 (products)")
                print("3. 流量表现 (traffic)")
                print("4. 订单表现 (orders)")
                print("5. 财务表现 (finance)")
                print("请输入选择的数字，用逗号分隔 (如: 1,2,3 或 回车=已打通的三类): ", end="")
                domain_input = input().strip() or "1,2,3"

                domain_map_num = {
                    "1": ("services", "服务表现"),
                    "2": ("products", "商品表现"),
                    "3": ("traffic", "流量表现"),
                    "4": ("orders", "订单表现"),
                    "5": ("finance", "财务表现"),
                }
                selected_domains = []
                for num in domain_input.split(","):
                    num = num.strip()
                    if num in domain_map_num:
                        selected_domains.append(domain_map_num[num])

            if not selected_domains:
                print("[FAIL] 未选择有效的数据域"); input("按回车键返回..."); return

            print(f"\n[OK] 已选择数据域: {', '.join([d[1] for d in selected_domains])}")
            READY_KEYS = {"services", "products", "traffic"}
            exec_domains = [d for d in selected_domains if d[0] in READY_KEYS]
            skipped = [d[1] for d in selected_domains if d[0] not in READY_KEYS]
            if skipped:
                print(f"[NEXT] 未实现/占位，已自动跳过: {', '.join(skipped)}")
            if not exec_domains:
                print("[FAIL] 未选择到任何已打通的数据域"); input("按回车返回..."); return

            # 3) 时间范围选择；支持一键预设覆盖
            from datetime import datetime, timedelta
            preset = getattr(self, "_one_click_preset", None)
            if isinstance(preset, dict) and preset.get("start_date") and preset.get("end_date"):
                start_date = str(preset["start_date"])
                end_date = str(preset["end_date"])
                granularity = str(preset.get("granularity", "daily"))
            else:
                print("\n[DATE] 选择时间范围:")
                print("1. 昨天（默认）  2. 过去7天  3. 过去30天")
                w = input("请选择 (1-3): ").strip() or "1"
                if w == '1':
                    end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                    start_date = end_date
                    granularity = "daily"
                elif w == '2':
                    end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                    start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
                    granularity = "weekly"
                elif w == '3':
                    end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                    granularity = "monthly"
                else:
                    end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                    start_date = end_date
                    granularity = "daily"

            # 4) 执行顺序确认
            print(f"\n[RETRY] 执行顺序: {' -> '.join([d[1] for d in exec_domains])}")
            print(f"[DATE] 时间范围: {start_date} ~ {end_date}")
            if not getattr(self, "_one_click_mode", False):
                if input("确认开始批量采集? (y/n): ").strip().lower() not in ['y','yes','是']:
                    return

            # 5) 遍历平台所有账号与店铺
            from modules.utils.account_manager import AccountManager
            am = AccountManager()
            accounts = [a for a in am.load_accounts().get('accounts', []) if a.get('platform','').lower()== platform and a.get('enabled', True) and a.get('login_url')]
            if not accounts:
                print(f"[FAIL] 未找到启用的 {platform} 账号"); input("按回车键返回..."); return

            from playwright.sync_api import sync_playwright
            from modules.services.shopee_playwright_exporter import ShopeePlaywrightExporter
            from modules.components.base import ExecutionContext
            from modules.services.platform_adapter import get_adapter
            from modules.platforms.shopee.components.config_registry import ConfigRegistry, DataDomain
            from modules.core.logger import get_logger as _get_logger

            total_tasks = 0; ok_count = 0; fail_count = 0
            results_by_domain = {domain[0]: {"ok": 0, "fail": 0} for domain in exec_domains}
            domain_name_map = {k: v for k, v in exec_domains}
            fail_records = []


            with sync_playwright() as p:
                for account in accounts:
                    account_label = account.get('store_name') or account.get('username') or str(account.get('account_id'))
                    print(f"\n[USER] 账号: {account_label}")
                    exp = ShopeePlaywrightExporter(p)
                    shops = exp.list_shops(account) if platform == "shopee" else []
                    if not shops:
                        print("  [WARN] 未拉取到店铺，跳过该账号")
                        continue

                    for shop in shops:
                        print(f"  [SHOP] 店铺: {getattr(shop,'name','shop')} (id={getattr(shop,'id','')}, region={getattr(shop,'region','')})")

                        # 按选择的数据域顺序执行
                        for domain_key, domain_name in exec_domains:
                            total_tasks += 1
                            print(f"    [DATA] 执行: {domain_name}")

                            try:
                                success = self._execute_single_domain_export(
                                    exp, account, shop, platform, domain_key,
                                    start_date, end_date, granularity, account_label
                                )
                                if success:
                                    ok_count += 1
                                    results_by_domain[domain_key]["ok"] += 1
                                    print(f"    [OK] {domain_name} 成功")
                                    # 一键模式收集明细
                                    if getattr(self, "_one_click_collector", None) is not None:
                                        try:
                                            self._one_click_collector.append({
                                                "platform": "shopee",
                                                "account": account_label,
                                                "shop": getattr(shop,'name','shop'),
                                                "domain": domain_key,
                                                "status": "success",
                                                "message": "",
                                            })
                                        except Exception:
                                            pass
                                else:
                                    try:
                                        fail_records.append((account_label, getattr(shop,'name','shop'), domain_key))
                                    except Exception:
                                        pass

                                    fail_count += 1
                                    results_by_domain[domain_key]["fail"] += 1
                                    print(f"    [FAIL] {domain_name} 失败")
                                    if getattr(self, "_one_click_collector", None) is not None:
                                        try:
                                            self._one_click_collector.append({
                                                "platform": "shopee",
                                                "account": account_label,
                                                "shop": getattr(shop,'name','shop'),
                                                "domain": domain_key,
                                                "status": "fail",
                                                "message": "",
                                            })
                                        except Exception:
                                            pass
                            except Exception as e:
                                fail_count += 1
                                results_by_domain[domain_key]["fail"] += 1
                                print(f"    [FAIL] {domain_name} 异常: {e}")
                                if getattr(self, "_one_click_collector", None) is not None:
                                    try:
                                        self._one_click_collector.append({
                                            "platform": "shopee",
                                            "account": account_label,
                                            "shop": getattr(shop,'name','shop'),
                                            "domain": domain_key,
                                            "status": "error",
                                            "message": str(e),
                                        })
                                    except Exception:
                                        pass

                        # 账号级收尾：关闭当前账号的所有上下文与回退浏览器，避免并窗
                        try:
                            if 'exp' in locals() and getattr(exp, 'pb', None):
                                aid = (
                                    account.get('account_id')
                                    or account.get('username')
                                    or account.get('store_name')
                                    or account.get('label')
                                    or 'unknown'
                                )
                                try:
                                    exp.pb.close_context('shopee', str(aid))
                                except Exception:
                                    pass
                                try:
                                    exp.pb.close_all_contexts()
                                except Exception:
                                    pass
                                # 额外关闭回退浏览器
                                try:
                                    fb = getattr(exp.pb, '_fallback_browsers', None)
                                    if isinstance(fb, dict):
                                        for _k, _br in list(fb.items()):
                                            try:
                                                _br.close()
                                            except Exception:
                                                pass
                                except Exception:
                                    pass
                                # 轮询确认资源释放
                                import time
                                for _ in range(24):
                                    any_open = False
                                    try:
                                        if getattr(exp.pb, 'active_contexts', None) and len(exp.pb.active_contexts) > 0:
                                            any_open = True
                                        if getattr(exp.pb, '_fallback_browsers', None) and len(exp.pb._fallback_browsers) > 0:
                                            any_open = True
                                    except Exception:
                                        pass
                                    if not any_open:
                                        break
                                    time.sleep(0.25)
                            #  清理无效注释：账号后台资源统计（确认后台也同步关闭）
                            try:
                                c_cnt = len(getattr(exp.pb, 'active_contexts', []) or [])
                                f_cnt = len(getattr(exp.pb, '_fallback_browsers', {}) or {})
                                print(f"    账号后台资源统计: contexts={c_cnt}, fallbacks={f_cnt}")
                            except Exception:
                                pass
                            try:
                                print(f"    账号后台资源统计: contexts={c_cnt}, fallbacks={f_cnt}")
                            except Exception:
                                pass


                        except Exception:
                            pass

            # 全局兜底关闭所有浏览器上下文，避免账号采集结束后残留
            try:
                from modules.utils.persistent_browser_manager import PersistentBrowserManager
                PersistentBrowserManager().close_all_contexts()
                print("\n已关闭所有浏览器上下文 (global cleanup)")
            except Exception:
                pass

            # 输出清晰的清理提示
            try:
                print("\n[CLEAN] 已关闭所有浏览器上下文 (global cleanup)")
            except Exception:
                pass


            if fail_records:
                print("\n[RECEIPT] 按账号/店铺/数据域失败清单：")
                for acct, shop_name, dkey in fail_records:
                    try:
                        dname = domain_name_map.get(dkey, dkey)
                        print(f"   - {acct} / {shop_name}: {dname}")
                    except Exception:
                        print(f"   - {acct} / {shop_name}: {dkey}")


            # 6) 结果汇总
            print("\n[DATA] 批量结果汇总：")
            print(f"   总任务: {total_tasks} | [OK] 成功: {ok_count} | [FAIL] 失败: {fail_count}")
            print("\n[CHART] 按数据域统计：")
            for domain_key, domain_name in exec_domains:
                stats = results_by_domain[domain_key]
                print(f"   {domain_name}: [OK] {stats['ok']} | [FAIL] {stats['fail']}")
            if not getattr(self, "_one_click_mode", False):
                input("\n按回车键返回...")

        except Exception as e:
            from modules.core.logger import get_logger
            get_logger(__name__).error(f"多数据域批量采集异常: {e}")
            print(f"[FAIL] 异常: {e}")
            input("按回车键返回...")
    def _execute_single_domain_export(self, exp, account, shop, platform, domain_key,
                                     start_date, end_date, granularity, account_label):
        """执行单个数据域的导出"""
        try:
            from modules.components.base import ExecutionContext
            from modules.services.platform_adapter import get_adapter
            from modules.platforms.shopee.components.config_registry import ConfigRegistry, DataDomain
            from modules.core.logger import get_logger as _get_logger

            # 根据数据域获取对应的导出组件
            domain_map = {
                "services": DataDomain.SERVICES,
                "products": DataDomain.PRODUCTS,
                "analytics": DataDomain.ANALYTICS,  # v4.10.0更新：统一使用analytics域，traffic域已废弃
                "orders": DataDomain.ORDERS,
                "finance": DataDomain.FINANCE
            }

            if domain_key not in domain_map:
                print(f"    [WARN] 不支持的数据域: {domain_key}")
                return False

            data_domain = domain_map[domain_key]

            # 获取导出组件类
            try:
                ExportCls = ConfigRegistry.get_export_component_class(data_domain)
            except Exception as e:
                print(f"    [WARN] 获取{domain_key}导出组件失败: {e}")
                return False

            # 创建执行上下文
            ctx_exp, page_exp, platform_exp, account_id_exp = exp._open_account_page(account)
            try:
                account_ctx = dict(account)
                account_ctx['label'] = account_label
                account_ctx['shop_id'] = getattr(shop, 'id', None)

                config = {
                    "shop_id": getattr(shop, 'id', None),
                    "granularity": granularity,
                    "start_date": start_date,
                    "end_date": end_date,
                    "shop_name": getattr(shop, 'name', None),
                }

                # 服务表现特殊配置
                if domain_key == "services":
                    config["services_subtype"] = "all"  # 默认全部子类型

                # 注入选中店铺名，供组件统一使用
                account_ctx['selected_shop_name'] = getattr(shop, 'name', None)

                exec_ctx = ExecutionContext(
                    platform=platform,
                    account=account_ctx,
                    logger=_get_logger(__name__),
                    config=config,
                )

                # 执行导出
                exporter = ExportCls(exec_ctx)

                # Shopee: 组件化域（products/traffic/...）先导航到目标页面；services 由组件内部处理
                try:
                    if platform.lower() == 'shopee' and data_domain in (DataDomain.ANALYTICS, DataDomain.PRODUCTS, DataDomain.ORDERS, DataDomain.FINANCE):
                        from modules.platforms.shopee.components.navigation import ShopeeNavigation
                        # 选择器按域选择（缺省回退到 AnalyticsSelectors）
                        sel = None
                        if data_domain == DataDomain.PRODUCTS:
                            from modules.platforms.shopee.components.products_config import ProductsSelectors as _Sel
                            sel = _Sel()
                        else:
                            from modules.platforms.shopee.components.analytics_config import AnalyticsSelectors as _Sel
                            sel = _Sel()
                        nav = ShopeeNavigation(exec_ctx, sel)
                        target = ConfigRegistry.get_navigation_target(data_domain)
                        nav_res = nav.run(page_exp, target)
                        if not nav_res.success:
                            print(f"    [FAIL] 导航失败: {nav_res.message}")
                            return False
                except Exception as _ne:
                    print(f"    [WARN] 导航步骤异常(继续尝试导出): {_ne}")

                # 统一域级限流：执行前冷却+抖动（由 config/data_collection.yaml 配置）
                try:
                    from modules.core.config import get_config_value as _get
                    import time, random
                    _j = _get('data_collection', 'execution.jitter_ms_range', [300, 1200])
                    _base = _get('data_collection', 'execution.domain_cooldown_ms', 400)
                    _rand = random.randint(int(_j[0]), int(_j[1])) if isinstance(_j, (list, tuple)) and len(_j) == 2 else 0
                    time.sleep(max(0, (int(_base) + int(_rand))) / 1000.0)
                except Exception:
                    pass

                    # 商品表现：采用组件化 DatePicker 并做可见校验，确保不是“今日实时”
                    if data_domain == DataDomain.PRODUCTS:
                        try:
                            from modules.components.date_picker.base import DateOption
                            from modules.services.platform_adapter import get_adapter as _get_adapter
                            from datetime import datetime as _dt, timedelta as _td

                            adapter = _get_adapter(platform, exec_ctx)
                            # 依据日期范围推断预设
                            try:
                                sd = _dt.strptime(str(start_date), "%Y-%m-%d")
                                ed = _dt.strptime(str(end_date), "%Y-%m-%d")
                                days = (ed - sd).days + 1
                                opt = DateOption.YESTERDAY
                                if days == 1:
                                    if ed.date() == _dt.now().date():
                                        opt = DateOption.TODAY_REALTIME
                                    else:
                                        opt = DateOption.YESTERDAY
                                elif days == 7:
                                    opt = DateOption.LAST_7_DAYS
                                elif days == 30:
                                    opt = DateOption.LAST_30_DAYS
                            except Exception:
                                opt = DateOption.YESTERDAY

                            try:
                                print(f"    [CAL] 商品表现-选择日期: {getattr(opt, 'value', str(opt))}")
                            except Exception:
                                pass

                            try:
                                cur_url = str(page_exp.url)
                            except Exception:
                                cur_url = ""
                            if ("timeRange=" in cur_url) or ("shortcut=" in cur_url):
                                print("    [CAL] 当前URL已包含时间参数，跳过日期选择组件")
                            else:
                                date_res = adapter.date_picker().run(page_exp, opt)
                                if not date_res.success:
                                    print(f"    [FAIL] 商品表现日期选择失败: {date_res.message}")
                                    return False
                        except Exception as _de:
                            print(f"    [WARN] 商品表现日期选择异常(将继续导出): {_de}")


                result = exporter.run(page_exp)

                # 商品表现：下载后校验文件名中的日期范围是否与预期一致，不一致则重试一次日期选择+导出
                if data_domain == DataDomain.PRODUCTS and result and getattr(result, 'success', False):
                    try:
                        expected_start = str(start_date)
                        expected_end = str(end_date)
                        fpath = getattr(result, 'file_path', None)
                        ok_dates = False
                        if fpath:
                            import os
                            base = os.path.basename(str(fpath))
                            try:
                                name, _ext = os.path.splitext(base)
                                parts = name.split('__')
                                if len(parts) >= 1:
                                    last = parts[-1]
                                    if '_' in last:
                                        tail_dates = last.split('_')
                                        if len(tail_dates) >= 2:
                                            got_start = tail_dates[-2]
                                            got_end = tail_dates[-1]
                                            ok_dates = (got_start == expected_start and got_end == expected_end)
                            except Exception:
                                ok_dates = False
                        if not ok_dates:
                            print(f"    [WARN] 日期校验不一致：期望 {expected_start}~{expected_end}，实际文件: {fpath}，将重选日期并重试导出")
                            try:
                                from modules.components.date_picker.base import DateOption
                                from modules.services.platform_adapter import get_adapter as _get_adapter
                                from datetime import datetime as _dt

                                adapter = _get_adapter(platform, exec_ctx)
                                try:
                                    sd = _dt.strptime(expected_start, "%Y-%m-%d"); ed = _dt.strptime(expected_end, "%Y-%m-%d")
                                    days = (ed - sd).days + 1
                                    opt = DateOption.YESTERDAY if days == 1 else (DateOption.LAST_7_DAYS if days == 7 else DateOption.LAST_30_DAYS)
                                except Exception:
                                    opt = DateOption.YESTERDAY
                                try:
                                    cur_url = str(page_exp.url)
                                except Exception:
                                    cur_url = ""
                                if ("timeRange=" in cur_url) or ("shortcut=" in cur_url):
                                    print("    [CAL] URL已含时间参数，跳过日期选择组件(重试)")
                                else:
                                    _res2 = adapter.date_picker().run(page_exp, opt)
                                    page_exp.wait_for_timeout(600)
                                result = exporter.run(page_exp)
                            except Exception as _re:
                                print(f"    [WARN] 重试日期选择/导出异常: {_re}")
                    except Exception:
                        pass

                if result and not result.success:
                    try:
                        print(f"    [FAIL] {domain_key} 失败: {result.message}")
                    except Exception:
                        pass
                return result.success if result else False

            finally:
                # 不在域级关闭持久化上下文，避免下一域/下一店铺复用时出现“context has been closed”
                # 上下文在账号级循环结束后统一通过 PersistentBrowserManager 关闭
                pass

        except Exception as e:
            print(f"    [FAIL] 执行{domain_key}导出异常: {e}")
            return False
    def _run_services_platform_wide_batch(self):
        """平台全量批量采集：一个平台的所有账号->所有店铺->服务表现（全部/指定子类型）。"""
        try:
            # 1) 平台选择（当前仅支持 Shopee）
            platforms = ["shopee"]
            print("\n[WEB] 可用平台：")
            for i, pf in enumerate(platforms, 1):
                print(f"  {i}. {pf}")
            ch = input("请选择平台 (默认1): ").strip() or "1"
            try:
                platform = platforms[int(ch) - 1]
            except Exception:
                print("[FAIL] 选择无效"); input("按回车键返回..."); return

            # 2) 时间范围选择（统一与组件化单店一致）
            from datetime import datetime, timedelta
            print("\n[DATE] 选择时间范围:")
            print("1. 昨天（默认）  2. 过去7天  3. 过去30天")
            w = input("请选择 (1-3): ").strip() or "1"
            if w == '1':
                end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                start_date = end_date
                granularity = "day"
            elif w == '2':
                end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
                granularity = "weekly"
            elif w == '3':
                end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                granularity = "monthly"
            else:
                end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                start_date = end_date
                granularity = "day"

            # 3) 子类型选择
            print("\n子类型选择:")
            print("1. 全部 (默认)  2. AI助手  3. 人工聊天")
            st = input("请选择 (1-3): ").strip() or "1"
            services_subtype = "all"
            if st == "2":
                services_subtype = "ai_assistant"
            elif st == "3":
                services_subtype = "agent"

            # 4) 遍历平台所有账号与店铺
            from modules.utils.account_manager import AccountManager
            am = AccountManager()
            accounts = [a for a in am.load_accounts().get('accounts', []) if a.get('platform','').lower()== platform and a.get('enabled', True) and a.get('login_url')]
            if not accounts:
                print(f"[FAIL] 未找到启用的 {platform} 账号"); input("按回车键返回..."); return

            from playwright.sync_api import sync_playwright
            from modules.services.shopee_playwright_exporter import ShopeePlaywrightExporter
            from modules.components.base import ExecutionContext
            from modules.services.platform_adapter import get_adapter
            from modules.platforms.shopee.components.config_registry import ConfigRegistry, DataDomain
            from modules.core.logger import get_logger as _get_logger

            total = 0; ok_count = 0; fail_count = 0

            with sync_playwright() as p:
                for account in accounts:
                    account_label = account.get('store_name') or account.get('username') or str(account.get('account_id'))
                    print(f"\n[USER] 账号: {account_label}")
                    exp = ShopeePlaywrightExporter(p)
                    shops = exp.list_shops(account) if platform == "shopee" else []
                    if not shops:
                        print("  [WARN] 未拉取到店铺，跳过该账号")
                        continue

                    for shop in shops:
                        total += 1
                        print(f"  [SHOP] 店铺: {getattr(shop,'name','shop')} (id={getattr(shop,'id','')}, region={getattr(shop,'region','')})")
                        try:
                            ctx_exp, page_exp, platform_exp, account_id_exp = exp._open_account_page(account)
                            try:
                                account_ctx = dict(account)
                                account_ctx['label'] = account_label
                                account_ctx['shop_id'] = getattr(shop, 'id', None)
                                account_ctx['selected_shop_name'] = getattr(shop, 'name', None)
                                exec_ctx = ExecutionContext(
                                    platform=platform,
                                    account=account_ctx,
                                    logger=_get_logger(__name__),
                                    config={
                                        "shop_id": getattr(shop, 'id', None),
                                        "granularity": granularity,
                                        "start_date": start_date,
                                        "end_date": end_date,
                                        "shop_name": getattr(shop, 'name', None),
                                        "services_subtype": services_subtype,
                                    },
                                )
                                adapter = get_adapter(platform, exec_ctx)
                                ExportCls = ConfigRegistry.get_export_component_class(DataDomain.SERVICES)
                                exporter = ExportCls(exec_ctx)
                                print("    [START] 导出：Shopee 服务表现（AI助手/人工聊天）")
                                result = exporter.run(page_exp)
                                if result.success:
                                    ok_count += 1
                                    print("    [OK] 成功")
                                else:
                                    fail_count += 1
                                    print(f"    [FAIL] 失败: {result.message}")
                            finally:
                                try:
                                    ctx_exp.close()
                                except Exception:
                                    pass
                        except Exception as e:
                            fail_count += 1
                            print(f"    [FAIL] 异常: {e}")

            print("\n[DATA] 批量结果汇总：")
            print(f"   总任务: {total} | [OK] 成功: {ok_count} | [FAIL] 失败: {fail_count}")
            input("\n按回车键返回...")
        except Exception as e:
            from modules.core.logger import get_logger
            get_logger(__name__).error(f"平台全量批量采集异常: {e}")
            print(f"[FAIL] 异常: {e}")
            input("按回车键返回...")

            print(f"[FAIL] 异常: {e}")
            input("按回车键返回...")



    def _select_shopee_account_unified(self):
        """统一的 Shopee 账号选择（代理到通用入口）"""
        return self._select_account_unified("shopee")

    def _select_account_unified(self, platform: str):
        """
        通用账号选择：
        - 统一来源与过滤：platform 匹配（含回退同义关键词），enabled=true，必须配置 login_url
        - 统一展示：显示名 + 登录URL + 备注
        - 返回 (account, account_label)；选择无效返回 None
        """
        try:
            from modules.utils.account_manager import AccountManager
            am = AccountManager()

            # 同义词映射与模糊匹配关键字
            synonyms = {
                'shopee': ['shopee'],
                'amazon': ['amazon'],
                'tiktok': ['tiktok', 'douyin', '抖音'],
                'miaoshou': ['miaoshou', '妙手', 'erp'],
            }
            keys = synonyms.get(platform.lower(), [platform.lower()])

            # 尝试平台精确过滤
            accounts = am.get_accounts_by_platform(platform) or am.get_accounts_by_platform(platform.capitalize())
            if not accounts:
                # 回退：在所有账号中做关键字模糊匹配
                all_accounts = am.load_accounts().get('accounts', [])
                accounts = [
                    acc for acc in all_accounts
                    if any(k in (acc.get('platform', '') or '').lower() for k in keys)
                    or any(k in (acc.get('store_name', '') or '').lower() for k in keys)
                    or any(k in (acc.get('username', '') or '').lower() for k in keys)
                ]

            # 过滤启用且配置了 login_url 的账号（遵循登录网址规范）
            accounts = [a for a in accounts if a.get('enabled', True) and a.get('login_url')]

            if not accounts:
                print("[FAIL] 未找到账号配置")
                print("[TIP] 请确保:")
                print(f"   1. 账号的 platform 字段设置为 '{platform.lower()}' 或同义")
                print("   2. 账号已启用 (enabled: true)")
                print("   3. 账号配置了 login_url")
                print("\n[TOOL] 可以通过'账号管理'模块添加或修改账号")
                input("按回车键返回...")
                return None

            print(f"\n[USER] 选择 {platform.capitalize()} 账号：")
            for i, acc in enumerate(accounts, 1):
                display_name = (
                    acc.get('store_name') or
                    acc.get('username') or
                    acc.get('label') or
                    f'账号{i}'
                )
                login_url = acc.get('login_url', '未配置')
                print(f"  {i}. {display_name} [OK]")
                print(f"     登录URL: {login_url}")
                if acc.get('备注'):
                    print(f"     备注: {acc.get('备注')}")

            try:
                aidx = int(input("请选择序号: ").strip())
                account = accounts[aidx-1]
                account_label = (
                    account.get('store_name') or
                    account.get('username') or
                    account.get('label') or
                    f'账号{aidx}'
                )
                return account, account_label
            except Exception:
                print("[FAIL] 选择无效")
                input("按回车键返回...")
                return None
        except Exception:
            print("[FAIL] 账号选择异常")
            input("按回车键返回...")
            return None


    def _run_shopee_product_performance_export(self):
        """运行 Shopee 商品表现数据导出（Playwright 自动化）"""
        try:
            print("\n[SHOP]  Shopee 商品表现数据导出")
            print("=" * 50)
            print("[LIST] 流程：选账号 -> 实时拉取店铺 -> (必要时) 选择日期 -> 导出")

            # 选择账号
            sel = self._select_shopee_account_unified()
            if not sel:
                return
            account, account_label = sel

            # 实时拉取店铺
            from playwright.sync_api import sync_playwright
            from modules.services.shopee_playwright_exporter import ShopeePlaywrightExporter
            with sync_playwright() as p:
                exp = ShopeePlaywrightExporter(p)
                shops = exp.list_shops(account)
                if not shops:
                    print("[FAIL] 未拉取到店铺，请确认账号登录状态"); input("按回车键返回..."); return
                print("\n[SHOP] 选择店铺：")
                for i, s in enumerate(shops, 1):
                    print(f"  {i}. {s.name} (id={s.id}, region={s.region})")
                sidx = input("请选择店铺序号: ").strip()
                try:
                    sidx = int(sidx); shop = shops[sidx-1]
                except Exception:
                    print("[FAIL] 选择无效"); input("按回车键返回..."); return

                # 选择时间范围（适配Shopee控件实际能力）
                from datetime import datetime, timedelta
                print("\n[DATE] 选择时间范围:")
                print("1. 今日实时  2. 昨天  3. 过去7天（推荐）  4. 过去30天")
                w = input("请选择 (1-4): ").strip()
                if w == '1':
                    # 今日实时
                    today = datetime.now().strftime("%Y-%m-%d")
                    start_date = today
                    end_date = today
                elif w == '2':
                    # 昨天
                    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                    start_date = yesterday
                    end_date = yesterday
                elif w == '3':
                    # 过去7天
                    end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")  # 昨天作为结束
                    start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
                elif w == '4':
                    # 过去30天
                    end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")  # 昨天作为结束
                    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

                else:
                    print("[FAIL] 选择无效"); input("按回车键返回..."); return

                # 导出选项
                print(f"\n参数确认：账号={account_label} 店铺={shop.name} 时间范围={start_date}~{end_date}")
                print("\n[TOOL] 导出选项:")
                print("1. 标准导出")
                print("2. 录制模式（Inspector+事件监听）")
                print("3. 对比诊断（手动前后快照）")
                mode = input("请选择模式 (1-3, 默认1): ").strip() or "1"
                enable_recording = (mode == "2")
                enable_compare = (mode == "3")

                if input("\n确认开始导出? (y/n): ").strip().lower() not in ['y','yes','是']:
                    return

                # 决策：组件化优先（可通过 simple_config.collection.component_first 开关）
                from modules.core.config import get_config_value
                component_first = get_config_value('simple_config', 'collection.component_first', True)

                if component_first:
                    print("[TOOL] 执行策略: 组件化优先路径")
                    try:
                        # 组件化路径：使用组件完成完整流程，跳过导出器的重复步骤
                        from modules.components.base import ExecutionContext
                        from modules.services.platform_adapter import get_adapter
                        from modules.components.navigation.base import TargetPage
                        from modules.components.date_picker.base import DateOption
                        from modules.core.logger import get_logger as _get_logger

                        print("[LOC] 步骤1: 获取页面对象...")
                        # 先获取 page 对象（从 exporter 的上下文中）
                        ctx_exp, page_exp, platform_exp, account_id_exp = exp._open_account_page(account)

                        print("[LOC] 步骤2: 构造执行上下文...")
                        # 构造执行上下文（为导航提供shop_id）
                        account_ctx = dict(account)
                        account_ctx['shop_id'] = shop.id
                        ctx = ExecutionContext(platform='shopee', account=account_ctx, logger=_get_logger(__name__))
                        adapter = get_adapter('shopee', ctx)

                        print("[LOC] 步骤3: 执行导航组件...")
                        # 组件化执行：navigate -> date（已通过 _open_account_page 完成入口，不再重复 login）
                        nav_result = adapter.navigation().run(page_exp, TargetPage.PRODUCTS_PERFORMANCE)
                        print(f"[LOC] 导航结果: success={nav_result.success}, url={nav_result.url}, message={nav_result.message}")

                        if not nav_result.success:
                            print(f"[FAIL] 导航失败: {nav_result.message}")
                            input("按回车键返回...")
                            try:
                                ctx_exp.close()
                            except Exception:
                                pass
                            return


                        # [LOC] 步骤3.5: 在执行日期选择之前，先检查是否存在弹窗/iframe 干扰并关闭
                        try:
                            print("[LOC] 步骤3.5: 检查并关闭弹窗(含 iframe)...")

                            close_selectors = [
                                ".survey-window-modal i.eds-modal__close",
                                ".survey-window-modal .eds-modal__close",
                                "i.eds-modal__close",
                                ".eds-modal__close",
                                ".ant-modal-close",
                                ".el-dialog__headerbtn",
                                ".modal-close",
                                ".btn-close",
                                "button[aria-label='Close']",
                                "[aria-label='Close']",
                                "text=关闭",
                                "text=知道了",
                                "button:has-text('关闭')",
                                "button:has-text('我知道了')",
                                "button:has-text('OK')",
                                "button:has-text('确定')",
                            ]

                            overlay_selectors = [
                                ".eds-modal__mask", ".eds-modal__overlay", ".ant-modal-mask", ".el-overlay", ".survey-window-modal",
                            ]

                            def _attempt_close(target):
                                for sel in close_selectors:
                                    try:
                                        loc = target.locator(sel)
                                        if loc.count() > 0 and loc.first.is_visible():
                                            loc.first.click(timeout=800)
                                            # 使用页面等待，避免 Frame 无该方法
                                            page_exp.wait_for_timeout(300)
                                            return True
                                    except Exception:
                                        pass
                                # 兜底：若看到遮罩层，发一个 ESC
                                try:
                                    for ov in overlay_selectors:
                                        ov_loc = target.locator(ov)
                                        if ov_loc.count() > 0 and ov_loc.first.is_visible():
                                            page_exp.keyboard.press("Escape")
                                            page_exp.wait_for_timeout(200)
                                            return True
                                except Exception:
                                    pass
                                return False

                            def _scan_all_roots_once() -> bool:
                                # 先扫 page
                                if _attempt_close(page_exp):
                                    return True
                                # 再扫 frames
                                try:
                                    for fr in getattr(page_exp, "frames", []):
                                        try:
                                            if _attempt_close(fr):
                                                return True
                                        except Exception:
                                            continue
                                except Exception:
                                    pass
                                return False

                            closed = _scan_all_roots_once()

                            # 为应对“页面加载后延迟2s才出现”的弹窗，进行短暂观察重试
                            if not closed:
                                watch_ms, step_ms = 6000, 300  # 共观察 ~6s，覆盖更晚出现的弹窗
                                waited = 0
                                while waited < watch_ms and not closed:
                                    try:
                                        page_exp.wait_for_timeout(step_ms)
                                    except Exception:
                                        pass
                                    closed = _scan_all_roots_once()
                                    waited += step_ms

                            if closed:
                                print("[OK] 已关闭干扰弹窗")
                            else:
                                print("[i] 未检测到干扰弹窗或无需处理")
                        except Exception as _popup_err:
                            print(f"[WARN] 弹窗预处理异常: {_popup_err}")

                        print("[LOC] 步骤4: 执行日期选择组件...")
                        opt_map = {
                            '1': DateOption.TODAY_REALTIME,
                            '2': DateOption.YESTERDAY,
                            '3': DateOption.LAST_7_DAYS,
                            '4': DateOption.LAST_30_DAYS,
                        }
                        date_result = adapter.date_picker().run(page_exp, opt_map.get(w, DateOption.YESTERDAY))
                        print(f"[LOC] 日期选择结果: success={date_result.success}, message={date_result.message}")

                        if not date_result.success:
                            print(f"[FAIL] 日期选择失败: {date_result.message}")
                            input("按回车键返回...")
                            try:
                                ctx_exp.close()
                            except Exception:
                                pass
                            return

                    except Exception as e:
                        print(f"[FAIL] 组件化路径异常: {e}")
                        print("[RETRY] 回退到传统路径...")
                        component_first = False  # 回退到传统路径

                    # 使用纯导出方法（跳过导出器内部的登录/导航/日期设置）
                    print("[TARGET] 组件化路径完成，开始纯导出...")
                    try:
                        # 从配置读取导出行为设置
                        from modules.core.config import get_export_settings
                        granularity = exp._calculate_granularity(start_date, end_date)
                        export_settings = get_export_settings("shopee", granularity)

                        ok, msg, path = exp.export_products_weekly_pure(
                            page_exp,  # 已设置好的page
                            shop,
                            start_date,
                            end_date,
                            account_label=account_label,
                            output_root=Path('temp/outputs'),
                            enable_diagnostics=False,
                            enable_compare_diagnostics=enable_compare,
                            enable_recording_mode=enable_recording,
                            enable_auto_regenerate=export_settings["auto_regenerate"],
                            enable_api_fallback=export_settings["api_fallback"],
                        )
                    finally:
                        # 始终关闭上下文
                        try:
                            ctx_exp.close()
                        except Exception:
                            pass
                else:
                    print("[TOOL] 执行策略: 传统完整路径")
                    print("[TOOL] 执行策略: 旧版程序化导出 (ShopeeExporter)")
                    # 传统路径：使用完整导出方法
                    # 从配置读取导出行为设置
                    from modules.core.config import get_export_settings
                    granularity = exp._calculate_granularity(start_date, end_date)
                    export_settings = get_export_settings("shopee", granularity)

                    ok, msg, path = exp.export_products_weekly(
                        account=account,
                        shop=shop,
                        start_date=start_date,
                        end_date=end_date,
                        account_label=account_label,
                        output_root=Path('temp/outputs'),
                        enable_diagnostics=False,  # 旧诊断模式已被录制模式替代
                        enable_compare_diagnostics=enable_compare,
                        enable_recording_mode=enable_recording,
                        enable_auto_regenerate=export_settings["auto_regenerate"],
                        enable_api_fallback=export_settings["api_fallback"],
                    )
                if ok:
                    print(f"\n[OK] 导出成功: {path}")
                    if enable_recording:
                        print("[ACTION] 录制配方已保存到 .diag/recipes/ 目录")
                    elif enable_compare:
                        print("[LIST] 诊断快照已保存到 .diag/ 目录")
                else:
                    print(f"\n[FAIL] 导出失败: {msg}")
                input("\n按回车键返回...")
        except Exception as e:
            from modules.core.logger import get_logger
            get_logger(__name__).error(f"Shopee 导出流程异常: {e}")
            print(f"[FAIL] 异常: {e}")
            input("按回车键返回...")

    def _run_shopee_collection_only(self):
        """运行Shopee多账号专属采集"""
        print("\n[SHOP]  Shopee多账号专属采集")
        print("=" * 40)
        print("[LIST] 功能说明: 专门针对Shopee平台的优化采集")
        print("[NEW] 特性: 多账号并行, 智能错误恢复, 实时监控")

        confirm = input("\n是否继续启动Shopee采集? (y/n): ").strip().lower()
        if confirm not in ['y', 'yes', '是']:
            return

        try:
            print("\n[START] 启动Shopee专属采集...")

            if self.shopee_handler:
                self.shopee_handler.run_shopee_collection_only()
            else:
                print("[FAIL] Shopee采集处理器未初始化")
                print("[TIP] Shopee采集功能开发中")

            input("按回车键返回...")

        except Exception as e:
            logger.error(f"Shopee采集失败: {e}")
            print(f"[FAIL] 采集失败: {e}")
            input("按回车键继续...")

    def _run_amazon_collection(self):
        """运行Amazon数据采集"""
        print("\n[STORE] Amazon数据采集")
        print("=" * 40)
        print("[LIST] 功能说明: Amazon卖家数据采集")
        print("[NEW] 特性: 多店铺支持, 数据标准化, 自动重试")

        confirm = input("\n是否继续启动Amazon采集? (y/n): ").strip().lower()
        if confirm not in ['y', 'yes', '是']:
            return

        try:
            print("\n[START] 启动Amazon数据采集...")

            # 统一账号选择
            sel = self._select_account_unified("amazon")
            if not sel:
                return
            account, account_label = sel
            print(f"[OK] 已选择账号: {account_label}")

            # Amazon采集功能
            print("[TIP] Amazon采集功能开发中")
            print("[LIST] 计划功能:")
            print("  • 订单数据采集")
            print("  • 库存数据同步")
            print("  • 绩效报告获取")
            print("  • 财务数据导出")

            input("按回车键返回...")

        except Exception as e:
            logger.error(f"Amazon采集失败: {e}")
            print(f"[FAIL] 采集失败: {e}")
            input("按回车键继续...")



    def _run_tiktok_collection(self):
        """运行TikTok数据采集（骨架）"""
        print("\n[MUSIC] TikTok数据采集")
        print("=" * 40)
        print("[LIST] 功能说明: TikTok/抖音跨境店铺数据采集")
        print("[NEW] 特性: 多店铺支持, 数据标准化, 自动重试")

        confirm = input("\n是否继续启动TikTok采集? (y/n): ").strip().lower()
        if confirm not in ['y', 'yes', '是']:
            return

        try:
            print("\n[START] 启动TikTok数据采集...")

            # 统一账号选择
            sel = self._select_account_unified("tiktok")
            if not sel:
                return
            account, account_label = sel
            print(f"[OK] 已选择账号: {account_label}")
            # 店铺选择（占位：手动输入模拟）
            shop_name = input("\n请输入店铺名称(示例: MainShop): ").strip() or "MainShop"
            shop_id = input("请输入店铺ID(示例: 1234567890): ").strip() or "1234567890"

            # 数据类型与粒度选择（占位）
            print("\n请选择数据类型: 1) traffic  2) product  3) order  4) finance  (默认1)")
            dt_choice = (input("输入编号: ").strip() or "1")
            data_type = {"1": "traffic", "2": "product", "3": "order", "4": "finance"}.get(dt_choice, "traffic")

            print("\n请选择粒度: 1) daily  2) weekly  3) monthly  (默认1)")
            gr_choice = (input("输入编号: ").strip() or "1")
            granularity = {"1": "daily", "2": "weekly", "3": "monthly"}.get(gr_choice, "daily")

            # 时间范围（简单输入占位）
            start_date = input("\n开始日期(YYYY-MM-DD, 默认过去7天起): ").strip()
            end_date = input("结束日期(YYYY-MM-DD, 默认昨天): ").strip()
            if not start_date or not end_date:
                from datetime import date, timedelta
                end_date = (date.today() - timedelta(days=1)).isoformat()
                start_date = (date.today() - timedelta(days=7)).isoformat()

            # 计划落盘路径（与 Shopee 规格一致）
            from pathlib import Path
            safe_shop = f"{shop_name}__{shop_id}"
            base_dir = Path("temp/outputs") / "tiktok" / account_label / safe_shop / data_type / granularity
            filename = f"{data_type}_{granularity}_{start_date}_{end_date}.xlsx"
            target = base_dir / filename
            manifest = Path(str(target) + ".json")

            print("\n[MAP] 计划落盘位置(占位):")
            print(f"  目录: {base_dir}")
            print(f"  文件: {target.name}")
            print(f"  清单: {manifest.name}")


            # TikTok采集功能（占位）
            print("[TIP] TikTok采集功能开发中")
            print("[LIST] 计划功能:")
            print("  • 店铺指标采集")
            print("  • 商品与视频表现")
            print("  • 订单与物流同步")
            print("  • 财务报表导出")

            input("按回车键返回...")

        except Exception as e:
            logger.error(f"TikTok采集失败: {e}")
            print(f"[FAIL] 采集失败: {e}")
            input("按回车键继续...")


    def _run_miaoshou_sync(self):
        """运行妙手ERP数据同步"""
        print("\n[RETRY] 妙手ERP数据同步")
        print("=" * 40)
        print("[LIST] 功能说明: 妙手ERP平台数据同步")
        print("[NEW] 特性: 智能登录, 数据同步, 状态监控")

        confirm = input("\n是否继续启动妙手ERP同步? (y/n): ").strip().lower()
        if confirm not in ['y', 'yes', '是']:
            return

        try:
            print("\n[START] 启动妙手ERP数据同步...")

            # 统一账号选择
            sel = self._select_account_unified("miaoshou")
            if not sel:
                return
            account, account_label = sel
            print(f"[OK] 已选择账号: {account_label}")


            # 妙手ERP同步功能
            print("[TIP] 妙手ERP同步功能开发中")
            print("[LIST] 计划功能:")
            print("  • 智能登录处理")
            print("  • 销售数据采集")
            print("  • 运营数据同步")
            print("  • 财务报表获取")

            input("按回车键返回...")

        except Exception as e:
            logger.error(f"妙手ERP同步失败: {e}")
            print(f"[FAIL] 同步失败: {e}")
            input("按回车键继续...")

    def _run_collection_management_ui(self):
        """运行统一采集管理界面"""
        print("\n[TARGET] 统一采集管理界面")
        print("=" * 40)
        print("[LIST] 功能: Web界面管理所有采集任务")
        print("[TIP] 提示: 将启动采集管理Web界面")

        confirm = input("\n是否继续启动采集管理界面? (y/n): ").strip().lower()
        if confirm not in ['y', 'yes', '是']:
            return

        try:
            print("\n[START] 启动采集管理界面...")
            print("[LINK] 访问地址: http://localhost:8505")

            # 调用Web界面管理功能
            print("[TIP] 界面启动功能开发中")
            print("[LIST] 计划功能:")
            print("  • 实时监控采集进度")
            print("  • 可视化配置采集任务")
            print("  • 错误日志查看")
            print("  • 性能指标统计")

            input("按回车键返回...")

        except Exception as e:
            logger.error(f"采集管理界面启动失败: {e}")
            print(f"[FAIL] 启动失败: {e}")
            input("按回车键继续...")

    def _show_collection_statistics(self):
        """显示采集统计"""
        try:
            if self.stats_handler:
                self.stats_handler.show_collection_stats()
            else:
                print("\n[DATA] 采集统计")
                print("=" * 40)
                print("[LIST] 暂无统计数据")
                print("[TIP] 统计功能开发中")

            input("按回车键继续...")

        except Exception as e:
            logger.error(f"显示统计失败: {e}")
            print(f"[FAIL] 显示统计失败: {e}")
            input("按回车键继续...")

    def _show_collector_configuration(self):
        """显示采集器配置"""
        try:
            if self.config_handler:
                self.config_handler.show_collection_config()
            else:
                print("\n[GEAR]  采集器配置")
                print("=" * 40)

                print("\n[TOOL] Shopee采集器")
                print("   [LIST] 支持平台: Shopee")
                print("   [NEW] 功能特性: 多账号并行, 智能错误恢复, 实时监控")

                print("\n[TOOL] Amazon采集器")
                print("   [LIST] 支持平台: Amazon")
                print("   [NEW] 功能特性: 多店铺支持, 数据标准化, 自动重试")

                print("\n[TOOL] 妙手ERP采集器")
                print("   [LIST] 支持平台: 妙手ERP")
                print("   [NEW] 功能特性: 智能登录, 数据同步, 状态监控")

            input("按回车键返回...")

        except Exception as e:
            logger.error(f"显示配置失败: {e}")
            print(f"[FAIL] 显示配置失败: {e}")
            input("按回车键继续...")

    def get_status(self) -> Dict[str, Any]:
        """获取应用状态"""
        base_status = super().get_status()
        base_status.update({
            "run_count": self.run_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "success_rate": (self.success_count / self.run_count * 100) if self.run_count > 0 else 0.0,
            "handlers_initialized": {
                "recording_handler": self.recording_handler is not None,
                "data_handler": self.data_handler is not None,
                "shopee_handler": self.shopee_handler is not None,
                "stats_handler": self.stats_handler is not None,
                "config_handler": self.config_handler is not None
            }
        })
        return base_status

    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            checks = {
                "handlers_available": True,
                "config_accessible": True,
                "dependencies_loaded": True
            }

            # 检查处理器
            if not all([
                self.recording_handler is not None,
                self.data_handler is not None,
                self.shopee_handler is not None
            ]):
                checks["handlers_available"] = False

            # 检查配置
            try:
                from pathlib import Path
                config_dir = Path("config")
                if not config_dir.exists():
                    checks["config_accessible"] = False
            except:
                checks["config_accessible"] = False

            # 检查依赖
            try:
                import playwright
                checks["dependencies_loaded"] = True
            except ImportError:
                checks["dependencies_loaded"] = False

            overall_health = all(checks.values())

            return {
                "healthy": overall_health,
                "checks": checks,
                "message": "所有检查通过" if overall_health else "存在问题需要关注"
            }

        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return {
                "healthy": False,
                "checks": {},
                "message": f"健康检查异常: {e}"
            }

    def _run_analytics_collection_menu(self):
        """客流数据采集子菜单（组件化优先）"""
        while True:
            print("\n[DATA] 客流数据采集")
            print("=" * 40)
            print("请选择具体的客流数据类型：")
            print("  1. [SHOP]  Shopee 流量表现数据导出（组件化优先 - 已增强）")
            print("  2. [MUSIC] TikTok 流量表现数据导出（组件化 - 深链接->时间->导出）")
            print("  3. [TOOLKIT] 妙手ERP 流量表现数据导出（组件化）")
            print("  4. [DATA] 运行客流数据录制脚本（事件回放）")
            print("  c. [EDIT]  快速修改组件配置（analytics_config.py）")
            print("  m. 管理稳定版脚本（查看/设置/取消）")
            print("  0. [BACK] 返回上级菜单")

            choice = input("\n请选择 (0-4/c/m): ").strip()
            if choice == "0":
                break
            elif choice == "1":
                self._run_shopee_analytics_export_component_first("traffic")
            elif choice == "2":
                self._run_tiktok_traffic_componentized()
            elif choice == "3":
                self._run_miaoshou_traffic_componentized()
            elif choice == "4":
                self._run_recorded_scripts_by_type("analytics")
            elif choice.lower() == "c":
                self._quick_edit_analytics_config()
            elif choice.lower() == "m":
                self._manage_stable_scripts_menu("analytics")
            else:
                print("[FAIL] 无效选择")
                input("按回车键返回...")

    def _run_shopee_traffic_overview_export(self):
        """运行 Shopee 流量表现数据导出"""
        try:
            print("\n[SHOP]  Shopee 流量表现数据导出")
            print("=" * 50)
            print("[LIST] 流程：选账号 -> 实时拉取店铺 -> 选择时间范围 -> 导出")

            sel = self._select_shopee_account_unified()
            if not sel:
                return
            account, account_label = sel

            # 实时拉取店铺
            from playwright.sync_api import sync_playwright
            from modules.services.shopee_playwright_exporter import ShopeePlaywrightExporter
            with sync_playwright() as p:
                exp = ShopeePlaywrightExporter(p)
                shops = exp.list_shops(account)
                if not shops:
                    print("[FAIL] 未拉取到店铺，请确认账号登录状态"); input("按回车键返回..."); return
                print("\n[SHOP] 选择店铺：")
                for i, s in enumerate(shops, 1):
                    print(f"  {i}. {s.name} (id={s.id}, region={s.region})")
                sidx = input("请选择店铺序号: ").strip()
                try:
                    sidx = int(sidx); shop = shops[sidx-1]
                except Exception:
                    print("[FAIL] 选择无效"); input("按回车键返回..."); return

                # 选择时间范围（流量表现特有：昨天、过去7天、过去30天）
                from datetime import datetime, timedelta
                print("\n[DATE] 选择时间范围:")
                print("1. 昨天（默认）  2. 过去7天  3. 过去30天")
                w = input("请选择 (1-3): ").strip()
                if w == '1' or w == '':
                    # 昨天
                    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                    start_date = yesterday
                    end_date = yesterday
                elif w == '2':
                    # 过去7天
                    end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")  # 昨天作为结束
                    start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
                elif w == '3':
                    # 过去30天
                    end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")  # 昨天作为结束
                    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                else:
                    print("[FAIL] 选择无效，使用默认：昨天")
                    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                    start_date = yesterday
                    end_date = yesterday

                print(f"\n[DATA] 导出参数:")
                print(f"   店铺: {shop.name}")
                print(f"   时间范围: {start_date} ~ {end_date}")

                if input("\n确认开始导出? (y/n): ").strip().lower() not in ['y','yes','是']:
                    return

                # 执行流量表现导出
                ok, msg, path = exp.export_traffic_overview(
                    account=account,
                    shop=shop,
                    start_date=start_date,
                    end_date=end_date,
                    account_label=account_label,
                    output_root=Path('temp/outputs'),
                    enable_diagnostics=False,
                    enable_compare_diagnostics=False,
                    enable_recording_mode=False,
                )
                if ok:
                    print(f"\n[OK] 导出成功: {path}")
                else:
                    print(f"\n[FAIL] 导出失败: {msg}")
                input("\n按回车键返回...")
        except Exception as e:
            from modules.core.logger import get_logger
            get_logger(__name__).error(f"Shopee 流量表现导出异常: {e}")
            print(f"[FAIL] 异常: {e}")
            input("按回车键返回...")

    def _run_shopee_analytics_export_component_first(self, analytics_type: str = "traffic"):
        """运行 Shopee 数据分析导出（组件化优先 - 支持多子类型）"""
        try:
            type_names = {
                "traffic": "流量表现",
                "order": "订单表现",
                "finance": "财务表现",
                "product": "商品表现"
            }
            type_name = type_names.get(analytics_type, analytics_type)

            print(f"\n[SHOP]  Shopee {type_name}数据导出（组件化优先 - 已增强）")
            print("=" * 60)
            print("[LIST] 流程：选账号 -> 实时拉取店铺 -> 选择时间范围 -> 增强组件化导出")
            print("[NEW] 新特性：多探针检测、跨地区选择器、最新报告面板支持、自动重试")

            # 选择账号
            from modules.utils.account_manager import AccountManager
            am = AccountManager()

            # 尝试多种方式获取 Shopee 账号
            accounts = am.get_accounts_by_platform("shopee")
            if not accounts:
                # 尝试大小写变体
                accounts = am.get_accounts_by_platform("Shopee")
            if not accounts:
                # 尝试从所有账号中筛选包含 shopee 的
                all_accounts = am.load_accounts().get('accounts', [])
                accounts = [
                    acc for acc in all_accounts
                    if 'shopee' in acc.get('platform', '').lower() or
                       'shopee' in acc.get('store_name', '').lower() or
                       'shopee' in acc.get('username', '').lower()
                ]

            if not accounts:
                print("[FAIL] 未找到 Shopee 账号配置")
                print("[TIP] 请确保:")
                print("   1. 账号的 platform 字段设置为 'shopee'")
                print("   2. 账号已启用 (enabled: true)")
                print("   3. 账号配置了 login_url")
                print("\n[TOOL] 可以通过'账号管理'模块添加或修改账号")
                input("按回车键返回...")
                return

            sel = self._select_shopee_account_unified()
            if not sel:
                return
            account, account_label = sel

            # 店铺列表优先使用缓存，支持即时刷新（更快进入选择）
            from pathlib import Path
            import json
            from modules.services.shopee_playwright_exporter import ShopeePlaywrightExporter, Shop
            from playwright.sync_api import sync_playwright

            def _account_id_of(acct):
                return (
                    acct.get('account_id')
                    or acct.get('username')
                    or acct.get('store_name')
                    or acct.get('label')
                    or 'unknown'
                )

            cache_dir = Path('data') / 'shops_cache' / 'shopee'
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = cache_dir / f"{_account_id_of(account)}.json"

            shops = []
            used_cache = False
            if cache_file.exists():
                # 按你的建议，默认实时发现店铺；缓存仅作为网络失败时的兜底
                pass

            # 默认实时发现店铺（按你的建议）
            with sync_playwright() as playwright:
                exp = ShopeePlaywrightExporter(playwright)
                shops = exp.list_shops(account)
                if not shops:
                    print("[FAIL] 未获取到店铺信息")
                    input("按回车键返回...")
                    return
                # 实时写入缓存并落库 + 目录初始化
                try:
                    cache_file.write_text(
                        json.dumps([s.__dict__ for s in shops], ensure_ascii=False, indent=2),
                        encoding='utf-8'
                    )
                except Exception:
                    pass
                try:
                    self._persist_shops_and_prepare_dirs('shopee', account_label, shops)
                except Exception:
                    pass

                print(f"\n[SHOP] 选择店铺：")
                for i, shop in enumerate(shops, 1):
                    print(f"  {i}. {shop.name} (id={shop.id}, region={shop.region})")
                try:
                    sidx = int(input("请选择店铺序号: ").strip())
                    shop = shops[sidx-1]
                except Exception:
                    print("[FAIL] 选择无效")
                    input("按回车键返回...")
                    return

                # 选择时间范围（无论是否使用缓存都执行）
                from datetime import datetime, timedelta
                print("\n[DATE] 选择时间范围:")
                print("1. 昨天（默认）  2. 过去7天  3. 过去30天")
                w = input("请选择 (1-3): ").strip()
                if w == '1' or w == '':
                    end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                    start_date = end_date
                    granularity = "daily"
                elif w == '2':
                    end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                    start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
                    granularity = "weekly"
                elif w == '3':
                    end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                    granularity = "monthly"
                else:
                    print("[FAIL] 选择无效")
                    input("按回车键返回...")
                    return

                print(f"\n[LIST] 参数确认：")
                print(f"   账号: {account_label}")
                print(f"   店铺: {shop.name}")
                print(f"   时间范围: {start_date} ~ {end_date}")
                print(f"   粒度: {granularity}")

                if input("\n确认开始导出? (y/n): ").strip().lower() not in ['y','yes','是']:
                    return

                # 组件化导出（优先）
                print("\n[START] 启动组件化导出...")
                success = self._try_component_export(account, shop, start_date, end_date, account_label, granularity, exporter=exp, analytics_type=analytics_type)

                if not success:
                    print("\n[WARN] 组件化导出失败，回退到服务层导出...")
                    # 回退到现有的服务层导出
                    ok, msg, path = exp.export_traffic_overview(
                        account=account,
                        shop=shop,
                        start_date=start_date,
                        end_date=end_date,
                        account_label=account_label,
                        output_root=Path('temp/outputs')
                    )
                    if ok:
                        print(f"\n[OK] 服务层导出成功: {path}")
                    else:
                        print(f"\n[FAIL] 服务层导出也失败: {msg}")

                input("\n按回车键返回...")
        except Exception as e:
            from modules.core.logger import get_logger
            get_logger(__name__).error(f"组件化流量表现导出异常: {e}")
            print(f"[FAIL] 异常: {e}")
            # 如果上层已有 Playwright + 持久化上下文（exporter.pb），为避免跨线程错误，直接在当前线程复用
            # 出错时直接返回，交由服务层回退，不在此处引用上层 exporter 变量
            return False

    def _try_component_export(self, account, shop, start_date, end_date, account_label, granularity, exporter=None, analytics_type: str = "traffic"):
        """尝试组件化导出
        优先复用调用方已有的 Playwright/持久化上下文，避免重复启动造成 user_data_dir 冲突。
        """
        try:
            from modules.components.base import ExecutionContext
            from modules.platforms.shopee.components.navigation import ShopeeNavigation
            from modules.platforms.shopee.components.analytics_export import ShopeeAnalyticsExport
            from modules.platforms.shopee.components.analytics_config import AnalyticsSelectors, TargetPage
            from modules.utils.persistent_browser_manager import PersistentBrowserManager

            # 创建执行上下文（带平台与选中店铺）
            from copy import deepcopy
            account_ctx = deepcopy(account)
            account_ctx["label"] = account_label  # 统一注入账号标签，供组件读取
            account_ctx["shop_id"] = str(shop.id)
            account_ctx["cnsc_shop_id"] = str(shop.id)
            # 覆盖为当前选择的店铺名称，避免账号名与店铺名相同导致目录重复
            account_ctx["store_name"] = shop.name
            #   date_preset
            try:
                from datetime import datetime
                sd = datetime.strptime(str(start_date), "%Y-%m-%d")
                ed = datetime.strptime(str(end_date), "%Y-%m-%d")
                days = (ed - sd).days + 1
                if days == 1:
                    date_preset = "yesterday"
                elif days == 7:
                    date_preset = "last7"
                elif days == 30:
                    date_preset = "last30"
                else:
                    date_preset = None
            except Exception:
                date_preset = None

            # 创建带日志的执行上下文 + 下载目录
            from modules.utils.logger import logger
            def _safe(s: str) -> str:
                return "".join(c if c.isalnum() or c in "._-" else "_" for c in str(s))
            downloads_dir = Path("temp/outputs") / "shopee" / _safe(account_label) / _safe(shop.name) / ".downloads"
            downloads_dir.mkdir(parents=True, exist_ok=True)
            cfg = {"downloads_path": str(downloads_dir), "granularity": granularity, "start_date": str(start_date), "end_date": str(end_date), "shop_name": getattr(shop, 'name', None), "one_click": bool(getattr(self, "_one_click_mode", False))}
            if date_preset:
                cfg["date_preset"] = date_preset
            # 注入选中店铺名，供组件统一使用
            account_ctx['selected_shop_name'] = getattr(shop, 'name', None)
            ctx = ExecutionContext(
                platform="shopee",
                account=account_ctx,
                logger=logger,
                config=cfg,
            )
            selectors = AnalyticsSelectors()

            # 创建组件
            navigation = ShopeeNavigation(ctx, selectors)
            analytics_exporter = ShopeeAnalyticsExport(ctx, selectors)

            # 子类型中文名映射（用于日志显示）
            type_names = {"traffic": "流量表现", "order": "订单表现", "finance": "财务表现", "product": "商品表现"}
            type_name = type_names.get(analytics_type, analytics_type)

            # 优先复用上层 exporter 的持久化上下文，避免再次初始化
            if exporter is not None and hasattr(exporter, 'pb'):

                try:
                    bm = exporter.pb
                    account_id = (
                        account.get('account_id')
                        or account.get('username')
                        or account.get('store_name')
                        or account.get('label')
                        or 'unknown'
                    )
                    context = bm.get_or_create_persistent_context(
                        platform="shopee",
                        account_id=str(account_id),
                        account_config=account,
                        accept_downloads=True,
                        downloads_path=str(downloads_dir),
                    )
                    page = context.pages[0] if context.pages else context.new_page()
                    # 根据类型选择导航目标
                    target_map = {
                        "traffic": TargetPage.TRAFFIC_OVERVIEW,
                        "order": TargetPage.ORDER_PERFORMANCE,
                        "finance": TargetPage.FINANCE_PERFORMANCE,
                        "product": TargetPage.PRODUCTS_PERFORMANCE
                    }
                    target = target_map.get(analytics_type, TargetPage.TRAFFIC_OVERVIEW)
                    print(f"[LOC] 导航到{type_name}页面...")
                    nav_result = navigation.run(page, target)
                    if not nav_result.success:
                        print(f"[FAIL] 导航失败: {nav_result.message}")
                        return False
                    print(f"[OK] 导航成功: {nav_result.url}")
                    print("[WAIT] 等待页面加载...")
                    page.wait_for_timeout(1500)

                    # 统一时间设置：使用 DateSelectionManager（配方优先 -> 快捷项回退 -> 严格校验）
                    try:
                        from modules.services.date_selection_manager import DateSelectionManager
                        preset = (ctx.config or {}).get("date_preset")
                        mgr = DateSelectionManager(playwright=bm)
                        ok = mgr.select_and_verify(
                            page=page,
                            preset=preset,
                            start_date=str(start_date),
                            end_date=str(end_date),
                            context=analytics_type,
                        )
                        if not ok:
                            print("[FAIL] 时间选择未生效，请稍后重试或检查页面结构")
                            return False
                    except Exception as e:
                        print(f"[WARN] 时间设置流程异常: {e}")

                    print("[DATA] 执行组件化导出...")
                    export_result = analytics_exporter.run(page)
                    try:
                        page.close()
                    except Exception:
                        pass
                    try:
                        bm.close_context("shopee", str(account_id))
                    except Exception:
                        pass
                    try:
                        bm.close_all_contexts()
                    except Exception:
                        pass
                    if export_result and export_result.success:
                        print(f"[OK] 组件化导出成功: {export_result.file_path}")
                        return True
                    else:
                        error_msg = export_result.message if export_result else "导出结果为空"
                        print(f"[FAIL] 组件化导出失败: {error_msg}")
                        return False
                except Exception as reuse_e:
                    print(f"[WARN] 复用上层上下文失败，将采用隔离线程方案: {reuse_e}")


            # 在独立线程中使用 Playwright Sync API，避免在已有 asyncio loop 中报错
            def _component_worker() -> bool:
                from playwright.sync_api import sync_playwright
                try:
                    with sync_playwright() as pw:
                        bm = PersistentBrowserManager(pw)
                        account_id = (
                            account.get('account_id')
                            or account.get('username')
                            or account.get('store_name')
                            or account.get('label')
                            or 'unknown'
                        )

                        try:
                            context = bm.get_or_create_persistent_context(
                                platform="shopee",
                                account_id=str(account_id),
                                account_config=account,
                                accept_downloads=True,
                                downloads_path=str(downloads_dir),
                            )
                        except Exception as e:
                            print(f"[WARN] 持久化上下文创建失败，使用普通浏览器: {e}")
                            browser = pw.chromium.launch(headless=False)
                            context = browser.new_context(accept_downloads=True, downloads_path=str(downloads_dir))

                        page = None
                        try:
                            page = context.pages[0] if context.pages else context.new_page()
                            # 根据类型选择导航目标（隔离线程分支）
                            target_map = {
                                "traffic": TargetPage.TRAFFIC_OVERVIEW,
                                "order": TargetPage.ORDER_PERFORMANCE,
                                "finance": TargetPage.FINANCE_PERFORMANCE,
                                "product": TargetPage.PRODUCTS_PERFORMANCE
                            }
                            target = target_map.get(analytics_type, TargetPage.TRAFFIC_OVERVIEW)
                            print(f"[LOC] 导航到{type_name}页面...")
                            nav_result = navigation.run(page, target)
                            if not nav_result.success:
                                print(f"[FAIL] 导航失败: {nav_result.message}")
                                return False
                            print(f"[OK] 导航成功: {nav_result.url}")
                            print("[WAIT] 等待页面加载...")
                            page.wait_for_timeout(1500)

                            # 统一时间设置：使用 DateSelectionManager（配方优先 -> 快捷项回退 -> 严格校验）
                            try:
                                from modules.services.date_selection_manager import DateSelectionManager
                                preset = (ctx.config or {}).get("date_preset")
                                mgr = DateSelectionManager(playwright=bm)
                                ok = mgr.select_and_verify(
                                    page=page,
                                    preset=preset,
                                    start_date=str(start_date),
                                    end_date=str(end_date),
                                    context=analytics_type,
                                )
                                if not ok:
                                    print("[FAIL] 时间选择未生效，请稍后重试或检查页面结构")
                                    return False
                            except Exception as e:
                                print(f"[WARN] 时间设置流程异常: {e}")

                            print("[DATA] 执行组件化导出...")
                            export_result = analytics_exporter.run(page)
                            if export_result and export_result.success:
                                print(f"[OK] 组件化导出成功: {export_result.file_path}")
                                return True
                            else:
                                error_msg = export_result.message if export_result else "导出结果为空"
                                print(f"[FAIL] 组件化导出失败: {error_msg}")
                                return False
                        finally:
                            try:
                                if page:
                                    page.close()
                            except Exception:
                                pass
                            try:
                                bm.close_context("shopee", str(account_id))
                            except Exception:
                                pass
                            try:
                                bm.close_all_contexts()
                            except Exception:
                                pass
                except Exception as e:
                    print(f"[FAIL] 组件化导出异常: {e}")
                    return False

            from threading import Thread
            _result = {"ok": False}
            def _runner():
                _result["ok"] = _component_worker()
            t = Thread(target=_runner, daemon=True)
            t.start()
            t.join()
            return _result["ok"]

        except Exception as e:
            print(f"[FAIL] 组件化导出异常: {e}")
            return False

    def _quick_edit_analytics_config(self):
        """快速编辑 analytics 组件配置（使用智能配置注册中心）"""
        from modules.platforms.shopee.components.config_registry import open_config_file
        open_config_file("analytics")
        input("\n按回车键返回...")

    def _quick_edit_config(self, domain: str):
        """通用智能配置编辑方法"""
        from modules.platforms.shopee.components.config_registry import open_config_file
        open_config_file(domain)
        input("\n按回车键返回...")



    def _run_all_platforms_one_click_batch(self):
        """一键所有平台批量采集：统一选择 -> 逐平台批量执行（Shopee/TikTok/妙手ERP）。
        - 仅调用各平台既有“平台级批量”实现；通过临时预设(_one_click_*)传参以免重复交互；
        - 统一时间范围选择：昨天/近7天/最近28/30天（TikTok/Miaoshou=28天；Shopee=30天）。
        - 统一数据域：优先执行已打通的三类（products/traffic/services）。
        """
        try:
            print("\n[COMPASS] 一键所有平台批量采集")
            print("=" * 40)

            # 标记一键模式（用于抑制子流程中的“按回车返回”提示，并开启明细收集）
            setattr(self, "_one_click_mode", True)
            setattr(self, "_one_click_collector", [])

            # 1) 平台选择（支持多选）
            print("\n[WEB] 选择平台（可多选，用逗号分隔）：")
            print("  1. 全平台 (默认)    2. shopee    3. tiktok    4. miaoshou    5. amazon(占位跳过)")
            pch = (input("请选择 (如: 1 或 2,3): ").strip() or "1").replace("，", ",").replace(" ", "")
            idx_map = {"2": "shopee", "3": "tiktok", "4": "miaoshou", "5": "amazon"}
            if "1" in pch.split(","):
                platforms = ["shopee", "tiktok", "miaoshou"]
            else:
                choices = [idx_map.get(x) for x in pch.split(",") if idx_map.get(x)]
                platforms = choices or ["shopee", "tiktok", "miaoshou"]

            # 2) 时间范围选择（统一）
            from datetime import datetime, timedelta
            print("\n[DATE] 选择时间范围:")
            print("1. 昨天（默认）  2. 过去7天  3. 最近28/30天")
            w = input("请选择 (1-3): ").strip() or "1"
            now = datetime.now()
            y_end = (now - timedelta(days=1)).strftime("%Y-%m-%d")

            def _make_preset(pf: str):
                nonlocal w, y_end
                if w == "2":
                    start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
                    gran = "weekly"
                elif w == "3":
                    if pf == "shopee":
                        start = (now - timedelta(days=30)).strftime("%Y-%m-%d")
                        gran = "monthly"
                    else:
                        start = (now - timedelta(days=28)).strftime("%Y-%m-%d")
                        gran = "monthly"
                else:
                    start = y_end
                    gran = "daily"
                return {
                    "platform": pf,
                    "start_date": start,
                    "end_date": y_end,
                    "granularity": gran,
                }

            # 3) 统一数据域（按现状：Shopee/TikTok 执行三类；妙手ERP执行 商品+订单）
            default_domains = {
                "shopee": ["products", "traffic", "services"],
                "tiktok": ["products", "traffic", "services"],
                "miaoshou": ["products", "orders"],
            }

            # 3.1）打印计划
            print("\n[PUZZLE] 计划执行清单：")
            for pf in platforms:
                if pf == "amazon":
                    print("  - amazon: 占位（跳过）")
                    continue
                preset_preview = _make_preset(pf)
                doms = ", ".join(default_domains.get(pf, ["products","traffic","services"]))
                print(f"  - {pf}: {preset_preview['start_date']} ~ {preset_preview['end_date']} · 域: {doms}")

            # 3.2）执行模式选择：顺序 或 并行（Beta 占位，当前回退为顺序）
            print("\n[GEAR] 执行模式：")
            print("  1. 顺序执行（默认，稳定）")
            print("  2. 并行执行（Beta）")
            exec_mode = (input("请选择 (1-2): ").strip() or "1")
            if exec_mode == "2":
                print("\n[START] 并行执行（Beta）：将为每个平台启动独立子进程（Playwright实例隔离）")

            # 4) 执行
            if exec_mode == "2":
                # 并行执行（多进程隔离）：每个平台一个子进程，独立 Playwright 实例
                import sys, os, json, subprocess
                print("\n[START] 并行执行模式：为每个平台启动独立子进程...")
                # 统一验证码等待超时（秒）——用于整体子进程超时控制（默认600）
                try:
                    cap_to = int(input("请输入验证码等待超时(秒，默认600): ").strip() or "600")
                except Exception:
                    cap_to = 600
                procs = []
                for pf in platforms:
                    if pf == "amazon":
                        print("\n[STORE] Amazon 暂为占位，已跳过。")
                        continue
                    preset = _make_preset(pf)
                    domains = default_domains.get(pf, ["products", "traffic", "services"])
                    payload = {"platform": pf, "preset": preset, "domains": domains}
                    env = os.environ.copy()
                    try:
                        env["ONE_CLICK_WORKER_PAYLOAD"] = json.dumps(payload, ensure_ascii=False)
                    except Exception:
                        # 回退_ascii
                        env["ONE_CLICK_WORKER_PAYLOAD"] = json.dumps(payload)
                    # 强制子进程以 UTF-8 输出，避免 Windows GBK 编码问题
                    env["PYTHONIOENCODING"] = "utf-8"
                    env["PYTHONUTF8"] = "1"
                    cmd = [sys.executable, "-c", "from modules.apps.collection_center.app import _one_click_worker_entry; _one_click_worker_entry()"]
                    print(f"  [START] 启动平台进程: {pf}")
                    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
                    procs.append((pf, p))
                # 实时输出与结果收集（流式读取子进程 stdout/stderr）
                coll = getattr(self, "_one_click_collector", []) or []
                import time, threading
                marker = "ONE_CLICK_RESULT_JSON:"
                results: dict[str, str] = {}
                timeouts: set[str] = set()
                threads = []
                # 以“无输出时长”为超时依据，避免长导出过程中被误杀
                last_output: dict[str, float] = {pf: time.time() for pf, _ in procs}
                files_all: list[str] = []
                uris_all: list[str] = []

                def _reader(pf_name, pipe, is_err=False):
                    try:
                        for raw in iter(pipe.readline, b""):
                            try:
                                line = raw.decode("utf-8", errors="ignore").rstrip()
                            except Exception:
                                line = str(raw)
                            # 记录活性心跳
                            last_output[pf_name] = time.time()
                            if line.startswith(marker):
                                results[pf_name] = line[len(marker):].strip()
                            else:
                                prefix = f"[{pf_name}]" if not is_err else f"[{pf_name}][ERR]"
                                print(f"{prefix} {line}")
                    finally:
                        try:
                            pipe.close()
                        except Exception:
                            pass

                for pf, p in procs:
                    t1 = threading.Thread(target=_reader, args=(pf, p.stdout, False), daemon=True)
                    t2 = threading.Thread(target=_reader, args=(pf, p.stderr, True), daemon=True)
                    t1.start(); t2.start()
                    threads.extend([t1, t2])

                alive = {pf: p for pf, p in procs}
                while alive:
                    now = time.time()
                    # 基于“无输出时长”的个体超时控制
                    for pf, p in list(alive.items()):
                        if now - last_output.get(pf, now) > cap_to:
                            try:
                                p.kill()
                            except Exception:
                                pass
                            timeouts.add(pf)
                            del alive[pf]
                    # 移除已结束进程
                    for pf, p in list(alive.items()):
                        if p.poll() is not None:
                            del alive[pf]
                    time.sleep(0.2)

                # 解析各子进程的结果标记，并汇总文件清单
                for pf, _p in procs:
                    result_line = results.get(pf)
                    if result_line:
                        try:
                            r = json.loads(result_line)
                            items = r.get("collector") or []
                            coll.extend(items)
                            # 合并文件清单
                            try:
                                _fs = r.get("files") or []
                                _uris = r.get("file_uris") or []
                                for _f in _fs:
                                    files_all.append(str(_f))
                                for _u in _uris:
                                    uris_all.append(str(_u))
                            except Exception:
                                pass
                            ok = r.get("ok", False)
                            if not ok:
                                print(f"  [FAIL] 子进程异常: {pf} · {r.get('error','')}")
                        except Exception as ex:
                            print(f"  [FAIL] 结果解析失败: {pf} · {ex}")
                            coll.append({"platform": pf, "account": "-", "shop": "-", "domain": "-", "status": "error", "message": "result parse error"})
                    else:
                        if pf in timeouts:
                            print(f"  [NEXT] 超时跳过: {pf}（可能等待验证码超时）")
                            coll.append({"platform": pf, "account": "-", "shop": "-", "domain": "-", "status": "fail", "message": "captcha timeout or worker timeout"})
                        else:
                            print(f"  [FAIL] 未获取到结果标记: {pf}")
                            coll.append({"platform": pf, "account": "-", "shop": "-", "domain": "-", "status": "error", "message": "no result marker"})

                # 写回收集器供后续汇总打印，并附带文件清单
                setattr(self, "_one_click_collector", coll)
                setattr(self, "_one_click_files_all", files_all)
                setattr(self, "_one_click_file_uris_all", uris_all)
            else:
                # 顺序执行（单平台进程串行）
                import sys, os, json, subprocess
                try:
                    cap_to = int(input("请输入验证码等待超时(秒，默认600): ").strip() or "600")
                except Exception:
                    cap_to = 600
                coll = getattr(self, "_one_click_collector", []) or []
                for pf in platforms:
                    if pf == "amazon":
                        print("\n[STORE] Amazon 暂为占位，已跳过。")
                        continue
                    preset = _make_preset(pf)
                    domains = default_domains.get(pf, ["products", "traffic", "services"])
                    payload = {"platform": pf, "preset": preset, "domains": domains}
                    env = os.environ.copy()
                    try:
                        env["ONE_CLICK_WORKER_PAYLOAD"] = json.dumps(payload, ensure_ascii=False)
                    except Exception:
                        env["ONE_CLICK_WORKER_PAYLOAD"] = json.dumps(payload)
                    env["PYTHONIOENCODING"] = "utf-8"
                    env["PYTHONUTF8"] = "1"
                    cmd = [sys.executable, "-c", "from modules.apps.collection_center.app import _one_click_worker_entry; _one_click_worker_entry()"]
                    print(f"  [START] 启动平台进程: {pf}")
                    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
                    try:
                        out, err = p.communicate(timeout=cap_to)
                        text = (out or b"").decode("utf-8", errors="ignore")
                        marker = "ONE_CLICK_RESULT_JSON:"
                        result_line = None
                        for line in text.splitlines()[::-1]:
                            if line.startswith(marker):
                                result_line = line[len(marker):].strip()
                                break
                        if result_line:
                            try:
                                r = json.loads(result_line)
                                items = r.get("collector") or []
                                coll.extend(items)
                                ok = r.get("ok", False)
                                if not ok:
                                    print(f"  [FAIL] 子进程异常: {pf} · {r.get('error','')}")
                            except Exception as ex:
                                print(f"  [FAIL] 结果解析失败: {pf} · {ex}")
                                coll.append({"platform": pf, "account": "-", "shop": "-", "domain": "-", "status": "error", "message": "result parse error"})
                        else:
                            print(f"  [FAIL] 未获取到结果标记: {pf}")
                            coll.append({"platform": pf, "account": "-", "shop": "-", "domain": "-", "status": "error", "message": "no result marker"})
                    except subprocess.TimeoutExpired:
                        try:
                            p.kill()
                        except Exception:
                            pass
                        print(f"  [NEXT] 超时跳过: {pf}（可能等待验证码超时）")
                        coll.append({"platform": pf, "account": "-", "shop": "-", "domain": "-", "status": "fail", "message": "captcha timeout or worker timeout"})
                setattr(self, "_one_click_collector", coll)

            # 5) 汇总：按平台/账号/店铺/数据域输出失败清单
            coll = getattr(self, "_one_click_collector", []) or []
            total = len(coll)
            succ = sum(1 for r in coll if r.get("status") == "success")
            fail = sum(1 for r in coll if r.get("status") in {"fail","error"})
            print("\n[DATA] 一键采集汇总：")
            print(f"   总任务: {total} | [OK] 成功: {succ} | [FAIL] 失败: {fail}")
            if fail:
                print("\n[RECEIPT] 失败明细（平台 / 账号 / 店铺 / 数据域 / 信息）：")
                for r in coll:
                    if r.get("status") in {"fail","error"}:
                        print(f"   - {r.get('platform')} / {r.get('account')} / {r.get('shop')} / {r.get('domain')} / {r.get('message','')}")


            # 打印所有成功导出的文件清单（来自各子进程聚合）
            try:
                files_all = getattr(self, "_one_click_files_all", []) or []
                if files_all:
                    print("\n[FILES] 导出文件清单（全部平台）：")
                    for ap in files_all:
                        print(f"  - {ap}")
                        print(f"EXPORTED_FILE:{ap}")
            except Exception:
                pass

            print("\n[OK] 全平台批量采集执行完毕。")
            if not getattr(self, "_one_click_mode", False):
                input("按回车键返回...")
        except Exception as e:
            print(f"[FAIL] 一键批量采集异常: {e}")
            if not getattr(self, "_one_click_mode", False):
                input("按回车键返回...")
        finally:
            # 清理一键标记
            if hasattr(self, "_one_click_mode"):
                try:
                    delattr(self, "_one_click_mode")
                except Exception:
                    pass
            if hasattr(self, "_one_click_collector"):
                try:
                    delattr(self, "_one_click_collector")
                except Exception:
                    pass


# —— 并行子进程入口：读取环境变量中的JSON负载，执行单平台批量并输出结果 ——
def _one_click_worker_entry():
    """Subprocess entry for one-click platform worker.
    Reads ONE_CLICK_WORKER_PAYLOAD from environment, runs the specified platform
    batch in one-click mode, and prints a single JSON line prefixed by
    'ONE_CLICK_RESULT_JSON:' for the parent process to parse.
    """
    import os, json, sys
    try:
        payload_raw = os.environ.get("ONE_CLICK_WORKER_PAYLOAD", "{}")
        payload = json.loads(payload_raw)
    except Exception as e:  # payload解析失败
        print("ONE_CLICK_RESULT_JSON:" + json.dumps({
            "platform": "unknown", "ok": False, "collector": [], "error": f"payload error: {e}",
        }, ensure_ascii=False))
        sys.exit(1)

    pf = payload.get("platform")
    preset = payload.get("preset") or {}
    domains = payload.get("domains") or []

    # 惰性导入防止模块顶层副作用
    from modules.apps.collection_center.app import CollectionCenterApp  # type: ignore

    app = CollectionCenterApp()
    # 一键模式下抑制所有交互暂停，并收集明细
    setattr(app, "_one_click_mode", True)
    setattr(app, "_one_click_preset", preset)
    setattr(app, "_one_click_domains", domains)
    setattr(app, "_one_click_collector", [])
    setattr(app, "_one_click_files", [])


    ok = True
    err = ""
    # 子进程起始提示（便于父进程实时观察）
    try:
        print(f"[{pf}] worker start · domains={domains}", flush=True)
    except Exception:
        pass
    try:
        if pf == "shopee":
            app._run_multi_domain_platform_wide_batch()
        elif pf == "tiktok":
            app._run_tiktok_platform_wide_batch()
        elif pf == "miaoshou":
            app._run_miaoshou_platform_wide_batch()
        else:
            ok = False
            err = f"unknown platform: {pf}"
    except Exception as e:
        ok = False
        err = str(e)
    # 子进程结束总结（成功/失败数）
    try:
        _coll = getattr(app, "_one_click_collector", []) or []
        _succ = sum(1 for r in _coll if r.get("status") == "success")
        _fail = sum(1 for r in _coll if r.get("status") in {"fail", "error"})
        print(f"[{pf}] worker done · total={len(_coll)} succ={_succ} fail={_fail}", flush=True)
    except Exception:
        pass

    # 汇总导出文件并打印清单（便于测试快速验证）
    try:
        import os
        files = getattr(app, "_one_click_files", []) or []
        abs_files = []
        file_uris = []
        for f in files:
            ap = os.path.abspath(str(f))
            abs_files.append(ap)
            try:
                uri = "file:///" + ap.replace("\\", "/")
                file_uris.append(uri)
            except Exception:
                pass
        if abs_files:
            print("\n[FILES] 导出文件清单：", flush=True)
            for ap in abs_files:
                print(f"  - {ap}", flush=True)
                # 解析友好标记，便于父进程或人工快速定位
                print(f"EXPORTED_FILE:{ap}", flush=True)
    except Exception:
        abs_files = []
        file_uris = []

    result = {
        "platform": pf,
        "ok": ok,
        "collector": getattr(app, "_one_click_collector", []) or [],
        "files": abs_files,
        "file_uris": file_uris,
        "error": err,
    }
    print("ONE_CLICK_RESULT_JSON:" + json.dumps(result, ensure_ascii=False))
    sys.exit(0 if ok else 1)
