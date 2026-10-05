# Lab 4 — injected temperature shift

**What fired:** Local PSI drift alert at `2026-10-05T04:32:22.766470+00:00`; `temp_c` reached 0.38333 against the 0.20 threshold. The external webhook evidence remains pending repository-secret configuration.

**True cause:** A deliberate +6 °C input shift; schema and null checks stayed valid, so this was distribution drift rather than a malformed batch.

**Retrain, roll back, or no action — and why:** No automatic retraining; first verify sensor calibration and units, because retraining on a producer fault would corrupt the last known-good model. Retrain only if the warmer fleet is legitimate and persistent.

**What this would have cost if unnoticed for a week:** At 89 predictions/day, roughly 623 maintenance decisions could be biased; multiply confirmed false interventions by the actual call-out cost before the live report is submitted.

**How to prevent or detect it faster:** Enforce upstream unit/range contracts and shorten the drift window after a sensor rollout while retaining the 0.20 PSI alert.
