from __future__ import annotations

from modules.components.base import ExecutionContext
from modules.platforms.miaoshou.components.orders_config import OrdersSelectors
from modules.platforms.miaoshou.components.orders_export_base import MiaoshouOrdersExportBase


class MiaoshouOrdersTiktokExport(MiaoshouOrdersExportBase):
    sub_domain = "tiktok"

    def __init__(self, ctx: ExecutionContext, selectors: OrdersSelectors | None = None) -> None:
        super().__init__(ctx, selectors=selectors)
