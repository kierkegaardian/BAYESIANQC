from __future__ import annotations

import math
from collections.abc import Sequence


def sample_mean_sd(values: Sequence[float]) -> tuple[float, float]:
    """
    Compute sample mean and sample standard deviation (ddof=1).

    Raises ValueError when fewer than two values are provided.
    """
    if len(values) < 2:
        raise ValueError("Need at least two values to compute sample SD")
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return mean, math.sqrt(variance)

