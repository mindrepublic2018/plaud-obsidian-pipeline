#!/usr/bin/env python3
"""
config.env 로더 — 레포 루트의 config.env 를 읽어 설정 dict 를 만든다.
파이썬 스크립트와 install.sh 가 공유하는 단일 진실 공급원(single source of truth).

CLI:
  python3 scripts/_config.py            # 전체 설정 JSON (들여쓰기)
  python3 scripts/_config.py --json     # 전체 설정 JSON (한 줄)
  python3 scripts/_config.py --get KEY  # 특정 키의 해석된 값만 출력 (install.sh 용)
"""
import os
import shutil

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(REPO_ROOT, "config.env")
HOME = os.path.expanduser("~")
STATE_DIR = os.path.join(REPO_ROOT, "state")

# v1 에서 레포 루트에 두던 상태파일 (state/ 로 마이그레이션 대상)
LEGACY_STATE_FILES = ("pulled_ids.txt", "skipped_ids.txt")

# 사용자가 config.env 에서 지정할 수 있는 키와 기본값.
# 빈 문자열 기본값은 "VAULT_PATH 등 다른 값에서 파생"을 의미한다.
DEFAULTS = {
    "VAULT_PATH": "",
    "INBOX_DIR": "",          # 파생 기본: $VAULT_PATH/_inbox
    "OUTPUT_DIR": "",         # 파생 기본: $VAULT_PATH/Voice Memos
    "ARCHIVE_DIR": "",        # 파생 기본: $HOME/Obsidian/_audio-archive
    "WHISPER_MODEL": "ggml-large-v3-turbo.bin",
    "WHISPER_LANG": "ko",
    "PULL_INTERVAL": "900",
    "SUMMARY_PROMPT_FILE": "",
}


def _parse_file(path):
    """KEY=VALUE 파싱. #주석/빈 줄 무시, 둘러싼 따옴표 제거."""
    vals = {}
    if not os.path.isfile(path):
        return vals
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                v = v[1:-1]
            if k:
                vals[k] = v
    return vals


def _expand(value, extra=None):
    """~, $HOME, $VAULT_PATH 등을 해석. extra={'VAULT_PATH': ...} 우선 치환."""
    if not value:
        return value
    if extra:
        for key, repl in extra.items():
            value = value.replace("${" + key + "}", repl).replace("$" + key, repl)
    return os.path.expanduser(os.path.expandvars(value))


def load():
    """해석 완료된 설정 dict 반환. 런타임 경로(MODEL_PATH 등)도 포함."""
    cfg = dict(DEFAULTS)
    cfg.update(_parse_file(CONFIG_PATH))

    vault = _expand(cfg.get("VAULT_PATH", ""), {"HOME": HOME})
    cfg["VAULT_PATH"] = vault
    subst = {"VAULT_PATH": vault, "HOME": HOME}

    if not cfg.get("INBOX_DIR"):
        cfg["INBOX_DIR"] = os.path.join(vault, "_inbox") if vault else ""
    if not cfg.get("OUTPUT_DIR"):
        cfg["OUTPUT_DIR"] = os.path.join(vault, "Voice Memos") if vault else ""
    if not cfg.get("ARCHIVE_DIR"):
        cfg["ARCHIVE_DIR"] = os.path.join(HOME, "Obsidian", "_audio-archive")

    for key in ("INBOX_DIR", "OUTPUT_DIR", "ARCHIVE_DIR", "SUMMARY_PROMPT_FILE"):
        cfg[key] = _expand(cfg.get(key, ""), subst)

    # 레포 안에 두는 런타임 경로 (전부 .gitignore 대상)
    cfg["REPO_ROOT"] = REPO_ROOT
    cfg["MODEL_PATH"] = os.path.join(REPO_ROOT, "models", cfg["WHISPER_MODEL"])
    cfg["LOG_DIR"] = os.path.join(REPO_ROOT, "logs")
    cfg["STATE_DIR"] = STATE_DIR
    cfg["STATE_PATH"] = os.path.join(STATE_DIR, "pulled_ids.txt")
    cfg["SKIP_PATH"] = os.path.join(STATE_DIR, "skipped_ids.txt")
    cfg["LOCK_PATH"] = os.path.join(STATE_DIR, ".lock")
    cfg["PULL_LOCK_PATH"] = os.path.join(STATE_DIR, ".pull.lock")
    cfg["FAIL_PATH"] = os.path.join(STATE_DIR, "transcribe_failures.txt")
    return cfg


def migrate_legacy_state():
    """v1(레포 루트) 상태파일을 state/ 로 이동. 멱등 — 스크립트 시작 시 호출."""
    os.makedirs(STATE_DIR, exist_ok=True)
    for name in LEGACY_STATE_FILES:
        old = os.path.join(REPO_ROOT, name)
        new = os.path.join(STATE_DIR, name)
        if os.path.isfile(old) and not os.path.isfile(new):
            shutil.move(old, new)


if __name__ == "__main__":
    import sys
    import json

    conf = load()
    if len(sys.argv) >= 3 and sys.argv[1] == "--get":
        print(conf.get(sys.argv[2], ""))
    elif len(sys.argv) >= 2 and sys.argv[1] == "--json":
        print(json.dumps(conf, ensure_ascii=False))
    else:
        print(json.dumps(conf, ensure_ascii=False, indent=2))
