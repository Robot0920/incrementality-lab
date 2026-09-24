# Decision log

Every consequential choice, the alternatives rejected, and the reason. Entries are
append-only; a superseded decision is marked, not deleted.

Format: **Context** (what forced a choice) · **Decision** · **Rejected** · **Consequence**.

---

## D1 · Scope: a measurement-methods study, not an end-to-end product project

**Context.** The project began as an end-to-end product data science project. The available
data supports one stage of that lifecycle — experiment readout — and none of the others:
there are no timestamps, no monetary values, no supply-side entities and no product funnel.
Continuing to present it as end-to-end would have required inventing the missing parts.

**Decision.** Narrow to one question that the data fully supports: whether a model-based
counterfactual recovers a known incremental effect.

**Rejected.** (a) Continue the end-to-end framing and simulate the missing stages — the
result would be a simulation wearing a business costume. (b) Switch datasets immediately —
discards work that is independently valuable.

**Consequence.** Narrow and deep rather than broad and thin. An end-to-end pipeline project
needs a different dataset and belongs in a separate repository.

## D2 · Dataset: Criteo-UPLIFT v2.1

**Context.** The question requires a known causal effect, and knowing the effect requires
randomisation. It also requires the distinction between *assigned* and *actually reached*,
because that distinction is where non-experimental methods usually fail.

