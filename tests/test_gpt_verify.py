"""scripts/gpt_verify.py 순수 함수 단위 테스트 (네트워크·키 불필요)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import gpt_verify  # noqa: E402 — 임포트 자체가 키/네트워크 없이 안전해야 함


class BuildPayloadTest(unittest.TestCase):
    def test_structure(self):
        p = gpt_verify.build_payload("전사원문", "TITLE: x\n---BODY---\n본문", "gpt-5.2")
        self.assertEqual(p["model"], "gpt-5.2")
        self.assertEqual(p["messages"][0]["role"], "system")
        self.assertEqual(p["messages"][0]["content"], gpt_verify.VERIFY_PROMPT)
        user = p["messages"][1]
        self.assertEqual(user["role"], "user")
        self.assertIn("전사원문", user["content"])
        self.assertIn("---BODY---", user["content"])


class VerifyPromptContractTest(unittest.TestCase):
    def test_prompt_mentions_output_contract_markers(self):
        # GPT 출력을 parse_claude_output 으로 재파싱하므로 계약 마커가 프롬프트에 있어야 함
        self.assertIn("---BODY---", gpt_verify.VERIFY_PROMPT)
        self.assertIn("---SPEAKERS---", gpt_verify.VERIFY_PROMPT)
        self.assertIn("TITLE:", gpt_verify.VERIFY_PROMPT)


class ExtractTextTest(unittest.TestCase):
    def test_normal_response(self):
        data = {"choices": [{"message": {"content": "TITLE: 교정본"}}]}
        self.assertEqual(gpt_verify.extract_text(data), "TITLE: 교정본")

    def test_missing_choices_returns_none(self):
        self.assertIsNone(gpt_verify.extract_text({}))

    def test_empty_choices_returns_none(self):
        self.assertIsNone(gpt_verify.extract_text({"choices": []}))

    def test_missing_message_returns_none(self):
        self.assertIsNone(gpt_verify.extract_text({"choices": [{}]}))

    def test_empty_content_returns_none(self):
        self.assertIsNone(gpt_verify.extract_text({"choices": [{"message": {"content": ""}}]}))

    def test_non_dict_returns_none(self):
        self.assertIsNone(gpt_verify.extract_text(None))


if __name__ == "__main__":
    unittest.main()
