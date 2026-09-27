"""Does the simulator's realised output match the population it was calibrated to?

`scripts/calibrate_simulator.py` solves the data-generating process against three moments
of the reference dataset, computing those moments exactly by quadrature. Drawing a finite
sample from the same process gives a different number: 16.6x against a population value of
18.3x for the baseline ratio, a 9% gap. There are exactly two explanations and they have
very different consequences:

    finite-sample error   the sample simply has not seen enough of the tail. Harmless,
                          and it tells us how large n must be for the study.
    a defect              the quadrature and the sampling code are not computing the same
                          quantity. Everything built on the simulator would be worthless.

This script separates them.

Result, recorded because a prediction that fails is part of the finding: the directional
prediction made when this was written -- that delivery concentrates in the right tail, so
the sample ratio should approach the population value *from below* -- was not supported.
With enough replicates the sample ratio is already within sampling error of 18.29x at one
million rows, with no downward bias at any size tested. The original 9% gap was entirely a
definitional error in `src/simulate.py`, which compared delivered units against everyone
undelivered rather than against assigned-but-undelivered units, and so included a control
arm that still held the high-activity units delivery would have taken. One cause, not two.

The verdict criterion reflects that: the question is whether the realised value sits within
sampling error of the population value at every size, not whether it climbs toward it. An
estimator that is already unbiased has nothing to converge from.

The second output matters more than the first. The headline study sweeps a parameter grid
and measures estimator bias at each point; a bias measurement is only meaningful if it is
larger than the simulator's own noise. This script reports the sample size at which that
noise falls below a chosen tolerance, which sets n for the whole study. It is the power
analysis for the simulation, and the same logic as computing a minimum detectable effect
for a real experiment.

Memory is constant: four scalar sums are accumulated over chunks rather than materialising
the full sample, so n is limited by time rather than by RAM.

    python scripts/check_simulator_convergence.py
"""

from __future__ import annotations

import numpy as np
from scipy.special import expit

# Parameters as solved by scripts/calibrate_simulator.py.
DELIVERY_INTERCEPT = -5.1321
SELECTION_STRENGTH = 2.2022
BASELINE_INTERCEPT = -8.4780
ACTIVITY_ON_OUTCOME = 2.1542

CHUNK = 2_000_000
SAMPLE_SIZES = [1_000_000, 4_000_000, 16_000_000, 64_000_000]
SEEDS_BY_SIZE = {1_000_000: 16, 4_000_000: 12, 16_000_000: 8, 64_000_000: 4}
TOLERANCE = 0.02  # relative standard deviation we are willing to accept for the study


def population_values() -> tuple[float, float, float]:
    """Exact moments by Gauss-Hermite quadrature: delivery rate, ratio, and the baselines."""
    nodes, weights = np.polynomial.hermite_e.hermegauss(200)
    weights = weights / weights.sum()
    d = expit(DELIVERY_INTERCEPT + SELECTION_STRENGTH * nodes)
    base = expit(BASELINE_INTERCEPT + ACTIVITY_ON_OUTCOME * nodes)
    delivery_rate = float(weights @ d)
    delivered_baseline = float((weights @ (base * d)) / delivery_rate)
    rest_baseline = float((weights @ (base * (1 - d))) / (1 - delivery_rate))
    return delivery_rate, delivered_baseline / rest_baseline, delivered_baseline


def sample_ratio(n: int, seed: int) -> tuple[float, float]:
    """Realised delivery rate and baseline ratio, accumulated in constant memory."""
    rng = np.random.default_rng(seed)
    s_base_delivered = s_delivered = s_base_rest = s_rest = 0.0
    remaining = n
    while remaining > 0:
        m = min(CHUNK, remaining)
        remaining -= m
        activity = rng.standard_normal(m)
        delivered = rng.random(m) < expit(DELIVERY_INTERCEPT + SELECTION_STRENGTH * activity)
        base = expit(BASELINE_INTERCEPT + ACTIVITY_ON_OUTCOME * activity)
        s_base_delivered += float(base[delivered].sum())
        s_delivered += float(delivered.sum())
        s_base_rest += float(base[~delivered].sum())
        s_rest += float((~delivered).sum())
    ratio = (s_base_delivered / s_delivered) / (s_base_rest / s_rest)
    return s_delivered / n, ratio


def main() -> None:
    pop_delivery, pop_ratio, _ = population_values()
    print(f"\npopulation values by quadrature: delivery {pop_delivery:.4%}, "
          f"baseline ratio {pop_ratio:.2f}x\n")
    print(f"{'n':>12}  {'seeds':>5}  {'mean ratio':>11}  {'sd':>7}  {'rel sd':>7}  "
          f"{'gap to pop':>11}  {'gap in SE':>9}")
    print("-" * 78)

    results = []
    for n in SAMPLE_SIZES:
        seeds = SEEDS_BY_SIZE[n]
        ratios = np.array([sample_ratio(n, seed=1000 + n // 1000 + s)[1] for s in range(seeds)])
        mean, sd = ratios.mean(), ratios.std(ddof=1)
        se = sd / np.sqrt(seeds)
        gap = mean - pop_ratio
        print(f"{n:>12,}  {seeds:>5}  {mean:>10.2f}x  {sd:>7.3f}  {sd / mean:>6.2%}  "
              f"{gap:>+10.2f}x  {gap / se:>+8.1f}")
        results.append((n, mean, sd))

    print()
    ns = np.array([r[0] for r in results], dtype=float)
    means = np.array([r[1] for r in results])
    sds = np.array([r[2] for r in results])

    # Primary evidence: at every sample size, is the realised value within sampling error
    # of the population value? Convergence toward it is a special case, not the criterion:
    # an estimator that is unbiased at the smallest size has nothing to converge from.
    gaps_in_se = np.array([
        abs(mean - pop_ratio) / (sd / np.sqrt(SEEDS_BY_SIZE[n]))
        for n, mean, sd in results
    ])
    worst = float(gaps_in_se.max())
    print(f"  largest deviation at any size       {worst:.1f} SE  (indistinguishable if < 2)")
    print(f"  monotone in n                       {bool(np.all(np.diff(means) > 0))}"
          f"   (a note, not a criterion)")

    # Secondary diagnostic, reported honestly rather than used to decide. A standard
    # deviation estimated from k replicates carries a relative error of about
    # 1/sqrt(2(k-1)), so with this many seeds the slope is imprecise, and a slope that
    # departs from -0.50 is weak evidence on its own.
    slope = float(np.polyfit(np.log(ns), np.log(sds), 1)[0])
    worst_k = min(SEEDS_BY_SIZE.values())
    print(f"  log-log slope of sd against n       {slope:+.2f}   (sampling error predicts -0.50;"
          f" sd itself is +-{1 / np.sqrt(2 * (worst_k - 1)):.0%} at the smallest seed count)")

    verdict = "unbiased at every size tested" if worst < 2.0 else "INVESTIGATE"
    print(f"\n  verdict: {verdict}   (decided on the deviations, not on the slope)")

    # The output the next step actually needs.
    rel_sd = sds / means
    fit = np.polyfit(np.log(ns), np.log(rel_sd), 1)
    n_needed = float(np.exp((np.log(TOLERANCE) - fit[1]) / fit[0]))
    print(f"\n  relative sd falls below {TOLERANCE:.0%} at n ~ {n_needed:,.0f}")
    print("  -> use this as the per-grid-point sample size for the headline study\n")


if __name__ == "__main__":
    main()
