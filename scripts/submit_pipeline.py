"""Submit the compiled Vertex pipeline only when --run is explicitly supplied."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google.cloud import aiplatform
import yaml

from src import config

parser = argparse.ArgumentParser()
parser.add_argument("--run", action="store_true", help="incurs cloud charges")
parser.add_argument("--schedule", action="store_true", help="create the weekly schedule paused")
args = parser.parse_args()
if args.run and args.schedule:
    parser.error("choose either --run or --schedule")
cfg = config.load()
service_account = cfg.identity_ref
if not service_account:
    raise ValueError("IDENTITY_REF must name the dedicated pipeline service account")
aiplatform.init(project=cfg.project_id, location=cfg.region)
job = aiplatform.PipelineJob(
    display_name="itcs355-lab5-pipeline",
    template_path="pipeline/lab5-pipeline.json",
    pipeline_root=f"{cfg.blob_uri.rstrip('/')}/lab5/pipeline-root",
    labels=cfg.tags(5),
    enable_caching=False,
)
if args.run:
    job.submit(service_account=service_account)
    print(f"submitted {job.resource_name}")
elif args.schedule:
    spec = yaml.safe_load(Path("pipeline/pipeline.yaml").read_text())
    schedule = aiplatform.PipelineJobSchedule(
        pipeline_job=job,
        display_name="itcs355-lab5-weekly",
    )
    schedule.create(
        cron=spec["schedule"],
        max_concurrent_run_count=1,
        service_account=service_account,
    )
    schedule.pause()
    print(f"created and paused {schedule.resource_name}")
else:
    print("configuration validated; pass --run or --schedule for a cloud mutation")
