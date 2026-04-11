from __future__ import annotations

from typing import Any


def calculate_performance_coefficient(score: Any) -> float:
    value = float(score or 0.0)
    if value >= 90:
        return 1.2
    if value >= 80:
        return 1.0
    if value >= 70:
        return 0.9
    if value >= 60:
        return 0.8
    return 0.5
