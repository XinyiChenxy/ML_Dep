"""Resumable study: 12 configurations × 3 seeds, fixed held-out split."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import signal
import time
from pathlib import Path

import joblib
import mlflow
import mlflow.sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

from cloudlayer.factory import get_adapter
from src import config, data, seeds
from src.train import git_commit

SEARCH_SPACE = {'n_estimators': [50, 150], 'max_depth': [4, 8, 12], 'min_samples_leaf': [1, 5]}


def grid(space):
    return [dict(zip(space, values)) for values in itertools.product(*space.values())]


def save_checkpoint(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, indent=2))
    temporary.replace(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--trials', type=int, default=36)
    ap.add_argument('--budget-thb', type=float, default=150)
    ap.add_argument('--instance', default='local')
    ap.add_argument('--hourly-thb', type=float, default=0)
    ap.add_argument('--trial-reserve-s', type=int, default=300)
    ap.add_argument('--seeds', type=int, nargs='+', default=[20260101, 20260102, 20260103])
    ap.add_argument('--experiment', default='itcs355-lab2')
    ap.add_argument('--study', default='lab2-local')
    ap.add_argument('--checkpoint', type=Path, default=Path('reports/tune_checkpoint.json'))
    ap.add_argument('--stop-after', type=int, help='Controlled interruption after N completed trials')
    args = ap.parse_args()
    if len(set(args.seeds)) < 3 or len(set(args.seeds)) != len(args.seeds):
        ap.error('Use at least three distinct model seeds')
    if args.trials != len(grid(SEARCH_SPACE)) * len(args.seeds):
        ap.error('Run the complete 12-configuration grid for every seed (default: 36 trials)')
    if args.hourly_thb < 0 or args.budget_thb <= 0 or args.trial_reserve_s <= 0:
        ap.error('Invalid cost/budget parameters')
    def trial_timeout(signum, frame):
        raise TimeoutError('Trial exceeded reserved time; reservation remains in checkpoint')
    signal.signal(signal.SIGALRM, trial_timeout)
    cfg = config.load(strict=False)
    remote = cfg.provider != 'local'
    if remote and (args.hourly_thb <= 0 or args.instance == 'local'):
        ap.error('Cloud study needs a verified hourly rate and instance type')
    adapter = get_adapter(cfg)
    training_job_id = adapter.training_job_id() if remote else 'local'
    checkpoint_key = f'studies/{args.study}/checkpoint.json'
    if remote:
        adapter.download(config.runtime_value('DATA_URI'), str(cfg.raw_path))
        adapter.download_if_exists(cfg.blob_uri.rstrip('/') + '/' + checkpoint_key, str(args.checkpoint))
    raw_hash = hashlib.md5(cfg.raw_path.read_bytes()).hexdigest()
    if remote and raw_hash != config.runtime_value('DATA_VERSION'):
        raise ValueError('Downloaded data does not match the DVC hash')
    candidates = [{**p, 'seed': s} for p in grid(SEARCH_SPACE) for s in args.seeds][:args.trials]
    if len(candidates) != args.trials:
        ap.error('Requested trials exceed the search space')
    source_hash = hashlib.sha256()
    for file in sorted((config.REPO_ROOT / 'src').glob('*.py')):
        source_hash.update(file.name.encode() + file.read_bytes())
    signature = {'source_sha256': source_hash.hexdigest(), 'candidates': candidates, 'data_version': raw_hash, 'split_seed': seeds.DEFAULT_SEED,
                 'git_commit': git_commit(), 'image_digest': config.runtime_value('IMAGE_DIGEST', 'local'),
                 'hourly_thb': args.hourly_thb, 'study': args.study}
    state = json.loads(args.checkpoint.read_text()) if args.checkpoint.exists() else {
        'signature': signature, 'completed': [], 'spent_thb': 0, 'reserved_thb': 0, 'resume_events': []}
    if state['signature'] != signature:
        raise ValueError('Checkpoint belongs to different code/data/configuration; use a new study')
    if state['completed'] or state['reserved_thb']:
        state['resume_events'].append({'time': time.time(), 'completed': len(state['completed'])})
        # An interrupted trial may have consumed its entire reservation.
        state['spent_thb'] += state['reserved_thb']
        state['reserved_thb'] = 0
        print(f"RESUMED: {len(state['completed'])} completed trials; retaining prior artifacts")
    def persist():
        save_checkpoint(args.checkpoint, state)
        if remote:
            adapter.upload(str(args.checkpoint), checkpoint_key)
    train, val, test = data.split(data.load_raw(cfg.raw_path), seed=seeds.DEFAULT_SEED)
    mlflow.set_tracking_uri(cfg.mlflow_tracking_uri)
    mlflow.set_experiment(args.experiment)
    persist()
    newly_completed = 0
    for index, candidate in enumerate(candidates):
        if any(row['index'] == index for row in state['completed']):
            continue
        reserve = args.trial_reserve_s / 3600 * args.hourly_thb
        if state['spent_thb'] + reserve > args.budget_thb:
            print('BUDGET STOP: cannot reserve the next trial; study incomplete')
            break
        state['reserved_thb'] = reserve
        persist()
        signal.alarm(args.trial_reserve_s)
        started = time.monotonic()
        params = dict(candidate)
        seed = params.pop('seed')
        with mlflow.start_run(run_name=f'{args.study}-{index:02d}') as run:
            model = RandomForestClassifier(**params, random_state=seed, n_jobs=-1)
            model.fit(train[data.FEATURES], train[data.TARGET])
            metrics = {}
            for label, partition in [('val', val), ('test', test)]:
                probability = model.predict_proba(partition[data.FEATURES])[:, 1]
                metrics[label + '_roc_auc'] = float(roc_auc_score(partition[data.TARGET], probability))
                metrics[label + '_pr_auc'] = float(average_precision_score(partition[data.TARGET], probability))
            directory = cfg.reports_dir / 'lab2-models' / run.info.run_id
            directory.mkdir(parents=True, exist_ok=True)
            joblib.dump(model, directory / 'model.joblib')
            lineage = {'git_commit': git_commit(), 'data_version': raw_hash,
                       'mlflow_run_id': run.info.run_id,
                       'training_job_id': training_job_id,
                       'image_digest': config.runtime_value('IMAGE_DIGEST', 'local'),
                       'seed': seed, 'split_seed': seeds.DEFAULT_SEED,
                       'metric_val': metrics['val_roc_auc'], 'metric_test': metrics['test_roc_auc'],
                       'data_uri': config.runtime_value('DATA_URI', ''), 'study': args.study,
                       'source_sha256': source_hash.hexdigest()}
            (directory / 'lineage.json').write_text(json.dumps(lineage, indent=2))
            mlflow.log_params({**candidate, 'split_seed': seeds.DEFAULT_SEED, 'instance': args.instance})
            mlflow.set_tags({**lineage, 'lab': '2', 'execution': 'cloud-spot' if remote else 'local'})
            info = mlflow.sklearn.log_model(model, name='model', input_example=train[data.FEATURES].head(5))
            artifact_uri = str(directory)
            if remote:
                for file in directory.iterdir():
                    artifact_uri = adapter.upload(str(file), f'studies/{args.study}/models/{run.info.run_id}/{file.name}').rsplit('/', 1)[0]
            duration = time.monotonic() - started
            cost = duration / 3600 * args.hourly_thb
            mlflow.log_metrics({**metrics, 'duration_s': duration, 'cost_thb': cost})
            row = {'index': index, 'run_id': run.info.run_id, **candidate, **metrics,
                   'duration_s': duration, 'cost_thb': cost, 'artifact_uri': artifact_uri,
                   'mlflow_model_uri': info.model_uri, 'execution': 'cloud-spot' if remote else 'local'}
        signal.alarm(0)
        state['spent_thb'] += cost
        state['reserved_thb'] = 0
        state['completed'].append(row)
        persist()
        print(f"trial {index}: val={metrics['val_roc_auc']:.5f}, {cost:.5f} THB", flush=True)
        newly_completed += 1
        if args.stop_after and newly_completed >= args.stop_after:
            print('CONTROLLED INTERRUPTION: checkpoint persisted; rerun without --stop-after')
            raise SystemExit(75)
    print(f"Completed {len(state['completed'])}/{len(candidates)}; estimated trial cost {state['spent_thb']:.4f} THB")
    if len(state['completed']) != len(candidates):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
