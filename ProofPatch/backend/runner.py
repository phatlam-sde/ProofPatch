from pathlib import Path
import json
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / ".demo-repo"


def classify_result(returncode, output):
    try:
        line = next(line for line in reversed(output.splitlines()) if line.startswith("PROOFPATCH_RESULT="))
        report = json.loads(line.split("=", 1)[1])
        results = report["results"]
        if report["exit_code"] != returncode or "error" in results:
            return "inconclusive"
        if returncode == 0 and "pass" in results:
            return "pass"
        if returncode == 1 and "assertion_failed" in results:
            return "assertion_failed"
    except (StopIteration, ValueError, KeyError, TypeError):
        pass
    return "inconclusive"

def git(*args):
    return subprocess.check_output(["git", "-C", str(REPO), *args], timeout=10)

def run_test(revision, test_source):
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory)
        (source / "shipping.py").write_bytes(git("show", f"{revision}:shipping.py"))
        (source / "test_shipping.py").write_text(test_source, encoding="utf-8")
        (source / "pytest_report.py").write_bytes((ROOT / "backend" / "pytest_report.py").read_bytes())
        name = f"proofpatch-{uuid.uuid4().hex}"
        command = [
            "docker", "run", "--rm", "--name", name, "--network", "none",
            "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777",
            "--memory", "256m", "--cpus", "1", "--pids-limit", "64",
            "--mount", f"type=bind,source={source},target=/src,readonly",
            "proofpatch-runner:local", "python", "-B", "pytest_report.py",
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=10)
            return {"status": "timeout", "output": "Test execution exceeded 30 seconds."}

        output = result.stdout + result.stderr
        status = classify_result(result.returncode, output)
        display_output = "\n".join(line for line in output.splitlines() if not line.startswith("PROOFPATCH_RESULT="))
        return {"status": status, "output": display_output}
