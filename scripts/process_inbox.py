#!/usr/bin/env python3
"""
INBOX_DIR 음성메모 자동처리:
  INBOX_DIR/*.{m4a,mp3,wav,...}
  → 전사 3단 체인: AssemblyAI(화자분리, 키 있을 때만) → WhisperX+pyannote(로컬 화자분리,
    venv 있을 때만) → whisper.cpp(항상 가능, 화자분리 없음)
  → claude -p(6섹션 회의록 요약 + 화자 이름 추론, 없으면 전사-only 폴백)
  → OUTPUT_DIR/{YYMMDD}_{제목}.md (YYMMDD = 녹음일 — 파일목록이 시간순 정렬됨)
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

from _config import load, migrate_legacy_state, HOME

# AssemblyAI 전사 모듈 (같은 디렉토리). import 실패해도 로컬 폴백으로 동작해야 하므로 방어
try:
    import assemblyai_transcribe
except Exception:
    assemblyai_transcribe = None

CFG = load()
INBOX = CFG["INBOX_DIR"]
OUTDIR = CFG["OUTPUT_DIR"]
ARCHIVE = CFG["ARCHIVE_DIR"]
MODEL = CFG["MODEL_PATH"]
LOGDIR = CFG["LOG_DIR"]
LOCK = CFG["LOCK_PATH"]
FAIL_PATH = CFG["FAIL_PATH"]
LANG = CFG["WHISPER_LANG"] or "ko"
PROMPT_FILE = CFG.get("SUMMARY_PROMPT_FILE", "")
# WhisperX(전사+화자분리) — 별도 venv 에서 실행 (없으면 이 티어는 건너뜀)
WHISPERX_PY = CFG["WHISPERX_PY"]
WHISPERX_SCRIPT = CFG["WHISPERX_SCRIPT"]

# 전사 실패가 이 횟수에 도달하면 INBOX/_failed 로 격리 (무한 재시도 방지)
MAX_TRANSCRIBE_FAILURES = 3

# 요약 호출 튜닝 — sonnet: 구조화·디테일·정확도 우위 (haiku 대비 ~2배 느리나 비동기라 무방).
CLAUDE_MODEL = CFG.get("CLAUDE_MODEL") or "sonnet"
CLAUDE_TIMEOUT = 180   # 6섹션 회의록 + 화자 추론으로 출력이 길어짐
CLAUDE_RETRIES = 2     # 일시적 실패(과부하 등) 대비 총 시도 횟수


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

DEFAULT_PROMPT = """당신은 한국어 통화/회의 녹취를 정리하는 회의록 전문가다. 아래 STDIN으로 들어온 전사 텍스트를 보고
옵시디언 노트의 '요약부'만 만든다. 전사 원문(전문)은 절대 다시 출력하지 말 것 — 시스템이 따로 첨부한다.
전사에는 자동 화자분리 라벨(화자 A, 화자 B, 화자 ? 등)이 붙어 있을 수 있다.
출력은 **정확히** 다음 형식만 (코드펜스 없이):

TITLE: <12자 내외 간결한 한국어 제목 (날짜·확장자 없이)>
---SPEAKERS---
A=<이름(역할)>
B=?
---BODY---
## 📋 안건
- <회의/통화에서 다룬 주제 항목별 불릿>

## 💬 주요 논의
- <중요한 논의 내용을 불릿 또는 짧은 문단으로>

## ✅ 결정사항
- <명확히 합의/결정된 사항만>

## 📝 액션 아이템
- [ ] <할 일> — **담당:** 이름 / **기한:** 날짜

## ⏭️ 다음 단계
- <후속 회의/추가 검토가 필요한 항목>

## 🎙️ 전반 톤 메모
<회의 *전체* 어조를 차분/평이/격앙 중 하나로 표시하고, 근거 발화 패턴을 1-2줄 인용
(반복 질문, 단답, 주제 회피, 부정어 빈도, 어조 변화 등). 화자별 톤 분리 금지.
판단 어려우면 "평이 (판단 근거 부족)">
> _본 톤 메모는 텍스트 전사 기반 보조 신호로 정확도 한계가 있으며, 인사평가 등 의사결정 용도로 사용하지 마세요._

