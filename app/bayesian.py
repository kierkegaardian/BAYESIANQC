"""Compatibility facade for Bayesian evaluation and posterior state operations.

Callers may continue importing the historical public and private helpers from
``app.bayesian`` while their implementations live in focused typed modules.
"""

from app.bayesian_history import active_prior as _active_prior
from app.bayesian_history import list_priors as _list_priors
from app.bayesian_replay import infer_risk_as_of
from app.bayesian_risk import ENGINE_ID as _ENGINE_ID
from app.bayesian_risk import _clamp01
from app.bayesian_risk import _probability_inside_bounds
from app.bayesian_risk import _student_t_cdf
from app.bayesian_risk import _student_t_interval_quantile
from app.bayesian_risk import _student_t_ppf
from app.bayesian_risk import _update_posterior
from app.bayesian_risk import available_probabilities as _available_probabilities
from app.bayesian_risk import interval_quantile as _interval_quantile
from app.bayesian_risk import risk_from_posterior as _risk_from_posterior
from app.bayesian_risk import unavailable_missing_prior as _unavailable_missing_prior
from app.bayesian_risk import update_policy_streaks as _update_policy_streaks
from app.bayesian_risk import update_posterior_and_infer_risk
from app.bayesian_state import infer_risk, rebuild_posterior_state

__all__ = [
    "_ENGINE_ID",
    "_active_prior",
    "_available_probabilities",
    "_clamp01",
    "_interval_quantile",
    "_list_priors",
    "_probability_inside_bounds",
    "_risk_from_posterior",
    "_student_t_cdf",
    "_student_t_interval_quantile",
    "_student_t_ppf",
    "_unavailable_missing_prior",
    "_update_policy_streaks",
    "_update_posterior",
    "infer_risk",
    "infer_risk_as_of",
    "rebuild_posterior_state",
    "update_posterior_and_infer_risk",
]
