# Project Charter — "Amplify" Revenue Engine

> This document is the deliverable you walk an interviewer through. Everything else in the
> repo is evidence that it is real.

---

## 1. The product

**Amplify** is a self-serve promotion marketplace inside a music streaming platform.

- **Supply side**: artists, managers, labels. They opt tracks into Amplify and accept a
  **royalty discount** (e.g. −30% per stream) on *promoted* streams only.
- **Demand side**: listeners on algorithmic surfaces (radio, autoplay, personalized mixes).
- **Platform revenue from Amplify** = royalties not paid out:

```
Amplify revenue = Σ_tracks (promoted_streams × per_stream_royalty × discount_rate)
```

- **Feature iteration → revenue** is therefore a real chain, not a metaphor:
  a change in the self-serve tool → more/better campaigns → more promoted streams →
  more discounted payout → revenue. Every link is measurable, and every link can break.

**The core measurement problem**: turning Amplify *on* is not the same as the algorithm
actually *promoting* the track, and promoted streams are not necessarily *incremental*
streams. Cannibalization of organic streams is the thing that makes naive readouts wrong.

---

## 2. Decision rights — how DS stops being an internal consultant

A consulting DS receives requests, produces analyses, and PM decides. The fix is not
attitude, it is **owning artifacts that gate shipping**.

| # | Decision right | Artifact that carries it | Failure mode without it |
|---|---|---|---|
| 1 | **Metric contract** — metric definitions and the event spec are authored and signed by DS | `metrics.yml` + instrumentation spec | everyone brings their own numbers; DS becomes a reconciliation clerk |
| 2 | **Pre-registered decision rule** — launch/no-launch criteria, MDE, guardrails, stopping rule, all fixed before data | `docs/prereg/<exp>.md` + readout template | post-hoc slicing; DS loses the referee role |
| 3 | **Allocation authority** — who gets promoted, at what discount, with what budget, is a model output | uplift / allocation model in production | a PM spreadsheet decides where the money goes; ML is "input" |
| 4 | **Opportunity sizing** — the ranked roadmap with expected revenue lift + confidence comes from DS | quarterly sizing memo | DS only works downstream of decisions already made |
| 5 | **Incident ownership** — DS is on-call owner for revenue anomalies, with authority to roll back | RCA runbook + `ops.change_events` | when it breaks, engineering owns the narrative |

**Talk track**
> "I don't deliver analyses on request. I own four artifacts that gate shipping — the metric
> contract, the pre-registered decision rule, the allocation model, and the quarterly sizing
> memo — and I'm the on-call owner for revenue incidents. PM owns sequencing; I own what
> counts as success and whether we hit it."

---

## 3. The metric tree (the spine of every dashboard, alert, and RCA)

```
Amplify revenue
├── DEMAND side
│   ├── listeners on algorithmic surfaces (MAU)
│   ├── × sessions / listener
│   ├── × promotable impressions / session      ← inventory
│   ├── × promoted-stream rate / impression     ← the algorithm's weighting
│   └── × royalty × discount_rate               ← price / take
└── SUPPLY side
    ├── active artists on Amplify
    │   ├── ← new campaign adoption   (self-serve funnel: view → configure → submit → live)
    │   └── ← retention / churn of campaigns
    ├── × tracks / artist
    ├── × budget or cap / campaign
    └── × delivery rate (fill: did we spend the demand we promised?)

Contribution margin = revenue − incremental serving cost − support cost − cannibalized organic payout
```

Every node must carry four things. This is the discipline that makes RCA fast:

1. an **owner pod**
2. a **daily metric in `gold`**, single definition
3. the **same fixed dimension cube**: `country · platform · surface · artist_tier · campaign_age · discount_tier · acquisition_channel`
4. a written list of **known failure modes**

With (2) and (3) in place, mix-vs-rate decomposition is computable for any node — which is
always the first fork in a root cause analysis.

---

## 4. Pods — four workstreams, each a full pipeline

| Pod | Mission | Hardest problem | Primary deliverable |
|---|---|---|---|
| **0 · Foundation** | ingestion → bronze/silver/gold → semantic layer → data quality | the data contract boundary with DE | trusted marts + `metrics.yml` + DQ gates |
| **1 · Experimentation** | causal evidence for feature iteration | what to do when a clean RCT is impossible | pre-reg + readout + decision memo |
| **2 · Unit economics** | margin, not just revenue | discount efficiency and cannibalization | margin tree + reallocation recommendation |
| **3 · ML & deployment** | turn "who gets promoted, how much" into a model decision | uplift ≠ propensity; offline-online gap | served model + guardrails + monitoring |
| **4 · Market feedback** | unstructured feedback → leading indicators | turning artist complaints into a revenue signal | insight → sizing backlog |

### Pod 1's ladder: when you can't run a rigorous RCT

Most real revenue questions do not come with a clean experiment. The ladder — and for each
rung you must be able to state **the identifying assumption, how you test it, and how the
conclusion changes when it fails**:

