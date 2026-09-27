"""Solve for the simulator parameters that reproduce the reference dataset's moments.

Hand-tuning simulation parameters until the output "looks about right" is how a simulation
stops being evidence. These four parameters are instead solved for, against three moments
measured on the real data, so the calibration is reproducible and auditable.

Targets, all measured on Criteo-UPLIFT v2.1 (see README section 2):

    delivery rate                       3.604%
    baseline of never-delivered units   0.1194%   (observed directly: assigned, not delivered)
    baseline of delivered units         2.1837%   (recovered from the mixture identity)

The control rate of 0.1938% is not a fourth target: randomisation makes it the mixture of
the two baselines at the delivery rate, so matching those two implies it. It is printed as
a check that the arithmetic closes.

Expectations are computed by Gauss-Hermite quadrature rather than by sampling, so the
solve is deterministic and free of Monte Carlo noise.

    python scripts/calibrate_simulator.py
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares
from scipy.special import expit

TARGET_DELIVERY_RATE = 0.03604
TARGET_BASELINE_UNDELIVERED = 0.001194
TARGET_BASELINE_DELIVERED = 0.021837
IMPLIED_CONTROL_RATE = (
    TARGET_DELIVERY_RATE * TARGET_BASELINE_DELIVERED
    + (1 - TARGET_DELIVERY_RATE) * TARGET_BASELINE_UNDELIVERED
)

# 200-node Gauss-Hermite quadrature for expectations over a standard normal latent trait.
_nodes, _weights = np.polynomial.hermite_e.hermegauss(200)
_weights = _weights / _weights.sum()


def moments(params: np.ndarray) -> tuple[float, float, float]:
    delivery_intercept, selection_strength, baseline_intercept, activity_on_outcome = params
    d = expit(delivery_intercept + selection_strength * _nodes)
    base = expit(baseline_intercept + activity_on_outcome * _nodes)

    delivery_rate = float(_weights @ d)
    baseline_delivered = float((_weights @ (base * d)) / delivery_rate)
    baseline_undelivered = float((_weights @ (base * (1 - d))) / (1 - delivery_rate))
    return delivery_rate, baseline_undelivered, baseline_delivered


def residuals(params: np.ndarray) -> np.ndarray:
    delivery_rate, baseline_undelivered, baseline_delivered = moments(params)
    # Relative residuals, so all three targets carry comparable weight despite differing
    # by an order of magnitude.
    return np.array([
        delivery_rate / TARGET_DELIVERY_RATE - 1.0,
        baseline_undelivered / TARGET_BASELINE_UNDELIVERED - 1.0,
        baseline_delivered / TARGET_BASELINE_DELIVERED - 1.0,
    ])


def main() -> None:
    start = np.array([-4.0, 1.5, -7.0, 1.5])
    fit = least_squares(residuals, start, xtol=1e-14, ftol=1e-14, gtol=1e-14)
    delivery_intercept, selection_strength, baseline_intercept, activity_on_outcome = fit.x
    delivery_rate, baseline_undelivered, baseline_delivered = moments(fit.x)
    control_rate = delivery_rate * baseline_delivered + (1 - delivery_rate) * baseline_undelivered

    print("\nsolved parameters -- paste into src/simulate.py defaults\n")
    print(f"    delivery_intercept   = {delivery_intercept:+.4f}")
    print(f"    selection_strength   = {selection_strength:+.4f}")
    print(f"    baseline_intercept   = {baseline_intercept:+.4f}")
    print(f"    activity_on_outcome  = {activity_on_outcome:+.4f}")

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
