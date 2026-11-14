"""Executed only inside the Docker runner; emit structured pytest outcomes."""
import json

import pytest


class Reporter:
    def __init__(self):
        self.results = []

    def pytest_runtest_makereport(self, item, call):
        if call.excinfo is not None:
            status = "assertion_failed" if call.when == "call" and call.excinfo.errisinstance(AssertionError) else "error"
        else:
            status = "pass" if call.when == "call" else "ok"
        self.results.append(status)


reporter = Reporter()
exit_code = pytest.main(["-q", "-p", "no:cacheprovider", "test_shipping.py"], plugins=[reporter])
print("PROOFPATCH_RESULT=" + json.dumps({"exit_code": int(exit_code), "results": reporter.results}))
raise SystemExit(exit_code)
