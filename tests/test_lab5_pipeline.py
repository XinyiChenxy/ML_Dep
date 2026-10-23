"""Lab 5 pipeline and metric-gate contracts, with no cloud calls."""
import json
import subprocess
import sys
from pathlib import Path

from cloudlayer.pipelines import compile_gcp, load_spec

ROOT = Path(__file__).resolve().parents[1]


def test_metric_gate_can_fail_and_emit_pipeline_decision(tmp_path):
    metrics = tmp_path / "metrics.json"
    metrics.write_text(json.dumps({"test_roc_auc": 0.70}))
    command = [
        sys.executable,
        str(ROOT / "scripts" / "evaluation_gate.py"),
        "--metrics",
        str(metrics),
    ]
    assert subprocess.run(command, capture_output=True, text=True).returncode == 1

    decision = tmp_path / "decision.txt"
    result = subprocess.run(
        [*command, "--decision-out", str(decision)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert decision.read_text() == "fail"


def test_gcp_pipeline_contains_real_registration_condition(tmp_path, monkeypatch):
    values = {
        "CLOUD_PROVIDER": "gcp",
        "PROJECT_ID": "itcs355-test",
        "REGION": "asia-southeast1",
        "BLOB_URI": "gs://itcs355-test/lab5",
        "CONTAINER_REGISTRY": "registry.invalid/itcs355",
        "MLFLOW_TRACKING_URI": "https://mlflow.invalid",
        "MODEL_REGISTRY_NAME": "itcs355-test",
        "IDENTITY_REF": "lab5-pipeline@example.invalid",
        "TRAINING_IMAGE_URI": "registry.invalid/train@sha256:" + "a" * 64,
        "SERVING_IMAGE_URI": "registry.invalid/serve@sha256:" + "b" * 64,
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.chdir(tmp_path)
    output = compile_gcp(load_spec())
    payload = json.loads(output.read_text())
    rendered = json.dumps(payload)
    assert "candidate-passed-evaluation" in rendered
    assert "== 'pass'" in rendered
    assert "lab5-register" in rendered
    assert "lab5-deploy-staging" in rendered
    assert rendered.count('"cpuLimit": 1.0') == 6
