from __future__ import annotations

from modules.components.base import ExecutionContext
from modules.components.export.base import ExportComponent, ExportMode, ExportResult
from modules.platforms.shopee.components.services_agent_export import ShopeeServicesAgentExport
from modules.platforms.shopee.components.services_ai_assistant_export import (
    ShopeeServicesAiAssistantExport,
)


class ShopeeServicesExport(ExportComponent):
    platform = "shopee"
    component_type = "export"
    data_domain = "services"

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    async def run(self, page, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        cfg = self.ctx.config or {}
        subtype = str(cfg.get("services_subtype") or cfg.get("sub_domain") or "all").strip().lower()

        if subtype == "ai_assistant":
            return await ShopeeServicesAiAssistantExport(self.ctx).run(page, mode)
        if subtype == "agent":
            return await ShopeeServicesAgentExport(self.ctx).run(page, mode)

        results: list[ExportResult] = []
        for component_cls in (ShopeeServicesAiAssistantExport, ShopeeServicesAgentExport):
            child_cfg = dict(self.ctx.config or {})
            child_cfg["services_subtype"] = component_cls.sub_domain
            child_ctx = ExecutionContext(
                platform=self.ctx.platform,
                account=self.ctx.account,
                logger=self.ctx.logger,
                config=child_cfg,
                step_callback=self.ctx.step_callback,
                step_prefix=self.ctx.step_prefix,
                is_test_mode=self.ctx.is_test_mode,
            )
            results.append(await component_cls(child_ctx).run(page, mode))

        failed = [result.message for result in results if not result.success]
        if failed:
            return ExportResult(success=False, message="; ".join(failed), file_path=None)

        last_file = next((result.file_path for result in reversed(results) if result.file_path), None)
        return ExportResult(success=True, message="services exports complete", file_path=last_file)
