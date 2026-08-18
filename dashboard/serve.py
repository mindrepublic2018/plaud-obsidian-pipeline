#!/usr/bin/env python3
"""plaud-obsidian-pipeline 관리 대시보드 로컬 서버 (읽기 전용).

- 127.0.0.1 전용 바인딩 — 외부 노출 금지 (PRD 비기능 요구사항).
- dashboard/ 정적 파일을 서빙하고, GET /dash-data.js 요청에는
  실제 state/·logs/·config 를 읽어 같은 export 계약의 ES 모듈을 실시간 생성한다.
- 파이프라인 상태 파일은 절대 쓰지 않는다 (조치 액션은 UI 프로토타입 단계).
- 시크릿(*_KEY/*_TOKEN)은 값 대신 설정됨/미설정 불리언만 내려간다.

사용: python3 dashboard/serve.py [--port 8787]
"""
import argparse
import datetime as dt
import http.server
import json
import os
import re
import subprocess
import sys

DASH_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(DASH_DIR)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
import _config  # noqa: E402  (경로/설정의 단일 소스)

CFG = _config.load()

AUDIO_EXT = {".mp3", ".m4a", ".wav", ".aac", ".opus", ".flac", ".aiff", ".aif",
             ".ogg", ".webm", ".mp4", ".m4v"}
TS_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")


