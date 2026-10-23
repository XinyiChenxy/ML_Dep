import json
import sys
import urllib.request

import pandas as pd
import pytest

from monitoring.drift import ALERT_THRESHOLD, compare, main, psi
from src.data import FEATURES


def test_psi_is_zero_for_identical_windows():
    values = pd.Series(range(100), dtype=float).to_numpy()
    assert psi(values, values) == pytest.approx(0.0)


def test_injected_shift_crosses_justified_threshold():
    reference = pd.DataFrame({"temp_c": list(range(100))})
    current = pd.DataFrame({"temp_c": [value + 30 for value in range(100)]})
    result = compare(reference, current, ["temp_c"])[0]
    assert result.psi >= ALERT_THRESHOLD
    assert result.verdict == "significant"


def test_missing_feature_is_treated_as_pipeline_breakage():
    reference = pd.DataFrame({"temp_c": [1.0, 2.0]})
    with pytest.raises(ValueError, match="missing required features"):
        compare(reference, pd.DataFrame({"other": [1.0, 2.0]}), ["temp_c"])


def test_delivered_drift_alert_is_a_successful_run(tmp_path, monkeypatch):
    reference = pd.DataFrame({feature: range(100) for feature in FEATURES})
    current = reference.copy()
    current["temp_c"] += 30
    reference_path = tmp_path / "reference.csv"
    current_path = tmp_path / "current.csv"
    reference.to_csv(reference_path, index=False)
    current.to_csv(current_path, index=False)
    captured = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def urlopen(request, timeout):
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(sys, "argv", [
        "monitoring.drift",
        "--reference", str(reference_path),
        "--current", str(current_path),
        "--out", str(tmp_path / "drift.json"),
        "--webhook-url", "https://hooks.example.invalid/test",
    ])

    assert main() == 0
    assert "temp_c" in captured["payload"]["text"]
    assert captured["timeout"] == 10
