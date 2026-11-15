import logging
import subprocess
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from backend.runner import git, run_test
from backend.generator import GenerationError, generate_test, validate_test
from backend.scenarios import SCENARIOS, get_scenario, list_scenarios, scenario_repository

app = FastAPI(title="ProofPatch")
logger = logging.getLogger(__name__)
CHECKOUT_FILES = ("checkout.py", "pricing.py", "shipping.py")


class LocalComparison(BaseModel):
    repo_path: str = Field(min_length=1, max_length=1024)
    base: str = Field(min_length=1, max_length=256)
    head: str = Field(min_length=1, max_length=256)
    requirement: str = Field(min_length=1, max_length=4000)
    test_source: str | None = Field(default=None, min_length=1, max_length=12000)
    trusted: Literal[True]


def comparison_report(base, head, before, after, diff, generation, requirement):
    verdict = {
        ("pass", "assertion_failed"): "regression",
        ("pass", "pass"): "no_regression_observed",
        ("assertion_failed", "pass"): "previously_failing_test_now_passes",
    }.get((before["status"], after["status"]), "inconclusive")
    return {
        "base": {"commit": base, **before},
        "head": {"commit": head, **after},
        "test_source": generation["test_source"],
        "diff": diff,
        "verdict": verdict,
        "generation": {key: value for key, value in generation.items() if key != "test_source"},
        "requirement": requirement,
    }


@app.post("/analyze/local")
def analyze_local(request: LocalComparison):
    try:
        path = Path(request.repo_path.strip()).expanduser()
        if not path.is_absolute() or not path.is_dir():
            raise ValueError
        repo = path.resolve()
        # Require a repository root instead of silently finding a parent repository.
        root = git("rev-parse", "--show-toplevel", repo=repo).decode().strip()
        if Path(root).resolve() != repo:
            raise ValueError
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise HTTPException(400, "Enter the absolute path to a local Git repository root.") from error

    try:
        base, head = (
            git("rev-parse", "--verify", "--end-of-options", f"{ref.strip()}^{{commit}}", repo=repo)
            .decode().strip() for ref in (request.base, request.head)
        )
    except subprocess.SubprocessError as error:
        raise HTTPException(400, "Both revisions must resolve to commits in this repository.") from error

    try:
        sources = [
            {name: git("show", f"{commit}:{name}", repo=repo).decode() for name in CHECKOUT_FILES}
            for commit in (base, head)
        ]
        diff = git("diff", "--no-ext-diff", "--no-textconv", base, head, "--", *CHECKOUT_FILES,
                   repo=repo).decode(errors="replace")
    except (UnicodeError, subprocess.SubprocessError) as error:
        raise HTTPException(400, "Both commits must contain UTF-8 checkout.py, pricing.py, and shipping.py.") from error

    requirement = request.requirement.strip()
    if not requirement:
        raise HTTPException(400, "Enter the intended checkout behavior.")
    profile = {"module": "checkout", "function_name": "checkout_total"}
    try:
        if request.test_source is None:
            generation = generate_test(*sources, diff, requirement=requirement, **profile)
        else:
            generation = {
                "test_source": validate_test(request.test_source, **profile),
                "source": "provided", "model": None,
                "rationale": "The same supplied test was run against both commits.",
            }
    except GenerationError as error:
        raise HTTPException(502 if request.test_source is None else 400, str(error)) from error
    try:
        before = run_test(base, generation["test_source"], repo=repo, files=CHECKOUT_FILES)
        after = run_test(head, generation["test_source"], repo=repo, files=CHECKOUT_FILES)
    except (OSError, subprocess.SubprocessError) as error:
        logger.exception("Local checkout comparison could not run.")
        raise HTTPException(503, "Could not run both revisions. Check Git and Docker.") from error
    return comparison_report(base, head, before, after, diff, generation, requirement)

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
    report = comparison_report(base, head, before, after, diff, generation, selected["requirement"])
    expected = selected["expected"]
    matches_expected = (before["status"] == expected["base"]
                        and after["status"] == expected["head"]
                        and report["verdict"] == expected["verdict"])
    return {**report, "scenario": selected, "matches_expected": matches_expected}
