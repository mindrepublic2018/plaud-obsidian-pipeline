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
import stat
import sys
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
    "ASSEMBLYAI_API_KEY": "",     # 비우면 클라우드 전사 안 씀 (100% 로컬 동작)
    "SPEAKERS_EXPECTED": "0",     # AssemblyAI 화자 수 힌트 (0 = 미전송, 통화는 2 권장)
    "HF_TOKEN": "",               # WhisperX 화자분리용 HuggingFace 토큰 (선택)
    "ANTHROPIC_API_KEY": "",      # 비우면 요약 생략 (전사만 저장)
    "CLAUDE_MODEL": "claude-opus-5",  # Claude API 요약 모델
    "OPENAI_API_KEY": "",         # 비우면 GPT 교차검증 생략
    "OPENAI_MODEL": "gpt-5.2",    # GPT 교차검증 모델
    "AUDIO_RETENTION_DAYS": "0",  # 아카이브 오디오 보관일. 0 = 자동삭제 안 함
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


def is_secret_key(name):
    """비밀값 키 이름 판별 (*_KEY / *_TOKEN). CLI 출력 마스킹·--get 거부에 사용."""
    return name.endswith("_KEY") or name.endswith("_TOKEN")


def mask_secrets(cfg):
    """비밀값이 설정돼 있으면 '***' 로 가린 사본 반환. 빈 값은 그대로(미설정 판별용)."""
    return {k: ("***" if is_secret_key(k) and v else v) for k, v in cfg.items()}


def ensure_private_dir(path):
    """0700 디렉터리 보장 (녹음 임시파일용 — /tmp 대신). 이미 있어도 퍼미션을 다시 조인다."""
    os.makedirs(path, exist_ok=True)
    os.chmod(path, 0o700)


def _warn_insecure_mode(path):
    """시크릿 파일이 group/other 에 열려 있으면 stderr 로 경고 (stdout 은 --get 소비자가 파싱)."""
    try:
        mode = stat.S_IMODE(os.stat(path).st_mode)
    except OSError:
        return
    if mode & 0o077:
        print(f"경고: {path} 퍼미션이 {oct(mode)} — 'chmod 600 {path}' 권장 (API 키 노출 위험)",
              file=sys.stderr)


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
    # basename 강제 — WHISPER_MODEL 에 '../' 등이 와도 models/ 밖으로 못 나감
    cfg["MODEL_PATH"] = os.path.join(REPO_ROOT, "models", os.path.basename(cfg["WHISPER_MODEL"]))
    cfg["LOG_DIR"] = os.path.join(REPO_ROOT, "logs")
    cfg["STATE_DIR"] = STATE_DIR
    cfg["TMP_DIR"] = os.path.join(STATE_DIR, "tmp")   # 임시파일 (0700, /tmp 대신)
    cfg["STATE_PATH"] = os.path.join(STATE_DIR, "pulled_ids.txt")
    cfg["SKIP_PATH"] = os.path.join(STATE_DIR, "skipped_ids.txt")
    cfg["LOCK_PATH"] = os.path.join(STATE_DIR, ".lock")
    cfg["PULL_LOCK_PATH"] = os.path.join(STATE_DIR, ".pull.lock")
    cfg["FAIL_PATH"] = os.path.join(STATE_DIR, "transcribe_failures.txt")
    cfg["PENDING_PATH"] = os.path.join(STATE_DIR, "pending_ids.txt")
    # 노트는 만들었지만 아카이브 이동이 실패한 오디오 (재전사 없이 이동만 재시도 — 중복 노트·API 비용 방지)
    cfg["PROCESSED_PATH"] = os.path.join(STATE_DIR, "processed_notes.txt")
    # 선택 기능(클라우드 전사/화자분리)용 키 파일·경로 — config.env 값이 우선
    cfg["AAI_KEY_PATH"] = os.path.join(REPO_ROOT, ".assemblyai_key")
    cfg["HF_TOKEN_PATH"] = os.path.join(REPO_ROOT, ".hf_token")
    cfg["ANTHROPIC_KEY_PATH"] = os.path.join(REPO_ROOT, ".anthropic_key")
    cfg["OPENAI_KEY_PATH"] = os.path.join(REPO_ROOT, ".openai_key")
    cfg["WHISPERX_PY"] = os.path.join(REPO_ROOT, ".venv-whisperx", "bin", "python")
    cfg["WHISPERX_SCRIPT"] = os.path.join(REPO_ROOT, "scripts", "whisperx_transcribe.py")
    # 시크릿 파일 퍼미션 점검 (존재하는 것만, stderr 경고)
    for p in (CONFIG_PATH, cfg["AAI_KEY_PATH"], cfg["HF_TOKEN_PATH"],
              cfg["ANTHROPIC_KEY_PATH"], cfg["OPENAI_KEY_PATH"]):
        if os.path.isfile(p):
            _warn_insecure_mode(p)
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
    import json

    conf = load()
    if len(sys.argv) >= 3 and sys.argv[1] == "--get":
        # 비밀 키는 --get 으로도 원문을 내주지 않는다 (터미널 스크롤·로그 유출 방지)
        key = sys.argv[2]
        val = conf.get(key, "")
        print("***" if is_secret_key(key) and val else val)
    elif len(sys.argv) >= 2 and sys.argv[1] == "--json":
        print(json.dumps(mask_secrets(conf), ensure_ascii=False))
    else:
        print(json.dumps(mask_secrets(conf), ensure_ascii=False, indent=2))
