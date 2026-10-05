"""The study: how estimator error behaves as the confounder becomes unobservable.

Everything measured so far sits at `observability = 1.0`, where the covariates reveal the
confounding trait exactly. That endpoint isolates **estimation** error: conditional
ignorability holds, the modelled counterfactual is identified, and any bias is the model's
fault rather than the data's. The answer there was already uncomfortable -- the best
properly tuned estimator sat at +6.7%.

This sweep varies the one thing that matters in practice. Real covariates never reveal the
whole confounder, and as `observability` falls the modelled counterfactual stops being
identified at all. The question is not whether bias appears -- it must -- but how fast, and
whether any estimator degrades gracefully.

Two configurations are carried through the whole sweep rather than one:

    def   scikit-learn's defaults, which saturate
    sel   chosen by held-out log-loss, separately per nuisance model

so the finding that configuration moves the answer can be checked at every grid point
instead of resting on a single one.

Reporting lives in src/report_study.py: this module only computes and records
per-replicate estimates, so a grid can be extended without recomputing what already exists.

Primary outcome is the decision-flip rate, not the bias. With break-even placed at
`threshold * true_effect`:

    threshold < 1   the correct decision is to ship.    A flip is estimate <  break-even
    threshold > 1   the correct decision is to decline. A flip is estimate >= break-even

The rate is reported as a function of the threshold rather than at one chosen value,
because no cost data exists here from which to derive a single break-even point. Anyone
with their own cost structure can read their own point off the curve.

Expect the curve to peak near threshold = 1 for every estimator, unbiased ones included:
a decision taken exactly at break-even is a coin flip no matter how good the estimate. What
bias shows up as is the asymmetry around that peak -- a positively biased estimator keeps
flipping for thresholds slightly above 1, which is the failure that costs money, shipping
what is not worth shipping.

    python -m src.run_study
    python -m src.run_study --reps 4 --n 200000        # a fast smoke run
"""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import numpy as np

from src.estimators import (
    BOOSTED_DEFAULTS,
    OUTCOME_KWARGS,
    PROPENSITY_KWARGS,
    aipw_both,
    itt,
    late,
    modelled_counterfactual,
    naive_delivered_vs_control,
)
from src.simulate import simulate

GRID_OBSERVABILITY = [1.0, 0.75, 0.5, 0.25, 0.0]
CONFIGS = {
    "def": (BOOSTED_DEFAULTS, BOOSTED_DEFAULTS),
    "sel": (OUTCOME_KWARGS, PROPENSITY_KWARGS),
}
THRESHOLDS = [0.25, 0.5, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5]

RESULTS = Path(__file__).resolve().parents[1] / "results"
RAW = RESULTS / "study_raw.csv"


def one_replicate(p, folds: int, seed: int) -> list[tuple[str, float, float]]:
    """(estimator, estimate, truth) for every estimator on one population."""
    rows = []
    for est in (
        naive_delivered_vs_control(p.outcome, p.assigned, p.delivered),
        itt(p.outcome, p.assigned),
        late(p.outcome, p.assigned, p.delivered),
        modelled_counterfactual(p.x, p.outcome, p.assigned, p.delivered, model="logistic"),
    ):
        truth = p.true_itt if est.targets == "true_itt" else p.true_effect
        rows.append((est.method, est.value, truth))

    for label, (outcome_kwargs, propensity_kwargs) in CONFIGS.items():
        plain, hajek = aipw_both(p.x, p.outcome, p.assigned, p.delivered, folds=folds,
                                 seed=seed, boosted_kwargs=outcome_kwargs,
                                 propensity_kwargs=propensity_kwargs)
        for est in (
            modelled_counterfactual(p.x, p.outcome, p.assigned, p.delivered,
                                    model="boosted", boosted_kwargs=outcome_kwargs),
            modelled_counterfactual(p.x, p.outcome, p.assigned, p.delivered,
                                    model="boosted", calibrate=True, seed=seed,
                                    boosted_kwargs=outcome_kwargs),
            plain,
            hajek,
        ):
            rows.append((f"{est.method}@{label}", est.value, p.true_effect))
    return rows


def flip_rate(estimates: np.ndarray, truth: float, threshold: float) -> float:
    """Share of replicates whose decision differs from the decision under the truth."""
    break_even = threshold * truth
    if truth >= break_even:                      # correct decision: ship
        return float((estimates < break_even).mean())
    return float((estimates >= break_even).mean())  # correct decision: decline


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=600_000)
    ap.add_argument("--reps", type=int, default=12)
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--seed", type=int, default=20261001)
    ap.add_argument("--grid", type=float, nargs="*", default=GRID_OBSERVABILITY,
                    help="observability values to sweep")
    ap.add_argument("--out", type=Path, default=RAW,
                    help="where to write per-replicate estimates")
    args = ap.parse_args()

    RESULTS.mkdir(exist_ok=True)
    started = time.time()
    raw: list[dict] = []

    for observability in args.grid:
        point_started = time.time()
        for r in range(args.reps):
            seed = args.seed + int(observability * 1000) + r
            p = simulate(n=args.n, observability=observability, seed=seed)
            for method, estimate, truth in one_replicate(p, args.folds, seed):
                raw.append({"observability": observability, "replicate": r,
                            "estimator": method, "estimate": estimate, "truth": truth})
        print(f"  observability {observability:.2f} done in "
              f"{time.time() - point_started:.0f}s", flush=True)

    with args.out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["observability", "replicate", "estimator",
                                                "estimate", "truth"])
        writer.writeheader()
        writer.writerows(raw)
    print(f"\nwrote {len(raw):,} rows to {args.out}")

    print(f"total elapsed {time.time() - started:.0f}s\n")


if __name__ == "__main__":
    main()
