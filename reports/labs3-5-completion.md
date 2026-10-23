# Labs 3–5 completion audit

**Audited:** 2026-10-24 (Asia/Bangkok)  
**Repository:** `XinyiChenxy/ML_Dep`

This audit separates implemented code from external evidence. A checked code item does not turn a
pending cloud run or screenshot into evidence.

## Lab 3 — serving, load testing, rollback

### Implemented and verified

- [x] FastAPI `/predict`, `/predict/batch`, `/health`, `/ready`, Pydantic validation and structured
  request logs.
- [x] Model loaded once at startup; model version returned in response body.
- [x] GCP deploy and invoke adapter. Vertex invocation uses RawPredict so the provider-neutral
  FastAPI body is preserved.
- [x] Serving model registration injects its immutable artifact URI and runtime configuration.
- [x] Endpoint labels match Lab 3/4/5 so the correct teardown command can find them.
- [x] Committed k6/Locust scripts and a predeclared p95 < 500 ms target.
- [x] Local three-concurrency baseline with p50/p95/p99, throughput, error rate, batch and payload
  measurements in `reports/lab3-load.md`.
- [x] Seven service HTTP integration tests pass against a real temporary Uvicorn process.

### Still required externally

- [ ] Deploy and smoke-test a real managed endpoint.
- [ ] Repeat the load test on that endpoint, including cold start if it scales to zero.
- [ ] Compare one larger instance and its actual price.
- [ ] Deploy the deliberately weaker version at 90/10, record metric-only detection and timestamped
  rollback evidence.
- [ ] Replace projected cost with billed/managed throughput figures.
- [ ] Run `make teardown LAB=3` and capture an empty endpoint list.

**Current verdict:** code ready; acceptance evidence incomplete.

## Lab 4 — CI/CD, observability, drift

### Implemented and verified

- [x] Unit, 10 data-contract, 5 model-behaviour and 7 service integration tests.
- [x] Full-history secret scanner; shallow checkout is rejected.
- [x] CI on pull requests and main, SHA image tags, container integration test.
- [x] CD is gated on green main CI, uses OIDC, uses repository variables instead of a hard-coded
  project, and deletes its temporary staging endpoint.
- [x] Dashboard-as-code covers request rate, 4xx/5xx, p50/p95/p99, rolling feature drift and model
  version. Dashboard and detector now share PSI threshold 0.20.
- [x] SLO includes target, window and error-budget response.
- [x] Scheduled detector, metric emission, webhook code, drift injection and reasoned five-line local
  post-mortem.
- [x] Main [CI run `39994453361`](https://github.com/XinyiChenxy/ML_Dep/actions/runs/39994453361)
  passed on commit `0d6ea64`.
- [x] GitHub OIDC authenticates through repository-scoped GCP Workload Identity Federation without
  a long-lived service-account key.
- [x] Live [scheduled drift run `39996053148`](https://github.com/XinyiChenxy/ML_Dep/actions/runs/39996053148)
  downloaded both GCS windows, emitted Cloud Monitoring PSI metrics and delivered the breached
  `temp_c=0.38333` alert to the real Slack `#all-itcs355` channel. The user captured both the green
  1m39s Actions run and delivered Slack message.

### Still required externally

- [x] Deliberately bad [pull request #1](https://github.com/XinyiChenxy/ML_Dep/pull/1) removed
  `temp_c`; the [Actions job](https://github.com/XinyiChenxy/ML_Dep/actions/runs/39986069085/job/120525462831?pr=1)
  recorded `test_schema_columns_present_and_typed` failing with
  `missing columns: ['temp_c']`. Close it without merging after preserving the screenshot.
- [ ] Capture the imported Cloud Monitoring dashboard showing the emitted PSI metric at the alert
  timestamp.
- [ ] Run teardown and verify the scheduler/endpoint lists are empty.

**Current verdict:** CI blocking, WIF, scheduled drift, metric emission and real-channel alert
evidence pass; dashboard and teardown evidence remain.

## Lab 5 — managed operation, portability, cost and LLM controls

### Implemented and verified

- [x] Six-step managed pipeline with a real conditional evaluation gate.
- [x] Pipeline steps constrained to the smallest requested CPU/memory footprint and training uses
  Spot compute.
- [x] Three-identity least-privilege design documented.
- [x] Paused weekly retraining schedule and system-specific three-strategy comparison.
- [x] Portability audit passes; AWS upload/download/invoke implementation has offline tests.
- [x] Twelve-case LLM golden set covers grounding, refusal, injection and insufficient input.
- [x] Baseline passes 12/12; deliberately regressed gate fails 8 named cases.
- [x] Token-cost helpers, output-cap saving and cache break-even tests.
- [x] Real GCP quota refusal recorded in `reports/lab5/quota-blocker.txt`; no Custom Jobs or Endpoints
  were left running, and the schedule is paused.

### Still required externally

- [ ] Upgrade/qualify the GCP billing account, obtain enough regional custom-training CPU quota and
  complete a successful managed pipeline run.
- [ ] Run the IAM removal experiment and preserve successful read → permission removal → 403 →
  restoration output.
- [ ] Demonstrate AWS upload/download/invoke against a real second account.
- [ ] Export tag-filtered billing and replace pending actual-cost fields.
- [ ] Run the live LLM evaluation and use provider-reported token fields.
- [ ] Delete the paused schedule and every remaining Lab 5 resource; capture the empty console list
  and repeat verification after 24 hours.

**Current verdict:** local logic and negative gate evidence pass; managed acceptance is blocked by
quota and several account-owned evidence steps remain.

## Reproducible local checks

```bash
make data
make test
make scan-secrets
make portability-audit
make pipeline
make llm-eval
make llm-gate  # expected non-zero; proves eight regressions are blocked
```
