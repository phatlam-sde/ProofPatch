import json
import unittest
import requests
from unittest.mock import Mock, patch

from backend.generator import GenerationError, generate_test, validate_test
from backend.runner import classify_result
from backend.scenarios import SCENARIOS, get_scenario, list_scenarios

VALID = "from shipping import calculate_shipping\n\ndef test_threshold():\n    assert calculate_shipping(50) == 0\n"


class GeneratorTests(unittest.TestCase):
    def test_valid_boundary_test(self):
        self.assertEqual(validate_test(VALID), VALID)

    def test_rejects_executable_extras(self):
        for source in [VALID + "\nimport os", VALID.replace("50", "__import__('os').getcwd()"),
                       VALID.replace("def test_threshold():", "@print('hi')\ndef test_threshold():"),
                       VALID.replace("assert calculate_shipping(50) == 0", "pass"),
                       VALID + VALID.split("\n", 1)[1]]:
            with self.subTest(source=source), self.assertRaises(GenerationError):
                validate_test(source)

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    @patch("backend.generator.requests.post")
    def test_structured_generation(self, post):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {"candidates": [{"finishReason": "STOP", "content": {
            "parts": [{"text": json.dumps({"test_source": VALID, "rationale": "Check the threshold."})}]}}]}
        self.assertEqual(generate_test("base", "head", "diff")["source"], "gemini")
        self.assertEqual(post.call_args.kwargs["headers"]["x-goog-api-key"], "test-key")

    @patch.dict("os.environ", {"GEMINI_API_KEY": ""})
    @patch("backend.generator.requests.post")
    def test_missing_key_does_not_call_api(self, post):
        with self.assertRaises(GenerationError):
            generate_test("", "", "")
        post.assert_not_called()

    @patch.dict("os.environ", {"GEMINI_API_KEY": "secret-test-key"})
    @patch("backend.generator.requests.post", return_value=Mock(status_code=429))
    def test_quota_error_is_actionable_and_redacted(self, post):
        with self.assertRaisesRegex(GenerationError, "HTTP 429") as error:
            generate_test("", "", "")
        self.assertNotIn("secret-test-key", str(error.exception))

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    @patch("backend.generator.requests.post")
    def test_transport_errors_are_distinguished(self, post):
        for error, message in [
            (requests.Timeout(), "timed out"),
            (requests.exceptions.SSLError(), "secure connection"),
            (requests.ConnectionError(), "establish or maintain"),
        ]:
            with self.subTest(error=type(error).__name__):
                post.side_effect = error
                with self.assertRaisesRegex(GenerationError, message):
                    generate_test("", "", "")

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    @patch("backend.generator.requests.post", return_value=Mock(status_code=503))
    def test_service_unavailable_is_not_reported_as_quota(self, post):
        with self.assertRaisesRegex(GenerationError, "temporarily unavailable or overloaded"):
            generate_test("", "", "")


class RunnerTests(unittest.TestCase):
    def test_classification(self):
        for code, results, expected in [
            (0, ["ok", "pass", "ok"], "pass"),
            (1, ["ok", "assertion_failed", "ok"], "assertion_failed"),
            (1, ["error"], "inconclusive"),
            (1, ["assertion_failed", "error"], "inconclusive"),
            (2, [], "inconclusive"), (5, [], "inconclusive"), (0, [], "inconclusive"),
        ]:
            with self.subTest(code=code, results=results):
                output = "PROOFPATCH_RESULT=" + json.dumps({"exit_code": code, "results": results})
                self.assertEqual(classify_result(code, output), expected)
        self.assertEqual(classify_result(1, "assert 5 == 0"), "inconclusive")


class ScenarioTests(unittest.TestCase):
    def test_catalog_fixtures_are_valid_generated_test_shapes(self):
        catalog = list_scenarios()
        self.assertEqual(len({item["id"] for item in catalog}), 7)
        for scenario in catalog:
            with self.subTest(scenario=scenario["id"]):
                folder = SCENARIOS / scenario["id"]
                validate_test((folder / "test_shipping.py").read_text(encoding="utf-8"))
                for version in ("base", "head"):
                    self.assertTrue((folder / version / "shipping.py").is_file())

    def test_unknown_scenario_cannot_select_arbitrary_paths(self):
        with self.assertRaises(ValueError):
            get_scenario("../../backend")

    @patch("backend.main.generate_test")
    @patch("backend.main.scenario_repository")
    @patch("backend.main.git", return_value=b"source")
    @patch("backend.main.run_test")
    def test_scenario_requirement_and_bug_fix_verdict(self, run_test, git, repository, generate):
        from backend.main import analyze
        repository.return_value.__enter__.return_value = ("repo", "base", "head")
        generate.return_value = {"test_source": VALID, "rationale": "Boundary", "source": "gemini", "model": "test"}
        run_test.side_effect = [{"status": "assertion_failed", "output": ""}, {"status": "pass", "output": ""}]
        report = analyze(scenario="bug_fix")
        self.assertTrue(report["matches_expected"])
        self.assertEqual(report["verdict"], "previously_failing_test_now_passes")
        self.assertEqual(generate.call_args.kwargs["requirement"], get_scenario("bug_fix")["requirement"])


if __name__ == "__main__":
    unittest.main()
