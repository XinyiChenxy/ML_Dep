# Lab 4 — blocked bad commit evidence

This file records the required external CI exercise. Create a short-lived branch that removes
`temp_c` from the generated fixture, open a pull request, and close it without merging after CI
fails.

Repository audit on 2026-10-23 found **zero pull-request workflow runs**, so the required exercise
has not happened yet. The latest failed main run was
[`39982013690`](https://github.com/XinyiChenxy/ML_Dep/actions/runs/39982013690), where the `secrets`
job failed because `make scan-secrets` did not exist. That implementation defect is fixed in the
working tree, but it is not data-contract evidence and must not be submitted as the blocked commit.

- Pull request URL: **pending live GitHub run**
- Failing workflow URL: **pending live GitHub run**
- Named test: `test_schema_columns_present_and_typed`
- Expected failure: `missing columns: ['temp_c']`
- Outcome: close without merging; attach the GitHub Actions timestamp/screenshot here.

Do not replace these fields with invented evidence. A real failed Actions run is part of the Lab 4
acceptance criteria.
