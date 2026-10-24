# Lab 5 cloud evidence status

Local code and deterministic evidence are committed separately from real cloud evidence. Add only
evidence produced by this project; do not copy resource IDs, bills or screenshots from the reference
repository.

Required before final submission:

- `pipeline-success.txt`: Vertex run URL/ID and six-step outcome, including one failed gate branch
- `portability-evidence.txt`: real AWS upload/download/invoke output (offline tests are already present)
- `billing.csv`: tag-filtered Lab 5 usage cost and credits after billing settles
- `teardown-24h.txt`: second teardown verification at least 24 hours later
- `empty-resources.png`: console screenshot showing no endpoint, schedule, job or compute remains

The absence of these files means the associated claim remains pending, not that it passed.

Completed cloud evidence:

- `schedule-evidence.txt`: schedule resource name, timezone, identity, concurrency and verified
  `PAUSED` state.
- `quota-blocker.txt`: real failed Vertex run, the exact custom-training CPU quota, Google's
  4-CPU request/1-CPU grant response, and a check confirming no Custom Jobs or Endpoints remain.
- `iam-removal.txt`: successful artifact read, permission removal, observed 403, restoration and
  final IAM-policy verification.
- `teardown.txt`: deletion of the paused schedule and immediate `PASS nothing found` verification.
- `llm-access-blocker.txt`: regional and global publisher-model access probes returning 404 before
  any content or usage metadata was produced, followed by the successful global-endpoint
  resolution.
- `llm-live-evidence.txt` and `../llm_eval-live.json`: real Vertex global evaluation, 12/12 gate,
  provider-reported token usage, latency, estimated token cost and credential cleanup.
- `billing-export-setup.txt`: billing-enabled project and labeled US multi-region dataset prepared;
  `make billing-export` is ready to query the provider-created table.

Current cloud blocker:

- Every listed Vertex region has an effective custom-training CPU limit of 1 and quota increase
  eligibility reports `NOT_ENOUGH_USAGE_HISTORY`. Google declined the request for 4. The six-step
  pipeline cannot produce `pipeline-success.txt` until the account becomes eligible for a
  sufficient quota increase. Do not replace this limitation with copied reference evidence.
- No AWS CLI/profile/credentials and no logged-in Azure subscription are present, so a real second
  provider run requires the user to connect one of those accounts.
- Billing is enabled and the `itcs355_billing` dataset exists, but Google requires the final
  Standard usage cost export selection in the Cloud Console. Actual tagged costs cannot be queried
  until that console-only setting is saved and the first export load settles.
