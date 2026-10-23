"""Launch the checkpoint-capable Lab 5 training step on Spot compute."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudlayer.factory import get_adapter
from src import config

cfg = config.load()
adapter = get_adapter(cfg)
job_id = adapter.submit_training(
    cfg.training_image_uri,
    {
        "_lab": 5,
        "upload_artifacts": True,
        "artifact_prefix": "lab5",
        "experiment": "itcs355-lab5",
        "metrics_out": "/app/reports/metrics.json",
        "instance": "n1-standard-1",
    },
)
result = adapter.wait_training(job_id)
if result["state"] not in {"JOB_STATE_SUCCEEDED", "PIPELINE_STATE_SUCCEEDED"}:
    raise RuntimeError(f"Spot training failed: {result['state']}")
print(f"Spot training completed: {job_id}")
