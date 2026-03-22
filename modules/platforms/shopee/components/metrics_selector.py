from __future__ import annotations

from typing import Any, Sequence

from modules.components.base import ExecutionContext
from modules.components.metrics_selector.base import MetricsSelectorComponent, MetricsSelectResult


class ShopeeMetricsSelector(MetricsSelectorComponent):
    """Non-canonical placeholder component.

    Kept only for compatibility with older adapter paths. Metrics selection is
    not part of the current canonical Shopee workflow and should not be used as
    a default maintenance target.
    """

    # Component metadata (v4.8.0)
    platform = "shopee"
    component_type = "metrics_selector"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    async def run(self, page: Any, metrics: Sequence[str]) -> MetricsSelectResult:  # type: ignore[override]
        return MetricsSelectResult(
            success=False,
            selected=tuple(metrics),
            message="metrics selector is not supported in the canonical Shopee workflow",
        )
