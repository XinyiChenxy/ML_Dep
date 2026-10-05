"""GCS, Artifact Registry and Vertex AI implementation for Labs 1–2."""
from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cloudlayer.base import CloudAdapter

LINEAGE = ('git_commit', 'data_version', 'mlflow_run_id', 'training_job_id',
           'image_digest', 'seed', 'metric_val', 'metric_test')


class GcpAdapter(CloudAdapter):
    def _blob(self, uri):
        from google.cloud import storage
        parsed = urlparse(uri)
        if parsed.scheme != 'gs' or not parsed.netloc or not parsed.path.strip('/'):
            raise ValueError(f'Expected a GCS object URI: {uri}')
        return storage.Client(project=self.cfg.project_id).bucket(parsed.netloc).blob(parsed.path.lstrip('/'))

    def upload(self, local_path: str, key: str) -> str:
        uri = self.cfg.blob_uri.rstrip('/') + '/' + key.lstrip('/')
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
        remote = self.cfg.container_registry.rstrip('/') + '/' + local_tag.rsplit('/', 1)[-1]
        subprocess.run(['gcloud', 'auth', 'configure-docker', remote.split('/')[0], '--quiet'], check=True)
        subprocess.run(['docker', 'tag', local_tag, remote], check=True)
        subprocess.run(['docker', 'push', remote], check=True)
        digest = subprocess.check_output(['gcloud', 'artifacts', 'docker', 'images', 'describe', remote,
                                          '--format=value(image_summary.digest)'], text=True).strip()
        if not digest.startswith('sha256:'):
            raise RuntimeError('Artifact Registry did not return a digest')
        return remote.rsplit(':', 1)[0] + '@' + digest

    def _client(self, kind):
        from google.cloud import aiplatform_v1
        return getattr(aiplatform_v1, kind)(client_options={
            'api_endpoint': f'{self.cfg.region}-aiplatform.googleapis.com'})

    @property
    def parent(self):
        return f'projects/{self.cfg.project_id}/locations/{self.cfg.region}'

    def submit_training(self, image_uri: str, args: dict[str, Any]) -> str:
        if '@sha256:' not in image_uri:
            raise ValueError('Training image must be digest-pinned')
        env = {k: str(getattr(self.cfg, attr)) for k, attr in {
            'CLOUD_PROVIDER': 'provider', 'PROJECT_ID': 'project_id', 'REGION': 'region',
            'BLOB_URI': 'blob_uri', 'CONTAINER_REGISTRY': 'container_registry',
            'MLFLOW_TRACKING_URI': 'mlflow_tracking_uri', 'MODEL_REGISTRY_NAME': 'model_registry_name',
            'IDENTITY_REF': 'identity_ref'}.items()}
        env.update(args['env'])
        context_uri = self.cfg.blob_uri.rstrip('/') + '/jobs/' + uuid.uuid4().hex + '.json'
        env['JOB_CONTEXT_URI'] = context_uri
        env['IMAGE_DIGEST'] = image_uri.split('@')[1]
        spec = {'service_account': self.cfg.identity_ref,
                'worker_pool_specs': [{'machine_spec': {'machine_type': args['instance']},
                    'replica_count': 1, 'container_spec': {'image_uri': image_uri,
                        'command': ['python', '-m', 'src.tune'], 'args': args['command_args'],
                        'env': [{'name': k, 'value': str(v)} for k, v in env.items()]}}],
                'scheduling': {'strategy': 'SPOT', 'timeout': {'seconds': args['timeout_s']},
                               'restart_job_on_worker_restart': True}}
        job = self._client('JobServiceClient').create_custom_job(parent=self.parent,
            custom_job={'display_name': args['study'], 'labels': self.cfg.tags(2), 'job_spec': spec})
        self._blob(context_uri).upload_from_string(json.dumps({'job_id': job.name}), content_type='application/json')
        return job.name

    def training_job_id(self) -> str:
        from google.api_core.exceptions import NotFound
        for _ in range(30):
            try:
                return json.loads(self._blob(os.environ['JOB_CONTEXT_URI']).download_as_text())['job_id']
            except NotFound:
                time.sleep(2)
        raise RuntimeError('Submitter did not persist job identity')

    def wait_training(self, job_id: str) -> dict[str, Any]:
        from google.cloud.aiplatform_v1.types import JobState
        client = self._client('JobServiceClient')
        while True:
            job = client.get_custom_job(name=job_id)
            if job.state == JobState.JOB_STATE_SUCCEEDED:
                return {'job_id': job.name, 'state': job.state.name}
            if job.state in (JobState.JOB_STATE_FAILED, JobState.JOB_STATE_CANCELLED,
                             JobState.JOB_STATE_EXPIRED):
                raise RuntimeError(f'{job.name}: {job.state.name}: {job.error}')
            time.sleep(20)

    def register_model(self, model_uri: str, name: str) -> str:
        from google.cloud import aiplatform
        lineage = json.loads(self._blob(model_uri.rstrip('/') + '/lineage.json').download_as_text())
        if any(not str(lineage.get(k, '')) for k in LINEAGE):
            raise ValueError('Missing required lineage fields')
        serving_image = os.environ['SERVING_IMAGE_URI']
        if '@sha256:' not in serving_image:
            raise ValueError('SERVING_IMAGE_URI must be digest-pinned')
        aiplatform.init(project=self.cfg.project_id, location=self.cfg.region)
        existing = aiplatform.Model.list(filter=f'display_name="{name}"')
        if len(existing) > 1:
            raise ValueError('Ambiguous model display name')
        model = aiplatform.Model.upload(display_name=name, artifact_uri=model_uri,
            serving_container_image_uri=serving_image,
            serving_container_command=["python", "-m", "cloudlayer.serve"],
            serving_container_predict_route="/predict", serving_container_health_route="/health",
            parent_model=existing[0].resource_name if existing else None,
            version_description=json.dumps(lineage, sort_keys=True),
            version_aliases=['candidate'], labels=self.cfg.tags(2))
        return model.resource_name + '@' + model.version_id

    def promote(self, version: str) -> None:
        from google.cloud import aiplatform
        aiplatform.init(project=self.cfg.project_id, location=self.cfg.region)
        aiplatform.Model(version).versioning_registry.add_version_aliases(['staging'])

    def model_metadata(self, version: str) -> dict:
        if '@' not in version or not version.rsplit('@', 1)[1].isdigit():
            raise ValueError('Use an immutable projects/.../models/ID@VERSION reference')
        model = self._client('ModelServiceClient').get_model(name=version)
        return {'artifact_uri': model.artifact_uri, 'lineage': json.loads(model.version_description)}

    def get_model_uri(self, name: str, version: str) -> str:
        from google.cloud import aiplatform
        aiplatform.init(project=self.cfg.project_id, location=self.cfg.region)
        models = aiplatform.Model.list(filter=f'display_name="{name}"')
        if len(models) != 1:
            raise ValueError(f'Expected one registered model named {name!r}, found {len(models)}')
        model = aiplatform.Model(model_name=f'{models[0].resource_name}@{version}')
        artifact_uri = model.gca_resource.artifact_uri
        if not artifact_uri:
            raise ValueError(f'Model {name!r} version {version!r} has no artifact URI')
        return artifact_uri.rstrip('/') + '/model.joblib'

    def deploy(self, model_ref: str, endpoint: str, instance: str) -> str:
        from google.cloud import aiplatform
        aiplatform.init(project=self.cfg.project_id, location=self.cfg.region)
        endpoints = aiplatform.Endpoint.list(filter=f'display_name="{endpoint}"')
        endpoint_obj = endpoints[0] if endpoints else aiplatform.Endpoint.create(
            display_name=endpoint, labels=self.cfg.tags(3), sync=True)
        models = aiplatform.Model.list(filter=f'display_name="{self.cfg.model_registry_name}"')
        if len(models) != 1:
            raise ValueError('Expected exactly one registered model container')
        registered = aiplatform.Model(model_name=f'{models[0].resource_name}@{model_ref}')
        endpoint_obj.deploy(model=registered, deployed_model_display_name=f'{endpoint}-v{model_ref}',
                            machine_type=instance, min_replica_count=1, max_replica_count=1,
                            traffic_percentage=100, sync=True)
        return endpoint_obj.resource_name

    def invoke(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        client = self._client('PredictionServiceClient')
        endpoint_name = endpoint if endpoint.startswith('projects/') else f'{self.parent}/endpoints/{endpoint}'
        response = client.predict(endpoint=endpoint_name, instances=[payload])
        prediction = list(response.predictions[0])
        probability = float(prediction[-1])
        return {'probability': probability, 'model_version': 'managed'}

    def emit_metric(self, name: str, value: float, unit: str = '1') -> None:
        from google.cloud import monitoring_v3
        from google.protobuf import timestamp_pb2

        client = monitoring_v3.MetricServiceClient()
        series = monitoring_v3.TimeSeries()
        series.metric.type = 'custom.googleapis.com/itcs355/' + name.replace('.', '/')
        series.resource.type = 'global'
        series.resource.labels['project_id'] = self.cfg.project_id
        point = monitoring_v3.Point()
        point.value.double_value = float(value)
        point.interval.end_time = timestamp_pb2.Timestamp()
        point.interval.end_time.GetCurrentTime()
        series.points = [point]
        client.create_time_series(name=f'projects/{self.cfg.project_id}', time_series=[series])

    def teardown(self, tags: dict[str, str]) -> list[str]:
        from google.cloud.aiplatform_v1.types import JobState
        client = self._client('JobServiceClient')
        deleted = []
        query = ' AND '.join(f'labels.{k}="{v}"' for k, v in tags.items())
        for job in client.list_custom_jobs(parent=self.parent, filter=query):
            if job.state not in (JobState.JOB_STATE_SUCCEEDED, JobState.JOB_STATE_FAILED,
                                 JobState.JOB_STATE_CANCELLED, JobState.JOB_STATE_EXPIRED):
                client.cancel_custom_job(name=job.name)
                try:
                    self.wait_training(job.name)
                except RuntimeError:
                    pass
            client.delete_custom_job(name=job.name).result(timeout=300)
            deleted.append(job.name)
        from google.cloud import aiplatform
        aiplatform.init(project=self.cfg.project_id, location=self.cfg.region)
        for endpoint in aiplatform.Endpoint.list():
            labels = dict(endpoint.gca_resource.labels)
            if all(labels.get(key) == value for key, value in tags.items()):
                name = endpoint.resource_name
                endpoint.delete(force=True, sync=True)
                deleted.append(name)
        return deleted
