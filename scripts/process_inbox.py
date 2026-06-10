#!/usr/bin/env python3
"""
INBOX_DIR 음성메모 자동처리:
  INBOX_DIR/*.{m4a,mp3,wav,...} → ffmpeg(16k wav) → whisper.cpp(WHISPER_LANG 전사)
  → claude -p(요약 노트 생성, 없으면 전사-only 폴백) → OUTPUT_DIR/{제목}_{YYMMDD}.md
  → 원본 오디오는 ARCHIVE_DIR 로 이동
launchd WatchPaths 가 INBOX_DIR 변경 시 호출. 동시실행 방지 락 포함.
설정은 레포 루트 config.env (scripts/_config.py 가 해석).
"""
import os
import re
import subprocess
import time
import datetime
import fcntl
import shutil

from _config import load, HOME

CFG = load()
INBOX = CFG["INBOX_DIR"]
OUTDIR = CFG["OUTPUT_DIR"]
ARCHIVE = CFG["ARCHIVE_DIR"]
MODEL = CFG["MODEL_PATH"]
LOGDIR = CFG["LOG_DIR"]
LOCK = CFG["LOCK_PATH"]
LANG = CFG["WHISPER_LANG"] or "ko"
PROMPT_FILE = CFG.get("SUMMARY_PROMPT_FILE", "")


# 절대경로 바이너리 (launchd 는 PATH 가 빈약함)
def which(*cands):
    for c in cands:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    for c in cands:
        p = shutil.which(os.path.basename(c))
        if p:
            return p
    return None


