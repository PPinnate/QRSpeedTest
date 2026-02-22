from __future__ import annotations

import math
import statistics
from typing import Iterable


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    sorted_vals = sorted(values)
    rank = (len(sorted_vals) - 1) * p
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return sorted_vals[int(rank)]
    frac = rank - low
    return sorted_vals[low] * (1 - frac) + sorted_vals[high] * frac


def compute_stats_ms(values: Iterable[float]) -> dict[str, float | int | None]:
    vals = list(values)
    if not vals:
        return {
            "count": 0,
            "mean_ms": None,
            "std_ms": None,
            "median_ms": None,
            "p95_ms": None,
            "min_ms": None,
            "max_ms": None,
            "coefficient_of_variation": None,
        }
    mean = statistics.fmean(vals)
    std = statistics.stdev(vals) if len(vals) > 1 else 0.0
    cov = (std / mean) if mean > 0 else None
    return {
        "count": len(vals),
        "mean_ms": mean,
        "std_ms": std,
        "median_ms": statistics.median(vals),
        "p95_ms": _percentile(vals, 0.95),
        "min_ms": min(vals),
        "max_ms": max(vals),
        "coefficient_of_variation": cov,
    }


def success_rate(successes: int, total: int) -> float:
    return (successes / total) if total else 0.0
