#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HAR Capture Utilities
=====================

提供独立的 HAR 录制工具函数，便于在录制向导中调用，避免复杂缩进与 try/except 嵌套问题。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional


def run_har_capture(playwright, current_page, *, platform_key: str, account_id: str,
                    account_label: str, platform_display: str, data_type_key: str) -> Path:
    """在新窗口中开启 HAR 抓取，按 Enter 结束，返回 HAR 路径。

    说明：
    - 复用 current_page 所在上下文的 storage_state，实现免登
    - 新建非持久化上下文 record_har_path + embed，确保只捕获确认后的操作
    - 用户按 Enter 结束后关闭上下文并写出 HAR 文件
    """
    # 延迟 import，规避全局依赖
    from playwright.sync_api import Playwright  # noqa: F401

    try:
        current_url = current_page.url
    except Exception:
        current_url = "about:blank"
    try:
        storage_state = current_page.context.storage_state()
    except Exception:
        storage_state = None

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("temp/har")
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_account = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in str(account_label)) or "account"
    har_path = out_dir / f"{ts}_{platform_key}_{safe_account}_{data_type_key}.har"
    meta_path = out_dir / f"{ts}_{platform_key}_{safe_account}_{data_type_key}.metadata.json"

    print("\n[TOOLKIT] 正在创建录制专用窗口（开启 HAR 捕获）...")
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context(
        storage_state=storage_state,
        record_har_path=str(har_path),
        record_har_content="embed",
        accept_downloads=True,
        viewport={"width": 1440, "height": 900},
    )
    page = context.new_page()
    if current_url and current_url != "about:blank":
        print(f"[LINK] 录制窗口直达: {current_url}")
        try:
            page.goto(current_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"[WARN] 录制窗口导航异常: {e}")

    keywords = ["export", "datacenter", "traffic", "product", "finance", "order"]

    def _on_response(resp):
        try:
            url = resp.url
            if any(k in url for k in keywords):
                print(f"[SIGNAL] RESPONSE {resp.status}: {url}")
        except Exception:
            pass

    page.on("response", _on_response)

    # 自动打开 Playwright Inspector（可视化录制面板）
    try:
        print("\n[TOOLS] 正在启动Playwright Inspector（可视化录制面板）...")
        page.pause()  # 将弹出 Inspector，用户点击“Resume”后继续
    except Exception as e:
        print(f"[WARN] 无法自动打开Inspector: {e}")

    print("\n[LIST] 说明：")
    print("- 请在【录制专用窗口】中进行以下操作：")
    print("  1) 切换 统计时间 -> 按周，选择目标周度")
    print("  2) 勾选需要的指标")
    print("  3) 点击 导出")
    print("- 操作完成后，回到终端按 Enter 结束 HAR 捕获...")

    input("\n[STOP]  按 Enter 结束捕获并保存 HAR... ")

    meta = {
        "platform": platform_display,
        "platform_key": platform_key,
        "account_id": account_id,
        "account_label": account_label,
        "data_type": data_type_key,
        "start_url": current_url,
        "har_file": str(har_path),
        "created_at": ts,
    }
    try:
        meta_path.write_text(import_json_dumps(meta), encoding="utf-8")
        print(f"[NOTE] 已保存元数据: {meta_path}")
    except Exception as e:
        print(f"[WARN] 无法写入元数据: {e}")

    try:
        context.close()
        browser.close()
    except Exception as e:
        print(f"[WARN] 关闭录制窗口失败: {e}")

    print(f"\n[OK] HAR 捕获完成: {har_path}")
    print("   请把该文件或路径发我，我将解析参数并生成参数化导出配置。")
    return har_path


def import_json_dumps(obj) -> str:
    """延迟导入 json.dumps，避免顶层导入副作用。"""
    import json

    return json.dumps(obj, ensure_ascii=False, indent=2)

