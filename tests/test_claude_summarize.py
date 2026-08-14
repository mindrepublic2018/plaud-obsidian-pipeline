"""scripts/claude_summarize.py 순수 함수 단위 테스트 (네트워크·키 불필요)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import claude_summarize  # noqa: E402 — 임포트 자체가 키/네트워크 없이 안전해야 함


class BuildPayloadTest(unittest.TestCase):
    def test_structure(self):
        p = claude_summarize.build_payload("프롬프트", "전사", "claude-opus-5", max_tokens=100)
        self.assertEqual(p["model"], "claude-opus-5")
        self.assertEqual(p["max_tokens"], 100)
        self.assertEqual(p["system"], "프롬프트")
        self.assertEqual(p["messages"], [{"role": "user", "content": "전사"}])

    def test_no_forbidden_params(self):
        # opus-5 는 temperature/top_p 전송 시 400, thinking 은 기본 ON — 절대 포함 금지
        p = claude_summarize.build_payload("p", "t", "claude-opus-5")
        for key in ("temperature", "top_p", "top_k", "thinking"):
            self.assertNotIn(key, p)


class ExtractTextTest(unittest.TestCase):
    def test_text_blocks_only(self):
        data = {"stop_reason": "end_turn",
                "content": [{"type": "text", "text": "TITLE: 회의"}]}
        self.assertEqual(claude_summarize.extract_text(data), "TITLE: 회의")

    def test_thinking_block_is_skipped(self):
        data = {"stop_reason": "end_turn",
                "content": [{"type": "thinking", "thinking": "내부 추론"},
                            {"type": "text", "text": "본문"}]}
        self.assertEqual(claude_summarize.extract_text(data), "본문")

    def test_multiple_text_blocks_joined(self):
        data = {"content": [{"type": "text", "text": "앞"}, {"type": "text", "text": "뒤"}]}
        self.assertEqual(claude_summarize.extract_text(data), "앞뒤")

    def test_refusal_returns_none(self):
        data = {"stop_reason": "refusal", "content": []}
        self.assertIsNone(claude_summarize.extract_text(data))

    def test_empty_content_returns_none(self):
        self.assertIsNone(claude_summarize.extract_text({"content": []}))

    def test_non_dict_returns_none(self):
        self.assertIsNone(claude_summarize.extract_text(None))


if __name__ == "__main__":
    unittest.main()
