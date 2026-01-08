#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强录制向导（精简安全版）
- 修复：此前文件被杂质字符（NUL）污染，导致导入时报 SyntaxError: source code string cannot contain null bytes
- 该精简版仅提供最小可用能力：平台/数据类型选择 + 为录制预热浏览器会话
- 真正的录制/回放仍走 temp/recordings/ 下你的脚本；本向导不修改磁盘脚本
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from modules.utils.logger import get_logger
from modules.utils.account_manager import AccountManager
from modules.utils.persistent_browser_manager import PersistentBrowserManager
from playwright.sync_api import sync_playwright

logger = get_logger(__name__)


class EnhancedRecordingWizard:
    """最小可用的录制向导。"""

    def __init__(self) -> None:
        self.am = AccountManager()

    def _select_platform(self) -> Optional[str]:
        print("\n[WEB] 选择平台：")
        print("  1. Shopee    2. TikTok    3. 妙手ERP    0. 返回")
        ch = input("请选择 (0-3): ").strip()
        if ch == "1":
            return "shopee"
        if ch == "2":
            return "tiktok"
        if ch == "3":
            return "miaoshou"
        return None

    def _select_account(self, platform: str) -> Optional[Dict[str, Any]]:
        accounts = self.am.get_accounts_by_platform(platform)
        if not accounts:
            print("[FAIL] 未找到账号，请先在账号管理中配置")
            return None
        print("\n[USER] 选择账号：")
        for i, a in enumerate(accounts, 1):
            label = (
                a.get('label') or a.get('store_name') or a.get('account_label')
                or a.get('username') or f"{platform}:{a.get('region') or a.get('shop_region') or ''}"
            )
            print(f"  {i}. {label}")
        idx = input(f"请选择 (1-{len(accounts)}): ").strip()
        try:
            i = int(idx) - 1
            if 0 <= i < len(accounts):
                return accounts[i]
        except Exception:
            pass
        print("[FAIL] 无效选择")
        return None

    def _select_dtype(self) -> Optional[str]:
        print("\n[DATA] 选择录制数据类型：")
        print("  1. orders    2. products    3. analytics    4. finance    5. services    0. 返回")
        ch = input("请选择 (0-5): ").strip()
        return {
            "1": "orders",
            "2": "products",
            "3": "analytics",
            "4": "finance",
            "5": "services",
        }.get(ch)

    def _default_entry(self, platform: str, dtype: str, account: Dict[str, Any]) -> str:
        """为录制提供一个安全入口 URL（无副作用）。"""
        if platform == "tiktok":
            # TikTok 流量页禁止带时间参数，仅允许 shop_region
            base = "https://seller.tiktokshopglobalselling.com"
            if dtype == "analytics":
                region = account.get("shop_region") or account.get("region") or "SG"
                return f"{base}/compass/data-overview?shop_region={region}"
            return base
        if platform == "shopee":
            return "https://seller.shopee.cn/"
        if platform == "miaoshou":
            # 入口优先使用账号配置的 login_url，未配置则进入欢迎页
            return account.get("login_url") or "https://erp.91miaoshou.com/?redirect=%2Fwelcome"
        return "about:blank"

    def run_wizard(self) -> None:
        platform = self._select_platform()
        if not platform:
            return
        account = self._select_account(platform)
        if not account:
            return
        dtype = self._select_dtype()
        if not dtype:
            return

        with sync_playwright() as p:
            pb = PersistentBrowserManager(p)
            acc_label = account.get("store_name") or account.get("username") or str(account.get("account_id") or "account")
            ctx = pb.get_or_create_persistent_context(platform, str(acc_label), account)
            page = ctx.new_page()
            url = self._default_entry(platform, dtype, account)
            print(f"\n[START] 已启动持久化上下文，打开入口: {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
            except Exception:
                try:
                    page.goto(url, wait_until="load", timeout=60000)
                except Exception as e:
                    logger.warning(f"打开入口失败: {e}")

            print("\n[ACTION] 现在你可以开始进行录制：")
            print("   • 登录并进入目标页面")
            print("   • 完成你要录制的操作路径（如时间选择、导出等）")
            print("   • 你的录制脚本保存路径建议：temp/recordings/<platform>/...")
            input("\n按回车键结束（将保存会话以便回放）...")

            try:
                pb.save_context_state(ctx, platform, str(acc_label))
            except Exception:
                pass
            try:
                pb.close_context(platform, str(acc_label))
            except Exception:
                pass

        print("\n[OK] 录制会话结束。你可以在‘运行录制脚本’菜单回放。")

