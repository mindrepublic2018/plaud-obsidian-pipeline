#!/usr/bin/env python3
"""
PLAUD 클라우드에서 신규 녹음 오디오를 당겨와 INBOX_DIR 로 떨군다.
  plaud files (페이지네이션) → 신규 id(state로 dedup) → plaud audio <id> → S3 URL → curl 다운로드
  → /tmp 에 받은 뒤 INBOX_DIR 로 원자적 이동(process_inbox.py 워처가 처리)
audio 가 서버에서 아직 준비 안 된 녹음은 state/pending_ids.txt 로 재시도하다가
한도(MAX_PENDING_ATTEMPTS) 초과 시에만 영구 스킵한다.
launchd 타이머(StartInterval)로 주기 실행. PLAUD OAuth 토큰은 `plaud login` 시 저장된 것 사용.
설정은 레포 루트 config.env (scripts/_config.py 가 해석).
"""
import os
import re
import subprocess
import datetime
import fcntl
import shutil

from _config import load, migrate_legacy_state, HOME

CFG = load()
INBOX = CFG["INBOX_DIR"]
STATE = CFG["STATE_PATH"]        # 이미 받은 id (dedup)
SKIP = CFG["SKIP_PATH"]          # 재시도 한도 초과 등 영구 스킵
PENDING = CFG["PENDING_PATH"]    # audio 미준비 → 재시도 대기 (id<TAB>시도횟수)
PULL_LOCK = CFG["PULL_LOCK_PATH"]
LOGDIR = CFG["LOG_DIR"]
CURL = shutil.which("curl") or "/usr/bin/curl"
PAGE_SIZE = 100
# audio 가 서버에서 준비될 때까지 재시도. 15분 간격 × 96 ≈ 24h 후에도 안 되면 영구 스킵.
# (긴 녹음은 업로드/서버처리에 시간이 걸려, 첫 pull 때 일시적으로 audio 가 없을 수 있음)
MAX_PENDING_ATTEMPTS = 96
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


def load_pending(path):
    """id → 시도횟수 dict 로드 (id<TAB>횟수). 깨진 줄은 횟수 0 으로 관용 처리."""
    d = {}
    if not os.path.isfile(path):
        return d
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            parts = ln.split("\t")
            try:
                d[parts[0]] = int(parts[1]) if len(parts) > 1 else 0
            except ValueError:
                d[parts[0]] = 0
    return d


def save_pending(path, d):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for fid, n in d.items():
            f.write(f"{fid}\t{n}\n")
    os.replace(tmp, path)


def _env():
    # plaud 는 `env node` 스크립트 → node 경로를 PATH 에 보장
    e = dict(os.environ)
    extra = ["/usr/local/bin", "/opt/homebrew/bin", "/usr/bin", "/bin", f"{HOME}/.npm-global/bin"]
    e["PATH"] = ":".join(extra + [p for p in e.get("PATH", "").split(":") if p and p not in extra])
    return e


def run(args, timeout=120):
    return subprocess.run([PLAUD, *args], capture_output=True, text=True, timeout=timeout, env=_env())


def parse_files_output(text, default_date=None):
    """`plaud files` 출력 한 페이지에서 (id, date) 추출 (사람용 텍스트 출력 파싱)."""
    default = default_date or datetime.date.today().strftime("%Y-%m-%d")
    items = []
    for ln in text.splitlines():
        m = ID_RE.match(ln.strip())
        if m:
            d = DATE_RE.search(ln)
            items.append((m.group(1), d.group(1) if d else default))
    return items


def list_all_files():
    """모든 페이지의 (id, date) 수집."""
    out = []
    page = 1
    while page <= 50:  # 안전 상한
        r = run(["files", "-p", str(page), "-s", str(PAGE_SIZE)])
        if r.returncode != 0:
            log(f"files 실패 p{page}: {r.stderr.strip()[:160] or r.stdout.strip()[:160]}")
            break
        ids_this = parse_files_output(r.stdout)
        # CLI 가 성공했고 출력도 있는데 id 가 하나도 안 잡히면 출력 포맷 변경 의심
        if page == 1 and not ids_this and r.stdout.strip():
            log("경고: files 출력에서 녹음 id 를 못 찾음 — 녹음이 0개이거나 "
                "plaud CLI 출력 포맷이 바뀌었을 수 있음 (`plaud update` 확인)")
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


def pull_new():
    os.makedirs(INBOX, exist_ok=True)
    pulled, skipped = load_set(STATE), load_set(SKIP)
    pending = load_pending(PENDING)
    files = list_all_files()
    if not files:
        log("녹음 목록 비어있음/조회 실패 (plaud login 만료 여부 확인)")
        return
    new = [(fid, d) for fid, d in files if fid not in pulled and fid not in skipped]
    log(f"전체 {len(files)}개 / 신규·재시도 {len(new)}개")
    for fid, d in new:
        url = get_audio_url(fid)
        if not url:
            # audio 미준비 — 영구 스킵하지 말고 재시도. 한도 초과 시에만 영구 스킵.
            n = pending.get(fid, 0) + 1
            if n >= MAX_PENDING_ATTEMPTS:
                log(f"  audio 미준비 {n}회 — 재시도 한도 초과, 영구 스킵: {fid}")
                add_to(SKIP, fid)
                pending.pop(fid, None)
            else:
                pending[fid] = n
                log(f"  audio 미준비 — 재시도 예정({n}/{MAX_PENDING_ATTEMPTS}): {fid}")
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
        pending.pop(fid, None)         # 받았으면 재시도 목록에서 제거
        log(f"  ✓ 받음 → {os.path.basename(dest)}")
    save_pending(PENDING, pending)


def main():
    if not CFG.get("VAULT_PATH"):
        log("VAULT_PATH 미설정 — config.env 를 확인하세요")
        return
    if not (os.path.isfile(PLAUD) or shutil.which("plaud")):
        log(f"plaud CLI 없음: {PLAUD} (npm install -g @plaud-ai/cli 후 plaud login)")
        return
    migrate_legacy_state()
    # 타이머 주기보다 pull 이 오래 걸릴 때(첫 동기화 등) 겹침 방지
    lockf = open(PULL_LOCK, "w")
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("이전 pull 아직 실행 중 — 종료")
        lockf.close()
        return
    try:
        pull_new()
    finally:
        fcntl.flock(lockf, fcntl.LOCK_UN)
        lockf.close()


if __name__ == "__main__":
    main()
