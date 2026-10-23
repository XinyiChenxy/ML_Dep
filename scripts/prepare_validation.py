"""Fetch the managed-pipeline dataset before running the contract tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudlayer.factory import get_adapter
from src import config

cfg = config.load()
get_adapter(cfg).download(
    f"{cfg.blob_uri.rstrip('/')}/lab5/raw/sensors.csv",
    str(cfg.raw_path),
)
print(f"downloaded validation input to {cfg.raw_path}")
