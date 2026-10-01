"""Estimators of the effect of delivery, at three levels of strength.

Rationale for each choice is in docs/04_estimator_selection.md. This module only
implements them.

Two groups:

randomisation-protected     itt, late
    Use the assignment only. Unbiased because assignment was randomised, whatever the
    delivery mechanism does. These are the ground truth the modelled estimators are
    graded against.

modelled counterfactual     naive, level 1 (logistic), level 2 (boosted), level 3 (AIPW)
    Use the treated arm only, as production reporting does: train a baseline model on
    units that received nothing, predict what the delivered units would have done, and
    take the difference. All of them require conditional ignorability, which no amount of
    model capacity can supply.

Every modelled estimator targets the same quantity -- the effect among delivered units,
comparable to `Population.true_effect`. `itt` targets `Population.true_itt` instead, since
it is diluted by everyone never delivered to.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, train_test_split

# Kept modest on purpose: the study needs on the order of a thousand fits on two cores.
#
# min_samples_leaf and l2_regularization are set away from their defaults deliberately.
# A leaf value is a Newton step, -sum(gradient) / (sum(hessian) + lambda), and the hessian
# is p*(1-p). As p approaches 0 or 1 that denominator collapses, so with lambda = 0 (the
# default) the step is unbounded and 150 iterations can drive expit(raw_score) to exactly
# 1.0 in float64. Measured with the defaults: the propensity model pinned 8 units at
# exactly 1.0, giving them infinite inverse-propensity weight, and the outcome model pinned
# 234 of 18,347 delivered units at exactly 1.0, which alone accounted for half the
# estimated counterfactual mean. The default of 20 for min_samples_leaf also lets the tree
# isolate a tail leaf whose hessian sum is negligible.
# The two configurations differ in exactly those two knobs and nothing else, so any
# difference in the estimates is attributable to them alone.
BOOSTED_DEFAULTS = dict(max_iter=150, learning_rate=0.1, max_leaf_nodes=31,
                        early_stopping=False, random_state=0)
BOOSTED_REGULARISED = dict(**BOOSTED_DEFAULTS, min_samples_leaf=500, l2_regularization=1.0)
BOOSTED_KWARGS = BOOSTED_REGULARISED

LOGISTIC_KWARGS = dict(max_iter=1000)

# Propensity clipping. Without it, e(X) -> 1 makes the AIPW weight diverge. With it, the
# number of clipped units is reported rather than hidden, because a large count is itself
# the overlap diagnosis.
E_MIN, E_MAX = 1e-6, 0.999


@dataclass(frozen=True)
class Estimate:
    value: float
    method: str
    targets: str                               # which truth this should be compared against
    diagnostics: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.value:+.6f}  ({self.method}, targets {self.targets})"


# --------------------------------------------------------------------------- ground truth

def itt(outcome: np.ndarray, assigned: np.ndarray) -> Estimate:
    """Difference in outcome rates between the whole treated arm and the control arm."""
    value = outcome[assigned == 1].mean() - outcome[assigned == 0].mean()
    return Estimate(float(value), "itt", "true_itt")


def late(outcome: np.ndarray, assigned: np.ndarray, delivered: np.ndarray) -> Estimate:
    """ITT divided by the delivery rate. Valid under one-sided non-compliance."""
    delivery_rate = delivered[assigned == 1].mean()
    value = itt(outcome, assigned).value / delivery_rate
    return Estimate(float(value), "late", "true_effect",
                    {"delivery_rate": float(delivery_rate)})


# ------------------------------------------------------------------ modelled counterfactual

def naive_delivered_vs_control(outcome: np.ndarray, assigned: np.ndarray,
                               delivered: np.ndarray) -> Estimate:
    """Delivered units against the whole control arm.

    Retained to quantify how wrong the common comparison is. It conditions on delivery,
    which is decided after randomisation, so it is not an estimate of anything.
    """
    value = outcome[delivered == 1].mean() - outcome[assigned == 0].mean()
    return Estimate(float(value), "naive_delivered_vs_control", "true_effect")


def _train_target_masks(assigned: np.ndarray, delivered: np.ndarray):
    """Training set received nothing; target set received delivery. Control arm unused."""
    train = (assigned == 1) & (delivered == 0)
    target = delivered == 1
    return train, target


def modelled_counterfactual(x: np.ndarray, outcome: np.ndarray, assigned: np.ndarray,
                            delivered: np.ndarray, *, model: str = "logistic",
                            calibrate: bool = False, seed: int = 0,
                            boosted_kwargs: dict | None = None) -> Estimate:
    """Levels 1 and 2: fit a baseline model on untreated units, predict for treated ones.

    `model="logistic"`  linear in the logit, calibrated in-sample by construction.
    `model="boosted"`   nonparametric, no calibration guarantee, extrapolates flat.
    `calibrate=True`    (boosted only) fit a monotone map from predicted probability to
                        observed frequency on held-out training rows.
    """
    boosted_kwargs = BOOSTED_KWARGS if boosted_kwargs is None else boosted_kwargs
    train, target = _train_target_masks(assigned, delivered)
    x_train, y_train = x[train], outcome[train]
    calibration_positives = None

    if model == "logistic":
        fitted = LogisticRegression(**LOGISTIC_KWARGS).fit(x_train, y_train)
        counterfactual = fitted.predict_proba(x[target])[:, 1]
        name = "level1_logistic"

    elif model == "boosted" and not calibrate:
        fitted = HistGradientBoostingClassifier(**boosted_kwargs).fit(x_train, y_train)
        counterfactual = fitted.predict_proba(x[target])[:, 1]
        name = "level2_boosted"

    elif model == "boosted":
        # Boosting carries no calibration guarantee, and this estimator is a difference of
        # means of predicted probabilities, so an offset in the predictions becomes bias
        # one for one. Half the training rows fit the model; the other half fit a monotone
        # map from predicted probability to observed frequency. Isotonic regression needs
        # events to be stable, so the number available is reported rather than assumed.
        fit_idx, calib_idx = train_test_split(
            np.arange(y_train.size), test_size=0.5, random_state=seed, stratify=y_train)
        booster = HistGradientBoostingClassifier(**boosted_kwargs).fit(
            x_train[fit_idx], y_train[fit_idx])
        raw = booster.predict_proba(x_train[calib_idx])[:, 1]
        isotonic = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(
            raw, y_train[calib_idx])
        counterfactual = isotonic.predict(booster.predict_proba(x[target])[:, 1])
        calibration_positives = int(y_train[calib_idx].sum())
        name = "level2_boosted_calibrated"

    else:
        raise ValueError(f"unknown model: {model!r}")

    value = outcome[target].mean() - counterfactual.mean()
    diagnostics = {
        "counterfactual_mean": float(counterfactual.mean()),
        "observed_mean": float(outcome[target].mean()),
        "n_train": int(train.sum()),
        "positives_train": int(y_train.sum()),
    }
    if calibration_positives is not None:
        diagnostics["calibration_positives"] = calibration_positives
    return Estimate(float(value), name, "true_effect", diagnostics)


def aipw_cross_fitted(x: np.ndarray, outcome: np.ndarray, assigned: np.ndarray,
                      delivered: np.ndarray, *, folds: int = 3, seed: int = 0,
                      normalized: bool = True,
                      boosted_kwargs: dict | None = None) -> Estimate:
    """Level 3: doubly robust, cross-fitted.

    Estimates the counterfactual mean for delivered units as

        E[Y(0) | D=1] = mean[ D*mu(X) + (1-D) * (e/(1-e)) * (Y - mu(X)) ] / P(D=1)

    where mu is the outcome model fitted on undelivered units and e the propensity model.
    Consistent if either nuisance model is correct, and the bias is the product of their
    two errors rather than the sum -- which is what allows machine-learning nuisances to be
    used at all. Cross-fitting is required for that result: nuisance predictions must not
    be made on the rows that trained them.

    Everything is computed within the treated arm. The control arm is not used, because the
    study's premise is that it is unavailable.
    """
    y_t, d_t, mu, e = _cross_fit_nuisances(x, outcome, assigned, delivered, folds, seed,
                                           boosted_kwargs)
    return _aipw_from_nuisances(y_t, d_t, mu, e, normalized=normalized, folds=folds)


def aipw_both(x: np.ndarray, outcome: np.ndarray, assigned: np.ndarray,
              delivered: np.ndarray, *, folds: int = 3, seed: int = 0,
              boosted_kwargs: dict | None = None) -> tuple[Estimate, Estimate]:
    """Both weight forms from a single cross-fitting pass.

    Cross-fitting is the expensive part -- two nuisance models per fold. The two weight
    forms differ only in arithmetic applied afterwards, so fitting twice would double the
    cost for nothing. Their difference is the cost of the naive specification, measured.
    """
    y_t, d_t, mu, e = _cross_fit_nuisances(x, outcome, assigned, delivered, folds, seed,
                                           boosted_kwargs)
    return (_aipw_from_nuisances(y_t, d_t, mu, e, normalized=False, folds=folds),
            _aipw_from_nuisances(y_t, d_t, mu, e, normalized=True, folds=folds))


def _cross_fit_nuisances(x, outcome, assigned, delivered, folds, seed, boosted_kwargs=None):
    """Out-of-fold predictions of the outcome and propensity models, within the treated arm."""
    boosted_kwargs = BOOSTED_KWARGS if boosted_kwargs is None else boosted_kwargs
    treated = assigned == 1
    x_t, y_t, d_t = x[treated], outcome[treated], delivered[treated]

    mu = np.empty(d_t.size, dtype=float)
    e = np.empty(d_t.size, dtype=float)

    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    for fit_idx, eval_idx in splitter.split(x_t, d_t):
        undelivered = fit_idx[d_t[fit_idx] == 0]
        outcome_model = HistGradientBoostingClassifier(**boosted_kwargs).fit(
            x_t[undelivered], y_t[undelivered])
        propensity_model = HistGradientBoostingClassifier(**boosted_kwargs).fit(
            x_t[fit_idx], d_t[fit_idx])
        mu[eval_idx] = outcome_model.predict_proba(x_t[eval_idx])[:, 1]
        e[eval_idx] = propensity_model.predict_proba(x_t[eval_idx])[:, 1]

    return y_t, d_t, mu, e


def _aipw_from_nuisances(y_t, d_t, mu, e, *, normalized: bool, folds: int) -> Estimate:
    """The cheap arithmetic, separated so both weight forms share one cross-fitting pass."""
    clipped = int(((e < E_MIN) | (e > E_MAX)).sum())
    e = np.clip(e, E_MIN, E_MAX)
    weight = e / (1.0 - e)

    undelivered = d_t == 0
    residual_term = weight[undelivered] * (y_t[undelivered] - mu[undelivered])
    model_term = mu[d_t == 1].mean()          # average prediction among the delivered

    if normalized:
        # Hajek, or self-normalised. Both denominators estimate n * P(D=1), but this one
        # is correlated with its own numerator, which cancels the variance a handful of
        # enormous weights would otherwise contribute.
        correction = residual_term.sum() / weight[undelivered].sum()
    else:
        # The textbook form, algebraically identical to dividing the whole score by the
        # count of delivered units. Retained so the cost of the naive specification can
        # be measured rather than asserted.
        correction = residual_term.sum() / d_t.sum()

    counterfactual_mean = model_term + correction
    value = y_t[d_t == 1].mean() - counterfactual_mean

    return Estimate(float(value),
                    "level3_aipw_hajek" if normalized else "level3_aipw_plain",
                    "true_effect", {
        "counterfactual_mean": float(counterfactual_mean),
        "observed_mean": float(y_t[d_t == 1].mean()),
        "delivery_rate": float(d_t.mean()),
        "max_weight": float(weight[undelivered].max()),
        "share_e_above_0.5": float((e > 0.5).mean()),
        "clipped_propensities": clipped,
        "folds": folds,
    })
