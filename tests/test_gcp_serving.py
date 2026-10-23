import json
from datetime import datetime
from types import SimpleNamespace

from google.cloud import monitoring_v3

from cloudlayer.gcp import GcpAdapter


def config():
    return SimpleNamespace(
        project_id="test-project",
        region="asia-southeast1",
    )


def test_raw_predict_preserves_provider_neutral_service_contract(monkeypatch):
    captured = {}

    class Client:
        def raw_predict(self, *, endpoint, http_body):
            captured["endpoint"] = endpoint
            captured["content_type"] = http_body.content_type
            captured["payload"] = json.loads(http_body.data)
            return SimpleNamespace(
                data=b'{"probability": 0.42, "model_version": "run-123"}'
            )

    adapter = GcpAdapter(config())
    monkeypatch.setattr(adapter, "_client", lambda _: Client())
    result = adapter.invoke("endpoint-7", {"temp_c": 78.4})

    assert captured == {
        "endpoint": (
            "projects/test-project/locations/asia-southeast1/endpoints/endpoint-7"
        ),
        "content_type": "application/json",
        "payload": {"temp_c": 78.4},
    }
    assert result == {"probability": 0.42, "model_version": "run-123"}


def test_endpoint_lab_label_matches_its_name():
    assert GcpAdapter._lab_from_endpoint("itcs355-lab3") == 3
    assert GcpAdapter._lab_from_endpoint("itcs355-lab4-staging") == 4
    assert GcpAdapter._lab_from_endpoint("itcs355-lab5-staging") == 5
    assert GcpAdapter._lab_from_endpoint("custom-endpoint") == 3


def test_emit_metric_uses_supported_timestamp(monkeypatch):
    captured = {}

    class Client:
        def create_time_series(self, *, name, time_series):
            captured["name"] = name
            captured["series"] = time_series[0]

    monkeypatch.setattr(monitoring_v3, "MetricServiceClient", Client)
    GcpAdapter(config()).emit_metric("drift.psi.temp_c", 0.38333)

    assert captured["name"] == "projects/test-project"
    assert captured["series"].metric.type == (
        "custom.googleapis.com/itcs355/drift/psi/temp_c"
    )
    end_time = captured["series"].points[0].interval.end_time
    assert isinstance(end_time, datetime)
    assert end_time.tzinfo is not None