규칙:
- SPEAKERS: 전사에 등장한 화자 라벨당 한 줄("A=이름(역할)"). 호칭·자기소개·직함 언급 등
  **명확한 근거가 있을 때만** 이름/역할을 적고, 근거가 없으면 "A=?"로 남길 것. 절대 추측 금지.
- BODY: 모든 섹션을 항상 출력. 해당 정보가 없으면 "(언급 없음)" 표기
  (액션 아이템은 "- [ ] 특이 액션 없음"). 담당/기한은 전사에 명시된 경우만 표기.
- 톤 메모 마지막의 disclaimer 인용문은 반드시 그대로 포함할 것.
- 사실만. 전사에 없는 내용을 지어내지 말 것. 한국어로 간결하게. 전사 원문 재출력 금지.
- 본문에서 화자를 지칭할 땐 이름이 밝혀진 경우 그 이름을, 아니면 역할 추정 표현만 사용."""


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


REC_DATE_RE = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")


def record_date(audio):
    """녹음 파일명에 박힌 녹음일(plaud_YYYY-MM-DD_... 형식) 추출. 없으면 처리일(오늘)로 폴백."""
    m = REC_DATE_RE.search(os.path.basename(audio))
    if m:
        try:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return datetime.date.today()


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


def parse_claude_output(out):
    """TITLE / ---SPEAKERS--- / ---BODY--- 파싱 → (title, speaker_map, body).
    speaker_map 예: {'A': '김대표(대표)'}. 'A=?'(근거 없음)는 매핑에서 제외 →
    전문에 '화자 A' 그대로 표시. 형식 불일치/빈 출력이면 폴백값 ("음성메모", {}, "")."""
    title, speaker_map = "음성메모", {}
    if not out or "---BODY---" not in out:
        return title, speaker_map, ""
    head, body = out.split("---BODY---", 1)
    body = body.strip()
    if "---SPEAKERS---" in head:
        head, spk_block = head.split("---SPEAKERS---", 1)
        for line in spk_block.strip().splitlines():
            m = re.match(r"\s*(?:화자\s*)?([A-Z]|\d+)\s*=\s*(.+?)\s*$", line)
            if m and m.group(2) not in ("?", ""):
                speaker_map[m.group(1)] = m.group(2)
    m = re.search(r"TITLE:\s*(.+)", head)
    if m:
        title = m.group(1).strip()
    return title, speaker_map, body


def load_fail_counts(path):
    """전사 실패 카운트 파일(이름<TAB>횟수) 로드. 깨진 줄은 무시."""
    counts = {}
    if not os.path.isfile(path):
        return counts
    with open(path, encoding="utf-8") as f:
        for ln in f:
            parts = ln.rstrip("\n").split("\t")
            if len(parts) == 2 and parts[1].isdigit():
                counts[parts[0]] = int(parts[1])
    return counts


def save_fail_counts(path, counts):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for name, n in sorted(counts.items()):
            f.write(f"{name}\t{n}\n")
    os.replace(tmp, path)


def bump_fail(counts, name):
    """실패 횟수 +1 한 새 dict 반환 (원본 불변)."""
    bumped = dict(counts)
    bumped[name] = bumped.get(name, 0) + 1
    return bumped


def quarantine(audio):
    """반복 실패한 오디오를 INBOX/_failed 로 이동해 재시도 루프에서 제외."""
    failed_dir = os.path.join(INBOX, "_failed")
    os.makedirs(failed_dir, exist_ok=True)
    dest = os.path.join(failed_dir, os.path.basename(audio))
    shutil.move(audio, dest)
    return dest


def run_claude(transcript):
    if not CLAUDE:
        return None
    cmd = [CLAUDE, "-p", PROMPT, "--model", CLAUDE_MODEL,
           "--tools", "", "--no-session-persistence"]
    for attempt in range(1, CLAUDE_RETRIES + 1):
        try:
            r = subprocess.run(cmd, input=transcript,
                               capture_output=True, text=True, errors="replace",
                               timeout=CLAUDE_TIMEOUT)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
            log(f"claude 실패(시도 {attempt}/{CLAUDE_RETRIES}) rc={r.returncode} err={r.stderr[:200]}")
        except Exception as e:
            log(f"claude 예외(시도 {attempt}/{CLAUDE_RETRIES}): {e}")
        if attempt < CLAUDE_RETRIES:
            time.sleep(5)
    return None


def transcribe_assemblyai(audio):
    """AssemblyAI 전사+화자분리. utterances 반환([{speaker: '화자 A', text}]), 실패/키 없음 시 None."""
    if not assemblyai_transcribe:
        return None
    utts = assemblyai_transcribe.transcribe(audio, log=log)
    if not utts:
        return None
    return [{"speaker": f"화자 {u['speaker']}", "text": u["text"]} for u in utts]


def transcribe_whisperx(audio):
    """WhisperX 전사 + 화자분리. stdout = 'SPEAKER_00: ...' 형식. venv 없음/실패 시 None."""
    if not (os.path.isfile(WHISPERX_PY) and os.path.isfile(WHISPERX_SCRIPT)):
        return None
    try:
        r = subprocess.run([WHISPERX_PY, WHISPERX_SCRIPT, audio],
                           capture_output=True, text=True, errors="replace", timeout=3600)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
        log(f"  whisperx rc={r.returncode}: {(r.stderr or '')[-300:]}")
    except Exception as e:
        log(f"  whisperx 예외: {e}")
    return None


def parse_whisperx_lines(text):
    """WhisperX 출력('SPEAKER_00: ...' 라인)을 utterances 로. SPEAKER_00→화자 A, 화자?→화자 ?."""
    utts = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"SPEAKER_(\d+):\s*(.*)", line)
        if m:
            n = int(m.group(1))
            sp = f"화자 {chr(ord('A') + n)}" if n < 26 else f"화자 {n}"
            utts.append({"speaker": sp, "text": m.group(2)})
        elif line.startswith("화자?:"):
            utts.append({"speaker": "화자 ?", "text": line.split(":", 1)[1].strip()})
        elif utts:
            utts[-1]["text"] += " " + line
        else:
            utts.append({"speaker": "화자 ?", "text": line})
    return utts or None


def transcribe_whispercpp(audio):
    base = os.path.splitext(os.path.basename(audio))[0]
    wav = f"/tmp/voicememo_{base}_{int(time.time())}.wav"
    # 16k mono wav (whisper.cpp 요구)
    r = subprocess.run([FFMPEG, "-y", "-i", audio, "-ar", "16000", "-ac", "1", wav],
                       capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        log(f"ffmpeg 실패: {r.stderr[:200]}")
        return None
    out_prefix = wav[:-4]  # whisper -of
    r = subprocess.run([WHISPER, "-m", MODEL, "-l", LANG, "-f", wav,
                        "-otxt", "-of", out_prefix, "-nt"],
                       capture_output=True, text=True, errors="replace")
    txt_path = out_prefix + ".txt"
    transcript = ""
    if os.path.isfile(txt_path):
        with open(txt_path, encoding="utf-8", errors="replace") as f:
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


def transcribe(audio):
    """(utterances, diarized) 반환. utterances = [{speaker, text}], 전사 실패 시 (None, False).
    체인: AssemblyAI → WhisperX+pyannote → whisper.cpp(화자분리 없음)."""
    utts = transcribe_assemblyai(audio)
    if utts:
        log("  전사 엔진: AssemblyAI (화자분리)")
        return utts, True
    t = transcribe_whisperx(audio)
    if t:
        utts = parse_whisperx_lines(t)
        if utts:
            log("  전사 엔진: WhisperX (화자분리)")
            return utts, True
    t = transcribe_whispercpp(audio)
    if t:
        log("  전사 엔진: whisper.cpp")
        return [{"speaker": None, "text": t}], False
    return None, False


def transcript_for_claude(utterances, diarized):
    """claude 입력용 전사 렌더링. 화자분리 시 '화자 A: 텍스트' 라인."""
    if diarized:
        return "\n".join(f"{u['speaker']}: {u['text']}" for u in utterances)
    return "\n".join(u["text"] for u in utterances)


def utterances_markdown(utterances, speaker_map):
    """'**[화자 A(김대표)]** 텍스트' 형식. 이름 추론이 없는 화자는 '**[화자 A]**' 유지."""
    lines = []
    for u in utterances:
        sp = u["speaker"] or "화자 ?"
        key = sp.replace("화자", "").strip()
        name = speaker_map.get(key)
        label = f"{sp}({name})" if name else sp
        lines.append(f"**[{label}]** {u['text']}")
    return "\n\n".join(lines)


def build_note(title, body, utterances, diarized, speaker_map, created):
    # created = 녹음일(YYYY-MM-DD). 녹음 파일명에서 추출, 없으면 처리일 폴백.
    # 요약 성공 시 active, claude 폴백(요약 없음)이면 summary_pending 으로 표시
    status = "active" if body else "summary_pending"
    fm = (f"---\ncreated: {created}\ntags: [음성메모, 자동전사]\n"
          f"type: voice-memo\nstatus: {status}\n---\n\n")
    h = f"# 📞 {title}\n\n"
    summary = (body + "\n\n") if body else ""
    # 전사 원문은 항상 코드가 직접 첨부 (claude 는 요약만 생성 → 출력이 전사 길이에 비례하지 않음)
    if diarized and utterances:
        transcript_block = "## 🗣️ 화자별 전문\n\n" + utterances_markdown(utterances, speaker_map) + "\n"
    else:
        plain = "\n".join(u["text"] for u in utterances) if utterances else "(전사 실패)"
        transcript_block = "## 🗒️ 전문(자동 전사)\n" + plain + "\n"
    return fm + h + summary + transcript_block


def process(audio):
    name = os.path.basename(audio)
    log(f"처리 시작: {name}")
    if not stable(audio):
        log(f"  파일 불안정/빈파일 — 건너뜀(다음 트리거에 재시도): {name}")
        return
    utterances, diarized = transcribe(audio)
    counts = load_fail_counts(FAIL_PATH)
    if not utterances:
        counts = bump_fail(counts, name)
        n = counts[name]
        if n >= MAX_TRANSCRIBE_FAILURES:
            quarantine(audio)
            counts = {k: v for k, v in counts.items() if k != name}
            log(f"  전사 {MAX_TRANSCRIBE_FAILURES}회 실패 — _failed/ 로 격리: {name}")
        else:
            log(f"  전사 결과 없음({n}/{MAX_TRANSCRIBE_FAILURES}) — 보류: {name}")
        save_fail_counts(FAIL_PATH, counts)
        return
    if name in counts:  # 성공 → 실패 기록 정리
        save_fail_counts(FAIL_PATH, {k: v for k, v in counts.items() if k != name})
    out = run_claude(transcript_for_claude(utterances, diarized))
    title, speaker_map, body = parse_claude_output(out)
    if not body:
        log("  claude 요약 없음 — 전사만 저장(폴백)")
    rec = record_date(audio)               # 녹음일 (파일명 기준, 없으면 처리일)
    rec6 = rec.strftime("%y%m%d")
    rec_iso = rec.strftime("%Y-%m-%d")
    os.makedirs(OUTDIR, exist_ok=True)
    fname = f"{rec6}_{slugify(title)}.md"   # 날짜를 앞에 → 파일목록이 시간순 정렬됨
    fpath = os.path.join(OUTDIR, fname)
    n = 2
    while os.path.exists(fpath):
        fpath = os.path.join(OUTDIR, f"{rec6}_{slugify(title)}_{n}.md")
        n += 1
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(build_note(title, body, utterances, diarized, speaker_map, rec_iso))
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
    # whisper.cpp 는 항상 가능한 마지막 폴백 티어 — 없으면 '전사 유실 없음' 보장이 깨지므로 필수
    if not (FFMPEG and WHISPER):
        log(f"필수 도구 없음 ffmpeg={FFMPEG} whisper={WHISPER} (brew install ffmpeg whisper-cpp)")
        return
    if not os.path.isfile(MODEL):
        log(f"모델 없음: {MODEL} (install.sh 가 다운로드. 완료 후 재시도)")
        return
    migrate_legacy_state()
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
