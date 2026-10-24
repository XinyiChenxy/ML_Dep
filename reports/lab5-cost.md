# Lab 5 — Full cost accounting

**Provider:** `gcp`<br>
**Region:** `asia-southeast1` for ML workloads; `global` for Gemini<br>
**Status:** implementation, IAM failure experiment, live LLM gate and teardown complete;
account-owned managed-pipeline quota, billing export and second-provider evidence still required

## 1. Estimate committed before the managed run

**25.00 THB.** This estimate reserves compute for one Spot training run, one
pipeline execution, short-lived staging serving, storage, and monitoring. It is now committed
before any Lab 5 managed run initiated from this implementation.

## 2. Actual cost from billing, filtered by `course=itcs355,lab=5`

**Pending first billing load.** Standard usage cost export is enabled for the labeled US dataset
`project-b9257458-cea1-4ef8-876.itcs355_billing`; Google's managed billing writer is present. After
the provider creates its table, `make billing-export PROJECT_ID=project-b9257458-cea1-4ef8-876`
writes the tag-filtered CSV with credits separate from usage cost. Do not replace this with the
answer repository's bill.

## 3. Estimate versus actual

Pending until the tag-filtered billing export is available.

## 4. Breakdown by component

| Component | Actual THB | Evidence required |
|---|---:|---|
| Training | Pending | Spot Custom Job SKU filtered by Lab 5 labels |
| Storage | Pending | object and registry storage SKUs |
| Serving | Pending | staging endpoint CPU and memory SKUs |
| Pipeline | Pending | Vertex Pipeline orchestration SKU |
| Monitoring | Pending | logging and custom metric SKUs |

## 5. Cost per 1,000 classifier predictions

Planning rate `n1-standard-2` = 3.80 THB/hour; measured Lab 3 throughput reused here =
23.9 requests/second. These are planning figures until the Lab 5 staging endpoint is
measured.

| Utilisation | THB per 1,000 predictions |
|---|---:|
| 5% | 0.8833 |
| 25% | 0.1767 |
| 80% | 0.0552 |

## 6. Applied optimisation — Spot training

The pipeline requests Spot compute and checkpoint-capable training. The course planning factor is
0.30, so the modeled compute rate falls from
6.40 to
1.92 THB/hour (**70% lower**).
This is a modeled before/after until the tagged billing export confirms it. Spot can increase
completion latency through interruption and retry; it does not change online prediction p95.

## 7. LLM token bill and controls

The real Vertex `global` run used `gemini-3.5-flash-lite` and passed **12/12** cases. Provider usage
averaged **415 input tokens**, **37 billed output tokens** (37 visible candidate, 0 thinking), with
**1,816 ms p95 latency**. At the course-reference GCP small-model rates, this is
**4.7855 THB/1,000 requests**. `reports/llm_eval-live.json` is the machine-readable evidence; unlike
the fixture report, its `usage_source` is `provider`.

The live configuration caps total output at 256 tokens. A hypothetical uncapped 1,024-output-token
response at the measured 415-token input would cost **26.1120 THB/1,000 requests more** at the same
course planning rates. A 64/128-token cap was rejected because real 3.8-model probes exhausted the
budget on hidden reasoning and produced truncated JSON; the selected 3.5-lite model reported zero
thinking tokens and passed the gate at 256.

Prompt caching breaks even above a **21.74%** hit rate. The golden prompts
are all distinct and no live cache-hit field has been collected, so the measured hit rate is not
claimed and caching remains disabled.

## Budget defence

The classifier cost is strongly utilisation-dependent, while the LLM cost is linear in provider-
reported tokens. We selected Spot training, the smaller Gemini variant and a 256-token ceiling.
The live 12/12 gate supports that choice; the trade-off remains possible Spot delay and deliberately
short explanations. The 4.7855 THB figure is a measured-token planning estimate, not a settled
Cloud Billing export.
