from __future__ import annotations

import math


def prior_beta_from_sigma(alpha0: float, sigma: float) -> float:
    """Return the NIG beta that gives the requested prior variance."""

    if not math.isfinite(alpha0) or alpha0 <= 1:
        raise ValueError("alpha0 must be finite and > 1")
    if not math.isfinite(sigma) or sigma <= 0:
        raise ValueError("sigma must be finite and > 0")
    return (alpha0 - 1.0) * sigma**2
