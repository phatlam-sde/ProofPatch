import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import check_pull_request as check
from backend.generator import GenerationError

CANDIDATE = "from checkout import checkout_total\n\ndef test_boundary():\n    assert checkout_total(60) == 50\n"
GENERATION = {"test_source": CANDIDATE, "source": "gemini", "model": "test", "rationale": "Boundary"}


class PRCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test")
        for name in check.CHECKOUT_FILES:
            (self.repo / name).write_text("# base source\n", encoding="utf-8")
        (self.repo / check.REQUIREMENTS_FILE).write_text("Original requirements", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD")
        (self.repo / "shipping.py").write_text("# changed source\n", encoding="utf-8")
        (self.repo / check.REQUIREMENTS_FILE).write_text("Changed requirements", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "head")
        self.head = self.git("rev-parse", "HEAD")
        self.pr = {side: {"sha": sha, "repo": {"full_name": "owner/demo"}}
                   for side, sha in [("base", self.base), ("head", self.head)]}
        self.event = self.root / "event.json"
        self.event.write_text(json.dumps({"pull_request": self.pr}), encoding="utf-8")
        self.output = self.root / "output"
        self.output.mkdir()
        self.env = patch.dict(os.environ, {"GITHUB_EVENT_PATH": str(self.event),
            "PROOFPATCH_TARGET": str(self.repo), "PROOFPATCH_OUTPUT": str(self.output),
            "GITHUB_STEP_SUMMARY": str(self.root / "summary.md")})
        self.env.start()
        self.addCleanup(self.env.stop)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args],
                                       stderr=subprocess.DEVNULL).decode().strip()

    @patch.object(check, "generate_test", return_value=GENERATION)
    def test_committed_base_requirements_and_both_sources_reach_generator(self, generate):
        (self.repo / check.REQUIREMENTS_FILE).write_text("Uncommitted rules", encoding="utf-8")
        payload, metadata, _ = check.prepare_candidate(self.pr, self.repo, self.output)
        self.assertEqual(payload["requirement"], "Original requirements")
        self.assertTrue(metadata["requirements_changed"])
        self.assertEqual(metadata["requirements_commit"], self.base)
        args, kwargs = generate.call_args
        self.assertEqual(args[0]["shipping.py"], "# base source\n")
        self.assertEqual(args[1]["shipping.py"], "# changed source\n")
        self.assertIn("+# changed source", args[2])
        self.assertEqual(kwargs["requirement"], "Original requirements")
        self.assertEqual((self.output / "test_candidate.py").read_text(), CANDIDATE)

    @patch.object(check, "generate_test", return_value=GENERATION)
    @patch.object(check, "compare")
    def test_outcomes_and_saved_evidence(self, compare, generate):
        for verdict, base_status, head_status, code in [
            ("regression", "pass", "assertion_failed", 1),
            ("no_regression_observed", "pass", "pass", 0),
            ("previously_failing_test_now_passes", "assertion_failed", "pass", 2),
            ("inconclusive", "pass", "timeout", 2),
        ]:
            with self.subTest(verdict=verdict):
                compare.return_value = {"verdict": verdict,
                    "base": {"commit": self.base, "status": base_status, "output": "base log"},
                    "head": {"commit": self.head, "status": head_status, "output": "head log"}}
                self.assertEqual(check.main(), code)
                report = json.loads((self.output / "report.json").read_text())
                self.assertEqual(report["generation"]["source"], "gemini")
                self.assertEqual(report["verdict"], "inconclusive" if code == 2 else verdict)
                self.assertEqual(compare.call_args.args[0]["test_source"], CANDIDATE)

    @patch.object(check, "generate_test", side_effect=GenerationError("Gemini returned HTTP 429"))
    @patch.object(check, "compare")
    def test_generation_failure_saves_inconclusive_without_execution(self, compare, generate):
        self.assertEqual(check.main(), 2)
        compare.assert_not_called()
        self.assertEqual(json.loads((self.output / "report.json").read_text())["verdict"], "inconclusive")

    @patch.object(check, "generate_test", return_value=GENERATION)
    @patch.object(check, "compare", side_effect=OSError("Docker unavailable"))
    def test_execution_failure_preserves_candidate(self, compare, generate):
        self.assertEqual(check.main(), 2)
        self.assertEqual((self.output / "test_candidate.py").read_text(), CANDIDATE)

    @patch.object(check, "generate_test")
    def test_missing_base_requirements_is_not_replaced_by_head_rules(self, generate):
        self.git("rm", check.REQUIREMENTS_FILE)
        self.git("commit", "-qm", "remove rules")
        self.pr["base"]["sha"] = self.git("rev-parse", "HEAD")
        with self.assertRaisesRegex(ValueError, "Base commit must contain"):
            check.prepare_candidate(self.pr, self.repo, self.output)
        generate.assert_not_called()

    @patch.object(check, "generate_test", return_value=GENERATION)
    @patch.object(check, "compare")
    def test_mismatched_api_commits_cannot_pass(self, compare, generate):
        compare.return_value = {"verdict": "no_regression_observed",
            "base": {"commit": self.head, "status": "pass", "output": ""}}
        self.assertEqual(check.main(), 2)
        self.assertEqual(json.loads((self.output / "report.json").read_text())["verdict"], "inconclusive")


if __name__ == "__main__":
    unittest.main()
