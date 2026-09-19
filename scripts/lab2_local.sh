#!/usr/bin/env bash
# Local rehearsal, deliberately distinct from real GCP evidence.
set -euo pipefail
cd "$(dirname "$0")/.."
export CLOUD_PROVIDER=local
export MLFLOW_TRACKING_URI=sqlite:///mlflow.db
export MODEL_REGISTRY_NAME=itcs355-lab2-local
source .venv/bin/activate
mkdir -p reports
python scripts/make_dataset.py --seed 20260101
if [[ ! -f reports/tune_checkpoint.json ]]; then
  set +e
  python -m src.tune --stop-after 3 2>&1 | tee reports/lab2-interruption.log
  code=${PIPESTATUS[0]}
  set -e
  [[ "$code" == 75 ]] || exit 1
fi
python -m src.tune 2>&1 | tee reports/lab2-resume.log
python scripts/compare_runs.py
python scripts/register_model.py
python scripts/reload_check.py