FFMPEG = which("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "ffmpeg")
WHISPER = which("/opt/homebrew/bin/whisper-cli", "/opt/homebrew/bin/whisper-cpp",
                "/usr/local/bin/whisper-cli", "whisper-cli", "whisper-cpp")
CLAUDE = which(f"{HOME}/.npm-global/bin/claude", "/opt/homebrew/bin/claude", "claude")

AUDIO_EXT = {".m4a", ".mp3", ".wav", ".aiff", ".aif", ".aac", ".ogg", ".opus", ".webm", ".flac", ".mp4", ".m4v"}

DEFAULT_PROMPT = """당신은 한국어 통화/회의 녹취를 정리하는 비서다. 아래 STDIN으로 들어온 전사 텍스트를 보고
옵시디언 노트를 만든다. 출력은 **정확히** 다음 형식만 (코드펜스 없이):

TITLE: <12자 내외 간결한 한국어 제목 (날짜·확장자 없이)>
---BODY---
## 🎯 한 줄 요약
<핵심 한 문장>

## 핵심 내용
- <불릿 3~7개>

## ✅ 액션 아이템
- [ ] <있으면. 없으면 "특이 액션 없음">

## 🗒️ 전문(자동 전사)
<전사 원문 그대로>

규칙: 사실만, 전사에 없는 내용 지어내지 말 것. 화자 추정 가능하면 표기. 한국어로."""


def load_prompt():
    if PROMPT_FILE and os.path.isfile(PROMPT_FILE):
        try:
            with open(PROMPT_FILE, encoding="utf-8") as f:
                t = f.read().strip()
                if t:
                    return t
        except OSError:
            pass
    return DEFAULT_PROMPT


PROMPT = load_prompt()


def log(msg):
    os.makedirs(LOGDIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(f"{LOGDIR}/pipeline.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def slugify(title):
    t = re.sub(r"[\\/:*?\"<>|\n\r\t]", " ", title).strip()
    t = re.sub(r"\s+", " ", t)
    return (t[:60] or "음성메모").strip()


def stable(path, checks=3, delay=1.5):
    """동기화가 아직 쓰는 중일 수 있으니 크기가 안정될 때까지 대기."""
    last = -1
    for _ in range(checks):
        try:
            sz = os.path.getsize(path)
        except OSError:
            return False
        if sz == last and sz > 0:
            return True
        last = sz
        time.sleep(delay)
    return last > 0


def run_claude(transcript):
    if not CLAUDE:
        return None
    try:
        r = subprocess.run([CLAUDE, "-p", PROMPT], input=transcript,
                           capture_output=True, text=True, timeout=240)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
        log(f"claude 실패 rc={r.returncode} err={r.stderr[:200]}")
    except Exception as e:
        log(f"claude 예외: {e}")
    return None


def transcribe(audio):
    base = os.path.splitext(os.path.basename(audio))[0]
    wav = f"/tmp/voicememo_{base}_{int(time.time())}.wav"
    # 16k mono wav (whisper.cpp 요구)
    r = subprocess.run([FFMPEG, "-y", "-i", audio, "-ar", "16000", "-ac", "1", wav],
                       capture_output=True, text=True)
    if r.returncode != 0:
        log(f"ffmpeg 실패: {r.stderr[:200]}")
        return None
    out_prefix = wav[:-4]  # whisper -of
    r = subprocess.run([WHISPER, "-m", MODEL, "-l", LANG, "-f", wav,
                        "-otxt", "-of", out_prefix, "-nt"],
                       capture_output=True, text=True)
    txt_path = out_prefix + ".txt"
    transcript = ""
    if os.path.isfile(txt_path):
        with open(txt_path, encoding="utf-8") as f:
            transcript = f.read().strip()
    for p in (wav, txt_path):
        try:
            os.remove(p)
        except OSError:
            pass
    if r.returncode != 0 and not transcript:
        log(f"whisper 실패: {r.stderr[:200]}")
        return None
    return transcript


def build_note(title, body, transcript):
    today = datetime.date.today().strftime("%Y-%m-%d")
    fm = (f"---\ncreated: {today}\ntags: [음성메모, 자동전사]\n"
          f"type: voice-memo\nstatus: active\n---\n\n")
    h = f"# 📞 {title}\n\n"
    if body:
        return fm + h + body + "\n"
    # claude 실패/미설치 시 폴백: 전사만
    return (fm + h + "## 🗒️ 전문(자동 전사)\n" + (transcript or "(전사 실패)") + "\n")


def process(audio):
    name = os.path.basename(audio)
    log(f"처리 시작: {name}")
    if not stable(audio):
        log(f"  파일 불안정/빈파일 — 건너뜀(다음 트리거에 재시도): {name}")
        return
    transcript = transcribe(audio)
    if not transcript:
        log(f"  전사 결과 없음 — 보류: {name}")
        return
    title, body = "음성메모", ""
    out = run_claude(transcript)
    if out and "---BODY---" in out:
        head, body = out.split("---BODY---", 1)
        m = re.search(r"TITLE:\s*(.+)", head)
        if m:
            title = m.group(1).strip()
        body = body.strip()
    else:
        log("  claude 요약 없음 — 전사만 저장(폴백)")
    today6 = datetime.date.today().strftime("%y%m%d")
    os.makedirs(OUTDIR, exist_ok=True)
    fname = f"{slugify(title)}_{today6}.md"
    fpath = os.path.join(OUTDIR, fname)
    n = 2
    while os.path.exists(fpath):
        fpath = os.path.join(OUTDIR, f"{slugify(title)}_{today6}_{n}.md")
        n += 1
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(build_note(title, body, transcript))
    log(f"  ✓ 노트 생성: {os.path.basename(fpath)}")
    # 오디오 아카이브
    os.makedirs(ARCHIVE, exist_ok=True)
    arc = os.path.join(ARCHIVE, f"{datetime.date.today().strftime('%y%m%d')}_{name}")
    try:
        shutil.move(audio, arc)
        log(f"  ✓ 오디오 아카이브: {os.path.basename(arc)}")
    except Exception as e:
        log(f"  ⚠️ 아카이브 실패({e}) — 원본 유지")


def main():
    if not CFG.get("VAULT_PATH"):
        log("VAULT_PATH 미설정 — config.env 를 확인하세요")
        return
    if not (FFMPEG and WHISPER):
        log(f"필수 도구 없음 ffmpeg={FFMPEG} whisper={WHISPER} (brew install ffmpeg whisper-cpp)")
        return
    if not os.path.isfile(MODEL):
        log(f"모델 없음: {MODEL} (install.sh 가 다운로드. 완료 후 재시도)")
        return
    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    lockf = open(LOCK, "w")
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("이미 처리 중 — 종료")
        return
    try:
        if not os.path.isdir(INBOX):
            os.makedirs(INBOX, exist_ok=True)
        files = [os.path.join(INBOX, f) for f in sorted(os.listdir(INBOX))
                 if os.path.splitext(f)[1].lower() in AUDIO_EXT]
        if not files:
            return
        log(f"대기 오디오 {len(files)}개")
        for a in files:
            try:
                process(a)
            except Exception as e:
                log(f"처리 예외 {os.path.basename(a)}: {e}")
    finally:
        fcntl.flock(lockf, fcntl.LOCK_UN)
        lockf.close()


if __name__ == "__main__":
    main()
