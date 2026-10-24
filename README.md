# ITCS355 Lab 1 — Reproducible Training

> **Course materials live in [`course/`](course/README.md)** — syllabus, slides, the faculty
> specification, all five lab handouts, and the project brief. Every document is Markdown and
> renders on GitHub, diagrams included. New to the repo? Start with the
> [portability reference](course/reference/cloud-portability-reference.md).
> Keep this block when you edit the rest of this file; it is not part of the Lab 1 deliverable.

Predicting machine failure within 7 days from sensor readings. The model is not the point;
whether a stranger can reproduce it is.

> **This README is graded.** A grader with Docker and nothing else from your setup runs one
> command and compares the result against the claim below.

---

## Reproduce

```bash
make reproduce
```

expected test_roc_auc: 0.848 ± 0.001

Runtime: about 40 seconds on 4 cores. No cloud account or credentials needed for this command —
that is deliberate, and it is why a grader can run it.

The claim is re-measured from the deterministic default run. The tolerance is intentionally small:
the model, grouped split, and seed are fixed. It should be updated only if the dataset or training
configuration changes.

---

## The problem

240 machines, 25 readings each, 6 sensor features, binary target `failed_within_7d` with a
positive rate near 12%.

Machines have persistent characteristics — a hot-running machine reads hot in every row. So the
train/validation/test split is **grouped by `machine_id`**: every reading from one machine lands
in exactly one partition. Splitting row-wise instead lets the model memorise the machine and
reports a validation score that will never survive production. `tests/test_data.py` asserts this
property holds, and Lab 4 turns it into a CI gate.

Bringing your own dataset is allowed. Replace `scripts/make_dataset.py`, update the schema in
`src/data.py`, and keep every test passing.

---

## Layout

```
src/          Layer 1 — provider-neutral. No SDKs, no bucket names, no absolute paths.
cloudlayer/   Layer 3 — the only place a provider SDK may be imported.
scripts/      Dataset generation, cloud check, portability audit, metric verification.
tests/        Data contract tests and split property tests.
```

`src/config.py` is the single point of environment knowledge. Everything else reads from it.
`make portability-audit` enforces the rule; it fails the build if a provider string appears in
`src/` or `tests/`.

---

## Setup

```bash
cp cloud.env.example cloud.env      # fill in, never commit
make setup
make cloud-check                    # eight slots, all PASS
make data                           # generate the dataset
make test                           # 10 tests, all passing
```

Post your `make cloud-check` output in the course channel before Session 1.

---

## What you must finish

The Docker base is pinned by digest and is configured to install only artifacts from the hash lock
file. The selected cloud adapter implements object-storage upload/download and digest-addressed
registry pushes. After generating the lock file and filling in `cloud.env` with your provider
values, publish the cloud artifacts with:

```bash
make image-push        # image reaches your registry, digest-pinned
dvc init && dvc remote add -d storage ${BLOB_URI}/dvc
dvc add data/raw && dvc push
```

Run five or more tracked runs varying something meaningful — not five identical runs with
different seeds.

---

## Reproducibility trade-off

Three things pin your build: hashed dependencies, a digest-pinned base image, and controlled
seeds. Under real time pressure you would keep some and drop others.

Under genuine time pressure I would drop seed control first. The image can still be built from the
same base and verified package artifacts, but experiment-to-experiment metrics and splits cease to
be directly comparable. I would not drop hashes or the base digest: either allows the same Git
revision to acquire different dependency or OS bits, so it may no longer build or run the same
program at all.

---

## Notes for the grader

Run `make reproduce` from the repository root. It generates the deterministic teaching dataset,
builds a `linux/amd64` image, and writes `reports/metrics.json`. The command intentionally needs
no cloud credentials. Provider credentials are required only for `dvc push` and `make image-push`.

---

## Checklist before you submit

