# Lab 4 — injected temperature shift

**What fired:** The GCP-backed [scheduled drift run `39996053148`](https://github.com/XinyiChenxy/ML_Dep/actions/runs/39996053148) started at `2026-10-23T17:33:32+00:00` and delivered a real Slack `#all-itcs355` alert at `2026-10-23T17:35:04.873190+00:00`; `temp_c` reached PSI 0.38333 against the 0.20 threshold. Trigger-to-notification latency was about 93 seconds, and the complete GitHub Actions run finished successfully in 1m39s.

**Dashboard evidence:** Cloud Monitoring dashboard [`346faf7b-ce0c-4a1b-a7d2-8d615e5f6020`](https://console.cloud.google.com/monitoring/dashboards/builder/346faf7b-ce0c-4a1b-a7d2-8d615e5f6020?project=project-b9257458-cea1-4ef8-876) shows the blue `temp_c` point near 0.38333 above the red 0.20 significant-drift threshold; screenshot captured on 2026-10-24 (Asia/Bangkok).

**True cause:** A deliberate +6 °C input shift; schema and null checks stayed valid, so this was distribution drift rather than a malformed batch.

**Retrain, roll back, or no action — and why:** No automatic retraining; first verify sensor calibration and units, because retraining on a producer fault would corrupt the last known-good model. Retrain only if the warmer fleet is legitimate and persistent.

**What this would have cost if unnoticed for a week:** At 89 predictions/day, roughly 623 maintenance decisions could be biased; multiply confirmed false interventions by the actual call-out cost before the live report is submitted.

**How to prevent or detect it faster:** Enforce upstream unit/range contracts and shorten the drift window after a sensor rollout while retaining the 0.20 PSI alert.
