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


def calculate_rank_band_coefficient(rank: int, total: int) -> float:
    if total <= 0:
        return 1.0
    top_20_cutoff = max(1, int(total * 0.2 + 0.999999))
    top_50_cutoff = max(top_20_cutoff, int(total * 0.5 + 0.999999))
    top_80_cutoff = max(top_50_cutoff, int(total * 0.8 + 0.999999))
    if rank <= top_20_cutoff:
        return 1.2
    if rank <= top_50_cutoff:
        return 1.0
    if rank <= top_80_cutoff:
        return 0.9
    return 0.8


def calculate_score_cap_coefficient(score: Any) -> float:
    value = float(score or 0.0)
    if value >= 80:
        return 1.2
    if value >= 70:
        return 1.0
    if value >= 60:
        return 0.8
    return 0.5


def calculate_ranked_performance_coefficient(score: Any, rank: int, total: int) -> float:
    return min(
        calculate_rank_band_coefficient(rank, total),
        calculate_score_cap_coefficient(score),
    )
