import subprocess
from typing import Literal

from fastapi import FastAPI, HTTPException

from backend.runner import git, run_test
from backend.generator import GenerationError, generate_test
from backend.scenarios import SCENARIOS, get_scenario, list_scenarios, scenario_repository

app = FastAPI(title="ProofPatch")

@app.get("/scenarios")
def scenarios():
    return list_scenarios()


@app.post("/analyze")
def analyze(mode: Literal["gemini", "fixture"] = "gemini", scenario: str = "threshold_regression"):
    try:
        selected = get_scenario(scenario)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    try:
        with scenario_repository(selected) as (repo, base, head):
            diff = git("diff", base, head, "--", "shipping.py", repo=repo).decode()
            if mode == "gemini":
                generation = generate_test(
                    git("show", f"{base}:shipping.py", repo=repo).decode(),
                    git("show", f"{head}:shipping.py", repo=repo).decode(), diff,
                    requirement=selected["requirement"],
                )
            else:
                generation = {
                    "test_source": (SCENARIOS / scenario / "test_shipping.py").read_text(encoding="utf-8"),
                    "source": "fixture", "model": None,
                    "rationale": "Handwritten reference tests for this scenario's requirement.",
                }
            test_source = generation["test_source"]
            before = run_test(base, test_source, repo=repo)
            after = run_test(head, test_source, repo=repo)
    except GenerationError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except (OSError, subprocess.SubprocessError) as error:
        raise HTTPException(status_code=503, detail="Check that Git, scenario files, and Docker are ready.") from error
    outcomes = before["status"], after["status"]
    verdict = {
        ("pass", "assertion_failed"): "regression",
        ("pass", "pass"): "no_regression_observed",
        ("assertion_failed", "pass"): "previously_failing_test_now_passes",
    }.get(outcomes, "inconclusive")
    expected = selected["expected"]
    matches_expected = (before["status"] == expected["base"]
                        and after["status"] == expected["head"]
                        and verdict == expected["verdict"])
    return {
        "base": {"commit": base, **before},
        "head": {"commit": head, **after},
        "test_source": test_source,
        "diff": diff,
        "verdict": verdict,
        "generation": {key: value for key, value in generation.items() if key != "test_source"},
        "requirement": selected["requirement"],
        "scenario": selected,
        "matches_expected": matches_expected,
    }
