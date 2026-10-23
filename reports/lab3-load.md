# Lab 3 — serving, load testing, and rollback

**Measured:** 2026-10-23 (Asia/Bangkok)  
**Evidence status:** local baseline complete; managed-endpoint and rollback evidence pending  
**Predeclared SLO:** prediction p95 below **500 ms**, error rate below **1%**

The target above is encoded in `loadtest/k6.js`. These measurements use the same FastAPI service
and exported model on localhost, not a managed Vertex endpoint. They are useful engineering evidence,
but they do not replace the cloud deployment, instance comparison, or timestamped traffic-split
evidence required by the handout.

## Test configuration

- Python 3.13.11 and Uvicorn, one process
- 12th Gen Intel Core i7-12700K; 20 logical CPUs visible
- Model version `local-baseline`, loaded once during FastAPI startup
- 300 POST requests per concurrency level, persistent HTTP client
- Payload: six valid sensor features; no think time

## Concurrency results

| Concurrency | Requests | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) | Error rate |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 300 | 14.23 | 74.42 | 81.97 | 83.71 | 0.00% |
| 10 | 300 | 13.90 | 711.61 | 943.12 | 1,056.12 | 0.00% |
| 50 | 300 | 13.11 | 3,817.07 | 4,240.63 | 4,393.54 | 0.00% |

The local configuration meets the 500 ms p95 target only at concurrency 1. The observed breaking
concurrency is therefore **10**: throughput has already flattened around 14 requests/second and
additional concurrency becomes queueing latency rather than useful capacity. Cold-start latency was
not measured because this local process does not scale to zero; a scale-to-zero cloud deployment
must report it separately.

## Batch-size finding

One hundred sequential `/predict` calls took **7,060.97 ms**. One `/predict/batch` request containing
the same 100 rows took **86.64 ms**, an **81.50×** wall-clock speedup with HTTP 200. Batching removes
99 HTTP and validation round trips and lets the model score one frame. This is not a quality result;
the service tests separately assert that batch probabilities equal the corresponding single calls.

## Payload-size finding

The same JSON values were sent as a compact 120-byte body and a whitespace-padded 1,333-byte body.

| Body | Bytes | p50 (ms) | p95 (ms) |
|---|---:|---:|---:|
| Compact | 120 | 74.61 | 82.31 |
| Whitespace-padded | 1,333 | 75.42 | 82.43 |

At 11.1× the payload size, p95 increased only 0.12 ms; model inference dominates at this scale.
The Pydantic contract forbids unrelated fields, so a larger semantic payload requires an explicit
schema change rather than silently accepting junk data.

## Instance-size finding

**Pending managed evidence.** The required comparison between `n1-standard-2` and one larger
instance has not been run. Local CPU measurements cannot be presented as an instance-size or cloud
cost comparison. Record both endpoint p95 and the provider SKU price here after quota permits a
short-lived deployment, then delete both deployments.

## Canary and rollback

**Pending managed evidence.** `scripts/canary_quality_check.py` measures degradation without reading
model-version labels, and the adapter supports managed deployment. The required 90/10 split,
detection timestamp, rollback timestamp, and provider metric screenshot have not been produced.
Do not claim Lab 3 acceptance until those timestamped artifacts show traffic genuinely moved.

Planned five-line interpretation after the real run:

1. Metric revealing degradation: test-window ROC-AUC/PR-AUC from unlabeled traffic samples.
2. Detection time: pending timestamped run.
3. Faster detection: increase labeled canary samples without raising bad-version exposure.
4. At 50/50, detection would be faster but five times as much traffic would see the weaker model.
5. Rollback evidence: pending managed endpoint traffic-split history.

## Cost per 1,000 predictions

Planning rate: **3.80 THB/hour** for `n1-standard-2`. Reusing the measured local capacity of
14.23 requests/second only as a projection gives:

`THB/1,000 = 3.80 / (14.23 × 3,600 × utilisation) × 1,000`

| Assumed utilisation | Projected THB/1,000 |
|---:|---:|
| 5% | 1.4836 |
| 25% | 0.2967 |
| 80% | 0.0927 |

This is not a billed cloud figure because the denominator is local throughput. A continuously warm
endpoint at that planning rate costs 91.20 THB/day; batch inference is cheaper whenever its daily
compute, startup, storage, and orchestration total stays below 91.20 THB. The exact request-volume
break-even remains pending the real batch SKU and managed throughput, and must not be invented.

## Teardown status

The local Uvicorn process was stopped immediately after measurement. The current GCP safety check
found no Vertex Custom Jobs and no Vertex Endpoints; the Lab 5 pipeline schedule remains paused.
After the required Lab 3 cloud exercise, run `make teardown LAB=3` and capture the empty endpoint
list before marking this deliverable complete.
