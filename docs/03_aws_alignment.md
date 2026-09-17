# AWS alignment — building for MLA-C02 without rewriting anything

Target: **AWS Certified Machine Learning Engineer – Associate, MLA-C02**
(the updated version; adds generative AI, Bedrock, RAG, agents and responsible AI on top
of the four MLA-C01 domains).

The principle: **develop locally in the Codespace against DuckDB, deploy to AWS as a
second backend.** Local iteration is free and instant; AWS is where the portfolio artifact
and the exam practice live. Anything that would force a rewrite when porting is decided
here, up front. Everything else waits until the corresponding course domain.

---

## Domain map

| MLA-C02 domain | Weight | Project pod | AWS implementation |
|---|---|---|---|
| D1 Data preparation | 28% | Pod 0 Foundation | S3 (bronze/silver/gold prefixes, Parquet, Hive partitions) · Glue Crawler + Data Catalog · Glue ETL · Glue DataBrew · **Glue Data Quality** · Athena · SageMaker Feature Store |
| D2 Model development | 26% | Pod 3 ML | SageMaker Training (built-in XGBoost, script mode) · Automatic Model Tuning · Experiments / MLflow · **Clarify** · Model Registry · Model Cards |
| D3 Deployment & orchestration | 22% | Pod 3 + Pod 0 | SageMaker Pipelines · Batch Transform · Serverless Inference · Step Functions · EventBridge · ECR · CDK · CodePipeline / CodeBuild |
| D4 Monitoring, maintenance, security | 24% | Pod 0 RCA system | SageMaker Model Monitor (data quality, model quality, bias drift, feature attribution drift) · CloudWatch dashboards + alarms · **CloudTrail as the AWS-native `ops.change_events`** · IAM least privilege · KMS · Secrets Manager |
| C02 generative AI additions | — | **Pod 4 Market feedback** | Bedrock (foundation models, Knowledge Bases = RAG, **Agents**, Guardrails, Evaluations) |

---

## The seven decisions made up front

### 1. Portable SQL only: the DuckDB ∩ Athena intersection

Athena runs Trino. Every file under `sql/` and, later, every dbt model must parse on both
engines. DuckDB-only conveniences are allowed in an exploratory session but never
committed to `sql/`.

| Avoid (DuckDB-only) | Use instead |
|---|---|
| `SUMMARIZE t` | exploration only, never committed |
| `USING SAMPLE n ROWS` | `TABLESAMPLE BERNOULLI(n)`, or exploration only |
| `UNPIVOT` | `UNION ALL`, or Athena's `CROSS JOIN UNNEST` |
| `read_csv_auto()` | ingestion scripts only, never in transformation |
| `SELECT * EXCLUDE (...)`, `GROUP BY ALL` | explicit column lists |

Safe on both: CTEs, window functions with `PARTITION BY`, `CASE WHEN`, `UNION ALL`,
`var_samp` / `stddev_samp`, `CREATE TABLE AS SELECT`.

Bonus: this intersection also parses on BigQuery and Snowflake, so the same models are
portable to the warehouse a future employer happens to run.

### 2. Lay data out as a lake from day one

```
data/lake/bronze/criteo_uplift/part-0000.parquet
data/lake/silver/<table>/dt=YYYY-MM-DD/part-0000.parquet
data/lake/gold/<table>/dt=YYYY-MM-DD/part-0000.parquet
```

maps one-to-one onto `s3://<bucket>/{bronze,silver,gold}/...`, so porting is an
`aws s3 sync` plus a Glue Crawler run.

- **Parquet, never CSV.** Athena bills by bytes scanned; columnar storage with column
  pruning cuts that by one to two orders of magnitude. "Why Parquet over CSV" is itself a
  D1 exam question.
- **Hive-style partitions** (`dt=YYYY-MM-DD/`) so the Glue Crawler infers partition
  columns automatically.
- **Parquet files are the source of truth; the DuckDB file is a convenience.** Deleting
  `data/revenue.duckdb` must never lose data.

### 3. dbt for the transformation layer, with two targets

One set of models, two backends: `dev` → dbt-duckdb (free, instant, in the Codespace),
`prod` → dbt-athena. Installed when Pod 0 reaches the silver layer, not before.

dbt also satisfies D1/D3 (ETL, dependency graph, lineage, tests) and appears by name in
the product-DS roles being targeted, so the investment pays twice.

