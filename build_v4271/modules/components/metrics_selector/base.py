from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from modules.components.base import ComponentBase, ResultBase


@dataclass
class MetricsSelectResult(ResultBase):
    selected: Sequence[str] = ()


class MetricsSelectorComponent(ComponentBase):
    """Optional component for selecting KPI/metrics (multi‑selector UIs)."""

    def run(self, page: Any, metrics: Sequence[str]) -> MetricsSelectResult:  # type: ignore[override]
        raise NotImplementedError

