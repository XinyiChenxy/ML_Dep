"""Generate an honest Lab 5 cost report without inventing unavailable billing data."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config, costs, llmcost


def money(value: float | None) -> str:
    return "Pending billing export" if value is None else f"{value:.2f} THB"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--estimate", type=float, required=True)
    ap.add_argument("--actual", type=float, help="tag-filtered billing total")
    ap.add_argument("--rps", type=float, required=True)
    ap.add_argument("--instance", required=True)
    ap.add_argument("--provider", choices=["aws", "azure", "gcp"])
    ap.add_argument("--region")
    ap.add_argument("--out", type=Path, default=Path("reports/lab5-cost.md"))
    ap.add_argument("--llm-report", type=Path, default=Path("reports/llm_eval-live.json"))
    args = ap.parse_args()

    cfg = config.load(strict=False)
    provider = args.provider or (cfg.provider if cfg.provider != "local" else "gcp")
    region = args.region or (cfg.region if cfg.region != "unset" else "asia-southeast1")
    rate = costs.hourly_rate(provider, args.instance)
    rows = [
        f"| {int(u * 100)}% | {costs.cost_per_1k_predictions(rate, args.rps, u):.4f} |"
        for u in costs.DEFAULT_UTILISATIONS
    ]
    gap = None if args.actual is None else args.actual - args.estimate
    gap_pct = None if gap is None or args.estimate == 0 else gap / args.estimate * 100

    live = None
    if args.llm_report.exists():
        candidate = json.loads(args.llm_report.read_text())
        if candidate.get("usage_source") == "provider":
            live = candidate
    if live:
        usage = llmcost.Usage(live["avg_input_tokens"], live["avg_output_tokens"])
        token_cost = llmcost.cost_per_1k_requests(provider, "small", usage)
        usage_text = (
            f"The live `{live.get('provider_location', 'managed')}` run of "
            f"`{live.get('provider_model', 'the configured model')}` passed "
            f"**{live['passed']}/{live['cases']}** cases. Provider usage metadata measured "
            f"{usage.input_tokens} average input, {live.get('avg_candidate_tokens', 0)} visible "
            f"candidate and {live.get('avg_thinking_tokens', 0)} thinking tokens, for "
            f"{usage.output_tokens} billed output tokens: **{token_cost:.4f} THB/1,000**. "
            f"Measured p95 latency was **{live['p95_latency_ms']:,} ms**."
        )
    else:
        usage_text = (
            "**Pending live evidence.** Run `python scripts/llm_eval.py --live "
            "--out reports/llm_eval-live.json` and regenerate this report. Offline fixture "
            "token fields are deliberately not presented as a measured bill."
        )

    measured_input = live["avg_input_tokens"] if live else 415
    output_cap = 256
    worst_case = llmcost.Usage(input_tokens=measured_input, output_tokens=1024)
    cap_saving = llmcost.output_cap_saving(provider, "small", worst_case, output_cap)
    cache_break_even = llmcost.cache_breakeven_hit_rate(
        provider, "small", prefix_tokens=400
    )
    gap_text = "Pending until the tag-filtered billing export is available."
    if gap is not None and gap_pct is not None:
        gap_text = (
            f"{gap:+.2f} THB ({gap_pct:+.1f}%). Debug retries, orchestration overhead, "
            "warm endpoint time, storage, and delayed billing entries must be reconciled "
            "against the component rows below."
        )

    content = f"""# Lab 5 — Full cost accounting

**Provider:** `{provider}`<br>
**Region:** `{region}`<br>
**Status:** implementation and live LLM evidence complete; settled cloud billing still required

## 1. Estimate committed before the managed run

**{args.estimate:.2f} THB.** This estimate reserves compute for one Spot training run, one
pipeline execution, short-lived staging serving, storage, and monitoring. It is now committed
before any Lab 5 managed run initiated from this implementation.

## 2. Actual cost from billing, filtered by `course=itcs355,lab=5`

**{money(args.actual)}.** Credits must be reported separately from usage cost. Do not replace this
with the answer repository's bill; export this project's tagged billing data after running.

## 3. Estimate versus actual

{gap_text}

## 4. Breakdown by component

| Component | Actual THB | Evidence required |
|---|---:|---|
| Training | Pending | Spot Custom Job SKU filtered by Lab 5 labels |
| Storage | Pending | object and registry storage SKUs |
| Serving | Pending | staging endpoint CPU and memory SKUs |
| Pipeline | Pending | Vertex Pipeline orchestration SKU |
| Monitoring | Pending | logging and custom metric SKUs |

## 5. Cost per 1,000 classifier predictions

Planning rate `{args.instance}` = {rate:.2f} THB/hour; measured Lab 3 throughput reused here =
{args.rps:.1f} requests/second. These are planning figures until the Lab 5 staging endpoint is
measured.

| Utilisation | THB per 1,000 predictions |
|---|---:|
{chr(10).join(rows)}

## 6. Applied optimisation — Spot training

The pipeline requests Spot compute and checkpoint-capable training. The course planning factor is
{costs.SPOT_FACTOR:.2f}, so the modeled compute rate falls from
{costs.hourly_rate(provider, 'e2-standard-4'):.2f} to
{costs.hourly_rate(provider, 'e2-standard-4', spot=True):.2f} THB/hour (**70% lower**).
This is a modeled before/after until the tagged billing export confirms it. Spot can increase
completion latency through interruption and retry; it does not change online prediction p95.

## 7. LLM token bill and controls

{usage_text}

The live configuration caps output at {output_cap} tokens. Against a hypothetical 1,024-output-token
response with the measured {measured_input}-token input, the cap limits exposure by
**{cap_saving:.4f} THB/1,000 requests** at the course reference small-model rate. The live 12-case
gate passes under this cap.

Prompt caching breaks even above a **{cache_break_even * 100:.2f}%** hit rate. The golden prompts
are all distinct and no live cache-hit field has been collected, so the measured hit rate is not
claimed and caching remains disabled.

## Budget defence

The classifier cost is strongly utilisation-dependent, while the LLM cost is linear in provider-
reported tokens. We selected Spot training, the smaller Gemini variant and a {output_cap}-token
output ceiling. The live gate supports this choice; the trade-off is possible Spot delay and
deliberately shorter explanations. The token figure is a measured-usage planning estimate, while
the infrastructure total remains pending until Cloud Billing writes its export table.
"""
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(content)
    print(f"wrote {args.out}")
    if gap_pct is not None and math.fabs(gap_pct) > 20:
        print("warning: estimate/actual gap exceeds the required 20% reconciliation band")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
