# Lab 5 — Full cost accounting

**Provider:** `gcp`<br>
**Region:** `asia-southeast1`<br>
**Status:** local implementation complete; cloud billing evidence still required

## 1. Estimate committed before the managed run

**25.00 THB.** This estimate reserves compute for one Spot training run, one
pipeline execution, short-lived staging serving, storage, and monitoring. It is now committed
before any Lab 5 managed run initiated from this implementation.

## 2. Actual cost from billing, filtered by `course=itcs355,lab=5`

**Pending billing export.** Credits must be reported separately from usage cost. Do not replace this
with the answer repository's bill; export this project's tagged billing data after running.

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

**Pending live evidence.** Run `python scripts/llm_eval.py --live --out reports/llm_eval-live.json` and regenerate this report. Offline fixture token fields are deliberately not presented as a measured bill.

The live configuration caps output at 64 tokens. Against a 200-output-token worst case with a
420-token input, the cap limits exposure by **4.6240 THB/1,000 requests** at the course
reference small-model rate. The 12-case offline gate passes with concise responses under this cap;
the live gate must also pass before this is claimed as a production saving.

Prompt caching breaks even above a **21.74%** hit rate. The golden prompts
are all distinct and no live cache-hit field has been collected, so the measured hit rate is not
claimed and caching remains disabled.

## Budget defence

The classifier cost is strongly utilisation-dependent, while the LLM cost is linear in provider-
reported tokens. We selected Spot training and a 64-token output ceiling, but will not claim an
actual per-1,000 LLM price until a live response supplies token usage metadata. The trade-off is
possible Spot delay and deliberately shorter explanations; the regression gate protects the four
critical behaviours before that cheaper configuration can ship.
