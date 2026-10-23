"""Deploy the gated model version to the staging endpoint."""
import argparse
from pathlib import Path

from cloudlayer.factory import get_adapter
from src import config

parser = argparse.ArgumentParser()
parser.add_argument("--target", default="staging", choices=["staging"])
args = parser.parse_args()
cfg = config.load()
adapter = get_adapter(cfg)
version_path = Path("/tmp/lab5-model-version.txt")
adapter.download(
    f"{cfg.blob_uri.rstrip('/')}/lab5/model-version.txt",
    str(version_path),
)
version = version_path.read_text().strip()
if not version:
    raise ValueError("registered model version is empty")
print(adapter.deploy(version, f"itcs355-lab5-{args.target}", "n1-standard-2"))
