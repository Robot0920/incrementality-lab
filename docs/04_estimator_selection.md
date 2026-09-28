# Estimator selection

Three estimators of the modelled counterfactual are run at every point of the study grid.
They are not three arbitrary models. They are the three points at which the error
decomposition changes.

---

## The organising principle

```
total bias  =  identification bias        +  estimation bias
               (X omits a confounder)        (given X, the function was got wrong)
```

Model choice cannot touch the first term. All three levels rest on the same identifying
assumption — **conditional ignorability**, that among units with equal `X`, delivery is as
good as randomised. Only the second term moves with model capacity.

This is why there are three levels rather than one. The study is a two-factor design:
sweeping `observability` moves identification bias, sweeping model strength moves
estimation bias, and the interaction between them says which term dominates. A single model
yields one number that cannot be decomposed, and therefore cannot distinguish "invest in
modelling" from "fund a holdout" — two conclusions that point at opposite budget decisions.

## What each estimator does

Training set is `assigned = 1, delivered = 0`; those units received nothing, so their
outcomes are the baseline. Target set is `delivered = 1`.

```
estimated lift = mean(Y | delivered) - mean(counterfactual | delivered)
```

---

## Level 1 — Logistic regression, main effects

**Theoretical role.** Consistent under a strong parametric assumption, linear in the logit.
The reference point against which "does capacity help?" is measured.

**Mathematical grounds.**

- *Logistic rather than a linear probability model.* At `p ~ 0.002` an OLS fit on a 0/1
  outcome predicts negative probabilities for many units and has severely heteroskedastic
  errors. The logit link bounds predictions to `(0,1)` by construction.
- *Calibration holds exactly, by construction.* The logistic score equations force the
  residuals to sum to zero, so in-sample mean prediction equals in-sample mean outcome.
  This matters here specifically, because the estimator is a **difference of two means of
  predictions**: any systematic calibration error passes straight through into the lift.
- *Extrapolation is smooth.* Linear-in-logit continues monotonically outside the training
  support. An assumption, but a transparent one.
- *Rare-event bias.* The logistic MLE is biased in finite samples when events are rare
  (King & Zeng 2001). On the full data, ~13,700 positives against 12 covariates is about
  1,100 events per variable, far above the conventional floor of ten, so it is negligible.
  At a grid point of `n = 650k` the training set holds roughly 630 positives, or ~50 per
  variable — still acceptable, but this is what sets the floor on grid-point size.

**Data characteristics motivating it.** A rare binary outcome with dense continuous
covariates and no missingness: the textbook setting for a generalised linear model.

**Operational cost.** Seconds per fit, deterministic, no hyperparameters.

---

## Level 2 — Histogram-based gradient boosting

**Theoretical role.** Nonparametric: it searches for the functional form rather than
assuming one, and so removes misspecification as an explanation for residual bias.

**Mathematical grounds.**

- *Trees rather than splines, polynomials or kernels.* The covariates are anonymised and
  randomly projected, which destroys interpretable structure. There is no basis to specify
  by hand, no interaction worth naming, no monotonicity prior to impose. The method has to
  search the function space adaptively.
- *Boosting rather than a random forest.* Boosting fits successive residuals, which suits
  a small signal riding on a large constant baseline — the situation at a 0.19% base rate.
  Random forests average deep trees and are poorly calibrated for very rare outcomes;
  boosting under a logistic loss behaves better.
- *Histogram binning, as a complexity argument.* Exact greedy split finding costs a sort
  per feature, `O(n log n)`, plus `O(n·d)` per level to score candidate splits. Histogram
  binning pays `O(n·d)` once, after which each level costs `O(bins·d)` with `bins ~ 256`.
  At `n ~ 10^6`-`10^7` and `d = 12` this is the difference between minutes and seconds per
  fit, against a grid requiring on the order of a thousand fits.
- *The weakness: no calibration guarantee.* Unlike the GLM, boosting does not force
  in-sample mean prediction to equal mean outcome; shrinkage and early stopping leave a
  systematic offset in predicted probabilities, and that offset becomes bias one-for-one.
  This is the specific argument for needing Level 3.
- *Extrapolation is piecewise constant.* Outside the training support a tree ensemble
  returns the boundary leaf's value, so it goes flat. Delivered units sit in the tail where
  training data is depleted, so the predicted counterfactual is too low for exactly those
  units, biasing the estimated lift **upward**. A directional prediction the study tests.

**Data characteristics motivating it.** Twelve anonymised features, so no feature
engineering is possible; large `n` with severe imbalance, so histogram binning is necessary
rather than merely convenient.

**Operational cost.** Seconds to a minute per fit on two cores. Deterministic only if the
thread count is pinned, so it is pinned.

---

## Level 3 — Cross-fitted AIPW

Not a bigger model — a different class of estimator.

```
e(X)  = P(delivered = 1 | X, assigned = 1)                     propensity model
mu(X) = E[Y | X, assigned = 1, delivered = 0]                  outcome model

E[Y(0) | D=1]  =  (1 / P(D=1)) * mean[ D*mu(X)
                                     + (1-D) * (e(X)/(1-e(X))) * (Y - mu(X)) ]
```