- [ ] `make reproduce` works from a fresh clone, on a machine that is not yours
- [ ] `make verify` passes against your claim line
- [ ] `make test` — all tests pass
- [ ] `make portability-audit` — clean
- [ ] Image builds for `linux/amd64` and is pushed, digest-pinned
- [ ] `dvc push` completed; a grader can `dvc pull`
- [ ] Five or more tracked runs with params, metrics, data fingerprint, and commit SHA
- [ ] All submission placeholders have been replaced
- [ ] `git log -p | grep -i -E "secret|password|AKIA|BEGIN PRIVATE"` returns nothing

That last check is not optional. A credential in Git history is an automatic deduction in this
course, and rotating it is your responsibility, not the grader's.

## Lab 2 — GCP

See [GCP setup and lab workflow](docs/lab2-gcp-zh.md) and the [comparison report and evidence status](reports/lab2-comparison.md). Local rehearsal: `bash scripts/lab2_local.sh`.

In a real organisation, an independent ML platform/release reviewer and model owner should authorize staging promotion after checking validation/test results, seed stability, lineage, cost, reproducible reload and rollback evidence. Training identities should not have production promotion permission. The lab script assigns staging automatically only to demonstrate the workflow.

## Lab 3 — serving and rollback

Build and push the serving image, set its immutable digest in `SERVING_IMAGE_URI`, and deploy with
`make deploy MODEL_REF=<registered-version>`. Save the returned resource name as
`ENDPOINT_RESOURCE` in `cloud.env`; `make smoke`, `make loadtest TARGET=<predict-url>`, and
`make canary-check` then use your endpoint without repository-specific IDs. Record your own
p50/p95/p99, throughput, errors, canary timestamps, rollback evidence, and cost calculation under
`reports/`, then run `make teardown LAB=3` immediately to stop endpoint charges.

## Lab 4 — CI/CD and reliability

The data-contract tests name real producer failures: the schema/type test catches a renamed,
removed, or string-encoded sensor column; the null test catches partial ingestion or failed joins;
the range test catches unit conversion errors such as Celsius arriving as Fahrenheit; and the
machine-group leakage test prevents the same machine appearing in training and evaluation.

CI runs lint, unit, data-contract, model-behaviour, image-build, and container integration checks
in that order. CD runs only after green CI on `main`, authenticates to GCP with GitHub OIDC, tags
the serving image with the commit SHA, deploys staging, and smoke-tests it. The hourly drift job
emits Cloud Monitoring metrics and sends breached alerts to `ALERT_WEBHOOK_URL` from GitHub
Secrets. Configure the repository variables and secrets named in `.github/workflows/cd.yml` and
`.github/workflows/drift.yml`; no long-lived credential is committed.

The PSI alert threshold is **0.20**. Stable calibration windows remain below 0.10, while the
injected spread fault crosses 0.20; this tighter-than-credit-scoring threshold is appropriate for
operational sensors because waiting for 0.25 risks consuming a maintenance cycle before detection.
An alert is not an automatic retraining trigger: schema, range, or null failures indicate an
upstream pipeline incident that must be fixed and backfilled before any retraining.

## Lab 5 — managed operation and LLM controls

### Pipeline and evaluation policy

`make pipeline` compiles the neutral six-step DAG to Vertex/Kubeflow JSON. Ingest uploads the
versioned dataset, validation aborts on contract failure, training uses Spot compute, and the
evaluation component writes a real `pass`/`fail` output. Registration and staging deployment live
inside a `dsl.If(decision == "pass")` branch. A candidate must reach test ROC-AUC **0.75** and,
when an incumbent is supplied, improve by at least **0.002**. The absolute floor protects the first
registration; the improvement margin avoids promotion on reported-decimal noise.

### Least-privilege identities

Exact identity references are injected through `cloud.env` and are not committed.

| Identity | Allowed scope | Why it is required |
|---|---|---|
| Training/pipeline service account | Read the Lab 5 input prefix; write Lab 5 model, metric, checkpoint and pipeline-root prefixes; create and observe Vertex jobs; emit metrics | Runs the managed DAG and persists reproducible lineage without serving permissions |
| Serving service account | Read only the selected model artifact; write service logs and metrics | Loads the model and exposes predictions without changing training data or registry state |
| GitHub OIDC CI service account | Push immutable images, submit the pipeline and deploy staging while impersonating only the serving identity | Automates releases without a stored service-account key or data access |

