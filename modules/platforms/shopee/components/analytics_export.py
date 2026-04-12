from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from modules.components.base import ExecutionContext
from modules.components.export.base import ExportComponent, ExportMode, ExportResult
from modules.platforms.shopee.components.date_picker import ShopeeDatePicker
from modules.platforms.shopee.components import _download_helpers as download_helpers
from modules.platforms.shopee.components.business_analysis_common import (
    build_domain_path,
    granularity_label,
    normalize_time_request,
    preset_label,
)
from modules.platforms.shopee.components.products_config import ProductsSelectors
from modules.platforms.shopee.components.products_export import ShopeeProductsExport


class ShopeeAnalyticsExport(ExportComponent):
    platform = "shopee"
    component_type = "export"
    data_domain = "analytics"
    DOWNLOAD_MODE = "direct"
    DIRECT_DOWNLOAD_EVENT_TIMEOUT_MS = 10000

    def __init__(self, ctx: ExecutionContext, selectors: ProductsSelectors | None = None) -> None:
        super().__init__(ctx)
        self._shared = ShopeeProductsExport(
            ctx,
            selectors=selectors or replace(
                ProductsSelectors(),
                overview_path=build_domain_path("analytics"),
            ),
        )
        self.sel = self._shared.sel
        self.service_sel = self._shared.service_sel
        self._shared._target_date_label = self._target_date_label  # type: ignore[method-assign]

    def _products_page_looks_ready(self, url: str) -> bool:
        current = str(url or "").strip().lower()
        if not current:
            return False
        return self.sel.overview_path in current

    async def _ensure_products_page_ready(self, page: Any) -> None:
        if self._products_page_looks_ready(str(getattr(page, "url", "") or "")):
            return
        target_url = f"https://seller.shopee.cn{build_domain_path('analytics')}"
        await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        if hasattr(page, "wait_for_timeout"):
            await page.wait_for_timeout(1200)
        if not self._products_page_looks_ready(str(getattr(page, "url", "") or "")):
            raise RuntimeError("analytics overview page is not ready")

    def _target_date_label(self, config: dict[str, Any]) -> str:
        time_selection = config.get("time_selection")
        if isinstance(time_selection, dict):
            if str(time_selection.get("mode") or "").strip().lower() == "preset" and time_selection.get("preset"):
                normalized = normalize_time_request(
                    "analytics",
                    time_mode="preset",
                    value=str(time_selection["preset"]),
                )
                return preset_label(normalized["value"])

        if config.get("date_preset"):
            normalized = normalize_time_request(
                "analytics",
                time_mode="preset",
                value=str(config["date_preset"]),
            )
            return preset_label(normalized["value"])

        if "preset" in config:
            normalized = normalize_time_request(
                "analytics",
                time_mode="preset",
                value=str(config["preset"]),
            )
            return preset_label(normalized["value"])

        granularity = str(config.get("granularity") or "daily").strip().lower()
        preset_by_granularity = {
            "day": "yesterday",
            "daily": "yesterday",
            "d": "yesterday",
            "week": "last_7_days",
            "weekly": "last_7_days",
            "w": "last_7_days",
            "month": "last_30_days",
            "monthly": "last_30_days",
            "m": "last_30_days",
        }
        preset_value = preset_by_granularity.get(granularity)
        if preset_value:
            return preset_label(preset_value)
        normalized = normalize_time_request(
            "analytics",
            time_mode="granularity",
            value=granularity,
        )
        return granularity_label(normalized["value"])

    async def _wait_download_complete(self, page: Any) -> str | None:
        waiter = self._download_waiter
        if waiter is None:
            if not hasattr(page, "wait_for_event"):
                return None
            try:
                download = await page.wait_for_event("download", timeout=self.DOWNLOAD_EVENT_TIMEOUT_MS)
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
        out_root = build_standard_output_root(self.ctx, data_type="analytics", granularity=granularity)
        out_root.mkdir(parents=True, exist_ok=True)
        suggested = getattr(download, "suggested_filename", None) or "analytics-export.xlsx"
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

    def _build_download_target_path(self, out_root: Path, suggested_filename: str) -> Path:
        candidate = out_root / suggested_filename
        if not candidate.exists():
            return candidate

        stem = Path(suggested_filename).stem or "analytics-export"
        suffix = "".join(Path(suggested_filename).suffixes) or ".xlsx"
        index = 1
        while True:
            retry_candidate = out_root / f"{stem}-{index}{suffix}"
            if not retry_candidate.exists():
                return retry_candidate
            index += 1

    async def _first_visible_locator(self, page: Any, selectors: tuple[str, ...]) -> Any | None:
        return await self._shared._first_visible_locator(page, selectors)

    async def _detect_export_throttled(self, page: Any) -> bool:
        return await self._shared._detect_export_throttled(page)

    async def _ensure_shop_selected(self, page: Any) -> None:
        await self._shared._ensure_shop_selected(page)

    async def _ensure_date_selection(self, page: Any) -> None:
        await self._shared._ensure_date_selection(page)

    async def ensure_page_ready(self, page: Any) -> None:
        await self._ensure_products_page_ready(page)
        if not await self._wait_analytics_business_ready(page):
            raise RuntimeError("analytics page shell loaded but business content not ready")

    async def _wait_analytics_business_ready(
        self,
        page: Any,
        *,
        timeout_ms: int = 15000,
        poll_ms: int = 500,
    ) -> bool:
        selectors = (
            'button:has-text("导出数据")',
            '[role="button"]:has-text("导出数据")',
            'button:has-text("下载数据")',
            '[role="button"]:has-text("下载数据")',
            'div:has-text("统计时间")',
            'button:has-text("过去 30 天")',
            'button:has-text("过去30天")',
            'button:has-text("过去 7 天")',
            'button:has-text("过去7天")',
            'button:has-text("按日")',
            'button:has-text("按周")',
            'button:has-text("按月")',
        )
        waited = 0
        while waited <= timeout_ms:
            for selector in selectors:
                try:
                    locator = page.locator(selector).first
                    if await locator.count() > 0 and await locator.is_visible(timeout=300):
                        return True
                except Exception:
                    continue
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            waited += poll_ms
        return False

    async def ensure_shop_ready(self, page: Any) -> None:
        await self._ensure_shop_selected(page)

    async def ensure_date_ready(self, page: Any) -> None:
        picker = ShopeeDatePicker(self.ctx)
        result = await picker.run(page, picker._resolve_option_from_context())
        if not getattr(result, "success", False):
            raise RuntimeError(getattr(result, "message", "date picker failed"))

    async def trigger_export(self, page: Any) -> Any:
        button = await self._first_visible_locator(page, self.sel.export_buttons)
        if button is None:
            raise RuntimeError("export button not found")
        return button

    async def collect_download_result(self, page: Any, trigger_button: Any) -> str | None:
        granularity = str((self.ctx.config or {}).get("granularity") or "manual")
        return await download_helpers.capture_direct_download_artifact(
            page=page,
            click_action=lambda: trigger_button.click(timeout=5000),
            ctx=self.ctx,
            data_type="analytics",
            granularity=granularity,
            timeout_ms=self.DIRECT_DOWNLOAD_EVENT_TIMEOUT_MS,
            reconcile_timeout_ms=12000,
            filename_hints=("traffic", "overview", "analytics"),
            suggested_filename="analytics-export.xlsx",
        )

    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        try:
            await self.ensure_page_ready(page)
            await self.ensure_shop_ready(page)
            await self.ensure_date_ready(page)

            trigger_button = await self.trigger_export(page)
            file_path = await self.collect_download_result(page, trigger_button)
            if file_path:
                return ExportResult(success=True, message="download complete", file_path=file_path)
            if await self._detect_export_throttled(page):
                return ExportResult(success=False, message="export throttled", file_path=None)
            return ExportResult(success=False, message="download did not complete", file_path=None)
        except Exception as exc:
            return ExportResult(success=False, message=str(exc), file_path=None)
