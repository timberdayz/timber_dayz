from __future__ import annotations

from dataclasses import replace
from typing import Any

from modules.components.base import ExecutionContext
from modules.components.date_picker.base import DateOption, DatePickResult, DatePickerComponent
from modules.platforms.shopee.components.business_analysis_common import (
    build_domain_path,
    granularity_label,
    normalize_time_request,
    preset_label,
)
from modules.platforms.shopee.components.products_config import ProductsSelectors
from modules.platforms.shopee.components.products_export import ShopeeProductsExport
from modules.platforms.shopee.components.services_config import ServicesSelectors


class ShopeeDatePicker(DatePickerComponent):
    platform = "shopee"
    component_type = "date_picker"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)
        cfg = self.ctx.config or {}
        domain = str(cfg.get("data_domain") or "products").strip().lower()
        subtype = str(
            cfg.get("services_subtype")
            or cfg.get("sub_domain")
            or ""
        ).strip().lower()
        service_selectors = ServicesSelectors()

        overview_path = build_domain_path("products")
        if domain == "analytics":
            overview_path = build_domain_path("analytics")
        elif domain == "services" and subtype in service_selectors.service_paths:
            overview_path = service_selectors.service_paths[subtype]

        selectors = replace(ProductsSelectors(), overview_path=overview_path)
        self._delegate = ShopeeProductsExport(self.ctx, selectors=selectors)
        self._delegate.service_sel = service_selectors
        self._delegate._target_date_label = self._target_date_label  # type: ignore[method-assign]

    def _resolve_option_from_context(self) -> DateOption:
        config = self.ctx.config or {}
        time_selection = config.get("time_selection") if isinstance(config.get("time_selection"), dict) else {}
        if str(time_selection.get("mode") or "").strip().lower() == "preset":
            raw = str(time_selection.get("preset") or "").strip().lower()
        else:
            raw = str(
                config.get("date_preset")
                or config.get("preset")
                or config.get("granularity")
                or "daily"
            ).strip().lower()

        if raw in {"today", "today_realtime"}:
            return DateOption.TODAY_REALTIME
        if raw in {"yesterday"}:
            return DateOption.YESTERDAY
        if raw in {"weekly", "week", "w", "last_7_days"}:
            return DateOption.LAST_7_DAYS
        if raw in {"monthly", "month", "m", "last_30_days"}:
            return DateOption.LAST_30_DAYS
        if raw in {"daily", "day", "d"}:
            return DateOption.YESTERDAY
        return DateOption.YESTERDAY

    def _target_date_label(self, config: dict[str, Any]) -> str:
        domain = str((self.ctx.config or {}).get("data_domain") or "products").strip().lower()
        time_selection = config.get("time_selection")
        if isinstance(time_selection, dict):
            if str(time_selection.get("mode") or "").strip().lower() == "preset" and time_selection.get("preset"):
                preset_value = str(time_selection["preset"])
                if domain == "services" and str(preset_value).strip().lower() == "today_realtime":
                    raise ValueError("unsupported preset 'today_realtime' for shopee/services")
                normalized = normalize_time_request(
                    domain,
                    time_mode="preset",
                    value=preset_value,
                )
                return preset_label(normalized["value"])

        if config.get("date_preset"):
            preset_value = str(config["date_preset"])
            if domain == "services" and preset_value.strip().lower() == "today_realtime":
                raise ValueError("unsupported preset 'today_realtime' for shopee/services")
            normalized = normalize_time_request(
                domain,
                time_mode="preset",
                value=preset_value,
            )
            return preset_label(normalized["value"])

        if "preset" in config:
            preset_value = str(config["preset"])
            if domain == "services" and preset_value.strip().lower() == "today_realtime":
                raise ValueError("unsupported preset 'today_realtime' for shopee/services")
            normalized = normalize_time_request(
                domain,
                time_mode="preset",
                value=preset_value,
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
            domain,
            time_mode="granularity",
            value=granularity,
        )
        return granularity_label(normalized["value"])

    async def run(self, page: Any, option: DateOption | None = None) -> DatePickResult:  # type: ignore[override]
        resolved_option = option or self._resolve_option_from_context()
        try:
            await self._delegate._ensure_date_selection(page)
            return DatePickResult(success=True, message="ok", option=resolved_option)
        except Exception as exc:
            return DatePickResult(success=False, message=str(exc), option=resolved_option)