```
RCT on users
 └─ can't randomize individuals?        → cluster / geo / market-level randomization
     └─ interference across sides?      → switchback / time-sliced / budget-split designs
         └─ must ship to everyone?      → interrupted time series + synthetic control
             └─ eligibility threshold?  → regression discontinuity
                 └─ staged rollout?     → staggered diff-in-diff
                     └─ observational?  → IPW / DML / matching, assumptions written down
                         └─ nothing?    → structured sizing with bounds, labeled "directional, not causal"
```

---

## 5. Every pod runs the same 7 stages

```
S1 Decision    the decision and its rule, written before the data ("if X then we do Y")
S2 Contract    metric definitions + event spec + data contract with DE
S3 Pipeline    ingestion → bronze → silver → gold, plus DQ gates
S4 Method      analysis / experiment / model design, assumptions, power
S5 Artifact    dashboard, model, or memo — and who reads it
S6 Rollout     launch, monitoring, alerting, rollback condition
S7 Retro       what we learned → backlog + runbook update
```

---

## 6. RCA by construction

### `ops.change_events` — one timeline for every suspect

Most teams are slow at RCA because "what changed" is scattered across five systems.
We build one table from day one:

```sql
ops.change_events (
    event_ts      TIMESTAMP,
    change_type   VARCHAR,  -- deploy | flag_flip | experiment_start | experiment_stop
                            -- | model_deploy | pricing_change | discount_change
                            -- | marketing_spend_shift | pipeline_run | schema_change
                            -- | vendor_incident
    entity        VARCHAR,  -- what it touched (surface, country, model name, table)
    owner         VARCHAR,
    payload       JSON
)
```

Any anomaly becomes a single join against a time window.

### Triage order — fixed, exhaustive, falsifiable

Never skip a step, and always say out loud which step you are on:

```
1. Is the data real?   freshness, row counts, null rate, event-schema drift, late arrivals
2. Did we change it?   deploy · flag · experiment · model · price · discount
3. Did the mix change? mix-vs-rate decomposition over the fixed dimension cube
4. Did demand change?  seasonality, holidays, platform (iOS/Android), competitor, macro
5. Is it measurement?  bots, dedup, timezone, attribution window
```

An interview answer to "revenue dropped 8% week over week" only earns points if it is an
**ordered, exhaustive, falsifiable** triage — not a list of possibilities.

---

## 7. Data assembly

| Layer | Source | Status |
|---|---|---|
| L1 Demand spine | ListenBrainz / Last.fm listens | real — power-law engagement and a real long tail |
| L2 Causal lab | Criteo-UPLIFT v2.1 | real randomized experiment, with `exposure` → ITT vs LATE |
| L2b Meta-experiment lab | Upworthy Research Archive | real ~32k A/B tests → effect-size distribution, peeking, MDE |
| L3 Product & supply | simulator with ground truth | flags, campaigns, budget pacing, revenue ledger, injected incidents |

**On the simulator** — say it this way:
> "Public data has no assignment logs and no counterfactuals, so I built a simulator with
> known ground-truth effects and injected known failure modes. That let me do two things
> observational data can't: validate that my estimators recover the true lift — including
> under interference and one-sided non-compliance — and benchmark my RCA runbook against
> incidents where I already knew the answer."

That is a senior move. "My data is simulated" is a weakness; "I simulated to validate my
estimators" is a credential. The difference is ground truth plus validation.

---

## 8. Roadmap

`[CORE]` = you must be able to talk through this. `[EXT]` = depth if time allows.

**Pod 0 — Foundation**
- `[CORE]` ingest Criteo-UPLIFT into bronze, with an ingestion gate
- `[CORE]` compliance profile: randomization ratio, one-sided non-compliance, base rates
- `[CORE]` silver: event semantics + `ops.change_events` skeleton
- `[CORE]` gold: daily metric tree tables over the fixed dimension cube
- `[EXT]` promote `sql/` into dbt models with tests; mirror gold into BigQuery + Looker Studio

**Pod 1 — Experimentation**
- `[CORE]` pre-registration doc + power/MDE calculation at a 0.2%-scale base rate
- `[CORE]` ITT vs LATE on Criteo: why the naive difference is wrong and by how much
- `[CORE]` decision memo template, and the readout that survives a hostile PM
- `[EXT]` sequential testing and peeking; CUPED; switchback for two-sided interference

**Pod 2 — Unit economics**
- `[CORE]` margin tree; cannibalization of organic streams; discount-tier efficiency
- `[EXT]` budget reallocation under a constraint

**Pod 3 — ML & deployment**
- `[CORE]` uplift model vs propensity model; Qini/AUUC; why targeting ≠ prediction
- `[EXT]` serving, monitoring, drift, offline-online gap

**Pod 4 — Market feedback**
- `[CORE]` artist feedback → topic signal → leading indicator of campaign churn
- `[EXT]` feeding the quarterly sizing memo

**Drills**
- `[CORE]` incident injection + timed RCA against known ground truth
