"""Register the gated candidate with lineage from its metrics payload."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudlayer.factory import get_adapter
from src import config

cfg = config.load()
adapter = get_adapter(cfg)
metrics_path = Path("/tmp/lab5-metrics.json")
adapter.download(
    f"{cfg.blob_uri.rstrip('/')}/lab5/metrics/metrics.json",
    str(metrics_path),
)
metrics = json.loads(metrics_path.read_text())
model_file = metrics["model_uri"]
model_dir = model_file.rsplit("/", 1)[0]
version = adapter.register_model(
    model_dir,
    cfg.model_registry_name,
)
version_path = Path("/tmp/lab5-model-version.txt")
version_path.write_text(str(version))
print(adapter.upload(str(version_path), "lab5/model-version.txt"))
