from __future__ import annotations

from backend.services.data_pipeline.refresh_registry import topologically_sort_targets


def build_refresh_plan(targets: list[str]) -> list[str]:
    return topologically_sort_targets(targets)
