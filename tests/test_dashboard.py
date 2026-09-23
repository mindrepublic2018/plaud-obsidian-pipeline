"""dashboard/serve.py 순수 함수 단위 테스트."""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboard"))
import serve  # noqa: E402

NOW = dt.datetime(2026, 9, 24, 12, 0, 0)
OK = "[{}] [pull] 전체 158개 / 신규·재시도 0개"
WARN = "[{}] [pull] 경고: files 출력에서 녹음 id 를 못 찾음"
FAIL = "[{}] [pull] 녹음 목록 비어있음/조회 실패 (plaud login 만료 여부 확인)"


class PullHealthTest(unittest.TestCase):
    def test_recent_success_is_ok(self):
        h = serve.pull_health([OK.format("2026-09-24 11:50:00")], NOW, 900)
        self.assertEqual((h["level"], h["lastOk"], h["failStreak"]), ("ok", "2026-09-24 11:50:00", 0))

    def test_failure_lines_do_not_count_as_last_pull(self):
        # 09-15~24 장애 재현: 실패 로그가 계속 찍혀도 lastOk 는 마지막 *성공* 시각
        lines = [OK.format("2026-09-15 16:45:33")]
        for h_ in range(10, 12):
            lines += [WARN.format(f"2026-09-24 {h_}:00:00"), FAIL.format(f"2026-09-24 {h_}:00:00")]
        h = serve.pull_health(lines, NOW, 900)
        self.assertEqual(h["level"], "bad")
        self.assertEqual(h["lastOk"], "2026-09-15 16:45:33")
        self.assertEqual(h["failStreak"], 2)

    def test_short_failure_streak_is_warn(self):
        lines = [OK.format("2026-09-24 11:30:00"), FAIL.format("2026-09-24 11:45:00")]
        self.assertEqual(serve.pull_health(lines, NOW, 900)["level"], "warn")

    def test_no_success_ever_but_failures_is_bad(self):
        self.assertEqual(serve.pull_health([FAIL.format("2026-09-24 11:45:00")], NOW, 900)["level"], "bad")

    def test_cli_missing_counts_as_failure(self):
        lines = [OK.format("2026-09-24 11:30:00"), "[2026-09-24 11:45:00] [pull] plaud CLI 없음: /x/plaud"]
        self.assertEqual(serve.pull_health(lines, NOW, 900)["failStreak"], 1)

    def test_empty_log_is_ok(self):
        h = serve.pull_health([], NOW, 900)
        self.assertEqual((h["level"], h["lastOk"]), ("ok", None))

    def test_quiet_but_old_success_is_bad(self):
        # 실패 로그조차 없이 잡이 멈춘 경우(launchd 미실행 등)도 잡는다
        self.assertEqual(serve.pull_health([OK.format("2026-09-24 08:00:00")], NOW, 900)["level"], "bad")


if __name__ == "__main__":
    unittest.main()
