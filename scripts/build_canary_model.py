"""Build a reproducible, deliberately degraded model for the Lab 3 canary exercise."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

from cloudlayer.factory import get_adapter
from src import config, data, seeds
from src.train import git_commit


def score(model, frame) -> dict[str, float]:
    probability = model.predict_proba(frame[data.FEATURES])[:, 1]
    return {
        "roc_auc": float(roc_auc_score(frame[data.TARGET], probability)),
        "pr_auc": float(average_precision_score(frame[data.TARGET], probability)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("reports/lab3-canary"))
    parser.add_argument("--seed", type=int, default=20260103)
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--artifact-prefix", default="lab3/models/canary")
    args = parser.parse_args()

    cfg = config.load(strict=args.upload)
    seed = seeds.set_all(args.seed)
    frame = data.load_raw(cfg.raw_path)
    train, validation, test = data.split(frame, seed=seed)

    stable = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        min_samples_leaf=5,
        random_state=seed,
        n_jobs=-1,
    ).fit(train[data.FEATURES], train[data.TARGET])
    canary = RandomForestClassifier(
        n_estimators=1,
        max_depth=1,
        min_samples_leaf=200,
        random_state=seed,
        n_jobs=-1,
    ).fit(train[data.FEATURES], train[data.TARGET])

    metrics = {
        "stable_validation": score(stable, validation),
        "stable_test": score(stable, test),
        "canary_validation": score(canary, validation),
        "canary_test": score(canary, test),
    }
    metrics["test_roc_auc_delta"] = (
        metrics["canary_test"]["roc_auc"] - metrics["stable_test"]["roc_auc"]
    )
    run_id = "lab3-canary-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    image_digest = cfg.serving_image_uri.rsplit("@", 1)[-1] or "unknown"
    lineage = {
        "git_commit": git_commit(),
        "data_version": data.data_fingerprint(cfg.raw_path),
        "mlflow_run_id": run_id,
        "training_job_id": "local-controlled-degradation",
        "image_digest": image_digest,
        "seed": str(seed),
        "metric_val": str(metrics["canary_validation"]["roc_auc"]),
        "metric_test": str(metrics["canary_test"]["roc_auc"]),
    }

    args.out.mkdir(parents=True, exist_ok=True)
    joblib.dump(canary, args.out / "model.joblib")
    (args.out / "lineage.json").write_text(json.dumps(lineage, indent=2) + "\n")
    report = {"run_id": run_id, "metrics": metrics, "lineage": lineage}

    if args.upload:
        adapter = get_adapter(cfg)
        prefix = args.artifact_prefix.rstrip("/")
        adapter.upload(str(args.out / "model.joblib"), f"{prefix}/model.joblib")
        adapter.upload(str(args.out / "lineage.json"), f"{prefix}/lineage.json")
        report["artifact_uri"] = f"{cfg.blob_uri.rstrip('/')}/{prefix}"

    (args.out / "metrics.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
