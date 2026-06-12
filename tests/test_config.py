"""scripts/_config.py 단위 테스트."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import _config  # noqa: E402


class ParseFileTest(unittest.TestCase):
    def _write(self, text):
        f = tempfile.NamedTemporaryFile("w", suffix=".env", delete=False, encoding="utf-8")
        f.write(text)
        f.close()
        self.addCleanup(os.remove, f.name)
        return f.name

    def test_parses_key_value_pairs(self):
        path = self._write("VAULT_PATH=/tmp/vault\nWHISPER_LANG=en\n")
        vals = _config._parse_file(path)
        self.assertEqual(vals, {"VAULT_PATH": "/tmp/vault", "WHISPER_LANG": "en"})

    def test_ignores_comments_and_blank_lines(self):
        path = self._write("# comment\n\nVAULT_PATH=/v\n#KEY=ignored\n")
        self.assertEqual(_config._parse_file(path), {"VAULT_PATH": "/v"})

    def test_strips_surrounding_quotes(self):
        path = self._write('A="quoted value"\nB=\'single\'\n')
        vals = _config._parse_file(path)
        self.assertEqual(vals["A"], "quoted value")
        self.assertEqual(vals["B"], "single")

    def test_ignores_lines_without_equals(self):
        path = self._write("not a config line\nA=1\n")
        self.assertEqual(_config._parse_file(path), {"A": "1"})

    def test_missing_file_returns_empty(self):
        self.assertEqual(_config._parse_file("/nonexistent/config.env"), {})


class ExpandTest(unittest.TestCase):
    def test_expands_tilde(self):
        self.assertEqual(_config._expand("~/x"), os.path.join(_config.HOME, "x"))

    def test_substitutes_extra_vars(self):
        out = _config._expand("$VAULT_PATH/_inbox", {"VAULT_PATH": "/v"})
        self.assertEqual(out, "/v/_inbox")

    def test_substitutes_braced_vars(self):
        out = _config._expand("${VAULT_PATH}/_inbox", {"VAULT_PATH": "/v"})
        self.assertEqual(out, "/v/_inbox")

    def test_empty_value_passthrough(self):
        self.assertEqual(_config._expand(""), "")


class LoadTest(unittest.TestCase):
    def _load_with(self, text):
        f = tempfile.NamedTemporaryFile("w", suffix=".env", delete=False, encoding="utf-8")
        f.write(text)
        f.close()
        self.addCleanup(os.remove, f.name)
        original = _config.CONFIG_PATH
        _config.CONFIG_PATH = f.name
        self.addCleanup(setattr, _config, "CONFIG_PATH", original)
        return _config.load()

    def test_derives_inbox_and_output_from_vault(self):
        cfg = self._load_with("VAULT_PATH=/tmp/vault\n")
        self.assertEqual(cfg["INBOX_DIR"], "/tmp/vault/_inbox")
        self.assertEqual(cfg["OUTPUT_DIR"], "/tmp/vault/Voice Memos")

    def test_explicit_dirs_override_derived(self):
        cfg = self._load_with("VAULT_PATH=/v\nINBOX_DIR=$VAULT_PATH/drop\n")
        self.assertEqual(cfg["INBOX_DIR"], "/v/drop")

    def test_state_paths_live_under_state_dir(self):
        cfg = self._load_with("VAULT_PATH=/v\n")
        state_dir = os.path.join(_config.REPO_ROOT, "state")
        self.assertEqual(cfg["STATE_DIR"], state_dir)
        self.assertEqual(cfg["STATE_PATH"], os.path.join(state_dir, "pulled_ids.txt"))
        self.assertEqual(cfg["SKIP_PATH"], os.path.join(state_dir, "skipped_ids.txt"))
        self.assertEqual(cfg["LOCK_PATH"], os.path.join(state_dir, ".lock"))
        self.assertEqual(cfg["PULL_LOCK_PATH"], os.path.join(state_dir, ".pull.lock"))
        self.assertEqual(cfg["FAIL_PATH"], os.path.join(state_dir, "transcribe_failures.txt"))


if __name__ == "__main__":
    unittest.main()
