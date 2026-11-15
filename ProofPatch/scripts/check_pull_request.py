"""Run the checkout PR check through the local ProofPatch API on a CI runner."""

import json
import os
from pathlib import Path
import socket
from threading import Thread
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import uvicorn


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
            with urlopen(request, timeout=150) as response:
                return json.load(response)
        finally:
            server.should_exit = True
            worker.join(timeout=5)


def main():
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        pr = event["pull_request"]
        payload = {
            "repo_path": os.environ["PROOFPATCH_TARGET"],
            "base": pr["base"]["sha"],
            "head": pr["head"]["sha"],
            "requirement": (
                "Orders of 60 or more get a discount of 10. Shipping costs 0 when the discounted "
                "subtotal is at least 50 and 5 otherwise. Checkout totals the subtotal and shipping."
            ),
            "test_source": Path(__file__).with_name("checkout_pr_fixture.py").read_text(encoding="utf-8"),
            "trusted": True,
        }
        report = compare(payload)
        verdict = report["verdict"]
        lines = [f"ProofPatch verdict: {verdict}"]
        for side in ("base", "head"):
            result = report[side]
            if result["commit"] != payload[side]:
                raise ValueError(f"API returned a different {side} commit.")
            lines.append(f"{side}: {result['commit']} ({result['status']})")
            print(f"{side} pytest output: {json.dumps(result['output'])}")
        status = {"no_regression_observed": 0, "previously_failing_test_now_passes": 0,
                  "regression": 1}.get(verdict, 2)
    except HTTPError as error:
        lines = [f"ProofPatch inconclusive: API returned HTTP {error.code}."]
        print("API response:", json.dumps(error.read().decode(errors="replace")))
        status = 2
    except (KeyError, OSError, RuntimeError, ValueError) as error:
        lines = [f"ProofPatch inconclusive: {error}"]
        status = 2

    summary = "\n".join(lines) + "\n"
    print(summary, end="")
    if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary_path).open("a", encoding="utf-8") as file:
            file.write(summary)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
