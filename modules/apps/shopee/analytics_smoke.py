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

from modules.apps.collection_center.browser_config_helper import (
    get_browser_context_args,
    get_browser_launch_args,
)
from modules.components.base import ExecutionContext
from modules.core.logger import get_logger
from modules.platforms.shopee.components.analytics_export import ShopeeAnalyticsExport


def classify_environment_state(*, url: str, title: str, body_text: str) -> str:
    current_url = str(url or "").strip().lower()
    current_title = str(title or "").strip().lower()
    current_body = " ".join(str(body_text or "").strip().lower().split())

    if "/account/signin" in current_url or "signin" in current_url:
        return "login_required"

    if current_body in {"", "s"}:
        return "loading_blocked"

    loading_markers = (
        "window.__performancebodyscriptstarttime",
        "window.__performanceframeworkscriptstarttime",
    )
    if any(marker in current_body for marker in loading_markers):
        return "loading_blocked"

    business_signals = (
        "gmt+",
        "下载数据",
        "流量",
    )
    if "/datacenter/traffic/overview" in current_url and any(
        signal in current_title or signal in current_body for signal in business_signals
    ):
        return "business_ready"

    return "unknown"


class AnalyticsSmokeProbe(ShopeeAnalyticsExport):
    async def debug_date_picker(self, page: Any) -> dict[str, Any]:
        diagnostics: dict[str, Any] = {
            "url_before_ready": str(getattr(page, "url", "") or ""),
            "ready_error": None,
            "url_after_ready": None,
            "trigger_candidates": [],
            "trigger_found": False,
            "trigger_selector": None,
            "panel_found": False,
            "panel_text_sample": None,
        }

        try:
            await self._ensure_products_page_ready(page)
        except Exception as exc:  # noqa: BLE001
            diagnostics["ready_error"] = str(exc)
            return diagnostics

        diagnostics["url_after_ready"] = str(getattr(page, "url", "") or "")

        for selector in self.sel.date_picker_triggers:
            item = {
                "selector": selector,
                "count": 0,
                "visible": False,
                "text": None,
            }
            try:
                locator = page.locator(selector)
                item["count"] = await locator.count()
                if item["count"] > 0:
                    probe = locator.first
                    try:
                        item["visible"] = bool(await probe.is_visible())
                    except Exception:
                        item["visible"] = False
                    try:
                        item["text"] = (await probe.text_content()) or None
                    except Exception:
                        item["text"] = None
            except Exception as exc:  # noqa: BLE001
                item["error"] = str(exc)
            diagnostics["trigger_candidates"].append(item)

        trigger = await self._find_date_picker_trigger(page)
        if trigger is None:
            return diagnostics

        diagnostics["trigger_found"] = True
        try:
            diagnostics["trigger_selector"] = await trigger.evaluate(
                """(node) => {
                    const text = (node.textContent || '').trim();
                    const tag = (node.tagName || '').toLowerCase();
                    const cls = node.className || '';
                    return `${tag}|${cls}|${text}`;
                }"""
            )
        except Exception:
            diagnostics["trigger_selector"] = "unavailable"

        await self._open_date_picker(page)
        panel = await self._find_date_panel(page)
        if panel is None:
            return diagnostics

        diagnostics["panel_found"] = True
        try:
            panel_text = (await panel.text_content()) or ""
            diagnostics["panel_text_sample"] = panel_text[:500]
        except Exception:
            diagnostics["panel_text_sample"] = None
        return diagnostics


