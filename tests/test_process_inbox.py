"""scripts/process_inbox.py 순수 함수 단위 테스트."""
import datetime
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


class ParseClaudeOutputTest(unittest.TestCase):
    def test_well_formed_output_with_speakers(self):
        out = ("TITLE: 주간 회의\n---SPEAKERS---\nA=김대표(대표)\nB=?\n"
               "---BODY---\n## 📋 안건\n- 내용")
        title, speaker_map, body = process_inbox.parse_claude_output(out)
        self.assertEqual(title, "주간 회의")
        self.assertEqual(speaker_map, {"A": "김대표(대표)"})  # B=? 는 근거 없음 → 제외
        self.assertEqual(body, "## 📋 안건\n- 내용")

    def test_speaker_label_prefix_and_digit_keys(self):
        out = "TITLE: t\n---SPEAKERS---\n화자 A=이과장\n3=박대리\n---BODY---\nb"
        _, speaker_map, _ = process_inbox.parse_claude_output(out)
        self.assertEqual(speaker_map, {"A": "이과장", "3": "박대리"})

    def test_no_speakers_block_gives_empty_map(self):
        title, speaker_map, body = process_inbox.parse_claude_output(
            "TITLE: 회의\n---BODY---\n본문")
        self.assertEqual(title, "회의")
        self.assertEqual(speaker_map, {})
        self.assertEqual(body, "본문")

    def test_missing_title_uses_default(self):
        title, _, body = process_inbox.parse_claude_output("머리말\n---BODY---\n본문")
        self.assertEqual(title, "음성메모")
        self.assertEqual(body, "본문")

    def test_no_body_marker_returns_empty_body(self):
        self.assertEqual(process_inbox.parse_claude_output("TITLE: 제목만 있음"),
                         ("음성메모", {}, ""))

    def test_none_input(self):
        self.assertEqual(process_inbox.parse_claude_output(None), ("음성메모", {}, ""))


class ParseWhisperxLinesTest(unittest.TestCase):
    def test_speaker_indices_map_to_letters(self):
        utts = process_inbox.parse_whisperx_lines("SPEAKER_00: 안녕하세요\nSPEAKER_01: 네 반갑습니다")
        self.assertEqual(utts, [{"speaker": "화자 A", "text": "안녕하세요"},
                                {"speaker": "화자 B", "text": "네 반갑습니다"}])

    def test_unknown_speaker_line(self):
        utts = process_inbox.parse_whisperx_lines("화자?: 누구 발화인지 모름")
        self.assertEqual(utts, [{"speaker": "화자 ?", "text": "누구 발화인지 모름"}])

    def test_continuation_line_appends_to_previous(self):
        utts = process_inbox.parse_whisperx_lines("SPEAKER_00: 첫 문장\n이어지는 문장")
        self.assertEqual(utts, [{"speaker": "화자 A", "text": "첫 문장 이어지는 문장"}])

    def test_leading_bare_line_becomes_unknown_speaker(self):
        utts = process_inbox.parse_whisperx_lines("라벨 없는 첫 줄")
        self.assertEqual(utts, [{"speaker": "화자 ?", "text": "라벨 없는 첫 줄"}])

    def test_empty_input_returns_none(self):
        self.assertIsNone(process_inbox.parse_whisperx_lines(""))


class RecordDateTest(unittest.TestCase):
    def test_extracts_date_from_plaud_filename(self):
        self.assertEqual(process_inbox.record_date("/x/plaud_2026-06-10_abcd1234.mp3"),
                         datetime.date(2026, 6, 10))

    def test_invalid_date_falls_back_to_today(self):
        self.assertEqual(process_inbox.record_date("plaud_2026-13-40_x.mp3"),
                         datetime.date.today())

    def test_no_date_falls_back_to_today(self):
        self.assertEqual(process_inbox.record_date("voice memo.m4a"), datetime.date.today())


class UtterancesMarkdownTest(unittest.TestCase):
    def test_mapped_speaker_gets_name_label(self):
        md = process_inbox.utterances_markdown(
            [{"speaker": "화자 A", "text": "안녕하세요"}], {"A": "김대표(대표)"})
        self.assertEqual(md, "**[화자 A(김대표(대표))]** 안녕하세요")

    def test_unmapped_speaker_keeps_plain_label(self):
        md = process_inbox.utterances_markdown(
            [{"speaker": "화자 B", "text": "네"}], {"A": "김대표"})
        self.assertEqual(md, "**[화자 B]** 네")

    def test_none_speaker_becomes_unknown(self):
        md = process_inbox.utterances_markdown([{"speaker": None, "text": "텍스트"}], {})
        self.assertEqual(md, "**[화자 ?]** 텍스트")


