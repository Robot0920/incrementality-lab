# Findings: estimation error with the confounder fully observed

Interim result. The study's main sweep varies how much of the confounder the covariates
reveal; this document reports only the endpoint where they reveal **all** of it.

That endpoint matters on its own. With the confounder fully observed, conditional
ignorability holds exactly and the modelled counterfactual is identified. Every bias
reported below is therefore **estimation error** — none of it is the identification problem
the study exists to measure. This is the easy case.

Setup: `observability = 1.0`, `n = 600,000`, 6 replicates, 3 cross-fitting folds. True
effect of delivery on the outcome probability: 0.032. Reproduce with
`python -m src.validate_estimators --n 600000 --reps 6 --observability 1.0`.

---

## Results

Boosted estimators are run under two configurations differing in exactly two knobs:
`def` uses scikit-learn's defaults for `min_samples_leaf` (20) and `l2_regularization` (0);
`reg` uses 500 and 1.0.

| estimator | estimate | bias | rel bias | std err | bias in SE |
|---|---|---|---|---|---|
| naive delivered vs control | +0.051194 | +0.019194 | +60.0% | 0.000605 | +31.7 |
| ITT | +0.001129 | −0.000029 | −2.5% | 0.000039 | −0.7 |
| LATE | +0.031305 | −0.000695 | −2.2% | 0.001089 | −0.6 |
| level 1, logistic | +0.036010 | +0.004010 | +12.5% | 0.000519 | +7.7 |
| level 2, boosted `@def` | +0.033658 | +0.001658 | +5.2% | 0.000844 | +2.0 |
| level 2, boosted + isotonic `@def` | +0.049082 | +0.017082 | +53.4% | 0.000699 | +24.4 |
| level 3, AIPW plain `@def` | +0.026076 | −0.005924 | −18.5% | 0.009649 | −0.6 |
| level 3, AIPW Hájek `@def` | +0.032769 | +0.000769 | +2.4% | 0.001711 | +0.4 |
| level 2, boosted `@reg` | +0.037976 | +0.005976 | +18.7% | 0.000608 | +9.8 |
| level 2, boosted + isotonic `@reg` | +0.040390 | +0.008390 | +26.2% | 0.000682 | +12.3 |
| level 3, AIPW plain `@reg` | +0.034318 | +0.002318 | +7.2% | 0.000610 | +3.8 |
| level 3, AIPW Hájek `@reg` | +0.034339 | +0.002339 | +7.3% | 0.000609 | +3.8 |

The randomisation-protected estimators are unbiased, as they must be: ITT at −0.7 SE and
LATE at −0.6 SE. They are the ruler, and the ruler reads true.

---

## 1. Hyperparameters move the answer more than the choice of estimator does

| estimator | `@def` | `@reg` | swing |
|---|---|---|---|
| level 2, boosted | +5.2% | +18.7% | 13.5 pp |
| level 2, boosted + isotonic | +53.4% | +26.2% | 27.2 pp |
| level 3, AIPW plain | −18.5% | +7.2% | **25.8 pp, with a sign flip** |
| level 3, AIPW Hájek | +2.4% | +7.3% | 4.9 pp |

Moving between estimator families changes the reported lift by roughly 10 to 15 points.
Changing two regularisation settings — settings most teams never touch — changes it by up
to 27 points and can reverse its direction.

The operational consequence: **a modelled counterfactual does not produce an estimate, it
produces a range**, and the width of that range is comparable to the effect being measured.
Any single number reported from such a pipeline is a point drawn from that range, selected
by configuration choices that are rarely recorded and almost never justified.

## 2. Variance can launder bias through a significance check

```
level 3, AIPW plain @def    -18.5% from the truth,  SE 0.009649  ->  reads "unbiased"
level 3, AIPW plain @reg     +7.2% from the truth,  SE 0.000610  ->  reads "BIASED"
```

The variant 2.6 times closer to the truth is the one flagged as biased, because the flag is
decided by precision rather than by accuracy. A sufficiently imprecise estimator passes
every unbiasedness test applied to it.

This is the same arithmetic that makes "no significant difference" an ambiguous readout: it
conflates *we measured no effect* with *we could not have measured one*.

## 3. Fixing one failure mode exposes another

The `@def` configuration suffered prediction **saturation**: with `l2_regularization = 0`, a
boosted leaf value is a Newton step whose denominator is `sum(p(1-p))`, which collapses as
predictions approach 0 or 1, so the step is unbounded and 150 iterations drive
`expit(raw_score)` to exactly 1.0 in float64. Measured consequences:

| | `@def` | `@reg` |
|---|---|---|
| propensity predictions pinned at exactly 1.0 | 8 | 0 |
| maximum inverse-propensity weight | 1,000,000 (clipped to 999) | 3.2 |
| delivered units with outcome prediction exactly 1.0 | 234 of 18,347 | 0 |
| level 3 plain, standard error | 0.009649 | 0.000610 |

Those 234 saturated predictions alone accounted for roughly half the estimated
counterfactual mean. Regularising removed saturation entirely and cut the standard error by
a factor of 16 — and the bias then became visible and, for Level 2, larger: the regularised
outcome model is too coarse for the curvature and interaction present in the data, so
variance was traded for bias and the trade overshot.

A corollary worth recording: under `@reg` the plain and Hájek forms of AIPW agree to four
decimals. Self-normalisation was a patch for unbounded weights, and once the weights were
bounded the patch became irrelevant — which is what should happen if the weights were the
cause.

## 4. Scope of these findings

| Established | Not established |
|---|---|
| With the confounder fully observed, every modelled counterfactual tested is biased by between 2% and 53% | anything about identification error; the sweep over `observability` has not run |
| Two regularisation settings swing the estimate by up to 27 points and can flip its sign | that any particular configuration is correct — both were chosen by hand |
| An imprecise estimator can pass an unbiasedness check while being further from the truth | how much a principled selection criterion narrows the range |
| Randomisation-protected estimators are unbiased throughout | whether these magnitudes transfer to the reference dataset |

The open question is whether choosing hyperparameters by a criterion available **without**
the truth — held-out log-loss or Brier score — narrows the 27-point range. Selecting them
to minimise bias against the known effect would make the study circular, and is therefore
not permitted.
