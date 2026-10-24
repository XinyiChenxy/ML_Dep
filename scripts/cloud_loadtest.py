"""Authenticated concurrent load test for a managed endpoint through the cloud adapter."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudlayer.factory import get_adapter
from src import config


PAYLOAD = {
    "temp_c": 78.4,
    "vibration_mm_s": 3.1,
    "pressure_kpa": 315.2,
    "hours_since_service": 4200.0,
    "load_pct": 68.0,
    "ambient_humidity": 55.0,
}


def measure(adapter, endpoint: str, concurrency: int, requests: int) -> dict:
    latencies: list[float] = []
    errors: list[str] = []

    def invoke_once() -> float:
        started = time.perf_counter()
        result = adapter.invoke(endpoint, PAYLOAD)
        if "probability" not in result or "model_version" not in result:
            raise ValueError("response omitted probability or model_version")
        return (time.perf_counter() - started) * 1000

    wall_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(invoke_once) for _ in range(requests)]
        for future in as_completed(futures):
            try:
                latencies.append(future.result())
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
    wall_seconds = time.perf_counter() - wall_started

    def percentile(pct: float) -> float | None:
        return round(float(np.percentile(latencies, pct)), 2) if latencies else None

    return {
        "concurrency": concurrency,
        "requests": requests,
        "successful": len(latencies),
        "errors": len(errors),
        "error_rate": round(len(errors) / requests, 6),
        "throughput_rps": round(requests / wall_seconds, 3),
        "p50_ms": percentile(50),
        "p95_ms": percentile(95),
        "p99_ms": percentile(99),
        "wall_seconds": round(wall_seconds, 3),
        "sample_errors": errors[:3],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default=os.environ.get("ENDPOINT_RESOURCE"))
    parser.add_argument("--concurrency", nargs="+", type=int, default=[1, 10, 50])
    parser.add_argument("--requests-per-level", type=int, default=100)
    parser.add_argument("--out", type=Path, default=Path("reports/lab3-cloud-load.json"))
    args = parser.parse_args()
    if not args.endpoint:
        parser.error("--endpoint or ENDPOINT_RESOURCE is required")
    if args.requests_per_level < max(args.concurrency):
        parser.error("requests per level must be at least the largest concurrency")

    cfg = config.load()
    adapter = get_adapter(cfg)
    results = [
        measure(adapter, args.endpoint, level, args.requests_per_level)
        for level in args.concurrency
    ]
    report = {
        "endpoint": args.endpoint,
        "provider": cfg.provider,
        "region": cfg.region,
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 1 if any(row["errors"] for row in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