**Decision.** Criteo-UPLIFT v2.1: a real randomized advertising experiment, 13,979,592 users,
carrying both `treatment` (randomised) and `exposure` (the auction's outcome) as separate
columns.

**Rejected.** Olist, RetailRocket, GA4 sample — richer in time, money and entities, but none
contains a randomized treatment, so none can supply ground truth. They are the right choice
for a pipeline project and the wrong choice for this one.

**Consequence.** Everything requiring time, money or a second market side is out of scope
and is stated as such rather than simulated. Effect magnitudes are not quotable externally
because the authors sub-sampled non-uniformly to obscure true incrementality levels.

## D3 · No fictional business framing

**Context.** An earlier version wrapped this dataset in an invented music-promotion
marketplace. The narrative and the data came from different domains.

**Decision.** The domain is advertising, because the data is advertising. Generalisation to
other promotion products is argued in prose, not disguised as data.

**Rejected.** Keeping the invented product. A reader who asks where the data came from finds
the mismatch immediately, and everything else becomes suspect.

**Consequence.** Weaker as a narrative, stronger as evidence.

## D4 · Simulation: a purpose-built calibrated generator

**Context.** Characterising *when* an estimator fails requires varying the conditions under
which it operates — selection strength, delivery rate, confounding — with the true effect
known at every point on the grid.

**Decision.** A small data-generating process, calibrated so its observable moments match
the reference dataset, with the treatment effect set by construction.

**Rejected.**
- **RecoGym** (Criteo, 2018) — a reinforcement-learning *environment* for learning
  recommendation policies. It answers "which policy is better", not "is this estimator
  unbiased". Wrong instrument, and largely dormant since 2019.
- **Open Bandit Pipeline / scope-rl** (ZOZO, actively maintained) — the current standard for
  **off-policy evaluation**. Deferred rather than rejected: it becomes the right tool if the
  project extends to evaluating alternative targeting policies.

**Consequence.** The simulator is small and auditable, and the axes of the stress grid are
chosen to match the failure modes actually seen in the real data.

## D5 · Estimators: doubly robust and cross-fitted, not hand-rolled regression

**Context.** A comparison of "model-based counterfactual versus truth" is only interesting
if the model side is represented by methods a competent team would actually use.

**Decision.** Difference in means and LATE as the randomisation-protected baseline; AIPW and
DML as the doubly robust comparators; DR-learner (EconML) and meta-learners with Qini/AUUC
(CausalML) for heterogeneity.

**Rejected.** A single hand-written T-learner. Beating a weak comparator proves nothing.

**Consequence.** Heavier dependencies, isolated in `requirements-causal.txt` (D9).

## D6 · Robustness: DoWhy refutation tests

**Context.** The study is about failure modes, so it must attack its own estimates rather
than report them.

**Decision.** Run DoWhy's refutation suite — placebo treatment, random common cause, data
subset — against each estimate. An estimate that survives a placebo treatment is reporting
noise.

**Rejected.** Reporting point estimates with intervals only.

**Consequence.** Some estimates are expected to fail refutation. That is the finding, not a
defect.

## D7 · Inference: anytime-valid confidence sequences alongside fixed-horizon intervals

**Context.** Fixed-horizon tests are only valid if the data is looked at once, at a
pre-committed sample size. In practice results are monitored continuously, which inflates
the false-positive rate. Anytime-valid methods are now in production at major platforms
([Waudby-Smith et al., WWW 2023](https://arxiv.org/pdf/2302.10108)).

**Decision.** Report both. Implement an asymptotic confidence sequence, and validate it with
a simulation harness that checks the empirical false-positive rate against the nominal level
under the null.

**Rejected.** Fixed-horizon t-tests alone.

**Consequence.** The implementation is validated before it is trusted; a published formula
implemented incorrectly is worse than no formula.

## D8 · Warehouse: DuckDB locally, portable SQL throughout

**Context.** The analysis is a single-machine workload, and cloud warehouses are slow and
metered to iterate against.

**Decision.** DuckDB for development, with every committed query restricted to the subset of
SQL that also parses on Trino, so the same files run on Athena unchanged.

**Rejected.** (a) Developing directly on BigQuery or Athena — slow feedback, metered.
(b) Using DuckDB-only conveniences such as `UNPIVOT`, `SUMMARIZE` and `GROUP BY ALL` in
committed files — they are permitted in exploration only.

**Consequence.** Some queries are more verbose than they would need to be. `UNION ALL`
instead of `UNPIVOT` is the recurring cost.

## D9 · Dependencies split by installation risk

**Context.** EconML, CausalML and DoWhy pull heavy transitive dependencies and occasionally
need compilation. A first-time setup that fails on dependency resolution is a bad first
impression and blocks the basic path.

**Decision.** `requirements.txt` holds only what the ingestion, SQL and power analysis need.
`requirements-causal.txt` holds the causal-inference stack and is installed on demand.

**Rejected.** One requirements file.

**Consequence.** `make ingest` through `make power` work in a minimal environment; the study
targets require one extra install step, which is stated where it is needed.

## D10 · Diagrams as Mermaid, not images

**Context.** Diagrams are needed in the README.

**Decision.** Mermaid, rendered natively by GitHub.

**Rejected.** Screenshots or externally hosted images — they cannot be diffed, they rot when
the underlying numbers change, and external links break.

**Consequence.** Diagram complexity is limited to what Mermaid renders reliably.

## D11 · Repetitive SQL is generated, not written

**Context.** The covariate balance query needs 96 near-identical aggregate expressions.
Typos in such a block are invisible in review.

**Decision.** `scripts/gen_balance_sql.py` generates `sql/04_covariate_balance.sql`. The
generator is what gets reviewed; the SQL is an artifact.

**Rejected.** Hand-writing it; or using `UNPIVOT`, which would be shorter but is not
portable (D8).

**Consequence.** The generated file carries a header saying not to edit it directly.

## D12 · Environment: devcontainer, reproducible from the repository

**Context.** The work must run identically for anyone who opens the repository, on a machine
with little free disk.

**Decision.** A devcontainer definition, so GitHub Codespaces builds the environment from
the repository. Data is downloaded inside the container and never committed.

**Rejected.** Local installation instructions only; notebook-first development, which makes
diffs unreviewable.

**Consequence.** Scripts and SQL files are the unit of work. Notebooks, if added, are for
presentation of results already produced by scripts.
