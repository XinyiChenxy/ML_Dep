"""Offline proof of the three AWS methods required by the Lab 5 provider swap."""
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from cloudlayer.factory import get_adapter


class FakeS3:
    def __init__(self):
        self.objects = {}

    def upload_file(self, local_path, bucket, key):
        self.objects[(bucket, key)] = Path(local_path).read_bytes()

    def download_file(self, bucket, key, local_path):
        Path(local_path).write_bytes(self.objects[(bucket, key)])


def test_aws_upload_and_download_without_application_changes(tmp_path, monkeypatch):
    s3 = FakeS3()
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *a, **k: s3))
    cfg = SimpleNamespace(provider="aws", blob_uri="s3://portable/lab5", region="us-east-1")
    adapter = get_adapter(cfg)
    source = tmp_path / "probe.txt"
    target = tmp_path / "nested" / "back.txt"
    source.write_text("portability probe\n")
    uri = adapter.upload(str(source), "probe/source.txt")
    adapter.download(uri, str(target))
    assert uri == "s3://portable/lab5/probe/source.txt"
    assert target.read_bytes() == source.read_bytes()


def test_aws_invoke_normalizes_sagemaker_response(monkeypatch):
    class FakeRuntime:
        def invoke_endpoint(self, **kwargs):
            assert kwargs["EndpointName"] == "lab5-endpoint"
            assert json.loads(kwargs["Body"]) == {"rows": [[1, 2]]}
            return {"Body": io.BytesIO(b'{"predictions": [0.87]}')}

    monkeypatch.setitem(
        sys.modules,
        "boto3",
        SimpleNamespace(client=lambda *a, **k: FakeRuntime()),
    )
    adapter = get_adapter(SimpleNamespace(provider="aws", region="us-east-1"))
    assert adapter.invoke("lab5-endpoint", {"rows": [[1, 2]]}) == {
        "predictions": [0.87]
    }


def test_factory_swaps_provider_without_layer_one_change():
    assert type(get_adapter(SimpleNamespace(provider="aws"))).__name__ == "AwsAdapter"
    assert type(get_adapter(SimpleNamespace(provider="gcp"))).__name__ == "GcpAdapter"
