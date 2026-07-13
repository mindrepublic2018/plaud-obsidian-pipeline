#!/usr/bin/env python3
"""
오디오 아카이브 정리: ARCHIVE_DIR 안에서 AUDIO_RETENTION_DAYS 보다 오래된
오디오 파일을 삭제한다. 노트(전사·요약)는 건드리지 않으며, 원본은 PLAUD
클라우드에 남아 있으므로 필요 시 다시 받을 수 있다.

AUDIO_RETENTION_DAYS=0(기본)이면 아무것도 지우지 않는다 — 자동삭제는 옵트인.
launchd 잡 com.plaud-obsidian.prune 이 매일 03:00 에 실행 (install.sh 가 생성).
설정은 레포 루트 config.env (scripts/_config.py 가 해석).
"""
import os
import sys
import time
from datetime import datetime

from _config import load

CFG = load()
ARCHIVE = CFG["ARCHIVE_DIR"]
AUDIO_EXTS = {".mp3", ".aiff", ".aif", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac"}


def retention_days():
    try:
        return int(CFG.get("AUDIO_RETENTION_DAYS") or 0)
    except ValueError:
        return 0


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [prune] {msg}", flush=True)


def main():
    days = retention_days()
    if days <= 0:
        log("AUDIO_RETENTION_DAYS=0 — 자동삭제 비활성, 스킵")
        return 0
    if not os.path.isdir(ARCHIVE):
        log(f"아카이브 폴더 없음, 스킵: {ARCHIVE}")
        return 0

    cutoff = time.time() - days * 86400
    deleted = 0
    freed = 0
    kept = 0

    for name in os.listdir(ARCHIVE):
        path = os.path.join(ARCHIVE, name)
        if not os.path.isfile(path):
            continue
        if os.path.splitext(name)[1].lower() not in AUDIO_EXTS:
            continue
        mtime = os.path.getmtime(path)
        if mtime >= cutoff:
            kept += 1
            continue
        size = os.path.getsize(path)
        try:
            os.remove(path)
            deleted += 1
            freed += size
            log(f"삭제: {name} ({size / 1_048_576:.1f}MB, "
                f"{(time.time() - mtime) / 86400:.1f}일 경과)")
        except OSError as e:
            log(f"삭제 실패: {name} — {e}")

    log(f"완료 — 삭제 {deleted}개 / {freed / 1_048_576:.1f}MB 확보 / "
        f"보관 {kept}개 (보관기간 {days}일)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
