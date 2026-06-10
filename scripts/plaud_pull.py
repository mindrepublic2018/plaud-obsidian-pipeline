#!/usr/bin/env python3
"""
PLAUD 클라우드에서 신규 녹음 오디오를 당겨와 INBOX_DIR 로 떨군다.
  plaud files (페이지네이션) → 신규 id(state로 dedup) → plaud audio <id> → S3 URL → curl 다운로드
  → /tmp 에 받은 뒤 INBOX_DIR 로 원자적 이동(process_inbox.py 워처가 처리)
launchd 타이머(StartInterval)로 주기 실행. PLAUD OAuth 토큰은 `plaud login` 시 저장된 것 사용.
설정은 레포 루트 config.env (scripts/_config.py 가 해석).
"""
import os
import re
import subprocess
import datetime
import shutil

from _config import load, HOME

CFG = load()
INBOX = CFG["INBOX_DIR"]
STATE = CFG["STATE_PATH"]        # 이미 받은 id (dedup)
SKIP = CFG["SKIP_PATH"]          # audio 없음 등 영구 스킵
LOGDIR = CFG["LOG_DIR"]
CURL = shutil.which("curl") or "/usr/bin/curl"
PAGE_SIZE = 100
ID_RE = re.compile(r"^([0-9a-f]{32})\b")
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def find_plaud():
    """plaud CLI 절대경로 탐색 (launchd PATH 가 빈약하므로 여러 후보 확인)."""
    direct = ["plaud"]
    paths = [
        f"{HOME}/.npm-global/bin/plaud",
        "/opt/homebrew/bin/plaud",
        "/usr/local/bin/plaud",
    ]
    for c in direct:
        p = shutil.which(c)
        if p:
            return p
    for p in paths:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return paths[0]  # 에러 메시지용 폴백


PLAUD = find_plaud()


def log(msg):
    os.makedirs(LOGDIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [pull] {msg}"
    print(line)
    with open(f"{LOGDIR}/pipeline.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_set(path):
    if not os.path.isfile(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {l.strip() for l in f if l.strip()}


def add_to(path, item):
    with open(path, "a", encoding="utf-8") as f:
        f.write(item + "\n")


def _env():
    # plaud 는 `env node` 스크립트 → node 경로를 PATH 에 보장
    e = dict(os.environ)
    extra = ["/usr/local/bin", "/opt/homebrew/bin", "/usr/bin", "/bin", f"{HOME}/.npm-global/bin"]
    e["PATH"] = ":".join(extra + [p for p in e.get("PATH", "").split(":") if p and p not in extra])
    return e


def run(args, timeout=120):
    return subprocess.run([PLAUD, *args], capture_output=True, text=True, timeout=timeout, env=_env())


def list_all_files():
    """모든 페이지의 (id, date) 수집."""
    out = []
    page = 1
    while page <= 50:  # 안전 상한
        r = run(["files", "-p", str(page), "-s", str(PAGE_SIZE)])
        if r.returncode != 0:
            log(f"files 실패 p{page}: {r.stderr.strip()[:160] or r.stdout.strip()[:160]}")
            break
        ids_this = []
        for ln in r.stdout.splitlines():
            m = ID_RE.match(ln.strip())
            if m:
                fid = m.group(1)
                d = DATE_RE.search(ln)
                ids_this.append((fid, d.group(1) if d else datetime.date.today().strftime("%Y-%m-%d")))
        out.extend(ids_this)
        if len(ids_this) < PAGE_SIZE:
            break
        page += 1
    return out


def get_audio_url(fid):
    r = run(["audio", fid])
    if "not available" in (r.stdout + r.stderr).lower():
        return None
    for ln in r.stdout.splitlines():
        ln = ln.strip()
        if ln.startswith("https://"):
            return ln
    return None


def download(url, dest):
    r = subprocess.run([CURL, "-fSL", "--retry", "2", "-o", dest, url],
                       capture_output=True, text=True, timeout=600)
    return r.returncode == 0 and os.path.isfile(dest) and os.path.getsize(dest) > 1000


def main():
    if not CFG.get("VAULT_PATH"):
        log("VAULT_PATH 미설정 — config.env 를 확인하세요")
        return
    if not (os.path.isfile(PLAUD) or shutil.which("plaud")):
        log(f"plaud CLI 없음: {PLAUD} (npm install -g @plaud-ai/cli 후 plaud login)")
        return
    os.makedirs(INBOX, exist_ok=True)
    pulled, skipped = load_set(STATE), load_set(SKIP)
    files = list_all_files()
    if not files:
        log("녹음 목록 비어있음/조회 실패 (plaud login 만료 여부 확인)")
        return
    new = [(fid, d) for fid, d in files if fid not in pulled and fid not in skipped]
    log(f"전체 {len(files)}개 / 신규 {len(new)}개")
    for fid, d in new:
        url = get_audio_url(fid)
        if not url:
            log(f"  audio 없음 — 영구 스킵: {fid}")
            add_to(SKIP, fid)
            continue
        tmp = f"/tmp/plaud_{fid}.mp3"
        if not download(url, tmp):
            log(f"  다운로드 실패(다음 실행 재시도): {fid}")
            try:
                os.remove(tmp)
            except OSError:
                pass
            continue
        dest = f"{INBOX}/plaud_{d}_{fid[:8]}.mp3"
        shutil.move(tmp, dest)         # 원자적 이동 → 워처가 완전한 파일만 봄
        add_to(STATE, fid)
        log(f"  ✓ 받음 → {os.path.basename(dest)}")


if __name__ == "__main__":
    main()
