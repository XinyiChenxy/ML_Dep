"""GCS, Artifact Registry, Vertex AI, monitoring and managed LLM adapter."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cloudlayer.base import CloudAdapter

LINEAGE = (
    "git_commit", "data_version", "mlflow_run_id", "training_job_id",
    "image_digest", "seed", "metric_val", "metric_test",
)


class GcpAdapter(CloudAdapter):
    def _blob(self, uri):
        from google.cloud import storage

        parsed = urlparse(uri)
        if parsed.scheme != "gs" or not parsed.netloc or not parsed.path.strip("/"):
            raise ValueError(f"Expected a GCS object URI: {uri}")
        return storage.Client(project=self.cfg.project_id).bucket(parsed.netloc).blob(
            parsed.path.lstrip("/")
        )

    def upload(self, local_path: str, key: str) -> str:
        uri = self.cfg.blob_uri.rstrip("/") + "/" + key.lstrip("/")
        self._blob(uri).upload_from_filename(local_path)
        return uri

    def download(self, uri: str, local_path: str) -> None:
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        self._blob(uri).download_to_filename(local_path)

    def download_if_exists(self, uri: str, local_path: str) -> bool:
        from google.api_core.exceptions import NotFound

        try:
            self.download(uri, local_path)
        except NotFound:
            return False
        return True

    def push_image(self, local_tag: str) -> str:
        remote = self.cfg.container_registry.rstrip("/") + "/" + local_tag.rsplit("/", 1)[-1]
        subprocess.run(
            ["gcloud", "auth", "configure-docker", remote.split("/")[0], "--quiet"],
            check=True,
        )
        subprocess.run(["docker", "tag", local_tag, remote], check=True)
        subprocess.run(["docker", "push", remote], check=True)
        digest = subprocess.check_output(
            [
                "gcloud", "artifacts", "docker", "images", "describe", remote,
                "--format=value(image_summary.digest)",
            ],
            text=True,
        ).strip()
        if not digest.startswith("sha256:"):
            raise RuntimeError("Artifact Registry did not return a digest")
        return remote.rsplit(":", 1)[0] + "@" + digest

    def _client(self, kind):
        from google.cloud import aiplatform_v1

        return getattr(aiplatform_v1, kind)(
            client_options={"api_endpoint": f"{self.cfg.region}-aiplatform.googleapis.com"}
        )

    @property
    def parent(self):
        return f"projects/{self.cfg.project_id}/locations/{self.cfg.region}"

    def submit_training(self, image_uri: str, args: dict[str, Any]) -> str:
        if "@sha256:" not in image_uri:
            raise ValueError("Training image must be digest-pinned")
        request = dict(args)
        lab = int(request.pop("_lab", 2))
        is_study = "command_args" in request
        supplied_env = request.pop("env", {})
        instance = request.pop("instance", "e2-standard-4")
        timeout_s = int(request.pop("timeout_s", 3600))
        display_name = request.pop("study", f"itcs355-lab{lab}-training")

        env = {
            key: str(getattr(self.cfg, attr))
            for key, attr in {
                "CLOUD_PROVIDER": "provider",
                "PROJECT_ID": "project_id",
                "REGION": "region",
                "BLOB_URI": "blob_uri",
                "CONTAINER_REGISTRY": "container_registry",
                "MLFLOW_TRACKING_URI": "mlflow_tracking_uri",
                "MODEL_REGISTRY_NAME": "model_registry_name",
                "IDENTITY_REF": "identity_ref",
            }.items()
        }
        env.update({key: str(value) for key, value in supplied_env.items()})
        context_uri = self.cfg.blob_uri.rstrip("/") + "/jobs/" + uuid.uuid4().hex + ".json"
        env["JOB_CONTEXT_URI"] = context_uri
        env["IMAGE_DIGEST"] = image_uri.split("@", 1)[1]

        if is_study:
            command = ["python", "-m", "src.tune"]
            command_args = request.pop("command_args")
        else:
            command = ["python", "-m", "src.train"]
            command_args = [
                item
                for key, value in request.items()
                for item in (
                    [f"--{key.replace('_', '-')}", "true"] if value is True
                    else [] if value is False or value is None
                    else [f"--{key.replace('_', '-')}={value}"]
                )
            ]

        job_spec = {
            "service_account": self.cfg.identity_ref,
            "worker_pool_specs": [{
                "machine_spec": {"machine_type": instance},
                "replica_count": 1,
                "container_spec": {
                    "image_uri": image_uri,
                    "command": command,
                    "args": command_args,
                    "env": [{"name": key, "value": value} for key, value in env.items()],
                },
            }],
            "scheduling": {
                "strategy": "SPOT",
                "timeout": {"seconds": timeout_s},
                "restart_job_on_worker_restart": True,
            },
        }
        job = self._client("JobServiceClient").create_custom_job(
            parent=self.parent,
            custom_job={
                "display_name": display_name,
                "labels": self.cfg.tags(lab),
                "job_spec": job_spec,
            },
        )
        self._blob(context_uri).upload_from_string(
            json.dumps({"job_id": job.name}), content_type="application/json"
        )
        return job.name

    def training_job_id(self) -> str:
        from google.api_core.exceptions import NotFound

        for _ in range(30):
            try:
                payload = self._blob(os.environ["JOB_CONTEXT_URI"]).download_as_text()
                return json.loads(payload)["job_id"]
            except NotFound:
                time.sleep(2)
        raise RuntimeError("Submitter did not persist job identity")

    def wait_training(self, job_id: str) -> dict[str, Any]:
        from google.cloud.aiplatform_v1.types import JobState

        client = self._client("JobServiceClient")
        while True:
            job = client.get_custom_job(name=job_id)
            if job.state == JobState.JOB_STATE_SUCCEEDED:
                return {"job_id": job.name, "state": job.state.name}
            if job.state in (
                JobState.JOB_STATE_FAILED,
                JobState.JOB_STATE_CANCELLED,
                JobState.JOB_STATE_EXPIRED,
            ):
                raise RuntimeError(f"{job.name}: {job.state.name}: {job.error}")
            time.sleep(20)

    def register_model(
        self,
        model_uri: str,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        from google.cloud import aiplatform

        lineage = metadata or json.loads(
            self._blob(model_uri.rstrip("/") + "/lineage.json").download_as_text()
        )
        if any(not str(lineage.get(key, "")) for key in LINEAGE):
            raise ValueError("Missing required lineage fields")
        serving_image = self.cfg.serving_image_uri or os.environ.get("SERVING_IMAGE_URI", "")
        if "@sha256:" not in serving_image:
            raise ValueError("SERVING_IMAGE_URI must be digest-pinned")
        aiplatform.init(project=self.cfg.project_id, location=self.cfg.region)
        existing = aiplatform.Model.list(filter=f'display_name="{name}"')
        if len(existing) > 1:
            raise ValueError("Ambiguous model display name")
        serving_environment = {
            "CLOUD_PROVIDER": self.cfg.provider,
            "PROJECT_ID": self.cfg.project_id,
            "REGION": self.cfg.region,
            "BLOB_URI": self.cfg.blob_uri,
            "CONTAINER_REGISTRY": self.cfg.container_registry,
            "MLFLOW_TRACKING_URI": self.cfg.mlflow_tracking_uri,
            "MODEL_REGISTRY_NAME": self.cfg.model_registry_name,
            "IDENTITY_REF": self.cfg.identity_ref,
            "MODEL_ARTIFACT_URI": model_uri.rstrip("/") + "/model.joblib",
            # Vertex allocates its numeric version after upload. The run ID is already
            # immutable and lets responses identify the exact artifact immediately.
            "MODEL_VERSION": str(lineage["mlflow_run_id"]),
        }
        model = aiplatform.Model.upload(
            display_name=name,
            artifact_uri=model_uri,
            serving_container_image_uri=serving_image,
            serving_container_predict_route="/predict",
            serving_container_health_route="/health",
            serving_container_environment_variables=serving_environment,
            parent_model=existing[0].resource_name if existing else None,
            version_description=json.dumps(lineage, sort_keys=True),
            version_aliases=["candidate"],
            labels=self.cfg.tags(5),
            sync=True,
        )
        return model.resource_name + "@" + model.version_id

    def model_metadata(self, version: str) -> dict:
        if "@" not in version or not version.rsplit("@", 1)[1].isdigit():
            raise ValueError("Use an immutable projects/.../models/ID@VERSION reference")
        model = self._client("ModelServiceClient").get_model(name=version)
        return {
            "artifact_uri": model.artifact_uri,
            "lineage": json.loads(model.version_description),
        }

    def get_model_uri(self, name: str, version: str) -> str:
        from google.cloud import aiplatform

        aiplatform.init(project=self.cfg.project_id, location=self.cfg.region)
        models = aiplatform.Model.list(filter=f'display_name="{name}"')
        if len(models) != 1:
            raise ValueError(f"Expected one registered model named {name!r}, found {len(models)}")
        model = aiplatform.Model(model_name=f"{models[0].resource_name}@{version}")
        artifact_uri = model.gca_resource.artifact_uri
        if not artifact_uri:
            raise ValueError(f"Model {name!r} version {version!r} has no artifact URI")
        return artifact_uri.rstrip("/") + "/model.joblib"

    def deploy(self, model_ref: str, endpoint: str, instance: str) -> str:
        from google.cloud import aiplatform

        aiplatform.init(project=self.cfg.project_id, location=self.cfg.region)
        endpoints = aiplatform.Endpoint.list(filter=f'display_name="{endpoint}"')
        endpoint_obj = endpoints[0] if endpoints else aiplatform.Endpoint.create(
            display_name=endpoint, labels=self.cfg.tags(self._lab_from_endpoint(endpoint)), sync=True
        )
        models = aiplatform.Model.list(
            filter=f'display_name="{self.cfg.model_registry_name}"'
        )
        if len(models) != 1:
            raise ValueError("Expected exactly one registered model container")
        version = model_ref.rsplit("@", 1)[-1]
        registered = aiplatform.Model(model_name=f"{models[0].resource_name}@{version}")
        endpoint_obj.deploy(
            model=registered,
            deployed_model_display_name=f"{endpoint}-v{version}",
            machine_type=instance,
            min_replica_count=1,
            max_replica_count=1,
            traffic_percentage=100,
            service_account=self.cfg.serving_service_account or None,
            sync=True,
        )
        return endpoint_obj.resource_name

    @staticmethod
    def _lab_from_endpoint(endpoint: str) -> int:
        """Keep teardown labels aligned with the lab that created an endpoint."""
        match = re.search(r"(?:^|-)lab([2-5])(?:-|$)", endpoint.lower())
        return int(match.group(1)) if match else 3

    def invoke(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        from google.api import httpbody_pb2

        client = self._client("PredictionServiceClient")
        endpoint_name = endpoint if endpoint.startswith("projects/") else (
            f"{self.parent}/endpoints/{endpoint}"
        )
        # RawPredict preserves the provider-neutral FastAPI request/response contract.
        # Standard Predict wraps requests in {"instances": ...}, which would couple the
        # service schema to Vertex and make the same container unusable elsewhere.
        response = client.raw_predict(
            endpoint=endpoint_name,
            http_body=httpbody_pb2.HttpBody(
                content_type="application/json",
                data=json.dumps(payload).encode("utf-8"),
            ),
        )
        result = json.loads(response.data.decode("utf-8"))
        if not isinstance(result, dict) or "probability" not in result:
            raise ValueError("Managed endpoint returned an invalid prediction response")
        return {
            "probability": float(result["probability"]),
            "model_version": str(result.get("model_version", "unknown")),
        }

    def emit_metric(self, name: str, value: float, unit: str = "1") -> None:
        from google.cloud import monitoring_v3
        from google.protobuf import timestamp_pb2

        client = monitoring_v3.MetricServiceClient()
        series = monitoring_v3.TimeSeries()
        series.metric.type = "custom.googleapis.com/itcs355/" + name.replace(".", "/")
        series.resource.type = "global"
        series.resource.labels["project_id"] = self.cfg.project_id
        point = monitoring_v3.Point()
        point.value.double_value = float(value)
        point.interval.end_time = timestamp_pb2.Timestamp()
        point.interval.end_time.GetCurrentTime()
        series.points = [point]
        client.create_time_series(
            name=f"projects/{self.cfg.project_id}", time_series=[series]
        )

    def generate(self, prompt: str, params: dict[str, Any]) -> dict[str, Any]:
        """Call Vertex and retain provider-reported usage rather than estimating tokens."""
        import vertexai
        from vertexai.generative_models import GenerationConfig, GenerativeModel

        options = dict(params)
        model_name = options.pop("model", self.cfg.llm_model)
        allowed = {
            "max_output_tokens", "temperature", "top_p", "top_k",
            "candidate_count", "stop_sequences", "response_mime_type",
        }
        unknown = sorted(set(options) - allowed)
        if unknown:
            raise ValueError(f"unsupported generation parameter(s): {', '.join(unknown)}")
        vertexai.init(project=self.cfg.project_id, location=self.cfg.region)
        started = time.perf_counter()
        response = GenerativeModel(model_name).generate_content(
            prompt, generation_config=GenerationConfig(**options)
        )
        usage = response.usage_metadata
        return {
            "response": response.text,
            "input_tokens": int(usage.prompt_token_count),
            "output_tokens": int(usage.candidates_token_count),
            "latency_ms": round((time.perf_counter() - started) * 1000),
        }

    def teardown(self, tags: dict[str, str]) -> list[str]:
        from google.cloud import aiplatform
        from google.cloud.aiplatform_v1.types import JobState

        deleted = []
        query = " AND ".join(f'labels.{key}="{value}"' for key, value in tags.items())
        client = self._client("JobServiceClient")
        terminal = {
            JobState.JOB_STATE_SUCCEEDED,
            JobState.JOB_STATE_FAILED,
            JobState.JOB_STATE_CANCELLED,
            JobState.JOB_STATE_EXPIRED,
        }
        for job in client.list_custom_jobs(parent=self.parent, filter=query):
            if job.state not in terminal:
                client.cancel_custom_job(name=job.name)
            client.delete_custom_job(name=job.name)
            deleted.append(job.name)

        aiplatform.init(project=self.cfg.project_id, location=self.cfg.region)
        for endpoint in aiplatform.Endpoint.list():
            labels = dict(endpoint.gca_resource.labels)
            if all(labels.get(key) == value for key, value in tags.items()):
                name = endpoint.resource_name
                endpoint.delete(force=True, sync=True)
                deleted.append(name)
        for schedule in aiplatform.PipelineJobSchedule.list():
            labels = dict(getattr(schedule.gca_resource, "labels", {}))
            belongs_to_lab = all(labels.get(key) == value for key, value in tags.items())
            named_for_lab = tags.get("lab") == "5" and schedule.display_name.startswith(
                "itcs355-lab5-"
            )
            if belongs_to_lab or named_for_lab:
                name = schedule.resource_name
                schedule.delete(sync=True)
                deleted.append(name)
        return deleted
