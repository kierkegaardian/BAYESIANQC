from __future__ import annotations

import math
from dataclasses import dataclass

from app.math.validation import finite_float, positive_finite_float

PosteriorParameters = tuple[float, float, float, float]


@dataclass(frozen=True)
class PosteriorSummary:
    degrees_of_freedom: float
    posterior_sigma: float | None
    mean_scale: float
    predictive_scale: float


def validate_nig_parameters(
    mu: float,
    kappa: float,
    alpha: float,
    beta: float,
    *,
    require_finite_variance_mean: bool = False,
) -> PosteriorParameters:
    validated_mu = finite_float("mu", mu)
    validated_kappa = positive_finite_float("kappa", kappa)
    validated_alpha = positive_finite_float("alpha", alpha)
    validated_beta = positive_finite_float("beta", beta)
    if require_finite_variance_mean and validated_alpha <= 1.0:
        raise ValueError("alpha must be > 1 when the prior variance mean is required")
    return validated_mu, validated_kappa, validated_alpha, validated_beta


def update_normal_inverse_gamma(
    mu: float,
    kappa: float,
    alpha: float,
    beta: float,
    observation: float,
) -> PosteriorParameters:
    mu0, kappa0, alpha0, beta0 = validate_nig_parameters(mu, kappa, alpha, beta)
    value = finite_float("observation", observation)
    kappa_n = kappa0 + 1.0
    mu_n = (kappa0 * mu0 + value) / kappa_n
    alpha_n = alpha0 + 0.5
    delta = value - mu0
    beta_n = beta0 + 0.5 * kappa0 * delta * delta / kappa_n
    return validate_nig_parameters(mu_n, kappa_n, alpha_n, beta_n)


def summarize_normal_inverse_gamma(
    mu: float,
    kappa: float,
    alpha: float,
    beta: float,
) -> PosteriorSummary:
    _, validated_kappa, validated_alpha, validated_beta = validate_nig_parameters(mu, kappa, alpha, beta)
    degrees_of_freedom = positive_finite_float(
        "degrees_of_freedom",
        2.0 * validated_alpha,
    )
    posterior_sigma = (
        positive_finite_float(
            "posterior_sigma",
            math.sqrt(validated_beta / (validated_alpha - 1.0)),
        )
        if validated_alpha > 1.0
        else None
    )
    mean_scale = positive_finite_float(
        "mean_scale",
        math.sqrt(validated_beta / (validated_alpha * validated_kappa)),
    )
    predictive_scale = positive_finite_float(
        "predictive_scale",
        math.sqrt(validated_beta * (validated_kappa + 1.0) / (validated_alpha * validated_kappa)),
    )
    return PosteriorSummary(
        degrees_of_freedom=degrees_of_freedom,
        posterior_sigma=posterior_sigma,
        mean_scale=mean_scale,
        predictive_scale=predictive_scale,
    )


def beta_from_expected_sigma(alpha: float, sigma: float) -> float:
    validated_alpha = positive_finite_float("alpha", alpha)
    if validated_alpha <= 1.0:
        raise ValueError("alpha must be > 1 to define an expected process variance")
    validated_sigma = positive_finite_float("sigma", sigma)
    return positive_finite_float(
        "beta",
        (validated_alpha - 1.0) * validated_sigma * validated_sigma,
    )
