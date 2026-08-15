from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime
from statistics import stdev

from app.evaluation_models import BayesianThresholdMode, ControlLimitSource, ResolvedControlLimits


def threshold_mode(warn_threshold: float | None, hold_threshold: float | None) -> BayesianThresholdMode:
    if warn_threshold is not None and hold_threshold is not None:
        return BayesianThresholdMode.EXPLICIT_PROBABILITIES
    if warn_threshold is None and hold_threshold is None:
        return BayesianThresholdMode.LEGACY_ACTION_RISK_SCORE
    return BayesianThresholdMode.MIXED_LEGACY


def resolve_control_limits(
    *,
    source: ControlLimitSource,
    configured_target: float,
    configured_sigma: float,
    warning_limit_sd: float,
    action_limit_sd: float,
    baseline_values: Sequence[float] = (),
    baseline_start: datetime | None = None,
    baseline_end: datetime | None = None,
    baseline_centerline: float | None = None,
    baseline_sigma: float | None = None,
    baseline_count: int | None = None,
) -> ResolvedControlLimits:
    centerline = configured_target
    sigma = configured_sigma
    resolved_baseline_count: int | None = None

    if source == ControlLimitSource.FIXED_BASELINE:
        if baseline_start is None or baseline_end is None:
            raise ValueError("fixed_baseline requires baseline_start and baseline_end")
        frozen = (baseline_centerline, baseline_sigma, baseline_count)
        if any(value is not None for value in frozen):
            if baseline_centerline is None or baseline_sigma is None or baseline_count is None:
                raise ValueError("fixed_baseline frozen statistics are incomplete")
            centerline = baseline_centerline
            sigma = baseline_sigma
            resolved_baseline_count = baseline_count
        else:
            if len(baseline_values) < 2:
                raise ValueError("fixed_baseline requires at least two included results")
            if any(not math.isfinite(value) for value in baseline_values):
                raise ValueError("fixed_baseline values must be finite")
            centerline = sum(baseline_values) / len(baseline_values)
            sigma = stdev(baseline_values)
            resolved_baseline_count = len(baseline_values)

    if not math.isfinite(centerline):
        raise ValueError("resolved centerline must be finite")
    if not math.isfinite(sigma) or sigma <= 0:
        raise ValueError("resolved sigma must be finite and > 0")

    warning_delta = warning_limit_sd * sigma
    action_delta = action_limit_sd * sigma
    return ResolvedControlLimits(
        source=source,
        centerline=centerline,
        sigma=sigma,
        warning_limit_sd=warning_limit_sd,
        action_limit_sd=action_limit_sd,
        warning_lower=centerline - warning_delta,
        warning_upper=centerline + warning_delta,
        action_lower=centerline - action_delta,
        action_upper=centerline + action_delta,
        baseline_start=baseline_start if source == ControlLimitSource.FIXED_BASELINE else None,
        baseline_end=baseline_end if source == ControlLimitSource.FIXED_BASELINE else None,
        baseline_count=resolved_baseline_count,
    )
