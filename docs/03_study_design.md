# Study design

Fixed before the results are seen. Changes after that point are recorded as amendments with
a date and a reason, not edited in silently.

---

## Question

Does a model-based counterfactual recover the true incremental effect of advertising, and
under what conditions does it fail?

## Why it matters

A randomized holdout costs revenue: every withheld user is an unmonetised impression. Teams
therefore report impact from non-experimental models instead. That trade is only sound if
the model's error is small relative to the decisions being made. This study estimates that
error where the truth is known, so the trade can be made with evidence rather than
preference.

**The decision this feeds:** whether a randomized holdout is a required investment or an
avoidable cost — and if required, how large it needs to be.

## Ground truth

The reference dataset is a real randomized experiment. Truth is defined as:

- **ITT** — difference in outcome rates between the full treated arm and the control arm.
- **LATE** — `ITT / delivery_rate`, valid here because non-compliance is one-sided
  (no control unit is ever exposed, asserted in `dq/criteo_uplift.dqdl`).

Both are already computed in `sql/02_itt_and_late.sql` and corroborated by an independent
mixture identity in `sql/03_exposure_bias.sql`.

## Estimators under test

| Group | Estimator | Role |
|---|---|---|
| Randomisation-protected | Difference in means (ITT); Wald ratio (LATE) | Ground truth |
| Naive non-experimental | Exposed versus control | Lower bound on quality; known to be badly biased |
| Adjusted | Regression adjustment on pre-treatment covariates | Minimum competent baseline |
| Doubly robust | AIPW; DML with cross-fitting | What a competent team would use today |
| Heterogeneity | DR-learner (EconML); T-/X-learner (CausalML) | Whether the error is uniform or concentrated in segments |

## Procedure

1. Withhold the control arm. Nothing downstream may read it until step 4.
2. Fit an outcome model on treated units only, predicting the outcome from pre-treatment
   covariates, and use it to impute the counterfactual for exposed units. This mirrors the
   production pattern: model what would have happened, compare against what did.
3. Compute the model-implied lift.
4. Unseal the control arm and compute the true ITT and LATE.
5. Report the error on four axes (below).
6. Repeat across the stress grid.

## How failure is measured

A single bias number is not enough, because the question is operational.

| Axis | Definition | Why it matters |
|---|---|---|
| **Bias** | model estimate − truth, absolute and relative | The headline error |
| **Coverage** | share of runs whose interval contains the truth | An interval that misses is worse than no interval |
| **Sign error** | share of runs where the estimated direction is wrong | The most expensive single failure |
| **Decision flip** | share of runs where the model and the truth fall on opposite sides of a break-even threshold | The only axis a stakeholder cares about |

Decision flip is the primary outcome. Bias that never flips a decision does not justify
spending on a holdout.

## Stress grid

The real dataset gives one point. The simulator supplies the rest, with the true effect set
by construction and moments calibrated to the reference data.

| Axis | Range | Question it answers |
|---|---|---|
| Delivery rate | 1% to 50% | Does low delivery amplify the error? |
| Selection strength | none to strong | How selective must the auction be before the model breaks? |
| Unobserved confounding | none to strong | What happens when the covariates are incomplete — the realistic case |
| True effect size | zero to large | Is the error worse near the decision threshold, where it matters most? |
| Sample size | 10⁴ to 10⁷ | Does more data fix it? (For bias, no. Stating this is the point.) |

## Decision rule, fixed in advance

- **Holdout not required** if, across the plausible region of the grid, the decision-flip
  rate is below 5% and no sign errors occur.
- **Holdout required** if the decision-flip rate exceeds 5% anywhere in the plausible
  region, or if any sign error occurs.
- **Inconclusive** if the result depends on an axis whose realistic range cannot be pinned
  down. In that case the axis is named, and pinning it down becomes the next piece of work
  rather than being papered over.

"Plausible region" is fixed before the results are read, from the reference dataset's own
observed values.

## Robustness

Every estimate is subjected to DoWhy's refutation suite: placebo treatment, random common
cause, and data subset. An estimate that survives placebo treatment is reporting noise and
is reported as such.

## Threats to validity

| Threat | Handling |
|---|---|
| Effect magnitudes in the reference data are distorted by disclosed non-uniform sub-sampling | Conclusions are stated about *relative* estimator error, never about absolute advertising effectiveness |
| Covariates are anonymised and randomly projected, so no domain knowledge can guide model specification | Reported as a limitation; it makes the test harder, not easier, and therefore conservative |
| One dataset, one advertiser population | The simulator exists precisely to avoid generalising from a single point |
| The counterfactual model implemented here may be weaker than a production system's | Several specifications of increasing strength are fitted, and the best is reported |

## Abandonment criteria

The study is stopped and reported as inconclusive if the ground truth itself fails
validation: if one-sided non-compliance does not hold, if covariate balance on assignment
fails, or if computed aggregates stop reconciling with the dataset's published figures.
