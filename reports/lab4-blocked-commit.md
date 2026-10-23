# Lab 4 — blocked bad commit evidence

This file records the required external CI exercise. Create a short-lived branch that removes
`temp_c` from the generated fixture, open a pull request, and close it without merging after CI
fails.

The exercise was run against the deliberately broken `lab4-bad-contract-evidence` branch. The
secret scan passed, the data-contract job failed, and the downstream image build was skipped, so
the bad producer change did not ship.

- Pull request URL: https://github.com/XinyiChenxy/ML_Dep/pull/1
- Failing workflow URL: https://github.com/XinyiChenxy/ML_Dep/actions/runs/39986069085/job/120525462831?pr=1
- Named test: `test_schema_columns_present_and_typed`
- Observed failure: `AssertionError: missing columns: ['temp_c']`
- Workflow outcome: 3 data tests failed, 7 passed; model-behaviour/service tests and image build
  were skipped after the contract gate exited with code 1.
- Pull-request outcome: close without merging after preserving the Actions log and screenshot.

Do not replace these fields with invented evidence. A real failed Actions run is part of the Lab 4
acceptance criteria.