async def wait_for_environment_ready(page: Any, *, timeout_ms: int = 30000, poll_ms: int = 1000) -> dict[str, Any]:
    elapsed = 0
    samples: list[dict[str, Any]] = []

    while elapsed <= timeout_ms:
        url = str(getattr(page, "url", "") or "")
        try:
            title = await page.title()
        except Exception:
            title = ""
        try:
            body_text = await page.locator("body").text_content()
        except Exception:
            body_text = ""

        state = classify_environment_state(url=url, title=title, body_text=body_text or "")
        samples.append(
            {
                "elapsed_ms": elapsed,
                "state": state,
                "url": url,
                "title": title,
                "body_sample": (body_text or "")[:300],
            }
        )

        if state in {"login_required", "business_ready"}:
            return {
                "final_state": state,
                "timed_out": False,
                "url": url,
                "title": title,
                "body_sample": (body_text or "")[:500],
                "samples": samples,
            }

        if hasattr(page, "wait_for_timeout"):
            await page.wait_for_timeout(poll_ms)
        elapsed += poll_ms

    url = str(getattr(page, "url", "") or "")
    try:
        title = await page.title()
    except Exception:
        title = ""
    try:
        body_text = await page.locator("body").text_content()
    except Exception:
        body_text = ""

    final_state = classify_environment_state(url=url, title=title, body_text=body_text or "")
    if final_state == "unknown":
        final_state = "loading_blocked"

    return {
        "final_state": final_state,
        "timed_out": True,
        "url": url,
        "title": title,
        "body_sample": (body_text or "")[:500],
        "samples": samples,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Shopee analytics date picker smoke probe")
    parser.add_argument(
        "--profile-dir",
        default=str(Path("output/playwright/profiles/shopee")),
        help="Persistent Playwright profile directory",
    )
    parser.add_argument(
        "--work-dir",
        default=str(Path("output/playwright/work/shopee/analytics-smoke")),
        help="Artifacts output directory",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode",
    )
    parser.add_argument(
        "--storage-state",
        default="",
        help="Optional storage_state json path for non-persistent fallback run",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    logger = get_logger("shopee.analytics_smoke")
    profile_dir = Path(args.profile_dir).resolve()
    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    storage_state_path = Path(args.storage_state).resolve() if args.storage_state else None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_before = work_dir / f"{timestamp}-before-open.png"
    screenshot_after = work_dir / f"{timestamp}-after-open.png"
    result_path = work_dir / f"{timestamp}-result.json"

    logger.info("analytics smoke starting")
    logger.info("profile_dir=%s", profile_dir)
    logger.info("work_dir=%s", work_dir)

    if not profile_dir.exists():
        payload = {
            "ok": False,
            "error": f"profile dir not found: {profile_dir}",
        }
        result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.error(payload["error"])
        return 2

    launch_args = get_browser_launch_args(debug_mode=not args.headless)
    launch_args["headless"] = bool(args.headless)
    context_args = get_browser_context_args()

    payload: dict[str, Any] = {
        "ok": False,
        "profile_dir": str(profile_dir),
        "storage_state": str(storage_state_path) if storage_state_path else None,
        "work_dir": str(work_dir),
        "headless": bool(args.headless),
        "result_path": str(result_path),
        "screenshots": {
            "before": str(screenshot_before),
            "after": str(screenshot_after),
        },
    }

    async with async_playwright() as playwright:
        browser = None
        context = None
        try:
            if storage_state_path and storage_state_path.exists():
                browser = await playwright.chromium.launch(**launch_args)
                context = await browser.new_context(
                    **context_args,
                    storage_state=str(storage_state_path),
                )
                payload["session_mode"] = "storage_state"
            else:
                context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir),
                    **launch_args,
                    **context_args,
                )
                payload["session_mode"] = "persistent_profile"

            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto("https://seller.shopee.cn/datacenter/traffic/overview", wait_until="domcontentloaded", timeout=60000)
            environment = await wait_for_environment_ready(page)
            payload["environment"] = environment
            await page.screenshot(path=str(screenshot_before), full_page=False)

            if environment["final_state"] != "business_ready":
                payload["ok"] = False
                payload["environment_failure"] = True
                payload["failure_kind"] = environment["final_state"]
                await page.screenshot(path=str(screenshot_after), full_page=False)
                result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                logger.warning("analytics smoke stopped before component probe: %s", environment["final_state"])
                logger.info("result_path=%s", result_path)
                return 1

            probe = AnalyticsSmokeProbe(
                ExecutionContext(
                    platform="shopee",
                    account={"label": "smoke", "store_name": "smoke"},
                    logger=logger,
                    config={"granularity": "daily"},
                    is_test_mode=True,
                )
            )
            diagnostics = await probe.debug_date_picker(page)
            payload["diagnostics"] = diagnostics

            await page.screenshot(path=str(screenshot_after), full_page=False)

            payload["ok"] = bool(diagnostics.get("trigger_found") and diagnostics.get("panel_found"))
            result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("analytics smoke completed ok=%s", payload["ok"])
            logger.info("result_path=%s", result_path)
            return 0 if payload["ok"] else 1
        except Exception as exc:  # noqa: BLE001
            payload["ok"] = False
            payload["error"] = str(exc)
            result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.error("analytics smoke failed: %s", exc)
            logger.info("result_path=%s", result_path)
            return 2
        finally:
            if context is not None:
                await context.close()
            if browser is not None:
                await browser.close()


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
