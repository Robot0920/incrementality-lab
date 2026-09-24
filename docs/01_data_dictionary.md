# Data dictionary — Criteo-UPLIFT v2.1

Source: Diemert et al. (2018), *A Large Scale Benchmark for Uplift Modeling*,
AdKDD Workshop @ KDD 2018. License: CC BY-NC-SA 4.0 (non-commercial; cite the paper).

Assembled from Criteo **incrementality tests**: randomized trials in which a random
share of users is deliberately withheld from advertising.

**Grain: one row = one user.** Not one impression, not one session.

## Columns

| Column | Type | Official definition | Role in causal inference |
|---|---|---|---|
| `f0`–`f11` | float | 12 anonymized dense features, randomly projected | **pre-treatment covariates** — usable for balance checks, variance reduction (CUPED), and as `X` in an uplift model |
| `treatment` | 0/1 | 1 = targeted by the campaign, 0 = withheld | **randomized assignment** — the only randomized column, and therefore the only legitimate basis for a causal claim |
| `exposure` | 0/1 | whether the user was *effectively* exposed to the treatment | **post-treatment compliance indicator** — NOT a feature, NOT an outcome |
| `visit` | 0/1 | user visited the advertiser site | **outcome** (proximal) |
| `conversion` | 0/1 | user converted / purchased | **outcome** (distal, monetary) |

Columns added by our ingestion: `_source`, `_loaded_at` (lineage metadata).

## Published aggregates — use these to reconcile your own numbers

| Quantity | Published | Computed from our load |
|---|---|---|
| rows | 13,979,592 | asserted in `src/ingest/criteo_uplift.py` |
| treatment ratio | 0.85 | 11,882,655 / 13,979,592 = 0.850 |
| average visit rate | 4.7% | 0.15 × 3.8201% + 0.85 × 4.854% = 4.70% |
| average conversion rate | 0.29% | 0.15 × 0.1938% + 0.85 × 0.3089% = 0.29% |

All three reconcile, which is evidence that the load and the aggregation logic are correct.

## Caveats that constrain what you may conclude

1. **The effect magnitudes are deliberately distorted.** The authors applied
   *non-uniform sub-sampling* specifically "to prevent deduction of the original
   incrementality levels", and feature values were randomly projected. Methods and
   pipelines transfer from this dataset; effect sizes and base rates do not.
2. **The documentation disagrees with the file.** The dataset page describes "25M users
   with 11 features"; the v2.1 file has 13,979,592 rows and 12 `f` columns. Trust the
   data, assert the row count, and record the discrepancy.
3. **`exposure` is produced by the ad-serving system** (auction outcome, inventory,
   frequency capping, whether the user was even online). It is correlated with user
   activity, so grouping by it destroys the comparability that randomization bought.
   Diagnose with it; never estimate with it.
4. **No timestamps.** There is no way to study time dynamics, novelty effects, or
   seasonality here. Those live in the simulated layer.

## Column roles, restated as rules

```
treatment            -> may split groups on this          (randomized)
f0..f11              -> may condition/adjust on these      (pre-treatment)
exposure             -> diagnose only, never estimate      (post-treatment)
visit, conversion    -> left-hand side only                (outcomes)
```
