"""Launch the checkpoint-capable Lab 5 training step on Spot compute."""
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
    },
)
result = adapter.wait_training(job_id)
if result["state"] not in {"JOB_STATE_SUCCEEDED", "PIPELINE_STATE_SUCCEEDED"}:
    raise RuntimeError(f"Spot training failed: {result['state']}")
print(f"Spot training completed: {job_id}")
