#!/usr/bin/env python3
"""
GPT 교차검증 모듈 (선택 기능 — OPENAI_API_KEY 가 있을 때만 동작).
process_inbox.py 가 import 해서 사용. Claude 요약을 전사 원문과 대조해
사실 오류·누락을 교정한 최종본을 같은 출력 계약(TITLE/---SPEAKERS---/---BODY---)으로 반환.
키 없음/실패/형식 불일치 시 None 반환 → Claude 요약을 그대로 사용 (verified: false).

REST 직접 호출 (표준 라이브러리 urllib 만 사용 — 이 레포는 서드파티 의존성 금지):
  POST /v1/chat/completions — system=검수 프롬프트, user=전사+요약.

API 키 해석 순서: 환경변수 OPENAI_API_KEY → config.env OPENAI_API_KEY
→ 레포 루트 .openai_key 파일 (전부 .gitignore 대상).

단독 실행(테스트): python3 scripts/gpt_verify.py <전사.txt> <요약.txt>
"""
import os
import sys

import _llm
from _config import load

API_URL = "https://api.openai.com/v1/chat/completions"

TIMEOUT = 300
RETRIES = 2            # 총 시도 횟수
RETRY_SLEEP = 5
MAX_INPUT_CHARS = 800_000  # 전사+요약 합산 캡. 초과 시 검증 건너뜀(요약 그대로)

VERIFY_PROMPT = """당신은 회의록 검수자다. (1) 통화/회의 전사 원문과 (2) 그 전사로 만든 요약이 주어진다.
요약을 전사와 대조해 다음만 수행하라:
- 사실 오류 수정: 숫자·금액·날짜·이름·결정사항이 전사와 다르면 전사 기준으로 고친다.
- 중요 누락 복원: 전사에 명확히 있는 결정사항/액션 아이템이 요약에 빠졌으면 추가한다.
- 전사에 없는 내용은 절대 추가하지 말 것. 기존 문체·구조·화자 라벨은 유지.
- 출력은 수정이 반영된 **요약 전체**를 원래 형식 그대로 (코드펜스·설명·코멘트 없이):
  "TITLE: ..." 줄, "---SPEAKERS---" 블록(원본에 있었다면), "---BODY---" 이후 6개 섹션.
  톤 메모 마지막의 disclaimer 인용문(> _본 톤 메모는...)도 그대로 포함할 것.
- 고칠 것이 없으면 요약을 한 글자도 바꾸지 말고 그대로 다시 출력하라."""


CFG = load()


def _api_key():
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    key = (CFG.get("OPENAI_API_KEY") or "").strip()
    if key:
        return key
    try:
        with open(CFG["OPENAI_KEY_PATH"], encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def build_payload(transcript, summary_output, model):
    """요청 바디 생성 (순수 함수). summary_output 은 Claude 원문 출력 전체
    (TITLE/SPEAKERS 포함) — GPT 가 계약 전체를 재출력하도록."""
    user = f"[전사 원문]\n{transcript}\n\n[검증 대상 요약]\n{summary_output}"
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": VERIFY_PROMPT},
            {"role": "user", "content": user},
        ],
    }


def extract_text(data):
    """응답 dict → choices[0].message.content or None (순수 함수, 구조 방어)."""
    if not isinstance(data, dict):
        return None
    choices = data.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return None
    content = (choices[0].get("message") or {}).get("content") or ""
    text = content.strip()
    return text or None


def verify(transcript, summary_output, log=print):
    """교정된 요약 전문(TITLE/---SPEAKERS---/---BODY--- 계약) or None.
    키 없음/실패/입력 캡 초과 전부 None — 절대 raise 하지 않는다."""
    key = _api_key()
    if not key:
        log("  gpt: API 키 없음 — 교차검증 생략")
        return None
    if len(transcript) + len(summary_output) > MAX_INPUT_CHARS:
        log(f"  gpt: 입력 {len(transcript) + len(summary_output):,}자 — 캡 초과, 검증 건너뜀")
        return None
    model = CFG.get("OPENAI_MODEL") or "gpt-5.2"
    log(f"  gpt: 교차검증 요청 (model={model})")
    headers = {"Authorization": f"Bearer {key}"}
    data = _llm.call_with_retry(API_URL, headers,
                                build_payload(transcript, summary_output, model),
                                TIMEOUT, RETRIES, RETRY_SLEEP, log, "gpt")
    if data is None:
        return None
    text = extract_text(data)
    if text is None:
        log("  gpt: 응답에 내용 없음 — 검증 생략")
    return text


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: gpt_verify.py <transcript.txt> <summary.txt>", file=sys.stderr)
        sys.exit(2)
    with open(sys.argv[1], encoding="utf-8") as f:
        ts = f.read()
    with open(sys.argv[2], encoding="utf-8") as f:
        sm = f.read()
    out = verify(ts, sm, log=lambda m: print(m, file=sys.stderr))
    if out is None:
        print("검증 실패", file=sys.stderr)
        sys.exit(1)
    print(out)
