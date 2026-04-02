from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from modules.components.base import ExecutionContext
from modules.components.export.base import build_standard_output_root
from modules.platforms.shopee.components.business_analysis_common import build_domain_path
from modules.platforms.shopee.components.products_config import ProductsSelectors
from modules.platforms.shopee.components.products_export import ShopeeProductsExport


class ShopeeAnalyticsExport(ShopeeProductsExport):
    platform = "shopee"
    component_type = "export"
    data_domain = "analytics"

    def __init__(self, ctx: ExecutionContext, selectors: ProductsSelectors | None = None) -> None:
        super().__init__(
            ctx,
            selectors=selectors or replace(
                ProductsSelectors(),
                overview_path=build_domain_path("analytics"),
            ),
        )

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
