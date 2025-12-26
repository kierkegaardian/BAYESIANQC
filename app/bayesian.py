from __future__ import annotations

import math

from app.models import BayesianRisk, QCRecordIn
from app.storage import storage


def infer_risk(record: QCRecordIn) -> BayesianRisk:
    baseline = storage.baseline_stats(record.stream_id)
    if baseline is None:
        return BayesianRisk(probability_outside_limits=0.0, risk_score=0)

    target, sigma = baseline
    z = (record.result_value - target) / sigma
    probability_outside_limits = min(1.0, max(0.0, math.erfc(abs(z) / math.sqrt(2))))
    risk_score = int(min(100, max(0, round(probability_outside_limits * 100))))
    return BayesianRisk(probability_outside_limits=probability_outside_limits, risk_score=risk_score)
