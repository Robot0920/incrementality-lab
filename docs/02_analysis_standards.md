# Analysis standards

How an unfamiliar dataset is taken on here, and what a result must contain before it is
reported. The ordering matters: each step prevents a mistake the next step would let
through.

`src/profile_asset.py` automates steps 1 to 4 and prints the capability verdict.

---

## Intake sequence

### S0 · Read the source documentation first

Four things determine whether a result can mean what it appears to mean:

1. **Sampling and anonymisation.** Sub-sampled, re-weighted, projected, obfuscated? This
   decides whether magnitudes generalise at all.
2. **Grain.** What does one row represent?
3. **Published aggregates.** Anything available to reconcile against.
4. **Collection mechanism.** Observational log, randomized trial, survey, vendor feed.

With no documentation, record that and treat every column role as a hypothesis.

### S1 · Shape and grain

```sql
SELECT count(*) AS rows, count(DISTINCT <id>) AS ids FROM <table>;
```

More rows than distinct ids means the grain is not what the column name implies. Resolve
before computing any rate.

### S2 · Schema

`DESCRIBE <table>` — watch for numerics stored as text, booleans stored as 0/1/NULL, dates
stored as strings.

### S3 · Column health

Null rate, cardinality, range, constants. Constant columns carry no information, unexpected
nulls silently change denominators, impossible ranges indicate an upstream defect.

### S4 · Assign a role to every column, in writing

| Role | Permitted use |
|---|---|
| identifier | joins, grain verification |
| pre-treatment covariate | balance checks, adjustment, model features |
| assignment | may define comparison groups |
| post-treatment | diagnosis only; never defines a comparison group |
| outcome | left-hand side only |
| metadata | audit |

Deciding pre- versus post-treatment: *could this value have differed had the assignment
differed?* If yes, it is post-treatment. A faster tell: a column that is constant within one
arm is post-treatment. Misclassifying one column invalidates everything downstream.

### S5 · Cross-tabulate the design columns before looking at outcomes

Structure is established before results are read, so that a dramatic number cannot anchor
interpretation.

### S6 · Add outcome means and both shares

```sql
SELECT
    <assignment>,
    <compliance_flag>,
    count(*)                                                          AS n,
    100.0 * count(*) / sum(count(*)) OVER ()                          AS pct_of_all,
    100.0 * count(*) / sum(count(*)) OVER (PARTITION BY <assignment>) AS pct_within_arm,
    avg(<outcome>)                                                    AS outcome_rate
FROM <table>
GROUP BY 1, 2
ORDER BY 1, 2;
```

`pct_of_all` gives the allocation design; `pct_within_arm` gives the compliance rate, which
is the denominator of a LATE. Both are reported so neither requires arithmetic later.
Aggregates may be nested inside window functions because aggregation is evaluated before
windowing; this parses identically on DuckDB, Trino, BigQuery and Postgres.

### S7 · Reconcile against published aggregates

Recompute whatever the source published. Agreement is evidence that the load and the
aggregation logic are both sound. Disagreement means a load defect, a definition mismatch,
or an error in the documentation — all three are material.

### S8 · Audit the design

- **Sample ratio mismatch** — chi-square observed allocation against intended.
- **Covariate balance** — standardized mean differences near zero across the assignment
  split, and not necessarily across any post-treatment split.

Standardized mean differences rather than t-tests: at large n every trivial difference
attains significance, so a p-value carries no information while an effect size does.

### S9 · Base rate and feasibility

```
MDE_absolute = 2.8 * sqrt( p*(1-p) * (1/n_control + 1/n_treatment) )
MDE_relative = MDE_absolute / p
```

2.8 is `z(0.975) + z(0.80)`. The term `1/n_control + 1/n_treatment` is dominated by the
smaller arm, so power is governed by the smaller arm regardless of total size.

### S10 · Record assumptions and open questions

What is being assumed, and what could not be determined together with how the conclusion
would change if it went the other way.

---

## Reporting standards

- Absolute and relative effects both reported, units named. Percentage points and percent
  are never used interchangeably.
- Uncertainty reported as an interval. At large n, p-values only alongside effect sizes.
- Every number carries a provenance label: `Measured`, `Benchmarked`, `Assumed`, `Simulated`.
- Inferences are labelled as inferences; reconstructed rationale is never presented as
  documented fact.
- A subgroup effect, such as a LATE, is not extrapolated to the full population.
- An estimate is reported with the refutation tests it survived, not only its value.

## Recurring defects

1. Computing before reading the sampling section of the source documentation.
2. Grouping or conditioning on a post-treatment variable.
3. `avg()` silently skipping nulls and shrinking a denominator.
4. Integer division where `100.0 * a / b` was intended.
5. Trusting a documented row count instead of asserting it at load time.
6. Shipping a data-quality rule that has never been observed to pass.
7. Engine-specific SQL in files intended to run on more than one engine.
8. Implementing a published formula without validating it against a case with a known answer.
