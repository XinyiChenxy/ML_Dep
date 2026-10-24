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
- [x] Local and real Vertex three-concurrency measurements with p50/p95/p99, throughput, error
  rate, batch and payload findings in `reports/lab3-load.md`.
- [x] Real `n1-standard-2` versus `n1-standard-4` comparison with the same model and request set.
- [x] Real 90/10 Vertex canary, model-blind quality detection, timestamped atomic rollback and
  post-rollback recovery verification.
- [x] Seven service HTTP integration tests pass against a real temporary Uvicorn process.

### Managed evidence

- [x] Deploy and smoke-test a real managed endpoint. Lab 4 CD run
  [`40006390277`](https://github.com/XinyiChenxy/ML_Dep/actions/runs/40006390277) deployed
  Vertex model version 1, passed all smoke requests and deleted the temporary endpoint.
- [x] Managed load test completed at concurrency 1, 10 and 50; fixed replicas do not scale to zero.
- [x] Compared the next larger instance using managed throughput and the course pricing rate.
- [x] Deployed deliberately weaker immutable v2 at 90/10; detected degradation without reading
  response version labels and restored v1 to 100%.
- [x] Cost-per-1,000 denominator uses measured managed throughput; the report distinguishes the
  planning hourly rate from a settled bill.
- [x] `make teardown LAB=3` deleted the endpoint and a filtered provider query returned `[]`.

**Current verdict:** managed serving, load, instance, canary, rollback and teardown evidence pass.

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
- [x] Final [CI run `40005606348`](https://github.com/XinyiChenxy/ML_Dep/actions/runs/40005606348)
  passed on commit `0dc78a5`; its gated
  [CD run `40006390277`](https://github.com/XinyiChenxy/ML_Dep/actions/runs/40006390277)
  authenticated with WIF, built and pushed the image, deployed Vertex model version 1 with the
  dedicated serving identity, passed the managed-endpoint smoke test and cleaned up staging.
- [x] GitHub OIDC authenticates through repository-scoped GCP Workload Identity Federation without
  a long-lived service-account key.
- [x] Live [scheduled drift run `39996053148`](https://github.com/XinyiChenxy/ML_Dep/actions/runs/39996053148)
  downloaded both GCS windows, emitted Cloud Monitoring PSI metrics and delivered the breached
  `temp_c=0.38333` alert to the real Slack `#all-itcs355` channel. The user captured both the green
  1m39s Actions run and delivered Slack message.
- [x] Imported Cloud Monitoring dashboard
  [`346faf7b-ce0c-4a1b-a7d2-8d615e5f6020`](https://console.cloud.google.com/monitoring/dashboards/builder/346faf7b-ce0c-4a1b-a7d2-8d615e5f6020?project=project-b9257458-cea1-4ef8-876)
  visibly plots `temp_c` PSI 0.38333 above the red 0.20 significant-drift threshold; screenshot
  captured.

### Still required externally

- [x] Deliberately bad [pull request #1](https://github.com/XinyiChenxy/ML_Dep/pull/1) removed
  `temp_c`; the [Actions job](https://github.com/XinyiChenxy/ML_Dep/actions/runs/39986069085/job/120525462831?pr=1)
  recorded `test_schema_columns_present_and_typed` failing with
  `missing columns: ['temp_c']`. Close it without merging after preserving the screenshot.
- [x] `make teardown LAB=4` returned `[]`; `scripts/teardown_verify.py --lab 4` returned
  `PASS nothing found`, recorded in `reports/lab4-teardown.txt`.
- [x] GitHub `Scheduled drift detection` is `disabled_manually`, so its hourly cron cannot continue
  emitting metrics and Slack alerts.

**Current verdict:** CI blocking, WIF, gated CD, real managed deployment and smoke test, scheduled
drift, metric emission, real-channel alert, dashboard, disabled cron and cloud teardown evidence
all pass.

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
- [x] Real GCP quota refusal recorded in `reports/lab5/quota-blocker.txt`; every listed Vertex region
  has an effective limit of 1 CPU and quota eligibility is `NOT_ENOUGH_USAGE_HISTORY`.
- [x] Controlled IAM experiment recorded in `reports/lab5/iam-removal.txt`: the serving identity
  read the registered artifact, lost bucket `objectViewer`, received HTTP 403
  `storage.objects.get denied`, regained the role and read successfully. Temporary impersonation
  permission was removed and final IAM state was verified.
- [x] Final `make teardown LAB=5` deleted the paused weekly schedule; immediate verification found
  no remaining tagged Lab 5 Custom Job, Endpoint or Schedule.
- [x] Live Vertex `global` evaluation uses `gemini-3.5-flash-lite`, records provider candidate and
  thinking tokens, passes all 12 cases, and reports 1,816 ms p95 plus 4.7855 THB/1,000 requests at
  the course planning rate. Earlier regional/model 404s and the successful resolution are recorded
  in `reports/lab5/llm-access-blocker.txt`.

### Still required externally

- [ ] Build enough GCP usage history, obtain at least 4 custom-training CPUs in one region and
  complete a successful managed pipeline run.
- [x] Run the IAM removal experiment and preserve successful read → permission removal → 403 →
  restoration output.
- [ ] Demonstrate AWS upload/download/invoke against a real second account.
- [ ] Standard usage cost export is enabled and its managed writer is present. After the first
  provider load creates a table, run `make billing-export` and replace pending actual-cost fields.
- [x] Run the live LLM evaluation with provider-reported token fields and preserve the passing gate.
- [x] Delete the paused schedule and every remaining tagged Lab 5 resource; immediate verification
  returned `PASS nothing found`. Repeat the same check after 24 hours for final delayed-deletion
  assurance.

**Current verdict:** local logic, IAM failure evidence, negative and live-positive LLM gates, and
teardown pass; managed acceptance remains blocked only by account-owned training quota,
second-cloud and billing-export requirements.

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
