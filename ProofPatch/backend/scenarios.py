"""Load checked-in scenarios and build isolated Git histories for analysis."""
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import tempfile

SCENARIOS = Path(__file__).resolve().parents[1] / "demo" / "scenarios"


def list_scenarios():
    return json.loads((SCENARIOS / "catalog.json").read_text(encoding="utf-8"))


def get_scenario(scenario_id):
    for scenario in list_scenarios():
        if scenario["id"] == scenario_id:
            return scenario
    raise ValueError("Unknown scenario.")


@contextmanager
def scenario_repository(scenario):
    # Separate repositories prevent concurrent analyses from changing each other's HEAD.
    with tempfile.TemporaryDirectory(prefix="proofpatch-scenario-") as directory:
        repo = Path(directory)

        def git(*args):
            return subprocess.check_output(["git", "-C", str(repo), *args], timeout=10,
                                           stderr=subprocess.PIPE)

        git("init", "--template=")
        revisions = []
        for version in ("base", "head"):
            source = SCENARIOS / scenario["id"] / version / "shipping.py"
            (repo / "shipping.py").write_bytes(source.read_bytes())
            git("add", "shipping.py")
            git("-c", "user.name=ProofPatch Demo", "-c", "user.email=proofpatch@example.invalid",
                "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
                "commit", "--allow-empty", "-m", version)
            revisions.append(git("rev-parse", "HEAD").decode().strip())
            if scenario.get("same_revision"):
                revisions.append(revisions[0])
                break
        yield repo, revisions[0], revisions[1]
