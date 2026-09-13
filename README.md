# ITCS355 Lab 1 — Reproducible Training

> **Course materials live in [`course/`](course/README.md)** — syllabus, slides, the faculty
> specification, all five lab handouts, and the project brief. Every document is Markdown and
> renders on GitHub, diagrams included. New to the repo? Start with the
> [portability reference](course/reference/cloud-portability-reference.md).
> Keep this block when you edit the rest of this file; it is not part of the Lab 1 deliverable.

Predicting machine failure within 7 days from sensor readings. The model is not the point;
whether a stranger can reproduce it is.

> **This README is graded.** A grader with Docker and nothing else from your setup runs one
> command and compares the result against the claim below.

---

## Reproduce

```bash
make reproduce
```

expected test_roc_auc: 0.848 ± 0.001

Runtime: about 40 seconds on 4 cores. No cloud account or credentials needed for this command —
that is deliberate, and it is why a grader can run it.

The claim is re-measured from the deterministic default run. The tolerance is intentionally small:
the model, grouped split, and seed are fixed. It should be updated only if the dataset or training
configuration changes.

---

## The problem

240 machines, 25 readings each, 6 sensor features, binary target `failed_within_7d` with a
positive rate near 12%.

Machines have persistent characteristics — a hot-running machine reads hot in every row. So the
train/validation/test split is **grouped by `machine_id`**: every reading from one machine lands
in exactly one partition. Splitting row-wise instead lets the model memorise the machine and
reports a validation score that will never survive production. `tests/test_data.py` asserts this
property holds, and Lab 4 turns it into a CI gate.

Bringing your own dataset is allowed. Replace `scripts/make_dataset.py`, update the schema in
`src/data.py`, and keep every test passing.

---

## Layout

```
src/          Layer 1 — provider-neutral. No SDKs, no bucket names, no absolute paths.
cloudlayer/   Layer 3 — the only place a provider SDK may be imported.
scripts/      Dataset generation, cloud check, portability audit, metric verification.
tests/        Data contract tests and split property tests.
```

`src/config.py` is the single point of environment knowledge. Everything else reads from it.
`make portability-audit` enforces the rule; it fails the build if a provider string appears in
`src/` or `tests/`.

---

## Setup

```bash
cp cloud.env.example cloud.env      # fill in, never commit
make setup
make cloud-check                    # eight slots, all PASS
make data                           # generate the dataset
make test                           # 10 tests, all passing
```

Post your `make cloud-check` output in the course channel before Session 1.

---

## What you must finish

The Docker base is pinned by digest and is configured to install only artifacts from the hash lock
file. The selected cloud adapter implements object-storage upload/download and digest-addressed
registry pushes. After generating the lock file and filling in `cloud.env` with your provider
values, publish the cloud artifacts with:

```bash
make image-push        # image reaches your registry, digest-pinned
dvc init && dvc remote add -d storage ${BLOB_URI}/dvc
dvc add data/raw && dvc push
```

Run five or more tracked runs varying something meaningful — not five identical runs with
different seeds.

---

## Reproducibility trade-off

Three things pin your build: hashed dependencies, a digest-pinned base image, and controlled
seeds. Under real time pressure you would keep some and drop others.

Under genuine time pressure I would drop seed control first. The image can still be built from the
same base and verified package artifacts, but experiment-to-experiment metrics and splits cease to
be directly comparable. I would not drop hashes or the base digest: either allows the same Git
revision to acquire different dependency or OS bits, so it may no longer build or run the same
program at all.

---

## Notes for the grader

Run `make reproduce` from the repository root. It generates the deterministic teaching dataset,
builds a `linux/amd64` image, and writes `reports/metrics.json`. The command intentionally needs
no cloud credentials. Provider credentials are required only for `dvc push` and `make image-push`.

---

## Checklist before you submit

- [ ] `make reproduce` works from a fresh clone, on a machine that is not yours
- [ ] `make verify` passes against your claim line
- [ ] `make test` — all tests pass
- [ ] `make portability-audit` — clean
- [ ] Image builds for `linux/amd64` and is pushed, digest-pinned
- [ ] `dvc push` completed; a grader can `dvc pull`
- [ ] Five or more tracked runs with params, metrics, data fingerprint, and commit SHA
- [ ] All submission placeholders have been replaced
- [ ] `git log -p | grep -i -E "secret|password|AKIA|BEGIN PRIVATE"` returns nothing

That last check is not optional. A credential in Git history is an automatic deduction in this
course, and rotating it is your responsibility, not the grader's.