def read_lines(path):
    """파일 없음 = 정상(빈 상태). 대시보드 원칙과 동일."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return [ln.rstrip("\n") for ln in f]
    except OSError:
        return []


def classify(line):
    if "⚠️" in line or "✗" in line or "실패" in line or "Error" in line:
        return "warn"
    if "✓" in line:
        return "ok"
    return "info"


def last_ts(lines, needle=None):
    """로그 라인들에서 (조건에 맞는) 마지막 타임스탬프."""
    for ln in reversed(lines):
        if needle and needle not in ln:
            continue
        m = TS_RE.match(ln)
        if m:
            return m.group(1)
    return None


def launchctl_jobs():
    """launchctl list 에서 잡 3개의 로드/종료코드 상태."""
    state = {}
    try:
        out = subprocess.run(["launchctl", "list"], capture_output=True, text=True,
                             timeout=10).stdout
        for ln in out.splitlines():
            parts = ln.split("\t")
            if len(parts) == 3 and parts[2].startswith("com.plaud-obsidian."):
                pid, status, label = parts
                state[label] = {"loaded": True,
                                "exit": 0 if status in ("0", "-") else int(status)}
    except Exception:  # launchctl 실패해도 대시보드는 뜬다
        pass
    return state


def parse_frontmatter(path):
    """노트 frontmatter 필드만 얕게 파싱 (created/status/verified/summary_model/speakers)."""
    fm = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            first = f.readline()
            if first.strip() != "---":
                return fm
            for ln in f:
                s = ln.rstrip("\n")
                if s.strip() == "---":
                    break
                if ":" in s:
                    k, v = s.split(":", 1)
                    fm[k.strip()] = v.strip()
    except OSError:
        pass
    return fm


def parse_speakers(raw):
    """frontmatter speakers 배열 파싱. 따옴표 유무 혼재 + 항목 내 쉼표(괄호 안) 대응.
    예: ["화자 A", "화자 B"] / [?(교육·매뉴얼 담당, 근거), ?(강사)]"""
    s = raw.strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    items, buf, depth, quote = [], [], 0, None
    for ch in s:
        if quote:
            if ch == quote:
                quote = None
            else:
                buf.append(ch)
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "([{":
            depth += 1
            buf.append(ch)
        elif ch in ")]}":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            items.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        items.append("".join(buf).strip())
    return [i for i in items if i]


def scan_notes(output_dir):
    notes = []
    try:
        names = sorted(os.listdir(output_dir), reverse=True)
    except OSError:
        return notes
    for name in names:
        if not name.endswith(".md") or name.startswith("."):
            continue
        fm = parse_frontmatter(os.path.join(output_dir, name))
        title = re.sub(r"^\d{6}_", "", name[:-3])
        verified = None
        if fm.get("verified") == "true":
            verified = True
        elif fm.get("verified") == "false":
            verified = False
        speakers = parse_speakers(fm.get("speakers", ""))
        notes.append({
            "file": name, "title": title,
            "date": fm.get("created", "20" + name[:2] + "-" + name[2:4] + "-" + name[4:6] if re.match(r"^\d{6}_", name) else ""),
            "status": fm.get("status", "active"), "verified": verified,
            "model": fm.get("summary_model") or None,
            "engine": "—",  # frontmatter에 미기록 — 정직하게 표기
            "speakers": speakers,
        })
    notes.sort(key=lambda n: (n["date"], n["file"]), reverse=True)
    return notes


def build_data():
    now = dt.datetime.now()
    log_dir = CFG["LOG_DIR"]
    pipeline = read_lines(os.path.join(log_dir, "pipeline.log"))

    interval = int(CFG.get("PULL_INTERVAL") or 900)
    last_pull = last_ts(pipeline, "[pull]")
    if last_pull:
        nxt = dt.datetime.strptime(last_pull, "%Y-%m-%d %H:%M:%S") + dt.timedelta(seconds=interval)
        next_pull = nxt.strftime("%Y-%m-%d %H:%M 예정")
    else:
        next_pull = "— (pull 기록 없음)"

    # ── launchd 잡 ──
    lstate = launchctl_jobs()
    prune_lines = read_lines(os.path.join(log_dir, "prune.out.log"))
    job_last = {
        "pull": last_pull,
        "process": last_ts(pipeline, "노트 생성") or last_ts(pipeline, "처리 시작"),
        "prune": last_ts(prune_lines),
    }
    jobs = []
    for jid, script, trigger in [
        ("pull", "plaud_pull.py", f"{interval}초 간격 · RunAtLoad"),
        ("process", "process_inbox.py", "INBOX 폴더 감시 · RunAtLoad"),
        ("prune", "prune_audio.py", "매일 03:00"),
    ]:
        label = f"com.plaud-obsidian.{jid}"
        st = lstate.get(label, {"loaded": False, "exit": 0})
        ts = job_last.get(jid)
        jobs.append({"id": jid, "label": label, "script": script, "trigger": trigger,
                     "loaded": st["loaded"], "exit": st["exit"],
                     "last": ts[5:16] if ts else "—"})

    # ── 카운터 ──
    def count_lines(path):
        return sum(1 for ln in read_lines(path) if ln.strip())

    inbox_dir = CFG["INBOX_DIR"]
    failed_dir = os.path.join(inbox_dir, "_failed")
    try:
        inbox_n = sum(1 for n in os.listdir(inbox_dir)
                      if os.path.splitext(n)[1].lower() in AUDIO_EXT)
    except OSError:
        inbox_n = 0
    pending = []
    for ln in read_lines(CFG["PENDING_PATH"]):
        parts = ln.split("\t")
        if len(parts) == 2 and parts[1].isdigit():
            pending.append({"id": parts[0], "tries": int(parts[1])})
    failed = []
    try:
        for n in sorted(os.listdir(failed_dir)):
            p = os.path.join(failed_dir, n)
            if not os.path.isfile(p):
                continue
            stt = os.stat(p)
            failed.append({"name": n, "size": f"{stt.st_size / 1e6:.1f} MB",
                           "at": dt.datetime.fromtimestamp(stt.st_mtime).strftime("%m-%d %H:%M")})
    except OSError:
        pass
    skipped = [ln.strip() for ln in read_lines(CFG["SKIP_PATH"]) if ln.strip()]
    pulled_n = count_lines(CFG["STATE_PATH"])
    notes = scan_notes(CFG["OUTPUT_DIR"])
    try:
        archive_n = sum(1 for n in os.listdir(CFG["ARCHIVE_DIR"]) if not n.startswith("."))
    except OSError:
        archive_n = 0

    funnel = [
        {"key": "pulled", "label": "수신", "value": pulled_n, "src": "pulled_ids.txt", "to": "notes"},
        {"key": "inbox", "label": "수신함 대기", "value": inbox_n, "src": "INBOX_DIR", "to": "queues"},
        {"key": "pending", "label": "보류", "value": len(pending), "src": "pending_ids.txt", "to": "queues"},
        {"key": "failed", "label": "전사 실패", "value": len(failed), "src": "_failed/", "to": "queues"},
        {"key": "skipped", "label": "건너뜀", "value": len(skipped), "src": "skipped_ids.txt", "to": "queues"},
        {"key": "notes", "label": "노트", "value": len(notes), "src": "OUTPUT_DIR", "to": "notes"},
        {"key": "archive", "label": "아카이브", "value": archive_n, "src": "ARCHIVE_DIR", "to": "notes"},
    ]

    # ── 타임라인: pipeline.log 마지막 10개 라인 ──
    timeline = []
    for ln in reversed([l for l in pipeline if l.strip()]):
        m = TS_RE.match(ln)
        timeline.append({
            "t": m.group(1)[5:] if m else "",
            "kind": classify(ln),
            "text": TS_RE.sub("", ln).strip(),
        })
        if len(timeline) >= 10:
            break

    # ── 정합성 갭 (추정치 — 로컬 투입 노트는 pull 유래와 구분 불가) ──
    unexplained = max(0, pulled_n - len(notes) - len(skipped) - len(pending) - len(failed))
    gap = {
        "pulled": pulled_n, "notes": len(notes), "localNotes": 0,
        "rows": [
            {"label": "수신 id (pulled_ids.txt)", "value": pulled_n, "sign": ""},
            {"label": "노트 생성 (OUTPUT_DIR — 로컬 투입분 포함 추정)", "value": len(notes), "sign": "−"},
            {"label": "건너뜀 (skipped_ids.txt)", "value": len(skipped), "sign": "−"},
            {"label": "보류 큐 (pending_ids.txt)", "value": len(pending), "sign": "−"},
            {"label": "전사 실패 격리 (_failed/)", "value": len(failed), "sign": "−"},
        ],
        "unexplained": unexplained,
    }

    # ── 로그 7종 tail ──
    log_files = []
    for name in ["pipeline.log", "plaudpull.out.log", "plaudpull.err.log",
                 "launchd.out.log", "launchd.err.log", "prune.out.log", "prune.err.log"]:
        log_files.append({"name": name,
                          "lines": read_lines(os.path.join(log_dir, name))[-300:]})

    # ── 설정 (시크릿은 set 불리언만 — 값은 절대 직렬화하지 않는다) ──
    def secret_set(key):
        return bool(CFG.get(key))

    vault = CFG.get("VAULT_PATH", "")
    inbox_warn = None
    if vault and os.path.realpath(inbox_dir).startswith(os.path.realpath(vault) + os.sep):
        inbox_warn = ("볼트 안 경로 — 처리 전 오디오가 볼트 동기화로 클라우드에 올라갈 수 있어요. "
                      "볼트 밖 경로 권장 (변경 후 install.sh 재실행 필요).")

    def disp(path):
        home = os.path.expanduser("~")
        return path.replace(home, "~") if path else "(미설정)"

    settings = [
        {"group": "경로", "keys": [
            {"k": "VAULT_PATH", "v": disp(vault), "d": "옵시디언 볼트 루트", "req": True},
            {"k": "INBOX_DIR", "v": disp(inbox_dir), "d": "오디오 수신함 (launchd 감시)",
             **({"warn": inbox_warn} if inbox_warn else {})},
            {"k": "OUTPUT_DIR", "v": disp(CFG["OUTPUT_DIR"]), "d": "생성 노트 폴더"},
            {"k": "ARCHIVE_DIR", "v": disp(CFG["ARCHIVE_DIR"]), "d": "처리 완료 오디오 보관"},
        ]},
        {"group": "전사", "keys": [
            {"k": "WHISPER_LANG", "v": CFG["WHISPER_LANG"], "d": "전사 언어"},
            {"k": "WHISPER_MODEL", "v": CFG["WHISPER_MODEL"], "d": "whisper.cpp 모델 (models/)"},
            {"k": "SPEAKERS_EXPECTED", "v": CFG["SPEAKERS_EXPECTED"], "d": "AssemblyAI 화자 수 힌트 — 0이면 미사용"},
            {"k": "ASSEMBLYAI_API_KEY", "secret": True, "set": secret_set("ASSEMBLYAI_API_KEY"),
             "d": "설정됨 → 클라우드 전사+화자분리 1순위. 오디오가 AssemblyAI 서버로 전송됨" if secret_set("ASSEMBLYAI_API_KEY") else "미설정 → 클라우드 전사 비활성 (100% 로컬)"},
            {"k": "HF_TOKEN", "secret": True, "set": secret_set("HF_TOKEN"),
             "d": "설정됨 → WhisperX 로컬 화자분리 사용 가능" if secret_set("HF_TOKEN") else "미설정 → WhisperX 로컬 화자분리 비활성 (2순위 폴백 없음)"},
        ]},
        {"group": "요약·검증", "keys": [
            {"k": "ANTHROPIC_API_KEY", "secret": True, "set": secret_set("ANTHROPIC_API_KEY"),
             "d": "설정됨 → Claude 6섹션 회의록 요약 사용. 미설정 시 전사 원문만 저장" if secret_set("ANTHROPIC_API_KEY") else "미설정 → 요약 생략, 전사 원문만 저장"},
            {"k": "CLAUDE_MODEL", "v": CFG["CLAUDE_MODEL"], "d": "요약 모델"},
            {"k": "OPENAI_API_KEY", "secret": True, "set": secret_set("OPENAI_API_KEY"),
             "d": "설정됨 → GPT 교차검증(사실오류·누락 교정) 사용" if secret_set("OPENAI_API_KEY") else "미설정 → 교차검증 생략 (verified: false)"},
            {"k": "OPENAI_MODEL", "v": CFG["OPENAI_MODEL"], "d": "교차검증 모델"},
            {"k": "SUMMARY_PROMPT_FILE", "v": CFG["SUMMARY_PROMPT_FILE"], "d": "미설정 → 내장 한국어 6섹션 회의록 프롬프트 사용"},
        ]},
        {"group": "운영", "keys": [
            {"k": "PULL_INTERVAL", "v": CFG["PULL_INTERVAL"], "d": "PLAUD 클라우드 pull 주기(초)",
             "warn": "변경 시 bash install.sh 재실행 필요 — launchd 플리스트가 재생성됩니다."},
            {"k": "AUDIO_RETENTION_DAYS", "v": CFG["AUDIO_RETENTION_DAYS"],
             "d": "0 = 자동 삭제 안 함 — prune 잡이 매일 03:00 스킵" if CFG["AUDIO_RETENTION_DAYS"] == "0" else "아카이브 오디오 보관일 — 초과분은 매일 03:00 삭제"},
        ]},
    ]

    out_dir = CFG["OUTPUT_DIR"]
    output_rel = (os.path.relpath(out_dir, vault)
                  if vault and os.path.realpath(out_dir).startswith(os.path.realpath(vault) + os.sep)
                  else os.path.basename(out_dir))

    return {
        "now": now.strftime("%Y-%m-%d %H:%M:%S"),
        "lastPull": last_pull or "—",
        "nextPull": next_pull,
        "pullInterval": interval,
        "vaultName": os.path.basename(vault.rstrip("/")) if vault else "",
        "outputRel": output_rel,
        "jobs": jobs, "funnel": funnel, "timeline": timeline,
        "pendingQ": pending, "failedQ": failed, "skippedQ": skipped,
        "notes": notes, "gap": gap, "logFiles": log_files, "settings": settings,
    }


def render_module(data):
    parts = []
    for key, val in data.items():
        parts.append(f"export const {key} = {json.dumps(val, ensure_ascii=False)};")
    return "// 실시간 생성 (serve.py) — dash-data.js 계약과 동일\n" + "\n".join(parts) + "\n"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DASH_DIR, **kwargs)

    def do_GET(self):
        if self.path.split("?")[0] == "/dash-data.js":
            try:
                body = render_module(build_data()).encode("utf-8")
            except Exception as e:  # 데이터 수집 실패 시에도 서버는 살아 있는다
                self.send_error(500, f"data build failed: {type(e).__name__}")
                sys.stderr.write(f"[dash] 데이터 생성 실패: {e}\n")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, fmt, *args):  # 조용한 액세스 로그
        if "/dash-data.js" not in (str(args[0]) if args else ""):  # log_error는 HTTPStatus를 넘긴다
            sys.stderr.write("[dash] " + fmt % args + "\n")


def main():
    ap = argparse.ArgumentParser(description="plaud 대시보드 로컬 서버 (127.0.0.1 전용)")
    ap.add_argument("--port", type=int, default=8791)  # 8787은 이 머신에서 다른 서비스가 사용 중
    args = ap.parse_args()
    addr = ("127.0.0.1", args.port)  # 보안: 루프백 고정 — 옵션으로도 열지 않는다
    httpd = http.server.ThreadingHTTPServer(addr, Handler)
    print(f"[dash] http://127.0.0.1:{args.port} — 읽기 전용 대시보드 (Ctrl+C 종료)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[dash] 종료")


if __name__ == "__main__":
    main()
