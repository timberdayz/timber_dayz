#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

_THIS_DIR = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from playwright.async_api import async_playwright

from modules.core.logger import get_logger
from tools.test_component import ComponentTester
from modules.apps.collection_center.python_component_adapter import create_adapter
from modules.platforms.shopee.components.analytics_export import ShopeeAnalyticsExport


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Shopee analytics export in runtime-aligned component test mode")
    parser.add_argument("--account-id", default="shopee-smoke", help="Logical account id used for session/fingerprint scope")
    parser.add_argument("--storage-state", default="", help="Optional storage_state json path")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument(
        "--work-dir",
        default=str(Path("output/playwright/work/shopee/analytics-runtime-smoke")),
        help="Artifacts output directory",
    )
    parser.add_argument(
        "--login-url",
        default="https://seller.shopee.cn",
        help="Base login URL used by login-gate priming",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    logger = get_logger("shopee.analytics_runtime_smoke")
    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    storage_state_path = Path(args.storage_state).resolve() if args.storage_state else None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = work_dir / f"{timestamp}-result.json"
    screenshot_before = work_dir / f"{timestamp}-before.png"
    screenshot_after = work_dir / f"{timestamp}-after.png"

    payload: dict[str, Any] = {
        "ok": False,
        "account_id": args.account_id,
        "headless": bool(args.headless),
        "storage_state": str(storage_state_path) if storage_state_path else None,
        "result_path": str(result_path),
        "screenshots": {
            "before": str(screenshot_before),
            "after": str(screenshot_after),
        },
    }

    runtime_config = {
        "data_domain": "analytics",
        "granularity": "daily",
        "output_dir": str(work_dir),
    }
    account_info = {
        "account_id": args.account_id,
        "shop_account_id": args.account_id,
        "platform": "shopee",
        "username": "",
        "password": "",
        "store_name": "runtime_smoke",
        "label": "runtime_smoke",
        "login_url": args.login_url,
    }

    tester = ComponentTester(
        platform="shopee",
        account_id=args.account_id,
        skip_login=False,
        headless=args.headless,
        screenshot_on_error=True,
        output_dir=str(work_dir),
        account_info=account_info,
        runtime_config=runtime_config,
    )

    async with async_playwright() as playwright:
        browser = None
        context = None
        try:
            browser = await playwright.chromium.launch(
                **tester._build_browser_launch_kwargs(
                    args=["--start-maximized"] if not args.headless else []
                )
            )

            storage_state = None
            if storage_state_path and storage_state_path.exists():
                with storage_state_path.open("r", encoding="utf-8") as fh:
                    storage_state = json.load(fh)

            context_options = await tester._build_component_browser_context_options(
                account_id=args.account_id,
                account_info=account_info,
                storage_state=storage_state,
                headless=args.headless,
            )
            context = await browser.new_context(**context_options)
            page = await context.new_page()

            await tester._prime_page_for_login_gate(
                page,
                account_info,
                component_type="export",
                component_name="analytics_export",
            )
            payload["primed_url"] = str(getattr(page, "url", "") or "")

            await page.screenshot(path=str(screenshot_before), full_page=False)

            from tools.test_component import ComponentTestResult, TestStatus

            gate_result = ComponentTestResult(
                component_name="analytics_export",
                platform="shopee",
                status=TestStatus.RUNNING,
            )
            login_gate_ready = await tester._check_login_gate(
                page=page,
                result=gate_result,
                component_name="shopee/login",
            )
            payload["login_gate_ready"] = bool(login_gate_ready)
            payload["login_gate_error"] = gate_result.error
            if not login_gate_ready:
                await page.screenshot(path=str(screenshot_after), full_page=False)
                result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                return 1

            adapter = create_adapter(
                platform="shopee",
                account=account_info,
                config=runtime_config,
                is_test_mode=True,
                override_export_class=ShopeeAnalyticsExport,
            )
            export_result = await adapter.export(page=page, data_domain="analytics")
            payload["export_result"] = {
                "success": bool(getattr(export_result, "success", False)),
                "message": getattr(export_result, "message", ""),
                "file_path": getattr(export_result, "file_path", None),
            }

            await page.screenshot(path=str(screenshot_after), full_page=False)
            payload["ok"] = bool(payload["export_result"]["success"])
            result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("analytics runtime smoke completed ok=%s", payload["ok"])
            logger.info("result_path=%s", result_path)
            return 0 if payload["ok"] else 1
        except Exception as exc:  # noqa: BLE001
            payload["error"] = str(exc)
            result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.error("analytics runtime smoke failed: %s", exc)
            logger.info("result_path=%s", result_path)
            return 2
        finally:
            if context is not None:
                await context.close()
            if browser is not None:
                await browser.close()


def main() -> int:
    args = _build_parser().parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
