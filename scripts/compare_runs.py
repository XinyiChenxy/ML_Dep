"""Compare completed checkpoint runs; select using validation only."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--experiment', default='itcs355-lab2')
    ap.add_argument('--checkpoint', type=Path, default=Path('reports/tune_checkpoint.json'))
    ap.add_argument('--out', type=Path, default=Path('reports/lab2-comparison.md'))
    args = ap.parse_args()
    state = json.loads(args.checkpoint.read_text())
    runs = pd.DataFrame(state['completed'])
    if len(runs) != len(state['signature']['candidates']):
        raise ValueError('Study incomplete; do not select from a partial study')
    keys = ['n_estimators', 'max_depth', 'min_samples_leaf']
    grouped = runs.groupby(keys).agg(val_mean=('val_roc_auc', 'mean'),
        val_std=('val_roc_auc', 'std'), seeds=('seed', 'nunique'),
        mean_cost=('cost_thb', 'mean'), mean_seconds=('duration_s', 'mean')).reset_index()
    if (grouped.seeds < 3).any():
        raise ValueError('Each configuration needs three distinct seeds')
    best = grouped.loc[grouped.val_mean.idxmax()]
    # Within 0.005 AUC of best mean, choose the fastest measured configuration.
    selected = grouped[grouped.val_mean >= best.val_mean - 0.005].sort_values(
        ['mean_seconds', 'n_estimators', 'max_depth']).iloc[0]
    matching = runs[(runs[keys] == selected[keys]).all(axis=1)]
    # Predetermined seed order, not test score, chooses the concrete model.
    winner = matching.sort_values('seed').iloc[0].to_dict()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    (args.out.parent / 'lab2-selection.json').write_text(json.dumps(winner, indent=2))
    local = set(runs.execution) == {'local'}
    cost_text = ('Local execution has no billed cloud compute cost; GCP training and monthly '
                 'retraining costs remain unmeasured.' if local else
                 f"Mean training cost is {selected.mean_cost:.4f} THB; one monthly retrain costs "
                 f"the same, or {selected.mean_cost * 12:.4f} THB annually, excluding overhead.")
    justification = (
        f"We select {int(selected.n_estimators)} trees, depth {int(selected.max_depth)}, "
        f"and minimum leaf size {int(selected.min_samples_leaf)}. Its mean validation ROC-AUC "
        f"is {selected.val_mean:.5f}, versus the best configuration's {best.val_mean:.5f}. "
        "Among configurations within a predeclared 0.005 AUC tolerance of the best mean, "
        "it has the shortest measured mean runtime. This tolerance is a practical tradeoff, "
        "not evidence of statistical equivalence. "
        f"Across three model seeds on the same group split, sample standard deviation is "
        f"{selected.val_std:.6f} (variance {selected.val_std ** 2:.8f}). "
        f"{cost_text} The representative model uses the smallest predetermined seed; "
        "test scores do not affect selection. This choice could be wrong because seed variance "
        "does not capture uncertainty across machines or future distribution shifts. "
        "Runtime rankings may also change on cloud hardware.")
    assert len(justification.split()) <= 200
    lines = ['# Lab 2 — Run comparison', '',
        '**LOCAL REHEARSAL ONLY — cloud submission requirements remain pending.**' if local else '**Cloud Spot study**', '',
        f"Completed trials: {len(runs)}; checkpoint resume events: {len(state['resume_events'])}.",
        f"Estimated trial cost: {state['spent_thb']:.6f} THB. This is not a billing export.", '',
        '## Configuration comparison', '', grouped.to_markdown(index=False), '',
        '## Selection justification (≤200 words)', '', justification, '',
        f"Selected MLflow run: `{winner['run_id']}`", '',
        '## All trials', '', runs.drop(columns=['artifact_uri', 'mlflow_model_uri']).to_markdown(index=False), '',
        '## Outstanding cloud evidence', '',
        'GCP Spot job ID, verified regional pricing and exchange rate, actual billing export, '
        'cloud restart logs, versioned Vertex model and staging alias, and teardown evidence '
        'must be attached after a real cloud execution. Do not substitute local results.', '']
    args.out.write_text('\n'.join(lines))
    print(f'Wrote {args.out}; selected {winner["run_id"]}')


if __name__ == '__main__':
    main()
