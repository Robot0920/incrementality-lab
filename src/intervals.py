"""Interval estimates for a difference in proportions.

Two methods are provided and are meant to be reported side by side.

Fixed-horizon Wald interval
    Valid only when the data is inspected once, at a sample size committed to in advance.
    Inspecting repeatedly raises the probability of at least one spurious exclusion of zero
    far above the nominal level. Reported because it is the common language.

Asymptotic confidence sequence
    Valid at every sample size simultaneously, so it may be monitored continuously and
    stopped at any moment without inflating the error rate. The price is a wider interval
    at any given sample size.

The confidence sequence follows the asymptotic construction of Waudby-Smith, Arbour,
Sinha, Kennedy and Ramdas, "Time-uniform central limit theory and asymptotic confidence
sequences":

    estimate  +-  sigma * sqrt( 2 * (t * rho^2 + 1) / (t^2 * rho^2)
                                * log( sqrt(t * rho^2 + 1) / alpha ) )

with a tuning parameter chosen to make the interval tightest near a planned sample size:

    rho = sqrt( ( -2 * log(alpha) + log(-2 * log(alpha) + 1) ) / t_opt )

`t_opt` has no default on purpose. A confidence sequence is only valid if its tuning is
fixed before the data is inspected; choosing it from the data already collected would
defeat the guarantee the method exists to provide.

This implementation is a transcription of a published formula and is not trusted on that
basis. `python -m src.validate_intervals` measures its actual error rate by simulation;
the numbers it produces are the reason to use it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from scipy.stats import norm


@dataclass(frozen=True)
class Interval:
    """A point estimate with lower and upper bounds, and the method that produced it."""

    estimate: float
    lower: float
    upper: float
    method: str

    @property
    def excludes_zero(self) -> bool:
        return self.lower > 0.0 or self.upper < 0.0

    def __str__(self) -> str:
        return f"{self.estimate:+.6f}  [{self.lower:+.6f}, {self.upper:+.6f}]  ({self.method})"


def _difference_moments(x_t: int, n_t: int, x_c: int, n_c: int) -> tuple[float, float, float]:
    """Return the estimated difference, its variance, and the effective sample size.

    The effective sample size is the harmonic combination that satisfies
    var(estimate) = sigma^2 / n_eff, which lets the one-sample confidence-sequence form be
    applied to a two-sample difference without modification.
    """
    p_t = x_t / n_t
    p_c = x_c / n_c
    estimate = p_t - p_c
    variance = p_t * (1.0 - p_t) / n_t + p_c * (1.0 - p_c) / n_c
    n_eff = 1.0 / (1.0 / n_t + 1.0 / n_c)
    return estimate, variance, n_eff


def wald_difference(x_t: int, n_t: int, x_c: int, n_c: int, alpha: float = 0.05) -> Interval:
    """Fixed-horizon interval for p_treated - p_control.

    Only valid at a single, pre-committed inspection.
    """
    estimate, variance, _ = _difference_moments(x_t, n_t, x_c, n_c)
    if variance <= 0.0:
        # No events observed in either arm: the data carries no information about the
        # difference, so the honest interval is unbounded rather than a point.
        return Interval(estimate, -math.inf, math.inf, "wald")
    half_width = norm.ppf(1.0 - alpha / 2.0) * math.sqrt(variance)
    return Interval(estimate, estimate - half_width, estimate + half_width, "wald")


def confidence_sequence_difference(
    x_t: int, n_t: int, x_c: int, n_c: int, t_opt: float, alpha: float = 0.05
) -> Interval:
    """Anytime-valid interval for p_treated - p_control.

    Valid simultaneously at every sample size, so it may be checked as often as desired.

    `t_opt` is the effective sample size the interval is tuned to be tightest at, and must
    be fixed before any data is seen.
    """
    estimate, variance, n_eff = _difference_moments(x_t, n_t, x_c, n_c)
    if variance <= 0.0:
        return Interval(estimate, -math.inf, math.inf, "confidence_sequence")

    sigma_squared = n_eff * variance  # so that sigma^2 / n_eff == variance
    rho_squared = (-2.0 * math.log(alpha) + math.log(-2.0 * math.log(alpha) + 1.0)) / t_opt

    inner = n_eff * rho_squared + 1.0
    half_width = math.sqrt(
        sigma_squared
        * (2.0 * inner / (n_eff**2 * rho_squared))
        * math.log(math.sqrt(inner) / alpha)
    )
    return Interval(
        estimate, estimate - half_width, estimate + half_width, "confidence_sequence"
    )
