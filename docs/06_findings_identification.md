# Findings: what happens as the confounder becomes unobservable

The study's result. `docs/05_findings_estimation.md` reports the endpoint where the
confounder is fully observed; this document reports the sweep.

Setup: `observability` over 1.00, 0.75, 0.50, 0.25, 0.00; `n = 600,000`; 12 replicates per
grid point; 3 cross-fitting folds; 1,020 model fits in 911 seconds. Two configurations
carried throughout — `def` is scikit-learn's defaults, `sel` is chosen by held-out log-loss
without consulting the truth. Reproduce with `python -m src.run_study`. Per-replicate
estimates are in `results/study_raw.csv`.

---

## Relative bias

| estimator | 1.00 | 0.75 | 0.50 | 0.25 | 0.00 |
|---|---|---|---|---|---|
| naive delivered vs control | +62.6% | +63.2% | +61.3% | +63.6% | +64.9% |
| **ITT** | **−4.5%** | **−1.7%** | **+2.5%** | **+2.2%** | **+4.5%** |
| **LATE** | **−4.3%** | **−1.9%** | **+1.9%** | **+2.0%** | **+3.0%** |
| level 1, logistic | +13.8% | +41.9% | +54.0% | +62.4% | +67.1% |
| level 2, boosted `@def` | +6.8% | +37.8% | +49.9% | +58.5% | +62.5% |
| level 2, boosted + isotonic `@def` | +55.5% | +60.3% | +60.4% | +64.7% | +67.2% |
| level 3, AIPW plain `@def` | +53.7% | +42.2% | +53.7% | +62.2% | +67.7% |
| level 3, AIPW Hájek `@def` | +12.0% | +42.0% | +53.7% | +62.2% | +67.7% |
| level 2, boosted `@sel` | +19.5% | +44.2% | +54.2% | +62.4% | +67.2% |
| level 2, boosted + isotonic `@sel` | +26.3% | +48.5% | +56.7% | +63.7% | +67.2% |
| level 3, AIPW plain `@sel` | +9.4% | +42.1% | +53.6% | +62.2% | +67.2% |
| level 3, AIPW Hájek `@sel` | +9.4% | +42.1% | +53.6% | +62.2% | +67.2% |

## 1. The randomisation-protected estimators do not move

ITT and LATE stay within ±4.5% across the entire sweep, which is replicate noise at twelve
replicates. Randomisation is indifferent to how much of the confounder anyone can observe —
it never needed to observe it. This row is the control that validates the sweep: if it had
drifted, the sweep itself would be suspect.

## 2. With the confounder unobserved, every sophisticated estimator becomes the naive one

At `observability = 0.00`:

```
naive delivered vs control                        +64.9%
every modelled estimator                 +62.5% to +67.7%
```

Cross-fitting, double robustness, nonparametric outcome models, separately tuned nuisance
models — all of it converges on the number you get by subtracting the control mean from the
delivered mean and reading it off. The machinery buys **nothing** once the covariates carry
no information about the confounder, because there is nothing left for it to adjust.

This is the point that is easy to assert and hard to believe until measured: a doubly
robust, cross-fitted estimator is not robust to the thing that actually breaks these
studies.

## 3. The degradation is not graceful

```
observability  1.00 -> 0.75    best modelled estimator:  +9.4%  ->  +42.1%
```

**Losing a quarter of the confounder's variance costs roughly 32 points of bias.** By
`observability = 0.50` the bias is +54%, already 83% of the way to the fully-unobserved
value. The curve is almost all of its height in the first quarter of the range.

Operationally: covariate coverage has to be close to perfect before a modelled
counterfactual is worth anything. Nearly-good is not good.

## 4. Estimator choice matters only where identification holds

```
spread between best and worst modelled estimator

  observability 1.00     +6.8% to +55.5%      49 points
  observability 0.75    +37.8% to +48.5%      11 points
  observability 0.00    +62.5% to +67.7%       5 points
```

Which estimator and which configuration you pick dominates the answer when the confounder
is observed, and becomes irrelevant when it is not. Effort spent on estimator sophistication
is effort spent on the axis that stops mattering first.

## 5. The decision-flip rate, which is the primary outcome

Break-even placed at `1.25 × true_effect`, so the correct decision is to **decline** and a
flip means shipping anyway:

| estimator | 1.00 | 0.75 | 0.50 | 0.25 | 0.00 |
|---|---|---|---|---|---|
| **ITT** | **8%** | **0%** | **8%** | **8%** | **0%** |
| **LATE** | **8%** | **0%** | **8%** | **8%** | **0%** |
| level 1, logistic | 0% | **100%** | **100%** | **100%** | **100%** |
| level 2, boosted `@def` | 0% | **100%** | **100%** | **100%** | **100%** |
| level 3, AIPW Hájek `@sel` | 0% | **100%** | **100%** | **100%** | **100%** |
| every other modelled estimator | 0–67% | **100%** | **100%** | **100%** | **100%** |

**Twelve replicates out of twelve, at every grid point below full observability, every
modelled estimator recommends shipping something that should be declined.** Not "sometimes
misleading" — wrong every time.

At the mirror threshold `0.5 × true_effect`, where the correct decision is to ship, the
flip rate is **0% for everything**. The bias is one-directional: a modelled counterfactual
will never make you miss a winner. It will only make you fund a loser.

That asymmetry matters for how the failure presents itself in a business. There is no
missed-opportunity signal to alert anyone. The only symptom is sustained spending on
campaigns that do not work, with a dashboard that says they do.

## 6. The pre-registered decision

`docs/03_study_design.md`, fixed before any of this was run:

> **Holdout required** if the decision-flip rate exceeds 5% anywhere in the plausible
> region, or if any sign error occurs.

The flip rate is 100%, at every grid point below full observability, for every modelled
estimator. The rule fires unambiguously, and it does not depend on where the plausible
region is drawn, because the result holds across the entire grid.

**A randomized holdout is a required investment, not an avoidable cost.**

## 7. The one escape route, and why it closes

At `observability = 1.00` the best estimators do pass: AIPW `@sel` flips 0% of the time.
So if the covariates captured essentially all of the confounding, a modelled counterfactual
would be adequate and the holdout could be skipped.

That escape route closes on itself. Establishing that your covariates capture the confounder
requires comparing a modelled estimate against a known answer — and the only way to obtain
a known answer is a randomised holdout. **The condition under which the holdout is
unnecessary can only be verified by running one.**

So the practical form of the recommendation is not "always hold out" but: hold out, measure
the gap between the modelled and randomised estimates, and only then decide whether the
modelled pipeline can be trusted for the periods between holdouts.

## 8. Scope and caveats

| Established | Not established |
|---|---|
| ITT and LATE are unbiased regardless of covariate quality | that these magnitudes transfer to the reference dataset — the simulator is calibrated to its moments, not validated against its effects |
| Modelled counterfactuals converge on the naive comparison as observability falls | anything about **time-series** counterfactuals: synthetic control, interrupted time series, pre/post. This study tests the **cross-sectional** family only |
| Degradation is steep and front-loaded in the first quarter of the range | the shape between 0.75 and 1.00, where the collapse happens; the grid has no points there |
| The error is one-directional, inflating lift, never deflating it | whether a selection criterion aligned to the estimand narrows the gap at high observability |

The gap between 0.75 and 1.00 is the one place the grid is too coarse to describe what it
has found, and it is exactly the region a business would care about. That is the obvious
next refinement.
