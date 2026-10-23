import json
from types import SimpleNamespace

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
