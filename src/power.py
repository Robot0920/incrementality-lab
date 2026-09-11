"""Pod 0 / S4 — the sample-size conversation, quantified.

The single most useful thing to hand a PM is not "how long will the test take" but a
TRADEOFF TABLE: holdout size vs detectable effect. Power is governed by the smaller
arm, so shrinking the holdout to protect revenue has a floor, and this prints it.

Run:
    python -m src.power                     # uses the real Criteo base rates
    python -m src.power --base-rate 0.002 --n-total 5_000_000
"""

from __future__ import annotations

import argparse

from scipy.stats import norm


def mde_absolute(p: float, n_control: float, n_treat: float, alpha: float = 0.05, power: float = 0.80) -> float:
    """Minimum detectable effect, in absolute percentage points.

    Two-proportion z-test, two-sided. The (z_alpha/2 + z_beta) multiplier is ~2.80
    for the conventional alpha=.05 / power=.80 —— 面试里直接说 "2.8 倍标准误" 就够。
    """
    z = norm.ppf(1 - alpha / 2) + norm.ppf(power)
    se = (p * (1 - p) * (1 / n_control + 1 / n_treat)) ** 0.5
    return z * se


def table(base_rate: float, n_total: float, alpha: float = 0.05, power: float = 0.80) -> None:
    print(f"\nbase rate = {base_rate:.4%}   total users = {n_total:,.0f}   alpha = {alpha}   power = {power}\n")
    print(f"{'holdout':>9} {'n_control':>12} {'n_treat':>13} {'MDE (abs pp)':>14} {'MDE (rel)':>10}")
    print("-" * 62)
    for share in (0.50, 0.30, 0.20, 0.15, 0.10, 0.05, 0.01):
        n_c = n_total * share
        n_t = n_total * (1 - share)
        mde = mde_absolute(base_rate, n_c, n_t, alpha, power)
        print(f"{share:>8.0%} {n_c:>12,.0f} {n_t:>13,.0f} {100*mde:>13.4f} {mde/base_rate:>9.1%}")
    print(
        "\nRead it as: every row to the left of your chosen holdout is monetised traffic\n"
        "you bought back, paid for with statistical power. The 1% row is where the\n"
        "experiment stops being able to detect anything worth shipping."
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    # defaults = the Criteo-UPLIFT conversion base rate and sample size
    ap.add_argument("--base-rate", type=float, default=0.001938)
    ap.add_argument("--n-total", type=float, default=13_979_592)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--power", type=float, default=0.80)
    args = ap.parse_args()
    table(args.base_rate, args.n_total, args.alpha, args.power)


if __name__ == "__main__":
    main()
