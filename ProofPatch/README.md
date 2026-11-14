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

The dashboard now offers seven selectable scenarios, including refactoring, an existing bug, a bug fix, a missing dependency, and a discount/shipping interaction. `GET /scenarios` lists them. Supply a scenario ID using `POST /analyze?scenario=discount_interaction&mode=gemini`; omitting it selects `threshold_regression`. Each analysis creates an isolated temporary Git history from the checked-in scenario files, so dashboard runs no longer require `.demo-repo`. The original demo setup script remains available for standalone runner use. See [scenario layout and batch checks](demo/scenarios/README.md).

The report includes the expected base/head outcomes and whether the actual results match. A base assertion failure followed by a passing head produces `previously_failing_test_now_passes`. Both versions failing still produces `inconclusive`.

`POST /analyze` defaults to Gemini; `POST /analyze?mode=fixture` uses the original demo test. The backend sends the shipping requirement, both source versions, and their diff to Google's Gemini API. It requests JSON containing test source and rationale and validates the response before execution. The default model is `gemini-3.5-flash`; set `GEMINI_MODEL` in the backend environment to use another compatible model. No additional Python packages are needed. Environment changes require restarting the backend; `.env` files are not automatically loaded.

This MVP accepts only simple, parameterless test functions asserting `calculate_shipping(literal_total) == literal_cost`, with one approved shipping import. It rejects other generated code before Docker execution. This deliberately supports the trusted shipping demo, not arbitrary repositories. The API key never enters the test container. The same generated tests run against both revisions. Assertion failures are identified through pytest reports; collection errors, runtime errors, skipped tests, and empty suites do not prove regressions.

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
