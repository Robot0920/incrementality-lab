"""Choose the boosted models' regularisation by held-out predictive loss.

The interim finding in docs/05_findings_estimation.md is that two regularisation settings
swing the estimated lift by up to 27 points. Both of those settings were chosen by hand,
which makes the finding incomplete: it shows that configuration matters, not what happens
when configuration is chosen responsibly.

One constraint governs everything here. **The selection must not look at the true effect.**
Tuning regularisation to minimise bias against a known answer would make the study
circular -- its entire premise is to measure what a team obtains when the answer is not
available. So the criterion is held-out log-loss, which is computable from observable data
alone and is what a competent team would actually use.

Log-loss suits this problem for a specific reason: scikit-learn clips predicted
probabilities before taking the logarithm, so a prediction of 1.0 against a true 0 costs
roughly 36 nats. Saturated models are therefore punished severely, which is the pathology
found in the `@def` configuration. The risk runs the other way: log-loss may over-regularise
and reintroduce the bias seen in `@reg`. If it does, that is a result rather than a defect.

The two models are selected separately, because their jobs are not the same:

    outcome model      fitted on assigned-but-undelivered units, predicting the outcome.
                       Its mean prediction enters the estimate directly, so accuracy in
                       level matters.
    propensity model   fitted on all treated units, predicting delivery. Its extremes
                       drive the inverse-propensity weights, so boundedness matters.

Selection runs on a dedicated simulated population with its own seed, never on the
replicates the study is evaluated on. Selecting and evaluating on the same draws would let
the selection flatter itself.

    python -m src.select_hyperparameters
"""

from __future__ import annotations

import argparse

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.model_selection import train_test_split

from src.estimators import BOOSTED_DEFAULTS, _train_target_masks
from src.simulate import simulate

GRID = [
    dict(min_samples_leaf=m, l2_regularization=l)
    for m in (20, 100, 500, 2000)
    for l in (0.0, 1.0, 10.0)
]


def select(x: np.ndarray, y: np.ndarray, *, label: str, seed: int,
           valid_fraction: float = 0.3) -> dict:
    """Return the grid entry with the lowest held-out log-loss, printing the whole grid."""
    x_fit, x_val, y_fit, y_val = train_test_split(
        x, y, test_size=valid_fraction, random_state=seed, stratify=y)

    print(f"\n  {label}")
    print(f"    fit rows {x_fit.shape[0]:,} ({int(y_fit.sum()):,} events)   "
          f"validation rows {x_val.shape[0]:,} ({int(y_val.sum()):,} events)")
    print(f"\n    {'min_samples_leaf':>17} {'l2':>6} {'log-loss':>12} {'brier':>12} "
          f"{'max pred':>10} {'pinned at 1':>12}")

    best, best_loss = None, np.inf
    for extra in GRID:
        model = HistGradientBoostingClassifier(**BOOSTED_DEFAULTS, **extra).fit(x_fit, y_fit)
        p = model.predict_proba(x_val)[:, 1]
        loss = log_loss(y_val, p, labels=[0, 1])
        brier = brier_score_loss(y_val, p)
        pinned = int((p >= 1.0).sum())
        marker = ""
        if loss < best_loss:
            best, best_loss = extra, loss
            marker = "  <- best so far"
        print(f"    {extra['min_samples_leaf']:>17} {extra['l2_regularization']:>6} "
              f"{loss:>12.6f} {brier:>12.8f} {p.max():>10.6f} {pinned:>12,}{marker}")

    print(f"\n    selected: {best}   held-out log-loss {best_loss:.6f}")
    return dict(**BOOSTED_DEFAULTS, **best)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=600_000)
    ap.add_argument("--observability", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=777, help="selection-only seed")
    args = ap.parse_args()

    print(f"\nselection population: n = {args.n:,}  observability = {args.observability}  "
          f"seed = {args.seed}")
    print("criterion: held-out log-loss. The true effect is never consulted.")

    p = simulate(n=args.n, observability=args.observability, seed=args.seed)
    train, _ = _train_target_masks(p.assigned, p.delivered)
    treated = p.assigned == 1

    outcome_kwargs = select(p.x[train], p.outcome[train],
                            label="outcome model: predict the outcome among undelivered units",
                            seed=args.seed)
    propensity_kwargs = select(p.x[treated], p.delivered[treated],
                               label="propensity model: predict delivery among treated units",
                               seed=args.seed)

    print("\n  paste into src/estimators.py\n")
    for name, kwargs in (("OUTCOME_KWARGS", outcome_kwargs),
                         ("PROPENSITY_KWARGS", propensity_kwargs)):
        extras = {k: v for k, v in kwargs.items() if k not in BOOSTED_DEFAULTS}
        print(f"    {name} = dict(**BOOSTED_DEFAULTS, "
              f"{', '.join(f'{k}={v}' for k, v in extras.items())})")
    print()


if __name__ == "__main__":
    main()
