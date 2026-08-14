"""scripts/_llm.py 순수 함수 단위 테스트."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import _llm  # noqa: E402


class RetryableTest(unittest.TestCase):
    def test_rate_limit_and_server_errors_are_retryable(self):
        for status in (429, 500, 502, 503, 529):
            self.assertTrue(_llm.retryable(status), status)

    def test_client_errors_are_fatal(self):
        for status in (400, 401, 403, 404, 422):
            self.assertFalse(_llm.retryable(status), status)


if __name__ == "__main__":
    unittest.main()
