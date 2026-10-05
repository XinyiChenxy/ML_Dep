"""Small Prometheus-compatible metrics registry for the inference service."""
from __future__ import annotations

import math
import threading
from collections import Counter, defaultdict, deque

LATENCY_BUCKETS_MS = (25, 50, 100, 250, 500, 1000, 2500, 5000, math.inf)
_lock = threading.Lock()
_requests: Counter[str] = Counter()
_latencies: deque[float] = deque(maxlen=4096)
_features: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=1000))


def observe_request(status_code: int, latency_ms: float) -> None:
    status_class = f"{status_code // 100}xx"
    with _lock:
        _requests[status_class] += 1
        _latencies.append(latency_ms)


def observe_features(rows: list[dict]) -> None:
    with _lock:
        for row in rows:
            for name, value in row.items():
                _features[name].append(float(value))


def render_prometheus(model_version: str) -> str:
    lines = [
        "# HELP http_requests_total HTTP requests split by status class.",
        "# TYPE http_requests_total counter",
    ]
    with _lock:
        for status_class in ("2xx", "3xx", "4xx", "5xx"):
            lines.append(
                f'http_requests_total{{status_class="{status_class}"}} {_requests[status_class]}'
            )
        lines.extend([
            "# HELP request_latency_ms Request latency histogram in milliseconds.",
            "# TYPE request_latency_ms histogram",
        ])
        for bucket in LATENCY_BUCKETS_MS:
            label = "+Inf" if math.isinf(bucket) else str(bucket)
            count = sum(value <= bucket for value in _latencies)
            lines.append(f'request_latency_ms_bucket{{le="{label}"}} {count}')
        lines.append(f"request_latency_ms_count {len(_latencies)}")
        lines.append(f"request_latency_ms_sum {sum(_latencies):.6f}")
        lines.extend([
            "# HELP feature_rolling_mean Rolling mean of recent inference features.",
            "# TYPE feature_rolling_mean gauge",
        ])
        for feature, values in sorted(_features.items()):
            if values:
                lines.append(
                    f'feature_rolling_mean{{feature="{feature}"}} {sum(values) / len(values):.8f}'
                )
    safe_version = model_version.replace('"', "")
    lines.extend([
        "# HELP model_version_info Currently loaded model version.",
        "# TYPE model_version_info gauge",
        f'model_version_info{{version="{safe_version}"}} 1',
    ])
    return "\n".join(lines) + "\n"
