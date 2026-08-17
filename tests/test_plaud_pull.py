"""scripts/plaud_pull.py 순수 함수 단위 테스트."""
import os
import shutil
import sys
import tempfile
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


class PendingStateTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        self.path = os.path.join(d, "pending_ids.txt")
        self.addCleanup(shutil.rmtree, d, True)

    def test_load_missing_file_returns_empty(self):
        self.assertEqual(plaud_pull.load_pending(self.path), {})

    def test_roundtrip(self):
        plaud_pull.save_pending(self.path, {FID1: 3, FID2: 95})
        self.assertEqual(plaud_pull.load_pending(self.path), {FID1: 3, FID2: 95})

    def test_line_without_count_defaults_to_zero(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(f"{FID1}\n")
        self.assertEqual(plaud_pull.load_pending(self.path), {FID1: 0})

    def test_malformed_count_defaults_to_zero(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(f"{FID1}\tNaN\n{FID2}\t7\n")
        self.assertEqual(plaud_pull.load_pending(self.path), {FID1: 0, FID2: 7})

    def test_save_overwrites_previous_content(self):
        plaud_pull.save_pending(self.path, {FID1: 1, FID2: 2})
        plaud_pull.save_pending(self.path, {FID2: 3})
        self.assertEqual(plaud_pull.load_pending(self.path), {FID2: 3})


class UnexpectedHostTest(unittest.TestCase):
    def test_s3_and_cloudfront_are_expected(self):
        self.assertFalse(plaud_pull.unexpected_host(
            "https://bucket.s3.ap-northeast-2.amazonaws.com/a.mp3?sig=x"))
        self.assertFalse(plaud_pull.unexpected_host("https://d111.cloudfront.net/a.mp3"))

    def test_other_hosts_are_unexpected(self):
        self.assertTrue(plaud_pull.unexpected_host("https://evil.example.com/a.mp3"))
        # 서브도메인 위장 (amazonaws.com.evil.com) 도 잡혀야 함
        self.assertTrue(plaud_pull.unexpected_host("https://x.amazonaws.com.evil.com/a.mp3"))

    def test_unparsable_url_is_unexpected(self):
        self.assertTrue(plaud_pull.unexpected_host("https://["))


if __name__ == "__main__":
    unittest.main()
