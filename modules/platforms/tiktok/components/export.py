from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from modules.components.export.base import ExportComponent, ExportResult, ExportMode, build_standard_output_root


class TiktokExport(ExportComponent):
    """Shared TikTok export helper for traffic/products pages.

    This helper currently standardizes the export-entry interaction for
    `data-overview` and `product-analysis`. Service analytics keeps a separate
    path because its export flow and page structure differ materially.
    """

    platform = "tiktok"
    component_type = "export"
    data_domain = None

    @staticmethod
    def _build_success_result(message: str, file_path: str | None = None) -> ExportResult:
        return ExportResult(success=True, message=message, file_path=file_path)

    @staticmethod
    def _build_error_result(message: str) -> ExportResult:
        return ExportResult(success=False, message=message, file_path=None)

    @staticmethod
    def _infer_data_type(url: str, products_default: str = "products") -> str:
        cur = str(url or "")
        if "/product-analysis" in cur:
            return products_default
        if "/data-overview" in cur:
            return "analytics"
        if "/service-analytics" in cur:
            return "services"
        return "unknown"

    def _write_manifest(self, target: Path, cfg: dict, account_label: str, shop_name: str, data_type: str) -> None:
        meta = {
            "platform": getattr(self.ctx, "platform", "tiktok"),
            "account_label": account_label,
            "shop_name": shop_name,
            "region": (self.ctx.config or {}).get("shop_region") or (self.ctx.account or {}).get("shop_region"),
            "data_type": data_type,
            "granularity": (cfg or {}).get("granularity"),
            "file_path": str(target),
        }
        (Path(str(target) + ".json")).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def _export_button_selectors(self) -> tuple[str, ...]:
        return (
            'button:has-text("导出")',
            'button:has-text("导出数据")',
            'button:has-text("Export")',
            '[data-testid*="export"]',
        )

    async def _is_clickable(self, locator: Any) -> bool:
        try:
            return bool(await locator.is_visible(timeout=500))
        except Exception:
            return False

    async def _click_first(self, page: Any, selectors: Iterable[str], *, timeout: int = 5000) -> bool:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0 and await self._is_clickable(locator):
                    try:
                        await locator.scroll_into_view_if_needed(timeout=1000)
                    except Exception:
                        pass
                    await locator.click(timeout=timeout)
                    return True
            except Exception:
                continue
        return False

    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        current_url = str(getattr(page, "url", "") or "")
        data_type = self._infer_data_type(current_url)

        if data_type not in {"analytics", "products", "services"}:
            return self._build_error_result("unsupported tiktok export page")

        if data_type == "services":
            await self._click_first(
                page,
                (
                    'button:has-text("聊天详情")',
                    'button:has-text("鑱婂ぉ璇︽儏")',
                    '[role="tab"]:has-text("聊天详情")',
                    'text=聊天详情',
                ),
                timeout=2000,
            )
            await page.wait_for_timeout(300)

        if not hasattr(page, "expect_download"):
            clicked = await self._click_first(page, self._export_button_selectors(), timeout=3000)
            if not clicked:
                return self._build_error_result("export button not found")
            await page.wait_for_timeout(500)
            return self._build_success_result("export triggered")

        try:
            async with page.expect_download(timeout=10000) as download_info:
                clicked = await self._click_first(page, self._export_button_selectors(), timeout=3000)
                if not clicked:
                    return self._build_error_result("export button not found")
                await page.wait_for_timeout(500)
            download = await download_info.value
        except Exception as exc:
            return self._build_error_result(str(exc))

        cfg = self.ctx.config or {}
        out_root = build_standard_output_root(
            self.ctx,
            data_type=data_type,
            granularity=str(cfg.get("granularity") or "range").lower(),
        )
        out_root.mkdir(parents=True, exist_ok=True)

        filename = getattr(download, "suggested_filename", None) or f"{data_type}.xlsx"
        target = out_root / filename
        await download.save_as(str(target))
        return self._build_success_result("ok", str(target))


# Backward-compatible alias used by older tests and references.
TiktokExporterComponent = TiktokExport
