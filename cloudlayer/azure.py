"""Azure adapter. Implement upload/download/push_image for Lab 1.

SDK:  pip install azure-storage-blob azure-identity azure-containerregistry
Docs: BlobServiceClient for storage; ACR push goes through `docker push` after
      `az acr login --name <registry>`.

Hints for Lab 1:
  * BLOB_URI is either abfss://container@account.dfs.core.windows.net/prefix or
    https://account.blob.core.windows.net/container/prefix. Pick one form and parse
    it here, never in src/.
  * Use DefaultAzureCredential rather than a connection string. It picks up your CLI
    login locally and your managed identity in CI, which is what Lab 4 needs.
  * push_image must return the digest reference: registry.azurecr.io/repo@sha256:...
  * Azure tags live on the resource, not the blob. Tag the storage account, the
    registry, and later the workspace with cfg.tags(1).
"""

from __future__ import annotations

from pathlib import Path
import subprocess
from urllib.parse import quote, unquote, urlparse

from cloudlayer.base import CloudAdapter


class AzureAdapter(CloudAdapter):
    @staticmethod
    def _parse_blob_uri(uri: str) -> tuple[str, str, str]:
        """Parse an HTTPS or ABFSS Azure blob URI into endpoint, container, and path."""
        parsed = urlparse(uri)
        if (
            parsed.scheme == "https"
            and parsed.hostname
            and parsed.hostname.endswith(".blob.core.windows.net")
        ):
            parts = [unquote(part) for part in parsed.path.split("/") if part]
            if not parts:
                raise ValueError("Azure blob URI must include a container name")
            return f"https://{parsed.hostname}", parts[0], "/".join(parts[1:])

        if parsed.scheme == "abfss" and parsed.hostname and parsed.username:
            account_host = parsed.hostname
            if not account_host.endswith(".dfs.core.windows.net"):
                raise ValueError("ABFSS URI must use an Azure Data Lake endpoint")
            endpoint = f"https://{account_host.removesuffix('.dfs.core.windows.net')}.blob.core.windows.net"
            path = "/".join(unquote(part) for part in parsed.path.split("/") if part)
            return endpoint, unquote(parsed.username), path

        raise ValueError(f"Unsupported Azure blob URI: {uri!r}")

    @staticmethod
    def _blob_client(endpoint: str, container: str, blob_name: str):
        # Provider-specific imports stay inside cloudlayer so local reproduction has no Azure dependency.
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient

        service = BlobServiceClient(account_url=endpoint, credential=DefaultAzureCredential())
        return service.get_blob_client(container=container, blob=blob_name)

    def upload(self, local_path: str, key: str) -> str:
        source = Path(local_path)
        if not source.is_file():
            raise FileNotFoundError(source)

        endpoint, container, prefix = self._parse_blob_uri(self.cfg.blob_uri)
        blob_name = "/".join(part for part in (prefix.strip("/"), key.strip("/")) if part)
        if not blob_name:
            raise ValueError("Blob key must not be empty")
        with source.open("rb") as stream:
            self._blob_client(endpoint, container, blob_name).upload_blob(stream, overwrite=True)
        return f"{endpoint}/{quote(container, safe='')}/{quote(blob_name, safe='/')}"

    def download(self, uri: str, local_path: str) -> None:
        endpoint, container, blob_name = self._parse_blob_uri(uri)
        if not blob_name:
            raise ValueError("Azure blob URI must include a blob name")

        destination = Path(local_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = self._blob_client(endpoint, container, blob_name).download_blob().readall()
        destination.write_bytes(payload)

    def push_image(self, local_tag: str) -> str:
        repository = self.cfg.container_registry.rstrip("/")
        registry, separator, image_name = repository.partition("/")
        if not separator or not image_name or not registry.endswith(".azurecr.io"):
            raise ValueError("CONTAINER_REGISTRY must be <registry>.azurecr.io/<repository>")

        tail = local_tag.rsplit("/", 1)[-1]
        tag = tail.rsplit(":", 1)[-1] if ":" in tail else "latest"
        remote_tag = f"{repository}:{tag}"
        subprocess.run(
            ["az", "acr", "login", "--name", registry.removesuffix(".azurecr.io")],
            check=True,
        )
        subprocess.run(["docker", "tag", local_tag, remote_tag], check=True)
        result = subprocess.run(
            ["docker", "push", remote_tag],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        for line in result.stdout.splitlines():
            if "digest: sha256:" in line:
                digest = line.split("digest:", 1)[1].strip().split()[0]
                return f"{repository}@{digest}"
        raise RuntimeError("docker push succeeded but did not report an image digest")

    # submit_training / register_model  -> Lab 2 (Azure ML command job + model registry)
    # deploy / invoke                   -> Lab 3 (managed online endpoint + deployment)
    # emit_metric                       -> Lab 4 (Azure Monitor custom metric)
    # generate                          -> Lab 5 (managed LLM endpoint; read the usage block for tokens)
    # teardown                          -> Lab 5 (resource graph query by tag)
