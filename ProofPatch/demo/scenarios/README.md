# Regression scenarios

`catalog.json` contains each scenario's title, requirement, expected base/head statuses, and expected verdict. Each scenario directory contains `base/shipping.py`, `head/shipping.py`, and a handwritten `test_shipping.py` reference suite.

| Scenario | Expected behavior |
| --- | --- |
| threshold_regression | Catch the inclusive threshold changing to an exclusive threshold |
| correct_refactor | Both versions pass after an equivalent rewrite |
| identical_revision | Run against the same commit twice; both pass |
| existing_bug | Both versions fail the requirement; regression verdict is inconclusive |
| bug_fix | The previously failing test now passes |
| missing_dependency | New version cannot import; result is inconclusive |
| discount_interaction | Applying a discount too early incorrectly adds shipping for totals from 50 to below 60 |

The backend builds a temporary Git repository per analysis and removes it after both runs. The identical-revision scenario uses the same commit ID twice. The other scenarios create two commits from the checked-in source files. Commit IDs can differ between analyses because these histories are recreated. The original `.demo-repo` is only used by the original standalone demo script and default runner helpers.

Gemini receives the requirement, source versions, and diff. Expected outcomes and reference tests are used to evaluate its results and are not included in the generation prompt. Matching an expected outcome is a scenario check, not a measure of complete test coverage. Gemini tests can differ between runs.

## Running the scenarios

In PowerShell in the `ProofPatch` directory, with Docker running, execute:

```powershell
.\.venv\Scripts\python.exe scripts/check_scenarios.py
```

This runs every handwritten reference suite against both revisions through the backend and Docker. Expect seven `MATCH` lines and zero mismatches or errors. It does not call Gemini.

In the same directory, with `GEMINI_API_KEY` set, execute:

```powershell
.\.venv\Scripts\python.exe scripts/check_scenarios.py --mode gemini --repeat 3
```

This makes 21 generation requests, runs each generated suite against both revisions, and prints whether the observed statuses and verdict match the catalog. Mismatches print the test and execution output for investigation. The script exits with a nonzero status if any analysis fails or differs from expectations.

For interactive use, restart the backend, refresh the dashboard, and choose a scenario and test source. The dashboard displays expected and actual outcomes.

All scenarios currently use the `calculate_shipping(total)` interface and shipping costs of 0 or 5. Adding a different function or multiple modules requires updating the generator validator and runner as well as adding scenario files.
