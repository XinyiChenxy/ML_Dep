"""GCP adapter. Implement upload/download/push_image for Lab 1.

SDK:  pip install google-cloud-storage google-cloud-aiplatform
Docs: storage.Client for GCS; Artifact Registry push goes through `docker push` after
      `gcloud auth configure-docker <region>-docker.pkg.dev`.

Hints for Lab 1:
  * BLOB_URI looks like gs://bucket/prefix — parse it here, never in src/.
  * Artifact Registry paths are region-scoped:
        <region>-docker.pkg.dev/<project>/<repo>/<image>
    A common first failure is pushing to gcr.io out of habit; it is a different service.
  * push_image must return the digest reference, not the tag.
  * GCP calls them labels, not tags, and they must be lowercase with no spaces.
    cfg.tags(1) already satisfies that constraint — do not "improve" the values.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from google.cloud import storage
from google.cloud import aiplatform

from cloudlayer.base import CloudAdapter
from google.cloud.aiplatform_v1.types import custom_job as gca_custom_job


class GcpAdapter(CloudAdapter):
    def upload(self, local_path: str, key: str) -> str:
        blob_uri = self.cfg.blob_uri
        bucket_name, prefix = blob_uri.removeprefix("gs://").split("/", 1)

        client = storage.Client(project=self.cfg.project_id)
        bucket = client.bucket(bucket_name)

        object_name = f"{prefix.rstrip('/')}/{key.lstrip('/')}"
        blob = bucket.blob(object_name)
        blob.upload_from_filename(local_path)

        return f"gs://{bucket_name}/{object_name}"

    def download(self, uri: str, local_path: str) -> None:
        bucket_name, object_name = uri.removeprefix("gs://").split("/", 1)

        client = storage.Client(project=self.cfg.project_id)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)

        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(local_path)

    def push_image(self, local_tag: str) -> str:
        registry = self.cfg.container_registry.rstrip("/")
        image_name = local_tag.split(":")[0]
        image_tag = local_tag.rsplit(":", 1)[1]

        remote_tag = f"{registry}/{image_name}:{image_tag}"

        subprocess.run(
            ["docker", "tag", local_tag, remote_tag],
            check=True,
        )

        subprocess.run(
            ["docker", "push", remote_tag],
            check=True,
        )

        result = subprocess.run(
            ["docker", "inspect", "--format={{index .RepoDigests 0}}", remote_tag],
            check=True,
            capture_output=True,
            text=True,
        )

        return result.stdout.strip()

    def submit_training(self, image_uri: str, args: dict) -> str:
        aiplatform.init(
            project=self.cfg.project_id,
            location=self.cfg.region,
        )

        job = aiplatform.CustomContainerTrainingJob(
            display_name="itcs355-lab2-training",
            container_uri=image_uri,
            staging_bucket=f"gs://{self.cfg.project_id}",
            labels=self.cfg.tags(2),
        )

        job.run(
            args=[f"--{k.replace('_', '-')}={v}" for k, v in args.items()],
            machine_type="e2-standard-4",
            replica_count=1,
            scheduling_strategy=gca_custom_job.Scheduling.Strategy.SPOT,
            environment_variables={
                "CLOUD_PROVIDER": self.cfg.provider,
                "PROJECT_ID": self.cfg.project_id,
                "REGION": self.cfg.region,
                "BLOB_URI": self.cfg.blob_uri,
                "CONTAINER_REGISTRY": self.cfg.container_registry,
                "MLFLOW_TRACKING_URI": "sqlite:////app/reports/mlflow.db",
                "MODEL_REGISTRY_NAME": self.cfg.model_registry_name,
                "IDENTITY_REF": self.cfg.identity_ref,
            },
            sync=False,
        )

        job.wait_for_resource_creation()

        return job.resource_name

    def wait_training(self, job_id: str) -> dict:
        from google.cloud import aiplatform_v1
        from google.api_core.client_options import ClientOptions
        import time

        client = aiplatform_v1.PipelineServiceClient(
            client_options=ClientOptions(
                api_endpoint=f"{self.cfg.region}-aiplatform.googleapis.com"
            )
        )

        while True:
            pipeline = client.get_training_pipeline(name=job_id)
            state = pipeline.state.name

            if state in {
                "PIPELINE_STATE_SUCCEEDED",
                "PIPELINE_STATE_FAILED",
                "PIPELINE_STATE_CANCELLED",
                "PIPELINE_STATE_PAUSED",
            }:
                return {
                    "job_id": job_id,
                    "state": state,
                }

            time.sleep(15)

    def register_model(self, model_uri: str, name: str) -> str:
        aiplatform.init(
            project=self.cfg.project_id,
            location=self.cfg.region,
        )

        existing = aiplatform.Model.list(
            filter=f'display_name="{name}"',
        )

        parent_model = existing[0].name if existing else None

        model = aiplatform.Model.upload(
            display_name=name,
            artifact_uri=model_uri,
            serving_container_image_uri=(
                "asia-docker.pkg.dev/vertex-ai/"
                "prediction/sklearn-cpu.1-6:latest"
            ),
            parent_model=parent_model,
            is_default_version=False if parent_model else True,
            sync=True,
        )

        return model.version_id

    def get_model_uri(self, name: str, version: str) -> str:
        aiplatform.init(
            project=self.cfg.project_id,
            location=self.cfg.region,
        )

    
        models = aiplatform.Model.list(
            filter=f'display_name="{name}"',
        )
        if not models:
            raise ValueError(f"Registered model {name!r} not found")

        model_id = models[0].name
        model = aiplatform.Model(
            model_name=f"{model_id}@{version}",
        )

        artifact_uri = model.gca_resource.artifact_uri

        if not artifact_uri:
            raise ValueError(
                f"Registered model {name!r} version {version!r} has no artifact URI"
        )

        return f"{artifact_uri.rstrip('/')}/model.joblib"

    def deploy(self, model_ref: str, endpoint: str, instance: str) -> str:
        aiplatform.init(
            project=self.cfg.project_id,
            location=self.cfg.region,
        )

        endpoint_obj = aiplatform.Endpoint.create(
            display_name=endpoint,
            labels=self.cfg.tags(3),
            sync=True,
        )
    
        models = aiplatform.Model.list(
         filter=f'display_name="{self.cfg.model_registry_name}"',
        )

        if not models:
            raise ValueError(
                f"Registered model {self.cfg.model_registry_name!r} not found"
            )

        model_id = models[0].name

        registered_model = aiplatform.Model(
            model_name=f"{model_id}@{model_ref}",
        )

        artifact_uri = registered_model.gca_resource.artifact_uri

        if not artifact_uri:
            raise ValueError(
                f"Registered model version {model_ref!r} has no artifact URI"
            )

        serving_image = self.cfg.serving_image_uri

        if not serving_image:
            raise ValueError("SERVING_IMAGE_URI is not configured")

        serving_model = aiplatform.Model.upload(
            display_name=f"{self.cfg.model_registry_name}-serve",
            artifact_uri=artifact_uri,
            serving_container_image_uri=serving_image,
            serving_container_predict_route="/predict",
            serving_container_health_route="/health",
            serving_container_ports=[8080],
            serving_container_environment_variables={
                "CLOUD_PROVIDER": self.cfg.provider,
                "PROJECT_ID": self.cfg.project_id,
                "REGION": self.cfg.region,
                "BLOB_URI": self.cfg.blob_uri,
                "CONTAINER_REGISTRY": self.cfg.container_registry,
                "MLFLOW_TRACKING_URI": self.cfg.mlflow_tracking_uri,
                "MODEL_REGISTRY_NAME": self.cfg.model_registry_name,
                "IDENTITY_REF": self.cfg.identity_ref,
                "MODEL_VERSION": str(model_ref),
                "MODEL_ARTIFACT_URI": f"{artifact_uri.rstrip('/')}/model.joblib",
            },
            labels=self.cfg.tags(3),
            sync=True,
        )

        endpoint_obj.deploy(
            model=serving_model,
            deployed_model_display_name=f"{endpoint}-v{model_ref}",
            machine_type=instance,
            min_replica_count=1,
            max_replica_count=1,
            traffic_percentage=100,
            sync=True,
        )
        self.emit_metric("model_version", float(model_ref))

        return endpoint_obj.resource_name

    def invoke(self, endpoint: str, payload: dict) -> dict:
        import json

        from google.api_core.client_options import ClientOptions
        from google.cloud import aiplatform_v1
        from google.api import httpbody_pb2

        client = aiplatform_v1.PredictionServiceClient(
            client_options=ClientOptions(
                api_endpoint=f"{self.cfg.region}-aiplatform.googleapis.com"
            )
        )

        http_body = httpbody_pb2.HttpBody(
            content_type="application/json",
            data=json.dumps(payload).encode("utf-8"),
        )

        request = aiplatform_v1.RawPredictRequest(
            endpoint=endpoint,
            http_body=http_body,
        )

        response = client.raw_predict(request=request)

        return json.loads(response.data.decode("utf-8"))

    def emit_metric(self, name: str, value: float, unit: str = "None") -> None:
        from google.cloud import monitoring_v3

        client = monitoring_v3.MetricServiceClient()
        project_name = f"projects/{self.cfg.project_id}"

        series = monitoring_v3.TimeSeries()
        series.metric.type = f"custom.googleapis.com/itcs355/{name}"
        series.resource.type = "global"
        series.resource.labels["project_id"] = self.cfg.project_id

        from google.protobuf.timestamp_pb2 import Timestamp

        point = monitoring_v3.Point()
        point.value.double_value = float(value)

        timestamp = Timestamp()
        timestamp.GetCurrentTime()
        point.interval = monitoring_v3.TimeInterval(end_time=timestamp)

        series.points = [point]

        client.create_time_series(
            name=project_name,
            time_series=[series],
        )

    def teardown(self, tags: dict[str, str]) -> list[str]:
        from google.cloud import aiplatform

        aiplatform.init(
            project=self.cfg.project_id,
            location=self.cfg.region,
        )

        deleted: list[str] = []

        # Delete endpoints that match this lab's labels.
        for endpoint in aiplatform.Endpoint.list():
            labels = dict(endpoint.gca_resource.labels)

            labels_match = all(
                labels.get(key) == value
                for key, value in tags.items()
            )

            if not labels_match:
                continue

            resource_name = endpoint.resource_name

            endpoint.delete(
                force=True,
                sync=True,
            )

            deleted.append(resource_name)

        return deleted

    # submit_training / register_model  -> Lab 2 (Vertex custom training + Model Registry)
    # deploy / invoke                   -> Lab 3 (Vertex Endpoint)
    # emit_metric                       -> Lab 4 (Cloud Monitoring time series)
    # generate                          -> Lab 5 (managed LLM endpoint; read usageMetadata for tokens)
    # teardown                          -> Lab 5 (filter resources by label)