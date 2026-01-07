from __future__ import annotations

from typing import Any, Sequence

from modules.components.base import ExecutionContext
from modules.components.metrics_selector.base import MetricsSelectorComponent, MetricsSelectResult


class ShopeeMetricsSelector(MetricsSelectorComponent):
    # Component metadata (v4.8.0)
    platform = "shopee"
    component_type = "metrics_selector"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    def run(self, page: Any, metrics: Sequence[str]) -> MetricsSelectResult:  # type: ignore[override]
        # Skeleton only: will implement multi-selector interaction
        return MetricsSelectResult(success=True, selected=tuple(metrics), message="skeleton")

