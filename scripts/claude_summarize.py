#!/usr/bin/env python3
"""
Claude API 요약 모듈 (선택 기능 — ANTHROPIC_API_KEY 가 있을 때만 동작).
process_inbox.py 가 import 해서 사용. 키 없음/실패 시 None 반환 → 전사-only 노트로 폴백.

REST 직접 호출 (표준 라이브러리 urllib 만 사용 — 이 레포는 서드파티 의존성 금지):
  POST /v1/messages — system=회의록 프롬프트, user=전사 텍스트.
  claude-opus-5 는 thinking 이 기본 ON (파라미터 생략), temperature/top_p 전송 금지(400).
  응답 content 에서 type=="text" 블록만 추출 (thinking 블록이 앞설 수 있음).
  stop_reason=="refusal" 은 실패 취급(폴백), "max_tokens" 는 잘림 경고 후 텍스트 반환.

API 키 해석 순서: 환경변수 ANTHROPIC_API_KEY → config.env ANTHROPIC_API_KEY
→ 레포 루트 .anthropic_key 파일 (전부 .gitignore 대상).

단독 실행(테스트): python3 scripts/claude_summarize.py <전사.txt>  (인자 없으면 stdin)
"""
import os
import sys

import _llm
from _config import load

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"

MAX_TOKENS = 16000     # thinking+본문 합산 캡 (비스트리밍 안전 기본값)
TIMEOUT = 600          # opus-5 는 thinking 기본 ON — 긴 전사에서 수 분 걸릴 수 있음
RETRIES = 2            # 총 시도 횟수 (일시적 과부하 대비)
RETRY_SLEEP = 5
MAX_TRANSCRIPT_CHARS = 2_000_000  # 1M 컨텍스트 대비 안전 캡. 초과분은 절단 + 경고

CFG = load()


def _api_key():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    key = (CFG.get("ANTHROPIC_API_KEY") or "").strip()
    if key:
        return key
    try:
        with open(CFG["ANTHROPIC_KEY_PATH"], encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def build_payload(prompt, transcript, model, max_tokens=MAX_TOKENS):
    """요청 바디 생성 (순수 함수). temperature/top_p/thinking 은 절대 포함하지 않는다
    (opus-5 에서 400 또는 불필요 — thinking 은 기본 ON)."""
    return {
        "model": model,
        "max_tokens": max_tokens,
        "system": prompt,
        "messages": [{"role": "user", "content": transcript}],
    }


def extract_text(data):
    """응답 dict → 요약 텍스트 or None (순수 함수).
    stop_reason=="refusal" → None (안전 분류기 거부 — 폴백 대상).
    content 의 type=="text" 블록만 이어붙임 (thinking 블록은 무시)."""
    if not isinstance(data, dict):
        return None
    if data.get("stop_reason") == "refusal":
        return None
    parts = [b.get("text", "") for b in (data.get("content") or [])
             if isinstance(b, dict) and b.get("type") == "text"]
    text = "".join(parts).strip()
    return text or None


def summarize(transcript, prompt, log=print):
    """전사 텍스트 → 요약 출력(TITLE/---SPEAKERS---/---BODY--- 계약) or None.
    키 없음/HTTP 실패/refusal 전부 None — 절대 raise 하지 않는다."""
    key = _api_key()
    if not key:
        log("  claude: API 키 없음 — 요약 생략 (전사만 저장)")
        return None
    model = CFG.get("CLAUDE_MODEL") or "claude-opus-5"
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        log(f"  claude: 전사 {len(transcript):,}자 — 캡({MAX_TRANSCRIPT_CHARS:,}) 초과분 절단")
        transcript = transcript[:MAX_TRANSCRIPT_CHARS]
    log(f"  claude: 요약 요청 (model={model}, 전사 {len(transcript):,}자)")
    headers = {"x-api-key": key, "anthropic-version": API_VERSION}
    data = _llm.call_with_retry(API_URL, headers, build_payload(prompt, transcript, model),
                                TIMEOUT, RETRIES, RETRY_SLEEP, log, "claude")
    if data is None:
        return None
    if data.get("stop_reason") == "max_tokens":
        log(f"  claude: ⚠️ max_tokens({MAX_TOKENS}) 도달 — 요약이 잘렸을 수 있음")
    text = extract_text(data)
    if text is None:
        log(f"  claude: 요약 없음 (stop_reason={data.get('stop_reason')})")
    return text


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        with open(sys.argv[1], encoding="utf-8") as f:
            src = f.read()
    else:
        src = sys.stdin.read()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from process_inbox import PROMPT  # noqa: E402 — 실제 파이프라인과 동일 프롬프트
    out = summarize(src, PROMPT, log=lambda m: print(m, file=sys.stderr))
    if out is None:
        print("요약 실패", file=sys.stderr)
        sys.exit(1)
    print(out)
