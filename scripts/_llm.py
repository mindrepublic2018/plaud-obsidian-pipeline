#!/usr/bin/env python3
"""
LLM API 공용 HTTP 헬퍼 — claude_summarize.py / gpt_verify.py 가 공유.

표준 라이브러리 urllib 만 사용 (이 레포는 서드파티 의존성 금지).
config.env 나 네트워크 없이도 임포트가 안전해야 한다 (테스트 규약) — 그래서 _config 미의존.

원칙:
- call_with_retry() 는 절대 raise 하지 않는다. 최종 실패는 None.
- 재시도는 일시적 오류(429/5xx/네트워크)만. 인증·요청 오류(4xx)는 즉시 포기.
- API 키 값은 절대 로그에 남기지 않는다 (헤더는 로그 대상이 아님).
"""
import json
import time
import urllib.request
import urllib.error


def retryable(status):
    """HTTP 상태코드가 재시도 가치가 있는지. 429(레이트리밋)/5xx(서버·과부하) → True,
    그 외 4xx(400 잘못된 요청, 401/403 인증) → False."""
    return status == 429 or status >= 500


def post_json(url, headers, payload, timeout):
    """JSON POST → (status, data, err_text).
    성공: (2xx, dict, ""). HTTP 오류: (status, None, 에러바디 앞 300자).
    네트워크 예외(URLError/timeout)는 호출자에게 그대로 전파."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("content-type", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8")), ""
    except urllib.error.HTTPError as e:
        try:
            err = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            err = ""
        return e.code, None, err


def call_with_retry(url, headers, payload, timeout, retries, sleep_s, log, label):
    """post_json 을 재시도 감싸기. 성공 시 응답 dict, 최종 실패 시 None.
    retries = 총 시도 횟수. 4xx(비재시도)는 즉시 None + 로그."""
    for attempt in range(1, retries + 1):
        try:
            status, data, err = post_json(url, headers, payload, timeout)
            if data is not None:
                return data
            log(f"  {label}: HTTP {status} (시도 {attempt}/{retries}) — {err}")
            if not retryable(status):
                return None
        except Exception as e:
            log(f"  {label}: 예외 (시도 {attempt}/{retries}) — {e}")
        if attempt < retries:
            time.sleep(sleep_s)
    return None
