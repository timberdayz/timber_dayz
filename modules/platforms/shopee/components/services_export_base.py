from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from modules.components.base import ExecutionContext
from modules.components.export.base import build_standard_output_root
from modules.platforms.shopee.components.date_picker import ShopeeDatePicker
from modules.platforms.shopee.components.navigation import ShopeeNavigation
from modules.platforms.shopee.components.products_config import ProductsSelectors
from modules.platforms.shopee.components.products_export import ShopeeProductsExport
from modules.platforms.shopee.components.services_config import ServicesSelectors


class ShopeeServicesExportBase(ShopeeProductsExport):
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
            selectors=selectors
            or replace(
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

    def _validate_services_preset(self, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized == "today_realtime":
            raise ValueError("unsupported preset 'today_realtime' for shopee/services")
        return normalized

    async def _ensure_products_page_ready(self, page: Any) -> None:
        await ShopeeNavigation(self.ctx).ensure_overview_ready(
            page,
            overview_path=self._service_path(self._resolved_subtype()),
            error_message="services page is not ready",
        )

    def _target_date_label(self, config: dict[str, Any]) -> str:
        picker = ShopeeDatePicker(
            ExecutionContext(
                platform=self.ctx.platform,
                account=self.ctx.account,
                config={
                    **(self.ctx.config or {}),
                    "data_domain": "services",
                    "services_subtype": self._resolved_subtype(config),
                },
                logger=self.logger,
            )
        )
        return picker._target_date_label(config)

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
        download = None
        if waiter is not None and waiter.done():
            self._log_export_diagnostic(
                "download_event_ready_before_report_button",
                sub_domain=self._resolved_subtype(),
            )
            try:
                download = await waiter
            except Exception:
                return None
            finally:
                self._download_waiter = None
        else:
            button = await self._wait_top_report_download_button(page)
            if button is not None:
                try:
                    await button.click(timeout=5000)
                except Exception:
                    return None

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

    async def _wait_latest_report_panel(
        self,
        page: Any,
        *,
        timeout_ms: int = 20000,
        poll_ms: int = 500,
    ) -> Any | None:
        return await super()._wait_latest_report_panel(page, timeout_ms=timeout_ms, poll_ms=poll_ms)

    async def _wait_top_report_download_button(
        self,
        page: Any,
        *,
        timeout_ms: int = 180000,
        poll_ms: int = 1500,
    ) -> Any | None:
        return await super()._wait_top_report_download_button(
            page,
            timeout_ms=timeout_ms,
            poll_ms=poll_ms,
        )
