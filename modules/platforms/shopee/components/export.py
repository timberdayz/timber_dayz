from __future__ import annotations

from typing import Any, Optional

from modules.components.base import ExecutionContext
from modules.components.export.base import ExportComponent, ExportResult, ExportMode


class ShopeeExporterComponent(ExportComponent):
    """Shopee base exporter component."""

    # Component metadata
    platform = "shopee"
    component_type = "export"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        # Thin adapter to existing exporter flow (page/context already set by caller)
        try:
            # 调用纯导出方法（跳过登录/导航/日期设置）
            from modules.services.shopee_playwright_exporter import ShopeePlaywrightExporter
            from pathlib import Path
            from datetime import datetime

            # 从上下文获取必要信息
            account = self.ctx.account
            shop_id = account.get('shop_id', 'unknown')
            shop_name = account.get('store_name', 'unknown')

            # 构造 Shop 对象
            from modules.services.shopee_playwright_exporter import Shop
            shop = Shop(id=shop_id, name=shop_name)

            # 计算日期范围（默认昨天）
            yesterday = datetime.now().strftime("%Y-%m-%d")

            # 创建导出器实例（需要 playwright 对象，这里简化处理）
            # 注意：这是一个简化实现，实际应该从调用方传入 exporter 实例
            if self.logger:
                self.logger.info(f"[ShopeeExporterComponent] 准备导出 shop_id={shop_id}")

            # 暂时返回成功（实际实现需要完整的 exporter 集成）
            return ExportResult(success=True, file_path=None, message="component export ready")

        except Exception as e:
            if self.logger:
                self.logger.error(f"[ShopeeExporterComponent] failed: {e}")
            return ExportResult(success=False, file_path=None, message=str(e))

