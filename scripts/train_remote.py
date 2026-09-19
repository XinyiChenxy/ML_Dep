"""Submit an immutable GCP study and fetch its completed checkpoint."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yaml
from cloudlayer.factory import get_adapter
from src import config
from src.train import git_commit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', required=True)
    ap.add_argument('--study', required=True)
    ap.add_argument('--instance', default='n1-standard-4')
    ap.add_argument('--hourly-thb', type=float, required=True)
    ap.add_argument('--pricing-source', required=True)
    ap.add_argument('--timeout-s', type=int, default=3600)
    args = ap.parse_args()
    cfg = config.load()
    if cfg.provider != 'gcp':
        ap.error('Configure CLOUD_PROVIDER=gcp')
    if not cfg.mlflow_tracking_uri.startswith('https://'):
        ap.error('Cloud workers need a reachable HTTPS MLflow server, not local SQLite')
    if args.hourly_thb <= 0 or args.timeout_s <= 0 or args.hourly_thb * args.timeout_s / 3600 > 120:
        ap.error('Job timeout compute estimate must be <=120 THB, reserving 30 THB for overhead')
    if subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip():
        ap.error('Commit code and DVC metadata first; lineage must identify exact source')
    version = hashlib.md5(cfg.raw_path.read_bytes()).hexdigest()
    metadata = yaml.safe_load(Path('data/raw/sensors.csv.dvc').read_text())
    if metadata['outs'][0]['md5'] != version:
        ap.error('DVC hash does not match raw data; run dvc add again')
    adapter = get_adapter(cfg)
    uri = adapter.upload(str(cfg.raw_path), f'data/{version}/sensors.csv')
    job = adapter.submit_training(args.image, {
        'study': args.study, 'instance': args.instance, 'timeout_s': args.timeout_s,
        'env': {'DATA_URI': uri, 'DATA_VERSION': version, 'GIT_COMMIT': git_commit(),
                'PRICE_SOURCE': args.pricing_source},
        'command_args': ['--study', args.study, '--instance', args.instance,
                         '--hourly-thb', str(args.hourly_thb), '--budget-thb', '120']})
    Path('reports').mkdir(exist_ok=True)
    record = {**vars(args), 'job_id': job, 'data_uri': uri, 'data_version': version}
    Path('reports/lab2-job.json').write_text(json.dumps(record, indent=2))
    print(job, flush=True)
    adapter.wait_training(job)
    adapter.download(cfg.blob_uri.rstrip('/') + f'/studies/{args.study}/checkpoint.json',
                     'reports/tune_checkpoint.json')


if __name__ == '__main__':
    main()
