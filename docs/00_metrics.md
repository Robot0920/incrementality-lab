# Metric specification

The hypothesis under test, the metric that adjudicates it, and the guardrails that protect
that metric from being satisfied without value being created.

Every metric carries eight fields. A metric missing any of them is not implementable, and
disagreements in practice concentrate in `population` and `attribution_window`.

---

## Hypothesis

> **If** campaign impact is reported from a model-based counterfactual rather than a
> randomized holdout, **then** reported lift will be overstated, **because** delivery is
> selected on user activity and no model can fully adjust for unobserved activity
> propensity, **and this is wrong if** the decision-flip rate stays below 5% across the
> plausible parameter region with no sign errors.

The falsifier is fixed in `03_study_design.md` before results are read.

## Decomposition

```
incremental conversions per 1k assigned  =  LATE  ×  delivery_rate  ×  1000
```

The identity separates two levers owned by different functions: raising the effect among
those reached, and reaching more of those assigned.

---

## North star metric

```yaml
name:                incremental_conversions_per_1k_assigned
definition:          conversions that occurred because the campaign was switched on,
                     per 1,000 randomly assigned units
formula:             (mean(conversion | treatment=1) - mean(conversion | treatment=0)) * 1000
unit:                conversions per 1,000 assigned units
grain:               campaign x period
population:          ALL assigned units, including those never exposed   # ITT scope
attribution_window:  within the experiment period; no cross-period carryover
dedup_rule:          first assignment only; units seen in both arms are excluded and alerted
owner:               Measurement
direction:           higher is better
current_value:       1.151 per 1k                                        # Measured
failure_modes:       sample ratio mismatch; identity-resolution loss dropping conversions;
                     a changed attribution window
```

`population` is the line that matters. Scoping it to exposed units only produces a number
62% larger and not causally interpretable.

### Rejected north star candidates

| Candidate | Why not |
|---|---|
| Attributed conversions | Gameable, and experimentally shown to overstate (Blake, Nosko & Tadelis 2015) |
| Conversion rate | Not a causal quantity; contaminated by delivery selection |
| Lift among exposed | Conditions on a post-treatment variable; measured here to overstate by 62% |

## Driver metrics

| Metric | Formula | Current | Lever owner |
|---|---|---|---|
| `delivery_rate` | `P(exposure = 1 \| treatment = 1)` | 3.604% (Measured) | Bidding, inventory, frequency capping |
| `late_conversion` | `ITT / delivery_rate` | +3.195 pp (Measured) | Creative, targeting, ranking |

## Guardrail metrics

| Class | Metric | Threshold | Computable here |
|---|---|---|---|
| Statistical validity | Sample ratio mismatch, chi-square p | p >= 0.001 | yes |
| Statistical validity | Covariate balance, max abs SMD on assignment | < 0.01 | yes |
| Statistical validity | One-sided non-compliance: `count(control AND exposed)` | = 0 | yes, enforced in `dq/` |
| Business | Cost per incremental conversion | threshold TBD | **no — no cost column** |
| User experience | Frequency fatigue, bounce | no degradation | **no — not in the dataset** |
| Ecosystem | Advertiser renewal rate | no decline | **no — no supply side** |
| Operational | Freshness, log completeness | within SLA | **no — static snapshot** |

Guardrails that cannot be computed are listed rather than dropped. A missing guardrail is a
risk that has to stay visible; deleting the row hides it.

## Gaming review

| Metric | How it could be moved without creating value | What prevents it |
|---|---|---|
| `delivery_rate` | Buy cheap junk inventory to raise reach | The north star is incremental conversions; junk traffic does not convert |
| North star | Target only users certain to convert | ITT scope covers all assigned units, so cherry-picking dilutes |
| Reported lift | Widen the attribution window | The window is part of this specification; changing it requires review |

## Diagnostic metrics

Not decision metrics. Used for root-cause work only.

| Metric | Current | Reads as |
|---|---|---|
| Naive exposed-minus-control gap | +5.185 pp | The magnitude of selection bias |
| Complier baseline ratio | 3.7x on visit, 18x on conversion | How selective delivery is |
| Negative-control z, unexposed-treated vs control | −23.3 | Rejects "delivery is random" |

## Provenance

`Measured` from the reference dataset. Effect magnitudes are not externally quotable: the
dataset's authors applied non-uniform sub-sampling to obscure true incrementality levels.

## Upstream assumption

The reference dataset arrives already aggregated to one row per unit, with assignment,
delivery and outcomes joined. Identity resolution, assignment de-duplication, attribution
windowing and late-arrival handling were performed upstream and cannot be verified here.
This is an `Assumed` dependency on the provider's pipeline.
