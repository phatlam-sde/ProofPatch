import json
import unittest
from unittest.mock import Mock, patch

from backend.generator import GenerationError, generate_test, validate_test
from backend.runner import classify_result

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


if __name__ == "__main__":
    unittest.main()
