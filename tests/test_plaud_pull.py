"""scripts/plaud_pull.py 순수 함수 단위 테스트."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import plaud_pull  # noqa: E402

FID1 = "0123456789abcdef0123456789abcdef"
FID2 = "fedcba9876543210fedcba9876543210"


class ParseFilesOutputTest(unittest.TestCase):
    def test_extracts_id_and_date(self):
        text = f"{FID1}  회의 녹음  2026-06-10 09:30\n"
        items = plaud_pull.parse_files_output(text, default_date="2026-01-01")
        self.assertEqual(items, [(FID1, "2026-06-10")])

    def test_multiple_lines_and_noise(self):
        text = (
            "Your recordings (page 1):\n"
            f"{FID1}  메모 A  2026-06-09\n"
            "---\n"
            f"{FID2}  메모 B  2026-06-11\n"
        )
        items = plaud_pull.parse_files_output(text, default_date="2026-01-01")
        self.assertEqual(items, [(FID1, "2026-06-09"), (FID2, "2026-06-11")])

    def test_missing_date_falls_back_to_default(self):
        text = f"{FID1}  날짜 없는 줄\n"
        items = plaud_pull.parse_files_output(text, default_date="2026-02-02")
        self.assertEqual(items, [(FID1, "2026-02-02")])

    def test_short_hex_is_not_an_id(self):
        items = plaud_pull.parse_files_output("0123abcd  too short\n", default_date="2026-01-01")
        self.assertEqual(items, [])

    def test_empty_output(self):
        self.assertEqual(plaud_pull.parse_files_output("", default_date="2026-01-01"), [])


if __name__ == "__main__":
    unittest.main()
