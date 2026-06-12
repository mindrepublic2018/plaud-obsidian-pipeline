"""scripts/process_inbox.py 순수 함수 단위 테스트."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import process_inbox  # noqa: E402


class SlugifyTest(unittest.TestCase):
    def test_strips_forbidden_filename_chars(self):
        self.assertEqual(process_inbox.slugify('a/b\\c:d*e?f"g<h>i|j'), "a b c d e f g h i j")

    def test_collapses_whitespace(self):
        self.assertEqual(process_inbox.slugify("회의   메모\n정리"), "회의 메모 정리")

    def test_truncates_to_60_chars(self):
        self.assertEqual(len(process_inbox.slugify("가" * 100)), 60)

    def test_empty_falls_back_to_default(self):
        self.assertEqual(process_inbox.slugify("///"), "음성메모")


class ParseSummaryTest(unittest.TestCase):
    def test_well_formed_output(self):
        out = "TITLE: 주간 회의\n---BODY---\n## 🎯 한 줄 요약\n내용"
        title, body = process_inbox.parse_summary(out)
        self.assertEqual(title, "주간 회의")
        self.assertEqual(body, "## 🎯 한 줄 요약\n내용")

    def test_missing_title_uses_default(self):
        title, body = process_inbox.parse_summary("머리말\n---BODY---\n본문")
        self.assertEqual(title, "음성메모")
        self.assertEqual(body, "본문")

    def test_no_body_marker_returns_empty_body(self):
        title, body = process_inbox.parse_summary("TITLE: 제목만 있음")
        self.assertEqual(title, "음성메모")
        self.assertEqual(body, "")

    def test_none_input(self):
        self.assertEqual(process_inbox.parse_summary(None), ("음성메모", ""))


class FailCountTest(unittest.TestCase):
    def setUp(self):
        f = tempfile.NamedTemporaryFile("w", delete=False)
        f.close()
        os.remove(f.name)
        self.path = f.name
        self.addCleanup(lambda: os.path.isfile(self.path) and os.remove(self.path))

    def test_load_missing_file_returns_empty(self):
        self.assertEqual(process_inbox.load_fail_counts(self.path), {})

    def test_roundtrip(self):
        process_inbox.save_fail_counts(self.path, {"a.mp3": 2, "b.m4a": 1})
        self.assertEqual(process_inbox.load_fail_counts(self.path), {"a.mp3": 2, "b.m4a": 1})

    def test_bump_fail_is_immutable(self):
        original = {"a.mp3": 1}
        bumped = process_inbox.bump_fail(original, "a.mp3")
        self.assertEqual(bumped, {"a.mp3": 2})
        self.assertEqual(original, {"a.mp3": 1})

    def test_bump_fail_new_entry_starts_at_one(self):
        self.assertEqual(process_inbox.bump_fail({}, "x.mp3"), {"x.mp3": 1})

    def test_load_skips_malformed_lines(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("a.mp3\t2\nbroken line\nb.mp3\tNaN\n")
        self.assertEqual(process_inbox.load_fail_counts(self.path), {"a.mp3": 2})


if __name__ == "__main__":
    unittest.main()
