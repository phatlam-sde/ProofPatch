# ProofPatch

Compare two revisions of a trusted Python demo repository. Run the same regression test in a separate Docker container for each revision and report the result.

| Path | Purpose |
|---|---|
| backend/main.py | FastAPI endpoint and verdict |
| backend/runner.py | Export Git revisions and run pytest in Docker |
| backend/generator.py | Request and validate targeted Gemini tests |
| backend/pytest_report.py | Collect structured pytest results inside Docker |
| frontend/app.py | Streamlit dashboard |
| demo/ | Known-good source, buggy source, and fixture test |
| demo/scenarios/ | Seven scenarios with requirements, source pairs, and reference tests |
| backend/scenarios.py | Load scenarios and create a temporary Git repository per analysis |
| scripts/check_scenarios.py | Run the scenario collection with fixture or Gemini tests |
| scripts/new_demo.py | Create a local demo repository with two commits |
| Dockerfile | Build the Python test runner |

## Run the starter on Windows

Extract the ZIP, then open PowerShell in the extracted ProofPatch folder. Have Python 3.11+, Git, and Docker running locally.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/new_demo.py
docker build -t proofpatch-runner:local .
```

These commands create a local Python environment, install app dependencies, create .demo-repo with two commits, and build the pytest runner image. Expect the script to print the two commit IDs and Docker to tag the finished image.

In that PowerShell window, set the API key and start the API. The key stays in the backend environment and is not sent to Docker or the dashboard. The secure prompt keeps it out of command history. If GEMINI_API_KEY is already set, skip the first two lines. Expect Uvicorn to report that the server is running on port 8000.

```powershell
$geminiSecret = Read-Host 'Gemini API key' -AsSecureString
$env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new('', $geminiSecret).Password
.\.venv\Scripts\python.exe -m uvicorn backend.main:app
```

In a second PowerShell window in the same extracted folder, start the dashboard. This opens the Streamlit app at http://localhost:8501. Select **Generate with Gemini**, then **Analyze demo**. Expect a generated test and rationale, base **pass**, head **assertion_failed**, and verdict **regression**. The handwritten fallback is selectable explicitly; API failures never silently substitute a fixture.

```powershell
.\.venv\Scripts\python.exe -m streamlit run frontend/app.py
```

## Gemini integration

To compare commits in the separate `checkout-test-repo`, select **Local checkout repository** in the dashboard. Enter the absolute path to that repository, use `baseline` and `regression` as the revisions, and enter the checkout rules from its README as the expected behavior. Confirm you trust the repository and select **Compare commits**. This mode reads `checkout.py`, `pricing.py`, and `shipping.py` at the selected commits without checking them out. It supports commit SHAs and tags.

Choose **Provide a test** to run the prefilled checkout assertion without calling Gemini. Expect the base to pass, the new commit to fail with `55 == 50`, and the verdict to be **regression**. **Generate with Gemini** sends those three files from both commits, their diff, and the expected behavior to the Gemini API and runs the generated test against both commits in Docker.

The dashboard now offers seven selectable scenarios, including refactoring, an existing bug, a bug fix, a missing dependency, and a discount/shipping interaction. `GET /scenarios` lists them. Supply a scenario ID using `POST /analyze?scenario=discount_interaction&mode=gemini`; omitting it selects `threshold_regression`. Each analysis creates an isolated temporary Git history from the checked-in scenario files, so dashboard runs no longer require `.demo-repo`. The original demo setup script remains available for standalone runner use. See [scenario layout and batch checks](demo/scenarios/README.md).

The report includes the expected base/head outcomes and whether the actual results match. A base assertion failure followed by a passing head produces `previously_failing_test_now_passes`. Both versions failing still produces `inconclusive`.

## GitHub pull request check

Publish the ProofPatch commit containing `.github/workflows/checkout-regression.yml` first. In the separate checkout repository, add `.github/workflows/proofpatch.yml` to the branch containing the working checkout code. Use the following contents and replace `PROOFPATCH_COMMIT_SHA` with the full SHA of the published ProofPatch commit:

```yaml
name: ProofPatch
on:
  pull_request:
    types: [opened, synchronize, reopened, edited]
permissions:
  contents: read
jobs:
  checkout-regression:
    uses: phatlam-sde/ProofPatch/.github/workflows/checkout-regression.yml@PROOFPATCH_COMMIT_SHA
```

This setup assumes the checkout repository can access the reusable ProofPatch workflow and read its source. The job runs only for PRs from branches in the same repository. It uses the PR event's base and head SHAs, calls the existing API with the supplied checkout test, and writes both outcomes to the job summary. It requires no Gemini key.

To demo it, open a PR into the branch containing the working checkout and the caller workflow, from a branch containing the same workflow plus the shipping regression. Expect the check to fail with the `regression` verdict and an assertion showing `55 == 50` in the step log. Push a fix restoring the inclusive threshold and expect a successful check. An inconclusive comparison fails the check with a separate verdict, so Docker or API failures cannot appear as a pass.

`POST /analyze` defaults to Gemini; `POST /analyze?mode=fixture` uses the original demo test. The backend sends the shipping requirement, both source versions, and their diff to Google's Gemini API. It requests JSON containing test source and rationale and validates the response before execution. The default model is `gemini-3.5-flash`; set `GEMINI_MODEL` in the backend environment to use another compatible model. No additional Python packages are needed. Environment changes require restarting the backend; `.env` files are not automatically loaded.

## Test validation

The built-in scenarios accept simple, parameterless tests asserting `calculate_shipping(literal_total) == literal_cost`. The local checkout comparison accepts the same shape with `checkout_total`. The API key never enters the test container. The same tests run against both revisions. Assertion failures are identified through pytest reports; collection errors, runtime errors, skipped tests, and empty suites do not prove regressions.

In PowerShell in the ProofPatch folder, run the backend checks below. They use mocked Gemini responses and check validation, missing credentials, quota errors, and verdict classification without spending API quota. Expect all tests to pass.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

API reference: [Gemini generateContent](https://ai.google.dev/api/generate-content).

## Next steps

1. Confirm the fixed shipping test produces pass → assertion failure. Check that missing dependencies and timeouts are inconclusive.
2. Evaluate generated test quality across repeated runs and additional boundary cases.
3. Expand beyond the shipping interface to multi-function examples after evaluating the seven included scenarios.
4. Keep the MVP local and limited to trusted demo repositories. Before accepting external repositories or relaxing generated-test restrictions, design and validate stronger isolation for untrusted code.

Gemini generation is implemented; the fixed fixture remains available for offline demos.
