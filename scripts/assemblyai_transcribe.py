#!/usr/bin/env python3
"""
AssemblyAI 전사 + 화자분리 모듈 (선택 기능 — 키가 있을 때만 동작).
process_inbox.py 가 import 해서 사용. 키 없음/실패 시 None 반환 → 로컬 전사로 폴백.

REST 직접 호출 (표준 라이브러리 urllib 만 사용 — 이 레포는 서드파티 의존성 금지):
  1) POST /v2/upload      — 오디오 바이너리 업로드 → upload_url
  2) POST /v2/transcript  — language_code, speaker_labels=true, speech_models=[universal-2]
  3) GET  /v2/transcript/{id} 폴링 → utterances [{speaker: "A", text, start, end}]

API 키 해석 순서: 환경변수 ASSEMBLYAI_API_KEY → config.env ASSEMBLYAI_API_KEY
→ 레포 루트 .assemblyai_key 파일 (전부 .gitignore 대상).

단독 실행(테스트): python3 scripts/assemblyai_transcribe.py <audio파일>
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

from _config import load

API_BASE = "https://api.assemblyai.com/v2"

UPLOAD_TIMEOUT = 600   # 업로드 HTTP 타임아웃(초) — 1시간+ 녹음 mp3 도 여유
POLL_INTERVAL = 10
POLL_TIMEOUT = 1800    # 전사 완료 대기 상한(초)

# 모델 고정 — 검증된 화자분리 품질 (미지정 시 최신 기본모델로 바뀔 수 있음)
SPEECH_MODELS = ["universal-2"]

CFG = load()


def _api_key():
    key = os.environ.get("ASSEMBLYAI_API_KEY", "").strip()
    if key:
        return key
    key = (CFG.get("ASSEMBLYAI_API_KEY") or "").strip()
    if key:
        return key
    try:
        with open(CFG["AAI_KEY_PATH"], encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def _http(method, url, key, body=None, content_length=None, timeout=60):
    """urllib 요청 → 응답 JSON dict. body 는 bytes 또는 file 객체(스트리밍 업로드)."""
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("authorization", key)
    if isinstance(body, bytes):
        req.add_header("content-type", "application/json")
    elif content_length is not None:
        # file 객체 업로드는 Content-Length 를 명시해야 urllib 이 스트리밍 전송한다
        req.add_header("content-length", str(content_length))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def transcribe(audio_path, log=print):
    """utterances 리스트 반환: [{"speaker": "A", "text": ..., "start": ms, "end": ms}]. 실패 시 None."""
    key = _api_key()
    if not key:
        log("  assemblyai: API 키 없음 — 건너뜀 (로컬 전사로 폴백)")
        return None
    try:
        size = os.path.getsize(audio_path)
        with open(audio_path, "rb") as f:
            up = _http("POST", f"{API_BASE}/upload", key,
                       body=f, content_length=size, timeout=UPLOAD_TIMEOUT)
        upload_url = up["upload_url"]

        payload = json.dumps({
            "audio_url": upload_url,
            "language_code": CFG.get("WHISPER_LANG") or "ko",
            "speaker_labels": True,
            "speech_models": SPEECH_MODELS,
        }).encode("utf-8")
        tid = _http("POST", f"{API_BASE}/transcript", key, body=payload)["id"]

        deadline = time.time() + POLL_TIMEOUT
        while time.time() < deadline:
            data = _http("GET", f"{API_BASE}/transcript/{tid}", key)
            status = data.get("status")
            if status == "completed":
                utts = [{"speaker": u.get("speaker"), "text": (u.get("text") or "").strip(),
                         "start": u.get("start"), "end": u.get("end")}
                        for u in (data.get("utterances") or []) if (u.get("text") or "").strip()]
                if not utts and (data.get("text") or "").strip():
                    # 화자분리 결과가 비면 전체 텍스트를 단일 화자로
                    utts = [{"speaker": "A", "text": data["text"].strip(), "start": 0, "end": 0}]
                return utts or None
            if status == "error":
                log(f"  assemblyai: 전사 실패 — {data.get('error')}")
                return None
            time.sleep(POLL_INTERVAL)
        log(f"  assemblyai: 폴링 타임아웃({POLL_TIMEOUT}s) — id={tid}")
        return None
    except Exception as e:
        log(f"  assemblyai: 예외 — {e}")
        return None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: assemblyai_transcribe.py <audio>", file=sys.stderr)
        sys.exit(2)
    result = transcribe(sys.argv[1], log=lambda m: print(m, file=sys.stderr))
    if result is None:
        print("전사 실패", file=sys.stderr)
        sys.exit(1)
    for u in result:
        print(f"화자 {u['speaker']}: {u['text']}")
