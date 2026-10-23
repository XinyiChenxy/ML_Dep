# Lab 5 cloud evidence status

Local code and deterministic evidence are committed separately from real cloud evidence. Add only
evidence produced by this project; do not copy resource IDs, bills or screenshots from the reference
repository.

Required before final submission:

- `pipeline-success.txt`: Vertex run URL/ID and six-step outcome, including one failed gate branch
- `iam-removal.txt`: successful artifact read, permission removal, observed 403, and restoration
- `portability-evidence.txt`: real AWS upload/download/invoke output (offline tests are already present)
- `billing.csv`: tag-filtered Lab 5 usage cost and credits after billing settles
- `teardown-24h.txt`: second teardown verification at least 24 hours later
- `empty-resources.png`: console screenshot showing no endpoint, schedule, job or compute remains
- `llm_eval-live.json`: provider-reported input/output tokens from the 12 live cases

The absence of these files means the associated claim remains pending, not that it passed.

Completed cloud evidence:

- `schedule-evidence.txt`: schedule resource name, timezone, identity, concurrency and verified
  `PAUSED` state.
