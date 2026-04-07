from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from typing import Any

from modules.components.base import ExecutionContext
from modules.components.export.base import build_standard_output_root
from modules.platforms.shopee.components.analytics_export import ShopeeAnalyticsExport
from modules.platforms.shopee.components.products_config import ProductsSelectors
from modules.platforms.shopee.components.services_config import ServicesSelectors


class ShopeeServicesExportBase(ShopeeAnalyticsExport):
    data_domain = "services"
    sub_domain: str | None = None

    def __init__(
        self,
        ctx: ExecutionContext,
        selectors: ProductsSelectors | None = None,
        service_selectors: ServicesSelectors | None = None,
    ) -> None:
        self.service_sel = service_selectors or ServicesSelectors()
        subtype = self._resolve_subtype_from_config(ctx.config or {})
        path = self._service_path(subtype)
        super().__init__(
            ctx,
            selectors=selectors or replace(
                ProductsSelectors(),
                overview_path=path,
            ),
        )

    def _resolve_subtype_from_config(self, config: dict[str, Any] | None = None) -> str:
        cfg = config or {}
        return str(
            cfg.get("services_subtype")
            or cfg.get("sub_domain")
            or self.sub_domain
            or "ai_assistant"
        ).strip().lower()

    def _resolved_subtype(self, config: dict[str, Any] | None = None) -> str:
        if config is not None:
            return self._resolve_subtype_from_config(config)
        return self._resolve_subtype_from_config(self.ctx.config or {})

    def _service_path(self, subtype: str) -> str:
        normalized = str(subtype or "").strip().lower()
        try:
            return self.service_sel.service_paths[normalized]
        except KeyError as exc:
            raise ValueError(f"unsupported services subtype: {subtype}") from exc

    def _products_page_looks_ready(self, url: str) -> bool:
        current = str(url or "").strip().lower()
        if not current:
            return False
        return self._service_path(self._resolved_subtype()) in current

    async def _ensure_products_page_ready(self, page: Any) -> None:
        if self._products_page_looks_ready(str(getattr(page, "url", "") or "")):
            return
        target_url = f"https://seller.shopee.cn{self._service_path(self._resolved_subtype())}"
        await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        if hasattr(page, "wait_for_timeout"):
            await page.wait_for_timeout(1200)
        if not self._products_page_looks_ready(str(getattr(page, "url", "") or "")):
            raise RuntimeError("services page is not ready")

    def _build_download_target_path(self, out_root: Path, suggested_filename: str) -> Path:
        candidate = out_root / suggested_filename
        if not candidate.exists():
            return candidate

        stem = Path(suggested_filename).stem or f"services-{self._resolved_subtype()}-export"
        suffix = "".join(Path(suggested_filename).suffixes) or ".xlsx"
        index = 1
        while True:
            retry_candidate = out_root / f"{stem}-{index}{suffix}"
            if not retry_candidate.exists():
                return retry_candidate
            index += 1

    async def _wait_download_complete(self, page: Any) -> str | None:
        waiter = self._download_waiter
        if waiter is None:
            if not hasattr(page, "wait_for_event"):
                return None
            try:
                download = await page.wait_for_event("download", timeout=60000)
            except Exception:
                return None
        else:
            try:
                download = await waiter
            except Exception:
                return None
            finally:
                self._download_waiter = None

        granularity = str((self.ctx.config or {}).get("granularity") or "manual")
        subtype = self._resolved_subtype()
        out_root = build_standard_output_root(
            self.ctx,
            data_type="services",
            granularity=granularity,
            subtype=subtype,
        )
        out_root.mkdir(parents=True, exist_ok=True)
        suggested = getattr(download, "suggested_filename", None) or f"services-{subtype}-export.xlsx"
        target = self._build_download_target_path(out_root, suggested)
        try:
            await download.save_as(str(target))
        except Exception:
            return None
        try:
            if not target.exists():
                return None
            if target.stat().st_size <= 0:
                return None
        except OSError:
            return None
        return str(target)

    async def _wait_latest_report_panel(self, page: Any, *, timeout_ms: int = 20000, poll_ms: int = 500) -> Any | None:
        waited = 0
        while waited <= timeout_ms:
            panel = await self._first_visible_locator(page, self.service_sel.latest_report_panels)
            if panel is not None:
                return panel
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            waited += poll_ms
        return None

    async def _top_report_action(self, panel: Any) -> tuple[Any | None, str | None]:
        try:
            actions = panel.locator("button, a, [role='button']")
            count = await actions.count()
        except Exception:
            return None, None

        for idx in range(count):
            candidate = actions.nth(idx)
            try:
                if not await candidate.is_visible():
                    continue
            except Exception:
                continue
            try:
                text = (await candidate.text_content()) or ""
            except Exception:
                text = ""
            normalized = str(text).strip()
            if any(token in normalized for token in self.service_sel.panel_action_tokens):
                return candidate, normalized
        return None, None

    async def _wait_top_report_download_button(
        self,
        page: Any,
        *,
        timeout_ms: int = 180000,
        poll_ms: int = 1500,
    ) -> Any | None:
        if self._download_waiter is None and hasattr(page, "wait_for_event"):
            self._download_waiter = asyncio.create_task(
                page.wait_for_event("download", timeout=timeout_ms)
            )

        waited = 0
        while waited <= timeout_ms:
            panel = await self._wait_latest_report_panel(page, timeout_ms=poll_ms, poll_ms=300)
            if panel is not None:
                action, text = await self._top_report_action(panel)
                if action is not None and text:
                    if "下载" in text:
                        return action
                    if "进行中" in text:
                        if hasattr(page, "wait_for_timeout"):
                            await page.wait_for_timeout(poll_ms)
                        waited += poll_ms
                        continue
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            waited += poll_ms
        return None
