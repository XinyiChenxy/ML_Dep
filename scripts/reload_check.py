"""Resolve an immutable registry version, verify data, and score held-out rows."""
import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import joblib
import mlflow
import mlflow.sklearn
import numpy as np
from mlflow.tracking import MlflowClient
from cloudlayer.factory import get_adapter
from src import config, data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--name')
    ap.add_argument('--version')
    ap.add_argument('--rows', type=int, default=5)
    args = ap.parse_args()
    if args.rows < 5:
        ap.error('At least five held-out rows required')
    cfg = config.load(strict=False)
    record = json.loads(Path('reports/lab2-registration.json').read_text()) if not args.version else {}
    name, version = args.name or record.get('name'), args.version or record.get('version')
    if not version:
        ap.error('Supply --version or run make register')
    with tempfile.TemporaryDirectory() as temporary:
        raw = cfg.raw_path
        if cfg.provider == 'local':
            mlflow.set_tracking_uri(cfg.mlflow_tracking_uri)
            lineage = MlflowClient().get_model_version(name, version).tags
            model = mlflow.sklearn.load_model(f'models:/{name}/{version}')
        else:
            adapter = get_adapter(cfg)
            metadata = adapter.model_metadata(version)
            lineage = metadata['lineage']
            model_path = Path(temporary) / 'model.joblib'
            adapter.download(metadata['artifact_uri'] + '/model.joblib', str(model_path))
            raw = Path(temporary) / 'sensors.csv'
            adapter.download(lineage['data_uri'], str(raw))
            model = joblib.load(model_path)
        if hashlib.md5(raw.read_bytes()).hexdigest() != lineage['data_version']:
            raise ValueError('Data version mismatch')
        _, _, heldout = data.split(data.load_raw(raw), seed=int(lineage['split_seed']))
        sample = heldout.head(args.rows)
        if len(sample) != args.rows:
            raise ValueError('Not enough held-out rows')
        probability = model.predict_proba(sample[data.FEATURES])[:, 1]
        if not np.isfinite(probability).all() or not ((probability >= 0) & (probability <= 1)).all():
            raise ValueError('Invalid predictions')
        evidence = {'registry_version': version, 'provider': cfg.provider, 'run_id': lineage['mlflow_run_id'],
                    'rows': [{'reading_id': int(r), 'probability': float(p)} for r, p in zip(sample[data.ID], probability)]}
        Path('reports/lab2-reload.json').write_text(json.dumps(evidence, indent=2))
        print(json.dumps(evidence, indent=2))
        print('PASS: model fetched by registry version and scored held-out rows')


if __name__ == '__main__':
    main()
