"""Settle three open questions about why the estimators behaved as they did.

Each is a hypothesis with a matching sign but no measurement behind it. The simulator
holds the ground truth for all three, which is the reason it exists.

1. Extreme AIPW weights: population or fitted model?
   The measured maximum weight was 999, the clipping ceiling. But the true propensity at
   the most extreme activity level a sample this size produces is about 0.97, implying a
   weight near 34. If the fitted propensity reaches 0.999 where the true one does not, the
   weights are an artefact of estimation in a sparse region -- leaf purity producing
   certainty the population does not have -- rather than a genuine overlap failure. The
   two diagnoses call for different remedies, so they must be separated.

2. Isotonic calibration: does the map have to extrapolate?
   Isotonic regression is defined only between the smallest and largest value it was
   fitted on, and outside that range `out_of_bounds="clip"` pins predictions to the
   boundary. The calibration set is drawn from undelivered units and the target set from
   delivered ones, which sit higher in predicted probability. If a material share of
   target predictions exceed the calibration range they are clipped downward, the
   counterfactual falls, and the estimated lift rises -- which matches the observed +53.4%.

3. Calibration versus data halving.
   The calibrated variant fits its model on half the training rows and the uncalibrated
   variant on all of them. Some of the degradation may be the smaller training set rather
   than the calibration map. Attributing all of it to calibration without checking would
   be the same mistake as reading a single replicate as bias.

    python scripts/diagnose_estimators.py
"""

from __future__ import annotations

import numpy as np
from scipy.special import expit
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import train_test_split

from src.estimators import BOOSTED_KWARGS, _cross_fit_nuisances, _train_target_masks
from src.simulate import delivery_logit, simulate

N = 600_000
SEED = 20260929
OBSERVABILITY = 1.0


def question_one(p) -> None:
    print("\n" + "=" * 78)
    print("1. extreme weights: population overlap, or propensity estimation error?")
    print("=" * 78)

    _, d_t, _, e_hat = _cross_fit_nuisances(p.x, p.outcome, p.assigned, p.delivered, 3, 0)
    e_true = expit(delivery_logit(p.activity[p.assigned == 1]))

    def weight(e):
        return e / (1.0 - np.minimum(e, 0.999999))

    print(f"\n  treated units                      {e_true.size:,}")
    print(f"  max activity in this sample        {p.activity[p.assigned == 1].max():.2f}")
    print(f"\n  {'':<34}{'true e':>12}{'fitted e':>12}")
    for q in (0.99, 0.999, 0.9999, 1.0):
        label = "maximum" if q == 1.0 else f"quantile {q}"
        print(f"  {label:<34}{np.quantile(e_true, q):>12.5f}{np.quantile(e_hat, q):>12.5f}")
    print(f"  {'implied max weight':<34}{weight(e_true.max()):>12.1f}{weight(e_hat.max()):>12.1f}")

    overconfident = int(((e_hat > 0.99) & (e_true < 0.99)).sum())
    genuinely_extreme = int((e_true > 0.99).sum())
    print(f"\n  units with true e > 0.99                     {genuinely_extreme:,}")
    print(f"  units the model calls > 0.99 that are not    {overconfident:,}")

    # Saturation: a predicted probability of exactly 0 or 1 means the leaf's logit was
    # pushed to an extreme with nothing holding it back. No finite sample supports that
    # claim, so any non-zero count here is a configuration problem, not a data property.
    print(f"\n  fitted e pinned at exactly 1.0               {int((e_hat >= 1.0).sum()):,}")
    print(f"  fitted e pinned at exactly 0.0               {int((e_hat <= 0.0).sum()):,}")

    verdict = ("propensity ESTIMATION error" if overconfident > 10 * max(genuinely_extreme, 1)
               else "genuine population overlap failure")
    print(f"\n  verdict: {verdict}")


def question_two_and_three(p) -> None:
    print("\n" + "=" * 78)
    print("2. does the isotonic map have to extrapolate?")
    print("   3. calibration map, or the halved training set?")
    print("=" * 78)

    train, target = _train_target_masks(p.assigned, p.delivered)
    x_train, y_train = p.x[train], p.outcome[train]

    full = HistGradientBoostingClassifier(**BOOSTED_KWARGS).fit(x_train, y_train)
    cf_full = full.predict_proba(p.x[target])[:, 1]

    fit_idx, calib_idx = train_test_split(
        np.arange(y_train.size), test_size=0.5, random_state=SEED, stratify=y_train)
    half = HistGradientBoostingClassifier(**BOOSTED_KWARGS).fit(
        x_train[fit_idx], y_train[fit_idx])
    raw_calib = half.predict_proba(x_train[calib_idx])[:, 1]
    raw_target = half.predict_proba(p.x[target])[:, 1]

    isotonic = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(
        raw_calib, y_train[calib_idx])
    cf_calibrated = isotonic.predict(raw_target)

    above = float((raw_target > raw_calib.max()).mean())
    print(f"\n  calibration set size               {calib_idx.size:,}"
          f"   positives {int(y_train[calib_idx].sum()):,}")
    print(f"  max prediction in calibration set  {raw_calib.max():.5f}")
    print(f"  delivered units, prediction quantiles")
    for q in (0.5, 0.9, 0.99, 1.0):
        label = "max" if q == 1.0 else f"q{q}"
        print(f"      {label:<8}{np.quantile(raw_target, q):>12.5f}")
    print(f"\n  share of delivered predictions ABOVE the calibration range   {above:.2%}")

    print("\n  outcome-model saturation")
    for label, v in (("calibration set", raw_calib), ("delivered units", raw_target)):
        print(f"      {label:<18} exactly 1.0 = {int((v >= 1.0).sum()):>6,}"
              f"   exactly 0.0 = {int((v <= 0.0).sum()):>6,}"
              f"   above 0.99 = {int((v > 0.99).sum()):>6,}   of {v.size:,}")

    observed = p.outcome[target].mean()
    truth = p.true_effect
    print(f"\n  {'':<40}{'counterfactual':>15}{'implied lift':>14}{'error':>10}")
    for label, cf in (("full training data, no map  (Level 2)", cf_full),
                      ("half training data, no map", raw_target),
                      ("half training data + isotonic", cf_calibrated)):
        lift = observed - cf.mean()
        print(f"  {label:<40}{cf.mean():>15.6f}{lift:>14.6f}{lift / truth - 1:>+9.1%}")

    halving = (observed - raw_target.mean()) - (observed - cf_full.mean())
    mapping = (observed - cf_calibrated.mean()) - (observed - raw_target.mean())
    total = halving + mapping
    print(f"\n  damage attributable to halving the data   {halving:+.6f}"
          f"   ({halving / total:.0%} of the total)")
    print(f"  damage attributable to the isotonic map   {mapping:+.6f}"
          f"   ({mapping / total:.0%} of the total)")


def main() -> None:
    print(f"\nn = {N:,}   observability = {OBSERVABILITY}   seed = {SEED}")
    p = simulate(n=N, observability=OBSERVABILITY, seed=SEED)
    question_one(p)
    question_two_and_three(p)
    print()


if __name__ == "__main__":
    main()
