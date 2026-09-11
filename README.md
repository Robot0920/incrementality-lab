# revenue-engine

An end-to-end **product data science** project where the DS owns the decisions, not the slides.

Domain: **Amplify** — a self-serve promotion marketplace on a music streaming platform.
Artists and labels accept a lower per-stream royalty in exchange for algorithmic weighting
in radio / autoplay. The platform's revenue is the royalty it *doesn't* pay out.
(A Discovery Mode analog: two-sided, incentive-aligned, and notoriously hard to measure.)

Read [`docs/00_charter.md`](docs/00_charter.md) first — it is the project's contract and the
artifact you actually walk an interviewer through.

---

## Quickstart (GitHub Codespaces — nothing lands on your laptop)

1. On the repo page: **Code → Codespaces → Create codespace on main**.
   The devcontainer installs `requirements.txt` automatically (~2 min).
2. In the Codespace terminal:

```bash
# Pod 0 / S3 — ingest the real randomized experiment (~297 MB, stays in the cloud)
python -m src.ingest.criteo_uplift

# Pod 0 / S4 — first analysis: what is this experiment's compliance structure?
python -m src.sqlrun sql/pod0/01_compliance_profile.sql
```

3. `Ctrl+Shift+P → Codespaces: Stop Current Codespace` when done, so you don't burn
   free hours. Your `data/` survives a stop; it is deleted when you *delete* the codespace.

Free tier: 120 core-hours/month on a 2-core machine = 60 h, plus 15 GB-months of storage.

## Layout

```
docs/     the charter, the RCA runbook, pre-registration docs, decision memos
src/      python: config, warehouse connection, ingestion, SQL runner
sql/      one question per file, named after the question; later promoted into dbt models
data/      git-ignored. bronze/silver/gold all live in data/revenue.duckdb
```

## Data sources

| Layer | Source | What's real about it |
|---|---|---|
| Causal lab | Criteo-UPLIFT v2.1 (13.98M rows) | a genuine randomized ad experiment, with an `exposure` column → ITT vs LATE |
| Meta-experiment lab | Upworthy Research Archive (~32k tests) | the real distribution of A/B test outcomes (most are null) |
| Demand spine | ListenBrainz / Last.fm listens | real power-law engagement, real long tail |
| Product & supply layer | simulated, with ground truth | flags, campaigns, budget pacing, revenue ledger, injected incidents |

Why simulate part of it: no company publishes feature-flag exposure logs, deploy logs, or
revenue ledgers. The simulator exists so estimators can be validated against a **known truth**
and the RCA runbook can be benchmarked against incidents whose cause is known in advance.