### 4. Data-quality rules are declarative, written in Glue DQDL

The ingestion gate moves out of Python into `dq/*.dqdl`, written in AWS Glue Data Quality's
own rule language so it can be pasted into a Glue job unchanged.

The important idea: **identifying assumptions are encoded as data-quality rules, not
comments.** If one-sided non-compliance ever breaks upstream, the pipeline fails loudly
instead of silently invalidating every causal estimate downstream.

### 5. Training scripts follow SageMaker script-mode conventions

```python
p.add_argument("--train",     default=os.environ.get("SM_CHANNEL_TRAIN", "data/lake/gold/train"))
p.add_argument("--model-dir", default=os.environ.get("SM_MODEL_DIR",     "artifacts/model"))
```

Locally the defaults apply; as a SageMaker training job the environment variables are
injected. The same file runs in both places with no edits. Choosing between script mode,
a built-in algorithm, and a bring-your-own container is a recurring D2/D3 exam question, so
the repo should demonstrate the reasoning, not just one option.

### 6. Pod 4 becomes the generative-AI pod, and gains an RCA Agent

C02's new content lands naturally on the pod that was already about unstructured feedback.
Pod 4 is promoted from `[EXT]` to `[CORE]` and gains one portfolio-grade deliverable:

> **RCA Agent** — the fixed triage order from the charter, plus `ops.change_events` and the
> metric tree, exposed as an agent. Input: "revenue is down 8% week over week." The agent
> queries the warehouse, works the triage order without skipping steps, and returns a
> ranked set of hypotheses with the evidence for each.

This exercises Bedrock **Agents** (tool use), **Knowledge Bases** (retrieval over the
runbook in `docs/`), **Guardrails** (never invent a number), and **Evaluations** — and the
evaluation set already exists, because the injected incidents come with ground truth.

Local development keeps prompts and evaluation sets as files in the repo and calls models
through a thin interface, so switching to the Bedrock `converse` API is a one-file change.

### 7. Cost controls come before resources

1. Create AWS Budgets (a $10 alert and a $25 alert) **before** creating any resource.
2. Default to shapes that cost nothing at rest: Athena (per query), **Batch Transform**
   (terminates when done), **Serverless Inference** (no charge with no traffic). Never
   leave a real-time endpoint running.
3. Create everything with CDK and `cdk destroy` after each exercise. Watch Bedrock
   Knowledge Bases in particular: the default OpenSearch Serverless vector store bills a
   minimum capacity even while idle. Stand it up last, tear it down immediately, and check
   current cheaper vector-store options before committing to it.

---

## Sequencing rule

For every block: **get the logic right locally against DuckDB first, then port.** Debugging
SQL in Athena is slow and metered, and porting incorrect logic accomplishes nothing.

## Service tiers for exam study

**Tier 1 — hands-on depth.** S3 · Glue (Crawler, Catalog, ETL, DataBrew, Data Quality) ·
Athena · SageMaker (Studio, Processing, Training, built-in algorithms, Automatic Model
Tuning, Feature Store, Experiments/MLflow, Clarify, Model Registry, Model Cards, Model
Monitor, Pipelines, and all four inference modes) · Step Functions · EventBridge · Lambda ·
ECR · CloudWatch · CloudTrail · IAM · KMS · Secrets Manager · CloudFormation/CDK ·
CodePipeline/CodeBuild · Budgets/Cost Explorer · **Bedrock** (models, Knowledge Bases,
Agents, Guardrails, Evaluations).

**Tier 2 — know when to choose it.** Kinesis / Data Firehose / Managed Flink · EMR ·
Redshift · MWAA · Batch · ECS/EKS · DynamoDB · ElastiCache · API Gateway · Lake Formation ·
Macie · OpenSearch · SQS/SNS · A2I · Ground Truth · Auto Scaling · Config.

**Tier 3 — recognize the name and one-line purpose.** Comprehend · Textract · Rekognition ·
Transcribe · Translate · Polly · Personalize · Fraud Detector · Kendra · Lex · Lookout
for * · CodeGuru · DevOps Guru · Q · HealthLake · Comprehend Medical · Mechanical Turk.

**The four recurring judgement questions.** Managed AI service vs SageMaker vs Bedrock ·
which of the four inference modes · Athena vs Glue ETL vs EMR vs Redshift · Step Functions
vs SageMaker Pipelines vs MWAA. Be able to give one decision criterion for each.
