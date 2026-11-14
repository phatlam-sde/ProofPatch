# ProofPatch

Compare two revisions of a trusted Python demo repository. Run the same regression test in a separate Docker container for each revision and report the result.

| Path | Purpose |
|---|---|
| backend/main.py | FastAPI endpoint and verdict |
| backend/runner.py | Export Git revisions and run pytest in Docker |
| frontend/app.py | Streamlit dashboard |
| demo/ | Known-good source, buggy source, and fixture test |
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

In that PowerShell window, start the API. This serves the analysis endpoint on localhost port 8000. Expect Uvicorn to report that the server is running.

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app
```

In a second PowerShell window in the same extracted folder, start the dashboard. This opens the Streamlit app at http://localhost:8501. Select **Analyze demo**. Expect base **pass**, head **assertion_failed**, and verdict **regression**.

```powershell
.\.venv\Scripts\python.exe -m streamlit run frontend/app.py
```

## Build order

1. Confirm the fixed shipping test produces pass → assertion failure. Check that missing dependencies and timeouts are inconclusive.
2. Add backend/generator.py. Send Gemini the Git diff, relevant source, and shipping requirement. Request a structured response with test source and rationale. Read GEMINI_API_KEY on the backend and keep it out of the runner. Keep the fixed test available as a demo fallback and label its source in the UI.
3. Add a second independent regression scenario, and show the diff, test source, and both results. Try an unchanged pair to confirm pass → pass.
4. Keep the MVP local and limited to trusted demo repositories. Before accepting external repositories or executing generated tests, design and validate stronger isolation for untrusted code.

The starter uses a fixed fixture test. Gemini generation is the next implementation milestone.
