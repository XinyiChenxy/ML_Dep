"""Training entry point.

Run locally:      python -m src.train --n-estimators 200 --max-depth 8
Run in Docker:    make reproduce

Every run logs: all hyperparameters, the seed, validation AND test metrics separately,
the data fingerprint, and the Git commit. A metric that cannot be traced to code and
data is not evidence of anything.
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
from pathlib import Path

import joblib
import mlflow
import mlflow.sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

from cloudlayer.factory import get_adapter
from src import config, data, seeds


def git_commit() -> str:
    env_sha = os.environ.get("GIT_COMMIT_SHA")
    if env_sha:
        return env_sha

    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, cwd=config.REPO_ROOT,
        )
        return out.stdout.strip()
    except Exception:
        return "unknown"

def dvc_hash() -> str:
    dvc_file = config.REPO_ROOT / "data/raw.dvc"
    try:
        for line in dvc_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("md5:") or line.startswith("- md5:"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return "unknown"

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ITCS355 Lab 1 — reproducible training")
    p.add_argument("--n-estimators", type=int, default=200)
    p.add_argument("--max-depth", type=int, default=8)
    p.add_argument("--min-samples-leaf", type=int, default=5)
    p.add_argument("--seed", type=int, default=seeds.DEFAULT_SEED)
    p.add_argument("--experiment", default="itcs355-lab1")
    p.add_argument("--run-name", default=None)
    p.add_argument(
        "--upload-artifacts",
        type=lambda value: value.lower() in {"1", "true", "yes"},
        default=False,
        help="Download input and upload outputs through the cloud adapter (remote jobs).",
    )
    p.add_argument("--metrics-out", type=Path, default=None,
                   help="Write final metrics as JSON. Used by `make verify`.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    cfg = config.load(strict=False)
    adapter = get_adapter(cfg) if args.upload_artifacts else None
    seed = seeds.set_all(args.seed)

    if not cfg.raw_path.exists() and adapter is not None:
        remote_data = f"{cfg.blob_uri.rstrip('/')}/lab2/sensors.csv"
        adapter.download(remote_data, str(cfg.raw_path))

    df = data.load_raw(cfg.raw_path)

    fingerprint = data.data_fingerprint(cfg.raw_path)
    train_df, val_df, test_df = data.split(df, seed=seed)

    mlflow.set_tracking_uri(cfg.mlflow_tracking_uri)

    client = mlflow.MlflowClient()
    experiment = client.get_experiment_by_name(args.experiment)

    if experiment is None:
        client.create_experiment(
            args.experiment,
            artifact_location=str(cfg.reports_dir / "mlartifacts"),
        )

    mlflow.set_experiment(args.experiment)

    with mlflow.start_run(run_name=args.run_name):
        mlflow.log_params({
            "n_estimators": args.n_estimators,
            "max_depth": args.max_depth,
            "min_samples_leaf": args.min_samples_leaf,
            "seed": seed,
            "n_features": len(data.FEATURES),
            "dvc_hash": dvc_hash(),
        })
        # Provenance. This is what makes the metric traceable.
        mlflow.set_tags({
            "git_commit": git_commit(),
            "data_fingerprint": fingerprint,
            "split_strategy": "group_by_machine_id",
            "n_train_rows": len(train_df),
            "n_val_rows": len(val_df),
            "n_test_rows": len(test_df),
        })

        model = RandomForestClassifier(
            n_estimators=args.n_estimators,
            max_depth=args.max_depth,
            min_samples_leaf=args.min_samples_leaf,
            random_state=seed,
            n_jobs=-1,
        )
        model.fit(train_df[data.FEATURES], train_df[data.TARGET])

        metrics: dict[str, float] = {}
        for name, part in (("val", val_df), ("test", test_df)):
            proba = model.predict_proba(part[data.FEATURES])[:, 1]
            metrics[f"{name}_roc_auc"] = float(roc_auc_score(part[data.TARGET], proba))
            metrics[f"{name}_pr_auc"] = float(average_precision_score(part[data.TARGET], proba))
        mlflow.log_metrics(metrics)
        mlflow.sklearn.log_model(model, name="model")

        run = mlflow.active_run()
        run_id = run.info.run_id if run else args.run_name or f"seed-{seed}"
        model_path = cfg.reports_dir / "model.joblib"
        joblib.dump(model, model_path)

        model_uri = str(model_path)
        if adapter is not None:
            model_uri = adapter.upload(
                str(model_path),
                f"lab2/models/{run_id}/model.joblib",
            )

        result = {
            "seed": seed,
            "data_fingerprint": fingerprint,
            "mlflow_run_id": run_id,
            "model_uri": model_uri,
            **metrics,
        }
        print(json.dumps(result, indent=2))
        if args.metrics_out is not None:
            args.metrics_out.parent.mkdir(parents=True, exist_ok=True)
            args.metrics_out.write_text(json.dumps(result, indent=2))
            if adapter is not None:
                adapter.upload(
                    str(args.metrics_out),
                    f"lab2/metrics/{args.metrics_out.name}",
                )


if __name__ == "__main__":
    main()
