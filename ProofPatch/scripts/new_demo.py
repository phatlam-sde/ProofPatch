from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
repo = ROOT / ".demo-repo"
repo.mkdir()

def git(*args):
    subprocess.run(["git", "-C", str(repo), *args], check=True)

git("init", "--template=")
for version, message in [("base", "Add free shipping threshold"), ("head", "Change threshold comparison")]:
    shutil.copyfile(ROOT / "demo" / version / "shipping.py", repo / "shipping.py")
    git("add", "shipping.py")
    git("-c", "user.name=ProofPatch Demo", "-c", "user.email=proofpatch@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "-m", message)

git("log", "-2", "--oneline")
