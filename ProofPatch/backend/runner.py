from pathlib import Path
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / ".demo-repo"

def git(*args):
    return subprocess.check_output(["git", "-C", str(REPO), *args], timeout=10)

def run_test(revision, test_source):
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory)
        (source / "shipping.py").write_bytes(git("show", f"{revision}:shipping.py"))
        (source / "test_shipping.py").write_text(test_source, encoding="utf-8")
        name = f"proofpatch-{uuid.uuid4().hex}"
        command = [
            "docker", "run", "--rm", "--name", name, "--network", "none",
            "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--memory", "256m", "--cpus", "1", "--pids-limit", "64",
            "--mount", f"type=bind,source={source},target=/src,readonly",
            "proofpatch-runner:local", "python", "-B", "-m", "pytest",
            "-q", "-p", "no:cacheprovider", "test_shipping.py",
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=10)
            return {"status": "timeout", "output": "Test execution exceeded 30 seconds."}

        output = result.stdout + result.stderr
        status = "inconclusive"
        if result.returncode == 0:
            status = "pass"
        elif result.returncode == 1 and "assert 5 == 0" in output:
            # The starter recognizes the single known assertion in its fixed demo.
            status = "assertion_failed"
        return {"status": status, "output": output}
