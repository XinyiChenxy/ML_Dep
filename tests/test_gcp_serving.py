import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

from google.cloud import aiplatform
from google.cloud import monitoring_v3

from cloudlayer.gcp import GcpAdapter


def config():
    return SimpleNamespace(
        project_id="test-project",
        region="asia-southeast1",
        llm_model="gemini-test",
        llm_location="global",
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


def test_teardown_passes_custom_job_filter_in_request(monkeypatch):
    client = Mock()
    client.list_custom_jobs.return_value = []
    adapter = GcpAdapter(config())
    monkeypatch.setattr(adapter, "_client", lambda _: client)
    monkeypatch.setattr(aiplatform, "init", lambda **_: None)
    monkeypatch.setattr(aiplatform.Endpoint, "list", lambda: [])
    monkeypatch.setattr(aiplatform.PipelineJobSchedule, "list", lambda: [])

    assert adapter.teardown({"course": "itcs355", "lab": "4"}) == []
    client.list_custom_jobs.assert_called_once_with(request={
        "parent": "projects/test-project/locations/asia-southeast1",
        "filter": 'labels.course="itcs355" AND labels.lab="4"',
    })


def test_endpoint_traffic_and_rollback_update(monkeypatch):
    deployed = [
        SimpleNamespace(id="stable", model="models/7@1", display_name="stable-v1"),
        SimpleNamespace(id="canary", model="models/7@2", display_name="canary-v2"),
    ]
    resource = SimpleNamespace(
        deployed_models=deployed,
        traffic_split={"stable": 90, "canary": 10},
    )
    endpoint = SimpleNamespace(
        resource_name="projects/test/locations/test/endpoints/3",
        gca_resource=resource,
        update=Mock(),
    )
    adapter = GcpAdapter(config())
    monkeypatch.setattr(adapter, "_endpoint", lambda _: endpoint)

    assert adapter.endpoint_traffic("itcs355-lab3") == [
        {
            "id": "stable",
            "model": "models/7@1",
            "display_name": "stable-v1",
            "traffic_percentage": 90,
        },
        {
            "id": "canary",
            "model": "models/7@2",
            "display_name": "canary-v2",
            "traffic_percentage": 10,
        },
    ]

    adapter.set_endpoint_traffic("itcs355-lab3", {"stable": 100, "canary": 0})
    endpoint.update.assert_called_once_with(
        traffic_split={"stable": 100, "canary": 0}
    )


def test_traffic_split_validation_rejects_bad_or_unknown_ids():
    try:
        GcpAdapter._validate_traffic_split({"stable": 90}, {"stable"})
    except ValueError as exc:
        assert "total 100" in str(exc)
    else:
        raise AssertionError("invalid total was accepted")

    try:
        GcpAdapter._validate_traffic_split(
            {"stable": 90, "unknown": 10}, {"stable", "canary"}
        )
    except ValueError as exc:
        assert "Unknown deployed model IDs" in str(exc)
    else:
        raise AssertionError("unknown deployed model ID was accepted")


def test_generate_uses_process_only_gemini_key(monkeypatch):
    """The API-key fallback reports provider usage and never needs cloud.env."""
    from google import genai

    captured = {}

    class FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                text='{"decision":"no_action","rationale":"0.04"}',
                usage_metadata=SimpleNamespace(
                    prompt_token_count=31,
                    candidates_token_count=12,
                    thoughts_token_count=7,
                ),
            )

    class FakeClient:
        def __init__(self, api_key, http_options):
            captured["api_key"] = api_key
            captured["http_options"] = http_options
            self.models = FakeModels()

    monkeypatch.setenv("GEMINI_API_KEY", "ephemeral-test-key")
    monkeypatch.setattr(genai, "Client", FakeClient)
    result = GcpAdapter(config()).generate("decide", {
        "temperature": 0.0,
        "max_output_tokens": 64,
        "response_mime_type": "application/json",
    })

    assert captured == {
        "api_key": "ephemeral-test-key",
        "http_options": {
            "timeout": 60_000,
            "retry_options": {"attempts": 2},
        },
        "model": "gemini-test",
        "contents": "decide",
        "config": {
            "temperature": 0.0,
            "max_output_tokens": 64,
            "response_mime_type": "application/json",
        },
    }
    assert result["input_tokens"] == 31
    assert result["output_tokens"] == 19
    assert result["candidate_tokens"] == 12
    assert result["thinking_tokens"] == 7
    assert result["response"].startswith("{")
