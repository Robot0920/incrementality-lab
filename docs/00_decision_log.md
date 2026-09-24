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

## D13 · Dependencies selected on measured maintenance, not reputation

**Context.** D5 named libraries from familiarity. Several well-known causal-inference
packages are no longer maintained, and an unmaintained dependency is a liability that only
shows up later.

**Decision.** Selection made against repository metadata measured on 2026-09-24:

| Library | Stars | Last push | Licence | Outcome |
|---|---:|---|---|---|
| py-why/dowhy | 8,327 | 2026-09-24 | MIT | adopted |
| py-why/EconML | 4,798 | 2026-09-21 | MIT | adopted |
| uber/causalml | 6,008 | 2026-08-20 | Apache-2.0 | adopted |
| spotify/confidence | 303 | 2026-02-26 | Apache-2.0 | adopted |
| WillianFuks/tfcausalimpact | 678 | 2026-09-20 | Apache-2.0 | conditional: needs a time dimension this dataset lacks |
| st-tech/zr-obp | 710 | 2024-06-03 | Apache-2.0 | deferred to any off-policy-evaluation work |
| maks-sh/scikit-uplift | 818 | 2023-10-21 | MIT | rejected: stale, superseded by causalml |
| hakuhodo-technologies/scope-rl | 143 | 2024-03-18 | Apache-2.0 | rejected: niche and stale |
| criteo-research/reco-gym | 482 | 2021-07-09 | Apache-2.0 | rejected: dormant, and answers a different question (D4) |

GitHub reports EconML and CausalML as "NOASSERTION" because of the formatting of their
LICENSE files; the file contents are MIT and Apache-2.0 respectively, both permissive.

**Consequence.** Every dependency here was pushed to within the last two months except
where explicitly deferred.

## D14 · Python pinned to 3.12

**Context.** Wheel availability measured on PyPI, 2026-09-24: `causalml` 0.17.0 requires
>=3.11 and publishes wheels for cp311 and cp312 only; `econml` 0.17.0 covers cp310-cp313;
`dowhy` 0.14 is pure Python.

**Decision.** 3.12 — the only version where every dependency installs from a prebuilt
wheel.

**Rejected.** 3.11 (works, but older); 3.13 (would force causalml to compile from source on
a two-core machine).

**Consequence.** Recorded in the devcontainer with the reasoning inline, so the pin is not
silently bumped later.

## D15 · Confidence sequences implemented in-repo rather than taken from `confseq`

**Context.** `confseq` is the reference implementation from the confidence-sequence
literature, but its latest release (0.0.11) ships wheels only up to cp310. On 3.11+ pip
compiles C++ from source, which is slow and fragile in a small container.

**Decision.** Implement the asymptotic confidence sequence directly — roughly fifteen lines
— and validate it with a simulation harness that checks the empirical false-positive rate
against the nominal level under the null.

**Rejected.** Depending on `confseq`; and implementing without validation.

**Consequence.** The validation harness is a prerequisite for using the estimator anywhere
else, and is built before the study that depends on it. A published formula transcribed
incorrectly is worse than no formula.

## D16 · Criteo Attribution dataset verified, then deferred

**Context.** A second Criteo dataset supplies exactly what this one lacks: timestamps,
campaign identifiers and cost, across 16M+ impressions and 700 campaigns over 30 days.

**Verification (2026-09-24).** `https://go.criteo.net/criteo-research-attribution-dataset.zip`
returns 206 on a ranged GET, redirecting to Azure blob storage. Two operational notes: the
host rejects HEAD requests, so probe with `curl -r 0-2000`; and despite the `.zip`
extension and `application/zip` content type the payload begins `1f 8b 08 08`, which is
gzip, so `unzip` will fail on it.

**Decision.** Record it as the leading candidate for a separate pipeline project. Do not
introduce it here.

**Rejected.** Adding it now. This study needs ground truth, and an observational log has
none, so it cannot serve the question. Adding it would repeat the scope drift that D1 was
written to correct.

## D17 · Toolchain: uv and ruff

**Context.** Cold-start time and an unconfigured linter. The devcontainer already installed
the ruff extension but the repository had no ruff configuration, so the extension did
nothing.

**Decision.** `uv` (Apache-2.0, 90k stars, actively developed) for dependency installation
in the devcontainer; `ruff` (MIT, 50k stars) configured in `pyproject.toml` for lint and
format, with format-on-save enabled.

**Consequence.** Dependency configuration stays in `requirements*.txt`, read identically by
uv and pip; `pyproject.toml` holds tooling configuration only.
