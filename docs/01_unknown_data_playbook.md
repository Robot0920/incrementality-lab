# Playbook — your first 20 minutes with an unfamiliar dataset

Written to be executed under interview pressure. The order is the point: each step
protects you from a mistake the next step would otherwise let you make.

---

## S0 — Read the documentation first, specifically these four things

Skipping this step is how you end up reporting a number that cannot mean what you
think it means.

1. **Sampling and anonymization.** Was the data sub-sampled, re-weighted, projected,
   or obfuscated? This determines whether effect sizes generalize at all.
2. **Grain.** What does one row represent? User, session, event, order, day?
3. **Published aggregates.** Any totals or rates you can reconcile against.
4. **Collection mechanism.** Observational log, randomized trial, survey, vendor feed?

If there is no documentation, say so out loud and treat every column role as a hypothesis.

## S1 — Shape and grain

```sql
SELECT count(*) FROM <table>;
SELECT count(*) AS rows, count(DISTINCT <id>) AS ids FROM <table>;  -- grain / key check
```

If `rows > ids`, the grain is not what the column name suggests. Find out why before
computing a single rate.

## S2 — Schema

```sql
DESCRIBE <table>;
```

Watch for numeric columns stored as text, booleans stored as 0/1/NULL, and dates stored
as strings.

## S3 — One-line health check

```sql
SUMMARIZE <table>;
```

DuckDB returns per column: type, min, max, approximate distinct count, average, standard
deviation, quartiles, and null percentage. Read it for three things: constant columns
(zero variance = useless), unexpected nulls, and impossible ranges (negative prices,
rates above 1).

```sql
SELECT * FROM <table> USING SAMPLE 5 ROWS;   -- then actually look at five rows
```

## S4 — Label the role of every column, in writing

This is the step everything else depends on, and the step most people skip.

| Role | Meaning | What you may do with it |
|---|---|---|
| identifier | keys | joins, grain checks |
| pre-treatment covariate | known before the intervention | balance checks, adjustment, model features |
| assignment | the randomized or quasi-randomized cause | split groups on it |
| post-treatment | produced after/because of the assignment | diagnose only — never split or condition on it |
| outcome | what you are trying to move | left-hand side only |
| metadata | lineage, load timestamps | audit |

Getting one column into the wrong row of this table invalidates everything downstream.
When unsure whether a column is pre- or post-treatment, ask: *could its value have been
changed by the treatment?* If yes, it is post-treatment.

## S5 — Cross-tabulate the design columns only

Understand the structure before you look at any result, so that a dramatic-looking
number cannot anchor your thinking.

```sql
SELECT <assignment>, <post_treatment_flag>, count(*) AS n
FROM <table>
GROUP BY 1, 2
ORDER BY 1, 2;
```

## S6 — Add outcome means, plus both kinds of share

```sql
SELECT
    <assignment>,
    <post_treatment_flag>,
    count(*)                                                        AS n,
    100.0 * count(*) / sum(count(*)) OVER ()                        AS pct_of_all,
    100.0 * count(*) / sum(count(*)) OVER (PARTITION BY <assignment>) AS pct_within_arm,
    avg(<outcome>)                                                  AS outcome_rate
FROM <table>
GROUP BY 1, 2
ORDER BY 1, 2;
```

`pct_of_all` tells you the **design** (the allocation ratio). `pct_within_arm` tells you
the **compliance rate**, which is the denominator you need for a LATE. You want both, so
that neither requires mental arithmetic later.

An aggregate can be nested inside a window function because SQL evaluates `GROUP BY` and
aggregation *before* window functions — so `sum(count(*)) OVER ()` means "add up the `n`
of all the groups". This works identically in BigQuery, Snowflake and Postgres.

## S7 — Reconcile against the published aggregates

Recompute whatever the documentation published. If your numbers match, the load and the
aggregation logic are both sound. If they don't, stop and find out why — you have either
a load bug, a definition mismatch, or a documentation error, and all three matter.

## S8 — Audit the design

- **Sample ratio mismatch (SRM):** chi-square the observed allocation against the intended
  one. On a live platform this is the first alarm to fire when bucketing breaks.
- **Covariate balance:** standardized mean differences on the pre-treatment covariates.
  Assignment vs control should balance; any post-treatment split should not.
- Use standardized mean differences, not t-tests. At large n every trivial difference is
  "significant", so p-values carry no information; an effect size does.

## S9 — Base rate and feasibility

Read the outcome rate in the untreated group, then check whether the question is even
answerable at this sample size:

```
MDE_absolute = 2.8 * sqrt( p*(1-p) * (1/n_control + 1/n_treatment) )
MDE_relative = MDE_absolute / p
```

`2.8` is `z(0.975) + z(0.80)`, i.e. two-sided alpha = 0.05 with 80% power. The term
`1/n_control + 1/n_treatment` is dominated by the **smaller** arm, so power is governed by
the smaller arm — always ask how big it is first.

## S10 — Write down assumptions and open questions

Two lists, in the notebook or the memo, before any conclusion:

- what you are assuming (grain, column roles, identifying assumptions)
- what you could not determine and how it would change the conclusion

## Pitfalls

1. Computing before reading the documentation's sampling section.
2. Grouping or conditioning on a post-treatment variable.
3. Presenting an inference as a documented fact.
4. Mixing percentage points and percent without saying which.
5. `avg()` silently skips NULLs, shrinking the denominator — always pair it with `count(*)`.
6. Integer division: write `100.0 * a / b`.
7. Reading p-values at huge n instead of effect sizes and interval widths.
8. Trusting a documented row count instead of asserting it.
9. Reporting only the absolute or only the relative effect.
10. Extrapolating a subgroup effect (e.g. a LATE) to the whole population.
