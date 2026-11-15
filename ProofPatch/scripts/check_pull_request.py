"""Run the checkout PR check through the local ProofPatch API on a CI runner."""

import json
import os
from pathlib import Path
import socket
import re
import subprocess
from threading import Thread
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import uvicorn

from backend.generator import GenerationError, generate_test
from backend.main import CHECKOUT_FILES
from backend.runner import git

REQUIREMENTS_FILE = "proofpatch-requirements.md"


def prepare_candidate(pr, repo, output):
    """Read committed inputs; never import or execute the target on the host."""
    base, head = pr["base"]["sha"], pr["head"]["sha"]
    if not all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in (base, head)):
        raise ValueError("PR base and head must be full commit SHAs.")
    metadata = {"base": base, "head": head, "requirements_file": REQUIREMENTS_FILE,
                "requirements_commit": base, "review_status": "candidate_not_reviewed"}
    (output / "inputs.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    try:
        requirement = git("show", f"{base}:{REQUIREMENTS_FILE}", repo=repo).decode("utf-8").strip()
    except (subprocess.SubprocessError, UnicodeError):
        raise ValueError(f"Base commit must contain a UTF-8 {REQUIREMENTS_FILE}.") from None
    if not requirement or len(requirement) > 4000:
        raise ValueError("Requirements must contain 1 to 4000 characters.")
    metadata["requirements_changed"] = bool(git(
        "diff", "--no-ext-diff", "--no-textconv", "--name-only", base, head,
        "--", REQUIREMENTS_FILE, repo=repo).strip())
    (output / "inputs.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (output / REQUIREMENTS_FILE).write_text(requirement, encoding="utf-8")
    sources = [{name: git("show", f"{sha}:{name}", repo=repo).decode("utf-8")
                for name in CHECKOUT_FILES} for sha in (base, head)]
    diff = git("diff", "--no-ext-diff", "--no-textconv", base, head, "--",
               *CHECKOUT_FILES, repo=repo).decode("utf-8")
    (output / "code-diff.patch").write_text(diff, encoding="utf-8")
    generation = generate_test(*sources, diff, requirement=requirement,
                               module="checkout", function_name="checkout_total")
    # Persist before execution so Docker/API failures do not lose the candidate.
    (output / "test_candidate.py").write_text(generation["test_source"], encoding="utf-8")
    (output / "generation.json").write_text(json.dumps(generation, indent=2), encoding="utf-8")
    return {"repo_path": str(repo), "base": base, "head": head,
            "requirement": requirement, "test_source": generation["test_source"],
            "trusted": True}, metadata, generation


def wait_for_api(server, worker):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and worker.is_alive():
        if server.started:
            return
        time.sleep(0.05)
    raise RuntimeError("ProofPatch API did not start.")


def compare(payload):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        # Import before starting the thread so script launch errors reach the CI summary.
        from backend.main import app

        server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
        worker = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        worker.start()
        try:
            wait_for_api(server, worker)
            request = Request(
                f"http://127.0.0.1:{port}/analyze/local",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urlopen(request, timeout=180) as response:
                return json.load(response)
        finally:
            server.should_exit = True
            worker.join(timeout=5)


def main():
    output = Path(os.environ.get("PROOFPATCH_OUTPUT", "proofpatch-results")).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {"verdict": "inconclusive", "review_status": "candidate_not_reviewed"}
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        pr = event["pull_request"]
        if pr["head"]["repo"]["full_name"] != pr["base"]["repo"]["full_name"]:
            raise ValueError("Only trusted same-repository PRs are supported.")
        payload, metadata, generation = prepare_candidate(
            pr, Path(os.environ["PROOFPATCH_TARGET"]).resolve(), output)
        report = compare(payload)
        report["inputs"] = metadata
        report["generation"] = {key: value for key, value in generation.items() if key != "test_source"}
        report["review_status"] = "candidate_not_reviewed"
        verdict = report["verdict"]
        lines = [f"ProofPatch verdict: {verdict}"]
        lines.append(f"Requirements: {REQUIREMENTS_FILE} from base commit {payload['base']}.")
        if metadata["requirements_changed"]:
            lines.append("Requirements changed in this PR: review needed; base requirements were used.")
        lines.append("Generated tests are candidates, not reviewed or verified tests.")
        for side in ("base", "head"):
            result = report[side]
            if result["commit"] != payload[side]:
                raise ValueError(f"API returned a different {side} commit.")
            lines.append(f"{side}: {result['commit']} ({result['status']})")
            print(f"{side} pytest output: {json.dumps(result['output'])}")
        # A candidate failing on the base has not established a reliable baseline.
        status = {"no_regression_observed": 0, "regression": 1}.get(verdict, 2)
        if status == 2:
            report["comparison_verdict"] = verdict
            report["verdict"] = "inconclusive"
            lines[0] = "ProofPatch verdict: inconclusive"
            lines.append("The candidate did not establish a passing base and a conclusive head result.")
    except HTTPError as error:
        lines = [f"ProofPatch inconclusive: API returned HTTP {error.code}."]
        print("API response:", json.dumps(error.read().decode(errors="replace")))
        status = 2
        report = {"verdict": "inconclusive", "error": lines[0]}
    except (KeyError, OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        lines = [f"ProofPatch inconclusive: {error}"]
        status = 2
        report = {"verdict": "inconclusive", "error": str(error)}
    except GenerationError as error:
        lines = [f"ProofPatch inconclusive: {error}"]
        status = 2
        report = {"verdict": "inconclusive", "error": str(error)}

    summary = "\n".join(lines) + "\n"
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (output / "summary.md").write_text(summary, encoding="utf-8")
    print(summary, end="")
    if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary_path).open("a", encoding="utf-8") as file:
            file.write(summary)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
