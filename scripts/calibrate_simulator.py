"""Solve the simulator's parameters against the reference dataset's moments.

Hand-tuning simulation parameters until the output looks about right is how a simulation
stops being evidence. Four parameters are instead solved for, against three moments
measured on the real data, so the calibration is reproducible and auditable.

Targets, measured on Criteo-UPLIFT v2.1 (README section 2):

    delivery rate                       3.604%
    baseline of never-delivered units   0.1194%   (observed: assigned but not delivered)
    baseline of delivered units         2.1837%   (recovered from the mixture identity)

The control rate of 0.1938% is deliberately not a fourth target. Randomisation makes it the
mixture of the two baselines at the delivery rate, so matching those two implies it; it is
printed as a check that the arithmetic closes.

Curvature and interaction are design knobs, not fitted quantities. They set how much
functional-form error a linear-in-logit model makes, which is what separates estimator
Level 1 from Level 2 (docs/04_estimator_selection.md). They are held fixed while the other
four parameters absorb whatever they do to the moments.

Expectations use Gauss-Hermite quadrature over both latent inputs -- the activity trait and
the modifier -- so the solve is deterministic and free of Monte Carlo noise. The logit
functions are imported from src.simulate rather than restated, so the integrated and
sampled versions of this process cannot drift apart.

    python scripts/calibrate_simulator.py
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares
from scipy.special import expit

from src.simulate import CURVATURE, INTERACTION, baseline_logit, delivery_logit

TARGET_DELIVERY_RATE = 0.03604
TARGET_BASELINE_UNDELIVERED = 0.001194
TARGET_BASELINE_DELIVERED = 0.021837
IMPLIED_CONTROL_RATE = (
    TARGET_DELIVERY_RATE * TARGET_BASELINE_DELIVERED
    + (1 - TARGET_DELIVERY_RATE) * TARGET_BASELINE_UNDELIVERED
)

# Two-dimensional quadrature: activity on one axis, the modifier on the other.
_n1d = 120
_nodes, _w = np.polynomial.hermite_e.hermegauss(_n1d)
_w = _w / _w.sum()
ACTIVITY = _nodes[:, None]                 # (n, 1)
MODIFIER = _nodes[None, :]                 # (1, n)
WEIGHTS = _w[:, None] * _w[None, :]        # (n, n), sums to 1


def moments(params: np.ndarray) -> tuple[float, float, float]:
    """Delivery rate, baseline among undelivered, baseline among delivered."""
    delivery_intercept, selection_strength, baseline_intercept, activity_on_outcome = params

    # Delivery depends only on activity, so it broadcasts along the modifier axis.
    d = expit(delivery_logit(ACTIVITY, delivery_intercept, selection_strength))
    base = expit(baseline_logit(ACTIVITY, MODIFIER, baseline_intercept, activity_on_outcome,
                                CURVATURE, INTERACTION))

    delivery_rate = float((WEIGHTS * d).sum())
    baseline_delivered = float((WEIGHTS * base * d).sum() / delivery_rate)
    baseline_undelivered = float((WEIGHTS * base * (1 - d)).sum() / (1 - delivery_rate))
    return delivery_rate, baseline_undelivered, baseline_delivered


def residuals(params: np.ndarray) -> np.ndarray:
    delivery_rate, baseline_undelivered, baseline_delivered = moments(params)
    # Relative residuals, so all three targets carry comparable weight despite differing by
    # an order of magnitude.
    return np.array([
        delivery_rate / TARGET_DELIVERY_RATE - 1.0,
        baseline_undelivered / TARGET_BASELINE_UNDELIVERED - 1.0,
        baseline_delivered / TARGET_BASELINE_DELIVERED - 1.0,
    ])


def main() -> None:
    start = np.array([-5.0, 2.0, -8.0, 2.0])
    fit = least_squares(residuals, start, xtol=1e-14, ftol=1e-14, gtol=1e-14)
    delivery_intercept, selection_strength, baseline_intercept, activity_on_outcome = fit.x
    delivery_rate, baseline_undelivered, baseline_delivered = moments(fit.x)
    control_rate = delivery_rate * baseline_delivered + (1 - delivery_rate) * baseline_undelivered

    print(f"\nheld fixed: curvature = {CURVATURE}, interaction = {INTERACTION}")
    print("\nsolved parameters -- paste into src/simulate.py\n")
    print(f"    DELIVERY_INTERCEPT  = {delivery_intercept:+.4f}")
    print(f"    SELECTION_STRENGTH  = {selection_strength:+.4f}")
    print(f"    BASELINE_INTERCEPT  = {baseline_intercept:+.4f}")
    print(f"    ACTIVITY_ON_OUTCOME = {activity_on_outcome:+.4f}")

    print("\nmoments reproduced                fitted      target\n")
    print(f"    delivery rate              {delivery_rate:9.4%}  {TARGET_DELIVERY_RATE:9.4%}")
    print(f"    baseline, never delivered  {baseline_undelivered:9.4%}  {TARGET_BASELINE_UNDELIVERED:9.4%}")
    print(f"    baseline, delivered        {baseline_delivered:9.4%}  {TARGET_BASELINE_DELIVERED:9.4%}")
    print(f"    baseline ratio             {baseline_delivered / baseline_undelivered:9.1f}x "
          f"{TARGET_BASELINE_DELIVERED / TARGET_BASELINE_UNDELIVERED:8.1f}x")
    print(f"\n    implied control rate       {control_rate:9.4%}  {IMPLIED_CONTROL_RATE:9.4%}"
          f"   <- not fitted; closes if the other three do")
    print(f"\n    max relative residual      {np.abs(residuals(fit.x)).max():.2e}\n")


if __name__ == "__main__":
    main()