The assessed permission-removal experiment was run on this project: the serving identity read the
chosen model, lost its bucket object-view permission, received HTTP 403
`storage.objects.get denied`, then read successfully after restoration. The temporary operator
impersonation permission was also removed. Evidence is in `reports/lab5/iam-removal.txt`.

### Retraining trigger

The selected schedule is **Sunday 02:00 Asia/Bangkok**, with one concurrent run. The schedule
should remain paused outside the evidence run so it cannot create an unnoticed bill.

| Strategy | When it is right for this failure-prediction system | How it fails |
|---|---|---|
| Weekly fixed schedule | Predictable sensor refresh cadence and a bounded, auditable training bill | Wastes a run during stable weeks and can wait nearly seven days after a genuine change |
| Data-volume threshold | Enough new machines have accumulated to support a fresh group split | Duplicated, noisy or single-machine readings can meet the count without adding information |
| Drift-triggered | Valid sensor distributions move materially and urgent adaptation is justified | A broken sensor or unit conversion looks like drift and can rapidly train bad data into a working model |

We choose the weekly schedule plus mandatory data contracts and the evaluation gate. Worst case:
corrupted upstream data arrives just before Sunday and destroys a good model. Contract failure must
therefore abort before training, and passing drift alone never authorizes promotion.

### Portability result and honest verdict

`make portability-audit` checks that provider SDKs and resource strings stay outside Layer 1.
The second adapter is AWS: `upload`, `download`, and `invoke` are exercised offline in
`tests/test_aws_portability.py`; a real-account run of `make swap-check SECOND=aws` remains required
for cloud evidence. Set `SECOND_BLOB_URI`, `SECOND_REGION`, `SECOND_PROJECT_ID`, and
`SECOND_ENDPOINT` in the uncommitted `cloud.env` before that run.

`invoke` was hardest because SageMaker uses a named endpoint, a byte-stream body and a response
envelope different from Vertex raw prediction. The abstraction genuinely leaks through resource
configuration: changing `CLOUD_PROVIDER` cannot turn a GCS URI into an S3 URI or provision a
compatible endpoint. A small production migration would take roughly **5–10 engineering days**
for IAM, S3/ECR, SageMaker training and serving, CI, monitoring, integration tests and cleanup.
The seam is worth keeping for storage and a stable prediction response, but it is not automatic
multi-cloud portability; for a permanently single-cloud service, the extra adapters may cost more
than deliberate lock-in.

### LLM golden set and guardrail

The machine-maintenance triage set contains **12 cases**, including grounding, refusal, injection
inside data fields, and insufficient input. `make llm-eval` records the deterministic baseline;
`make llm-gate` deliberately regresses borderline escalation, invents a part and date, obeys
injected data, leaks hidden instructions, and must exit non-zero on the per-case comparison.

The most expensive guardrail failure is an injected or disclosure request influencing a work order
or exposing credentials. Cases `triage-006`, `triage-007`, `triage-010`, and `triage-011` enforce
refusal and data/instruction separation. Reproduce the control with:

```bash
make llm-gate   # expected non-zero: the guardrail regression is caught
```

Offline fixtures are test evidence, not token-billing evidence. A live Vertex run reads
`usage_metadata` in `GcpAdapter.generate`; only `reports/llm_eval-live.json` may supply measured
token counts to `make cost`. The final Vertex `global` run used `gemini-3.5-flash-lite`, passed
12/12 cases, and recorded 415 average input tokens, 37 average billed output tokens, 1,816 ms p95
and 4.7855 THB/1,000 requests at the course planning rate. Earlier regional/model 404s and their
resolution are preserved in `reports/lab5/llm-access-blocker.txt`. The generated
[Lab 5 cost report](reports/lab5-cost.md) keeps settled billing, managed-run and second-provider
evidence visibly pending.