class TranscriptForClaudeTest(unittest.TestCase):
    def test_diarized_renders_speaker_lines(self):
        t = process_inbox.transcript_for_claude(
            [{"speaker": "화자 A", "text": "안녕"}, {"speaker": "화자 B", "text": "네"}], True)
        self.assertEqual(t, "화자 A: 안녕\n화자 B: 네")

    def test_plain_renders_text_only(self):
        t = process_inbox.transcript_for_claude([{"speaker": None, "text": "전사 원문"}], False)
        self.assertEqual(t, "전사 원문")


class BuildNoteTest(unittest.TestCase):
    UTTS = [{"speaker": "화자 A", "text": "안녕하세요"}]

    def test_summary_with_verified_frontmatter(self):
        note = process_inbox.build_note("제목", "## 본문", self.UTTS, True,
                                        {"A": "김대표(대표)"}, "2026-08-10",
                                        summary_model="claude-opus-5", verified=True)
        self.assertIn("status: active\n", note)
        self.assertIn("summary_model: claude-opus-5\n", note)
        self.assertIn("verified: true\n", note)
        self.assertIn('speakers: ["김대표(대표)"]\n', note)

    def test_summary_unverified(self):
        note = process_inbox.build_note("제목", "## 본문", self.UTTS, True, {}, "2026-08-10",
                                        summary_model="claude-opus-5", verified=False)
        self.assertIn("verified: false\n", note)
        self.assertNotIn("speakers:", note)

    def test_fallback_note_has_no_summary_metadata(self):
        note = process_inbox.build_note("음성메모", "", self.UTTS, True, {}, "2026-08-10")
        self.assertIn("status: summary_pending\n", note)
        self.assertNotIn("summary_model:", note)
        self.assertNotIn("verified:", note)


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


class ProcessedNotesTest(unittest.TestCase):
    def setUp(self):
        f = tempfile.NamedTemporaryFile("w", delete=False)
        f.close()
        self.path = f.name
        self.addCleanup(os.remove, self.path)

    def test_round_trip(self):
        process_inbox.save_processed(self.path, {"a.mp3": "250817_회의.md", "b.m4a": "250817_통화.md"})
        self.assertEqual(process_inbox.load_processed(self.path),
                         {"a.mp3": "250817_회의.md", "b.m4a": "250817_통화.md"})

    def test_load_skips_malformed_lines(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("a.mp3\tnote.md\nbroken line\n\tno-name.md\nno-note\t\n")
        self.assertEqual(process_inbox.load_processed(self.path), {"a.mp3": "note.md"})

    def test_missing_file_returns_empty(self):
        self.assertEqual(process_inbox.load_processed("/nonexistent/processed.txt"), {})

    def test_save_overwrites_previous_content(self):
        process_inbox.save_processed(self.path, {"a.mp3": "x.md"})
        process_inbox.save_processed(self.path, {"b.mp3": "y.md"})
        self.assertEqual(process_inbox.load_processed(self.path), {"b.mp3": "y.md"})


class YamlQuoteTest(unittest.TestCase):
    def test_plain_name_is_quoted(self):
        self.assertEqual(process_inbox.yaml_quote("김대표(대표)"), '"김대표(대표)"')

    def test_double_quote_is_escaped(self):
        self.assertEqual(process_inbox.yaml_quote('a"b'), '"a\\"b"')

    def test_backslash_is_escaped(self):
        self.assertEqual(process_inbox.yaml_quote("a\\b"), '"a\\\\b"')

    def test_bracket_and_colon_stay_inside_quotes(self):
        # LLM 이 만든 이름의 ] : 가 frontmatter 리스트를 못 깨는지
        self.assertEqual(process_inbox.yaml_quote("x] evil: y"), '"x] evil: y"')

    def test_build_note_speakers_line_is_quoted(self):
        note = process_inbox.build_note(
            "t", "body", [{"speaker": "화자 A", "text": "hi"}], True,
            {"A": 'k"s'}, "2026-08-17", summary_model="m")
        self.assertIn('speakers: ["k\\"s"]\n', note)


if __name__ == "__main__":
    unittest.main()
