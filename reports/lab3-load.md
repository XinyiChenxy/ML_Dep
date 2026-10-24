# Lab 3 — serving, load testing, and rollback

**Measured:** 2026-10-23 to 2026-10-24 (Asia/Bangkok)

**Evidence status:** managed endpoint, instance comparison, canary, rollback and teardown complete
**Predeclared SLO:** prediction p95 below **500 ms**, error rate below **1%**

The target above is encoded in `loadtest/k6.js`. The first section preserves the local baseline;
the managed sections report authenticated RawPredict calls against a real Vertex endpoint. Raw
measurements are committed in `lab3-cloud-load.json` and `lab3-cloud-load-large.json`.

## Managed Vertex endpoint

Vertex endpoint `4762602785432666112` served immutable registry version 1 in
`asia-southeast1`. Three smoke requests returned valid probability and model-version fields. The
fixed deployment used one minimum and maximum replica, so request scale-to-zero/cold-start latency
does not apply; initial endpoint provisioning took approximately 17 minutes.

### `n1-standard-2` managed results

| Concurrency | Requests | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) | Error rate |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 100 | 5.559 | 161.65 | 257.01 | 319.18 | 0.00% |
| 10 | 100 | 18.536 | 527.87 | 795.39 | 951.80 | 0.00% |
| 50 | 100 | 13.852 | 3,047.80 | 5,955.91 | 6,117.68 | 0.00% |

The managed breaking concurrency is **10**: this is the first level above the 500 ms p95 SLO. At
50, throughput falls by 25.3% from its concurrency-10 peak while p95 grows 7.5 times, indicating
queueing rather than useful capacity. All 300 requests completed successfully.

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

The same immutable model, endpoint, payloads and request counts were repeated on the next larger
`n1-standard-4` instance.

| Instance / concurrency | Throughput (req/s) | p95 (ms) | Error rate | Planning THB/hour | THB/1,000 at measured throughput |
|---|---:|---:|---:|---:|---:|
| `n1-standard-2` / 10 | 18.536 | 795.39 | 0.00% | 3.80 | 0.05695 |
| `n1-standard-4` / 10 | 22.214 | 681.85 | 0.00% | 7.60 | 0.09504 |

The larger instance improved throughput **19.84%** and reduced p95 **14.27%**, but its projected
cost per 1,000 increased **66.89%** and it still missed the 500 ms SLO. It is therefore not the
preferred steady-state size for this low-volume workload. The hourly values use the course planning
rate (the larger machine is exactly twice the vCPU/RAM); actual billing export may post later.

## Canary and rollback

`scripts/build_canary_model.py` created a deliberately weak but contract-compatible model. Its
offline test ROC-AUC was 0.7188 versus 0.8384 for the controlled local stable model. It was uploaded
with lineage and registered as immutable Vertex version 2.

- Rollout recorded at **2026-10-24 04:55:46 UTC**: deployed v1 ID `2250948791685349376` = 90%,
  v2 ID `2811083995339554816` = 10%, unused larger v1 deployment = 0%.
- The 1,200-row check intentionally ignored `model_version`. Stable ROC-AUC/PR-AUC were
  0.906514/0.654717; the 90/10 endpoint fell to 0.901887/0.650931.
- Degradation was measured at **04:56:47 UTC**, 61 seconds after the recorded split.
- Rollback completed at **04:57:11 UTC**: v1 = 100%, v2 = 0%, larger v1 = 0%.
- A post-rollback blind check returned exactly 0.906514/0.654717, confirming restoration.

Machine-readable provider states are in `lab3-canary-rollout.json` and
`lab3-canary-rollback.json`; quality results are in `lab3-canary-quality.json` and
`lab3-post-rollback-quality.json`. A 50/50 split would collect bad-version evidence faster but
expose five times as much traffic, so 90/10 was retained.

## Cost per 1,000 predictions

Planning rate: **3.80 THB/hour** for `n1-standard-2`. Using the real managed peak of
18.536 requests/second gives:

`THB/1,000 = 3.80 / (14.23 × 3,600 × utilisation) × 1,000`

| Assumed utilisation | Projected THB/1,000 |
|---:|---:|
| 5% | 1.1389 |
| 25% | 0.2278 |
| 80% | 0.0712 |

The denominator is now measured managed throughput, while the numerator remains the course planning
rate rather than a settled invoice. A continuously warm endpoint at that rate costs 91.20 THB/day;
batch inference is cheaper whenever its daily compute, startup, storage and orchestration total is
below that amount.

## Teardown status

At the end of the exercise `make teardown LAB=3` undeployed all three deployed models and deleted
endpoint `4762602785432666112`. A provider query filtered to `labels.lab=3` returned `[]`; the
captured command output is in `lab3-teardown.txt`. No Lab 3 online compute remains running.
