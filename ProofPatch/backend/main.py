import subprocess

from fastapi import FastAPI, HTTPException

from backend.runner import ROOT, git, run_test

app = FastAPI(title="ProofPatch")

@app.post("/analyze")
def analyze():
    try:
        base = git("rev-parse", "HEAD~1").decode().strip()
        head = git("rev-parse", "HEAD").decode().strip()
        diff = git("diff", base, head, "--", "shipping.py").decode()
        test_source = (ROOT / "demo" / "test_shipping.py").read_text(encoding="utf-8")
        before = run_test(base, test_source)
        after = run_test(head, test_source)
    except (OSError, subprocess.SubprocessError) as error:
        raise HTTPException(status_code=503, detail="Check that the demo repository and Docker are ready.") from error
    outcomes = before["status"], after["status"]
    verdict = {
        ("pass", "assertion_failed"): "regression",
        ("pass", "pass"): "no_regression_observed",
    }.get(outcomes, "inconclusive")
    return {
        "base": {"commit": base, **before},
        "head": {"commit": head, **after},
        "test_source": test_source,
        "diff": diff,
        "verdict": verdict,
    }
