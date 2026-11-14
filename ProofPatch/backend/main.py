import subprocess
from typing import Literal

from fastapi import FastAPI, HTTPException

from backend.runner import ROOT, git, run_test
from backend.generator import GenerationError, REQUIREMENT, generate_test

app = FastAPI(title="ProofPatch")

@app.post("/analyze")
def analyze(mode: Literal["gemini", "fixture"] = "gemini"):
    try:
        base = git("rev-parse", "HEAD~1").decode().strip()
        head = git("rev-parse", "HEAD").decode().strip()
        diff = git("diff", base, head, "--", "shipping.py").decode()
        if mode == "gemini":
            generation = generate_test(
                git("show", f"{base}:shipping.py").decode(),
                git("show", f"{head}:shipping.py").decode(), diff,
            )
        else:
            generation = {"test_source": (ROOT / "demo" / "test_shipping.py").read_text(encoding="utf-8"),
                          "source": "fixture", "model": None,
                          "rationale": "Handwritten demo test for free shipping at the inclusive threshold."}
        test_source = generation["test_source"]
        before = run_test(base, test_source)
        after = run_test(head, test_source)
    except GenerationError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
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
        "generation": {key: value for key, value in generation.items() if key != "test_source"},
        "requirement": REQUIREMENT,
    }
