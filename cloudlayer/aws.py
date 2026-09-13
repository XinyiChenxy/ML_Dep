"""AWS adapter. Implement upload/download/push_image for Lab 1.

SDK:  pip install boto3
Docs: S3 -> boto3 client("s3"); ECR -> boto3 client("ecr") for the auth token,
      then `docker push` through subprocess.

Hints for Lab 1:
  * BLOB_URI looks like s3://bucket/prefix — parse it here, never in src/.
  * ECR login expires. If a push that worked yesterday fails today, re-authenticate:
        aws ecr get-login-password --region $REGION | docker login --username AWS \
            --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
  * Return the DIGEST reference from push_image, not the tag. `docker inspect` or the
    push output gives you the sha256.
  * Tag the bucket objects and the ECR repository with cfg.tags(1).
"""
from __future__ import annotations

import base64
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from cloudlayer.base import CloudAdapter


class AwsAdapter(CloudAdapter):
    def _s3_location(self, uri: str) -> tuple[str, str]:
        parsed = urlparse(uri)
        if parsed.scheme != "s3" or not parsed.netloc:
            raise ValueError("BLOB_URI must be an s3://bucket/optional-prefix URI")
        return parsed.netloc, parsed.path.lstrip("/").rstrip("/")

    def _object_key(self, key: str) -> tuple[str, str]:
        bucket, prefix = self._s3_location(self.cfg.blob_uri)
        return bucket, "/".join(part for part in (prefix, key.lstrip("/")) if part)

    @staticmethod
    def _run(command: list[str], *, input_text: str | None = None) -> str:
        return subprocess.run(command, input=input_text, text=True, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()

    def upload(self, local_path: str, key: str) -> str:
        import boto3

        bucket, object_key = self._object_key(key)
        boto3.client("s3", region_name=self.cfg.region).upload_file(local_path, bucket, object_key)
        return f"s3://{bucket}/{object_key}"

    def download(self, uri: str, local_path: str) -> None:
        import boto3

        bucket, object_key = self._s3_location(uri)
        destination = Path(local_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        boto3.client("s3", region_name=self.cfg.region).download_file(bucket, object_key, str(destination))

    def push_image(self, local_tag: str) -> str:
        import boto3

        registry = self.cfg.container_registry.rstrip("/")
        if not registry:
            raise RuntimeError("CONTAINER_REGISTRY must be set to an ECR repository URI")
        repository = registry.rsplit("/", 1)[-1]
        ecr = boto3.client("ecr", region_name=self.cfg.region)
        auth = ecr.get_authorization_token()["authorizationData"][0]
        user, password = base64.b64decode(auth["authorizationToken"]).decode().split(":", 1)
        endpoint = auth["proxyEndpoint"].removeprefix("https://")
        self._run(["docker", "login", "--username", user, "--password-stdin", endpoint], input_text=password)
        remote_tag = f"{registry}:{local_tag.rsplit(':', 1)[-1]}"
        self._run(["docker", "tag", local_tag, remote_tag])
        self._run(["docker", "push", remote_tag])
        digest = ecr.describe_images(repositoryName=repository,
            imageIds=[{"imageTag": remote_tag.rsplit(":", 1)[-1]}])["imageDetails"][0]["imageDigest"]
        return f"{registry}@{digest}"

    # submit_training / register_model  -> Lab 2 (SageMaker training job + model package group)
    # deploy / invoke                   -> Lab 3 (SageMaker real-time endpoint)
    # emit_metric                       -> Lab 4 (CloudWatch put_metric_data)
    # generate                          -> Lab 5 (managed LLM endpoint; read the usage block for tokens)
    # teardown                          -> Lab 5 (resourcegroupstaggingapi to find by tag)
