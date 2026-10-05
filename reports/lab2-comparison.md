# Lab 2 — Run comparison

**Cloud comparison evidence is pending.**

This report is the stable destination for the Lab 2 comparison links. The measured tables and
selection rationale are generated only after the complete hyperparameter study has finished:

```bash
make tune
make compare
```

`make compare` reads `reports/tune_checkpoint.json`, verifies that every candidate configuration
has results from three distinct seeds, selects a model using validation ROC-AUC and measured
runtime, and replaces this page with the generated comparison. It deliberately rejects a partial
study so that an incomplete run cannot be presented as final evidence.

## Required evidence

- All 36 completed trials (12 configurations with 3 seeds each)
- Mean and sample standard deviation of validation ROC-AUC for each configuration
- Measured runtime and cost for the selected configuration
- Selection rationale based only on validation results
- MLflow run ID and reload verification for the registered model
- GCP Spot job ID, restart logs, billing evidence, Vertex model version, staging alias, and teardown
  evidence from a real cloud execution

Local rehearsal is useful for validating the workflow, but it is not a substitute for the required
cloud evidence. No measured values are claimed in this placeholder report.
