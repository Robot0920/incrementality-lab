"""Measure the actual error rate of the interval methods in src/intervals.py.

A published formula transcribed into code is a hypothesis, not a result. This harness
tests it the only way that settles the question: simulate data where the answer is known,
apply the method the way it will actually be used, and count how often it is wrong.

Three quantities are measured under a true effect of exactly zero, at the allocation and
base rate of the study this repository runs:

    single-look Wald        inspected once, at the final sample size.
                            Expected ~= alpha. If this is off, the simulator is wrong, not
                            the method, so it runs first as a check on the harness itself.

    repeatedly-inspected    Wald evaluated at every checkpoint, counted as a failure if it
    Wald                    ever excludes zero. Expected to be far above alpha. This number
                            is the cost of looking at a fixed-horizon test more than once.

    confidence sequence     evaluated at every checkpoint, counted as a failure if it ever
                            excludes zero. Expected <= alpha, and this is the claim being
                            checked.

A second pass under a known non-zero effect reports coverage of the true value, which
catches an interval that achieves its error rate by being uselessly wide in one direction.

Run:
    python -m src.validate_intervals
    python -m src.validate_intervals --reps 2000 --base-rate 0.002 --alpha 0.05
"""

from __future__ import annotations

import argparse

import numpy as np

from src.intervals import confidence_sequence_difference, wald_difference


def checkpoint_sizes(n_total: int, treat_share: float, n_checks: int,
                     first_fraction: float) -> tuple[np.ndarray, np.ndarray]:
    """Log-spaced inspection points, as cumulative arm sizes.

    Inspections start at a fraction of the total rather than at the first observation: the
    method is asymptotic, and applying it before the normal approximation holds tests the
    approximation rather than the construction.
    """
    fractions = np.geomspace(first_fraction, 1.0, n_checks)
    n_treat = np.maximum(1, (n_total * treat_share * fractions).astype(np.int64))
    n_control = np.maximum(1, (n_total * (1.0 - treat_share) * fractions).astype(np.int64))
    return n_treat, n_control


def simulate(rng: np.random.Generator, n_treat: np.ndarray, n_control: np.ndarray,
             p_control: float, lift: float, reps: int) -> tuple[np.ndarray, np.ndarray]:
    """Cumulative successes at each checkpoint, shape (reps, n_checks).

    Increments between checkpoints are drawn independently and accumulated, which is
    equivalent to drawing one long stream and reading it at those points, but costs
    memory proportional to the number of checkpoints rather than to the sample size.
    """
    p_treat = p_control + lift
    inc_treat = np.diff(n_treat, prepend=0)
    inc_control = np.diff(n_control, prepend=0)

    x_treat = np.cumsum(
        rng.binomial(np.broadcast_to(inc_treat, (reps, inc_treat.size)), p_treat), axis=1
    )
    x_control = np.cumsum(
        rng.binomial(np.broadcast_to(inc_control, (reps, inc_control.size)), p_control), axis=1
    )
    return x_treat, x_control


def run(reps: int, n_total: int, treat_share: float, p_control: float, alpha: float,
        n_checks: int, first_fraction: float, seed: int) -> None:
    rng = np.random.default_rng(seed)
    n_treat, n_control = checkpoint_sizes(n_total, treat_share, n_checks, first_fraction)
    n_eff_final = 1.0 / (1.0 / n_treat[-1] + 1.0 / n_control[-1])

    print(f"\nreps={reps:,}  n_total={n_total:,}  treated={treat_share:.0%}  "
          f"base rate={p_control:.4%}  alpha={alpha}")
    print(f"{n_checks} inspections, log-spaced from {first_fraction:.0%} to 100% of the sample")
    print(f"confidence sequence tuned at t_opt = effective n at the final look = {n_eff_final:,.0f}\n")

    # ---- pass 1: no true effect. How often does each method claim one? ----------------
    x_treat, x_control = simulate(rng, n_treat, n_control, p_control, 0.0, reps)

    single_look = 0
    peeked_wald = 0
    sequence = 0
    for r in range(reps):
        ever_wald = False
        ever_cs = False
        for k in range(n_checks):
            w = wald_difference(int(x_treat[r, k]), int(n_treat[k]),
                                int(x_control[r, k]), int(n_control[k]), alpha)
            c = confidence_sequence_difference(int(x_treat[r, k]), int(n_treat[k]),
                                               int(x_control[r, k]), int(n_control[k]),
                                               t_opt=n_eff_final, alpha=alpha)
            ever_wald |= w.excludes_zero
            ever_cs |= c.excludes_zero
            if k == n_checks - 1 and w.excludes_zero:
                single_look += 1
        peeked_wald += ever_wald
        sequence += ever_cs

    def rate(count: int) -> str:
        p = count / reps
        se = (p * (1 - p) / reps) ** 0.5
        return f"{p:6.2%}  (+/- {1.96 * se:.2%})"

    print("false-positive rate under a true effect of exactly zero")
    print(f"  single-look Wald, final sample only   {rate(single_look)}   expect ~{alpha:.0%}"
          f"   <- checks the simulator")
    print(f"  Wald inspected at all {n_checks} points       {rate(peeked_wald)}   "
          f"expect >> {alpha:.0%}   <- the cost of peeking")
    print(f"  confidence sequence, all {n_checks} points    {rate(sequence)}   "
          f"expect <= {alpha:.0%}   <- the claim under test")

    verdict = "PASS" if sequence / reps <= alpha + 1.96 * (alpha * (1 - alpha) / reps) ** 0.5 else "FAIL"
    print(f"\n  confidence sequence verdict: {verdict}")

    # ---- pass 2: a known non-zero effect. Does the interval contain it? --------------
    lift = 2.0 * p_control  # a 200% relative lift, comfortably detectable at this size
    x_treat, x_control = simulate(rng, n_treat, n_control, p_control, lift, reps)

    covered = 0
    widths = []
    for r in range(reps):
        k = n_checks - 1
        c = confidence_sequence_difference(int(x_treat[r, k]), int(n_treat[k]),
                                           int(x_control[r, k]), int(n_control[k]),
                                           t_opt=n_eff_final, alpha=alpha)
        w = wald_difference(int(x_treat[r, k]), int(n_treat[k]),
                            int(x_control[r, k]), int(n_control[k]), alpha)
        covered += c.lower <= lift <= c.upper
        widths.append((c.upper - c.lower, w.upper - w.lower))

    widths_arr = np.array(widths)
    print(f"\ncoverage of a true lift of {lift:.4%} at the final look")
    print(f"  confidence sequence contains the truth   {covered / reps:6.2%}   "
          f"expect >= {1 - alpha:.0%}")
    print(f"  mean width, confidence sequence          {widths_arr[:, 0].mean():.6f}")
    print(f"  mean width, Wald                         {widths_arr[:, 1].mean():.6f}")
    print(f"  the sequence is {widths_arr[:, 0].mean() / widths_arr[:, 1].mean():.2f}x wider "
          f"-- this is the price of being allowed to look whenever you like\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reps", type=int, default=1000)
    ap.add_argument("--n-total", type=int, default=13_979_592)
    ap.add_argument("--treat-share", type=float, default=0.85)
    ap.add_argument("--base-rate", type=float, default=0.001938)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--n-checks", type=int, default=30)
    ap.add_argument("--first-fraction", type=float, default=0.02)
    ap.add_argument("--seed", type=int, default=20260925)
    args = ap.parse_args()
    run(args.reps, args.n_total, args.treat_share, args.base_rate, args.alpha,
        args.n_checks, args.first_fraction, args.seed)


if __name__ == "__main__":
    main()