**Theoretical role.** Semiparametric, with a known influence function. Consistent if
*either* nuisance model is correct — but it still requires conditional ignorability, so it
does not enlarge what is identifiable.

**Mathematical grounds.**

- *Rate double robustness — why machine-learning models may enter a causal estimate at
  all.* If the outcome model converges at `n^-a` and the propensity model at `n^-b`, the
  bias of AIPW is of order `n^-(a+b)`, a **product** of the two errors. A plug-in outcome
  regression carries bias of order `n^-a`, which is first order. ML estimators typically
  converge slower than `n^-1/2`, so a plug-in is not root-n consistent, while AIPW is,
  provided `a + b >= 1/2`.
- *Cross-fitting is not optional.* The product-bias result requires the nuisance estimates
  to be independent of the data they are evaluated on. Fit and evaluate on the same rows
  and own-observation overfitting adds a bias term that does not vanish with `n`. Sample
  splitting removes it (Chernozhukov et al. 2018, *Double/Debiased Machine Learning*).
- *It still cannot fix unmeasured confounding.* Double robustness concerns estimating two
  nuisance functions, both conditioning on `X`. If `X` omits the confounder, both target
  the wrong quantity, and two chances to be right become two chances to be wrong in the
  same direction.
- *Its own vulnerability is overlap.* Residuals are weighted by `e(X)/(1-e(X))`; as
  `e(X) -> 1` the weights explode and variance blows up. The strongest estimator is
  therefore the one **most** sensitive to poor overlap. It trades misspecification bias for
  variance, and this dataset is thinnest exactly where the trade bites.

**Data characteristics motivating it.** A 3.6% delivery rate under strong selection puts
the propensity distribution near zero for most units with a tail near one — poor overlap by
construction. That is the single most consequential property of this data, and what makes
the weak-versus-strong comparison informative rather than academic.

**Operational cost.** `K` folds times two nuisance models is ten fits per estimate rather
than one. This dominates the grid's runtime.

---

## Summary

| | Level 1 | Level 2 | Level 3 |
|---|---|---|---|
| Estimator | Logistic regression | Histogram gradient boosting | Cross-fitted AIPW |
| Class | Parametric | Nonparametric | Semiparametric |
| Removes | nothing (reference) | misspecification | misspecification and first-order plug-in bias |
| Cannot remove | misspecification, overlap, confounding | overlap, confounding | **confounding** |
| Calibration | exact in-sample | none guaranteed | corrected by the residual term |
| Extrapolation | smooth, monotone | flat, biases lift upward | partly corrected, at a variance cost |
| Bias order | `n^-a` | `n^-a` | `n^-(a+b)` |
| Fits per estimate | 1 | 1 | ~10 |
| Fails when | the truth is curved | delivered units leave the training support | `e(X) -> 1` and variance explodes |

## Rejected alternatives

| Rejected | Reason |
|---|---|
| Linear probability model | predicts outside `[0,1]` at `p = 0.002`; heteroskedastic |
| Random forest | poorly calibrated for very rare outcomes; this estimator needs calibrated absolute probabilities, not rankings |
| Neural network | no advantage on twelve anonymised tabular features; hyperparameter burden, nondeterminism, compute unavailable |
| Nearest-neighbour or coarsened exact matching | under poor overlap the matches are poor by construction; discards data; memory-heavy at 11M rows |
| Plain IPW | no outcome model to stabilise it; variance explodes under exactly this overlap problem |
| Propensity stratification | `e(X)` is massed near zero, so most strata contain no delivered units |
| Downsampling the negatives | non-uniform sub-sampling preserves ranking but destroys calibration, and this estimator depends on calibrated absolute probabilities. It would need a `logit + ln(r)` correction, adding a failure mode for no gain |
| EconML DR-learner | the right tool in production, but heavy transitive dependencies and not verifiable in the current local environment. Deferred, not rejected: forty lines of AIPW on scikit-learn give the same estimator with local verifiability |
| Synthetic control, CausalImpact, interrupted time series | require a time dimension this dataset does not have |

## The binding operational constraint

```
fits = grid points (6) x replicates (20) x levels (3) x folds (5, level 3 only)
     ~ 1,800 model fits on two cores and 8 GB
```

This forces histogram boosting over exact boosting, `n ~ 10^6` per grid point rather than
`10^7`, and scikit-learn over EconML. It also imposes a floor: below roughly 650k per grid
point the events-per-variable ratio for Level 1 thins enough that rare-event bias becomes a
competing explanation for any difference between levels — which would confound the very
comparison the study exists to make. The two constraints squeeze from opposite sides, and
`n ~ 10^6` sits in the window between them.

## Self-check

At `observability = 1.0` the covariates reveal the confounder exactly, so conditional
ignorability holds and **Levels 2 and 3 must be unbiased**. Level 1 need not be: its
misspecification survives, which is the reason it is in the study.

If Level 2 or Level 3 shows bias at `observability = 1.0`, the defect is in the
implementation, not in the method. This is the same device as requiring the single-look
Wald interval to produce a 5% error rate in `src/validate_intervals.py`, and the same
device as the negative control that returned `z = -23.3` in `sql/03_exposure_bias.sql`:
validate the instrument against a case whose answer is already known, before trusting it on
a case whose answer is not.
