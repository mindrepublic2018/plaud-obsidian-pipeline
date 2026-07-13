#!/bin/bash
# ============================================================
# plaud-obsidian-pipeline — 설치 스크립트 (macOS)
# 사용법:  bash install.sh
#   1) brew 의존성(whisper-cpp, ffmpeg) + node + @plaud-ai/cli 설치
#   2) config.env 없으면 대화형으로 생성 (볼트 경로/출력 폴더/언어/AssemblyAI 키)
#   3) whisper 모델(~1.5GB) 다운로드
#   4) launchd plist 3개 생성 (pull/process/prune — 이 레포 위치 기준)
#   5) 사용자 직접 단계 안내(plaud login 등) → launchctl load
# 스크립트는 이 레포 디렉터리에서 in-place 실행됩니다(복사 안 함).
# ============================================================
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="$REPO/scripts"
LA="$HOME/Library/LaunchAgents"
CONFIG="$REPO/config.env"
PY="$(command -v python3 || echo /opt/homebrew/bin/python3)"

LABEL_PULL="com.plaud-obsidian.pull"
LABEL_PROC="com.plaud-obsidian.process"
LABEL_PRUNE="com.plaud-obsidian.prune"

echo "▶ 레포: $REPO"
echo "▶ python3: $PY"

# 0. macOS 확인
if [ "$(uname)" != "Darwin" ]; then
  echo "✗ 이 파이프라인은 macOS(launchd) 전용입니다. 현재: $(uname)"; exit 1
fi

# 1. Homebrew
if ! command -v brew >/dev/null 2>&1; then
  echo "✗ Homebrew 가 없습니다. 먼저 설치: https://brew.sh"; exit 1
fi

# 2. 시스템 의존성
echo "▶ brew 의존성 (whisper-cpp, ffmpeg)..."
brew list whisper-cpp >/dev/null 2>&1 || brew install whisper-cpp
brew list ffmpeg      >/dev/null 2>&1 || brew install ffmpeg

# 3. node + plaud CLI
if ! command -v node >/dev/null 2>&1; then
  echo "✗ node 가 없습니다. 'brew install node' 후 다시 실행하세요."; exit 1
fi
echo "▶ @plaud-ai/cli 전역 설치..."
npm install -g @plaud-ai/cli

# 4. config.env (없으면 대화형 생성)
if [ ! -f "$CONFIG" ]; then
  echo ""
  echo "▶ config.env 가 없습니다. 몇 가지를 물어보고 생성합니다."
  DEFAULT_VAULT="$HOME/Obsidian/MyVault"
  read -r -p "  옵시디언 볼트 경로 [$DEFAULT_VAULT]: " IN_VAULT
  IN_VAULT="${IN_VAULT:-$DEFAULT_VAULT}"
  read -r -p "  노트 출력 폴더명 [Voice Memos]: " IN_OUT
  IN_OUT="${IN_OUT:-Voice Memos}"
  read -r -p "  전사 언어 (ko/en/ja...) [ko]: " IN_LANG
  IN_LANG="${IN_LANG:-ko}"
  echo "  AssemblyAI API 키 (선택): 넣으면 클라우드 전사+화자분리를 1순위로 사용."
  echo "  ⚠️ 키를 넣으면 오디오가 AssemblyAI 서버로 전송됩니다. 비우면 100% 로컬 전사."
  read -r -p "  AssemblyAI API 키 [없음]: " IN_AAI
  {
    echo "# plaud-obsidian-pipeline 설정 (install.sh 가 생성)"
    echo "VAULT_PATH=$IN_VAULT"
    echo "OUTPUT_DIR=\$VAULT_PATH/$IN_OUT"
    echo "WHISPER_LANG=$IN_LANG"
    if [ -n "$IN_AAI" ]; then echo "ASSEMBLYAI_API_KEY=$IN_AAI"; fi
  } > "$CONFIG"
  chmod 600 "$CONFIG"
  echo "  ✓ config.env 작성 완료. (필요하면 직접 편집: $CONFIG)"
else
  echo "▶ config.env 이미 있음 — 그대로 사용 (편집하려면: $CONFIG)"
fi

# 5. config 해석값 가져오기 (_config.py 단일 진실 공급원)
get() { "$PY" "$SCRIPTS/_config.py" --get "$1"; }
VAULT_PATH="$(get VAULT_PATH)"
INBOX_DIR="$(get INBOX_DIR)"
OUTPUT_DIR="$(get OUTPUT_DIR)"
ARCHIVE_DIR="$(get ARCHIVE_DIR)"
MODEL_PATH="$(get MODEL_PATH)"
PULL_INTERVAL="$(get PULL_INTERVAL)"

if [ -z "$VAULT_PATH" ]; then
  echo "✗ VAULT_PATH 가 비었습니다. $CONFIG 를 확인하세요."; exit 1
fi
case "$PULL_INTERVAL" in
  ''|*[!0-9]*) PULL_INTERVAL=900 ;;
esac

echo "▶ 볼트:    $VAULT_PATH"
echo "▶ inbox:   $INBOX_DIR"
echo "▶ 출력:    $OUTPUT_DIR"
echo "▶ archive: $ARCHIVE_DIR"

# 6. 디렉터리
mkdir -p "$INBOX_DIR" "$OUTPUT_DIR" "$ARCHIVE_DIR" "$REPO/models" "$REPO/logs" "$REPO/state" "$LA"
touch "$REPO/state/pulled_ids.txt" "$REPO/state/skipped_ids.txt"

# 7. whisper 모델 (~1.5GB)
if [ ! -f "$MODEL_PATH" ] || [ "$(stat -f%z "$MODEL_PATH" 2>/dev/null || echo 0)" -lt 1000000000 ]; then
  echo "▶ whisper 모델 다운로드 (~1.5GB)..."
  curl -L -o "$MODEL_PATH" \
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$(basename "$MODEL_PATH")"
else
  echo "▶ 모델 이미 있음 — 건너뜀"
fi

# 8. launchd plist 3개 생성
echo "▶ launchd plist 생성..."
PATH_ENV="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$HOME/.npm-global/bin"

cat > "$LA/$LABEL_PROC.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL_PROC</string>
  <key>ProgramArguments</key><array><string>$PY</string><string>$SCRIPTS/process_inbox.py</string></array>
  <key>WatchPaths</key><array><string>$INBOX_DIR</string></array>
  <key>RunAtLoad</key><true/>
  <key>ThrottleInterval</key><integer>20</integer>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>$PATH_ENV</string><key>HOME</key><string>$HOME</string></dict>
  <key>StandardOutPath</key><string>$REPO/logs/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$REPO/logs/launchd.err.log</string>
</dict></plist>
EOF

cat > "$LA/$LABEL_PULL.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL_PULL</string>
  <key>ProgramArguments</key><array><string>$PY</string><string>$SCRIPTS/plaud_pull.py</string></array>
  <key>StartInterval</key><integer>$PULL_INTERVAL</integer>
  <key>RunAtLoad</key><true/>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>$PATH_ENV</string><key>HOME</key><string>$HOME</string></dict>
  <key>StandardOutPath</key><string>$REPO/logs/plaudpull.out.log</string>
  <key>StandardErrorPath</key><string>$REPO/logs/plaudpull.err.log</string>
</dict></plist>
EOF

# 아카이브 오디오 정리 (매일 03:00 — AUDIO_RETENTION_DAYS=0 이면 스크립트가 아무것도 안 지움)
cat > "$LA/$LABEL_PRUNE.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL_PRUNE</string>
  <key>ProgramArguments</key><array><string>$PY</string><string>$SCRIPTS/prune_audio.py</string></array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>0</integer></dict>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>$PATH_ENV</string><key>HOME</key><string>$HOME</string></dict>
  <key>StandardOutPath</key><string>$REPO/logs/prune.out.log</string>
  <key>StandardErrorPath</key><string>$REPO/logs/prune.err.log</string>
</dict></plist>
EOF

echo ""
echo "============================================================"
echo "✅ 기계 설치 완료. 이제 본인이 직접 할 대화형 단계:"
echo "============================================================"
echo "  (a) PLAUD 로그인 (필수):   plaud login        # 브라우저 OAuth"
echo "  (b) Claude Code 설치+로그인 (요약용, 선택):"
echo "        없으면 요약을 건너뛰고 '전사 원문'만 노트에 저장됩니다."
echo "  (c) 모바일에서 보려면: 이 볼트를 평소 쓰는 방식(Obsidian Sync 등)으로 폰과 동기화"
echo ""
echo "  그 다음 launchd 잡 로드:"
echo "    launchctl load -w \"$LA/$LABEL_PROC.plist\""
echo "    launchctl load -w \"$LA/$LABEL_PULL.plist\""
echo "    launchctl load -w \"$LA/$LABEL_PRUNE.plist\"   # 아카이브 정리 (AUDIO_RETENTION_DAYS>0 일 때만 동작)"
echo ""
echo "  검증:"
echo "    launchctl list | grep plaud-obsidian"
echo "    tail -f \"$REPO/logs/pipeline.log\""
echo ""
echo "  빠른 스모크 테스트: 아무 오디오 파일을 $INBOX_DIR 에 복사하면"
echo "    1~2분 내 전사가 시작되고 완료 시 $OUTPUT_DIR 에 노트가 생깁니다."
echo ""
echo "  ⚠️ 맥은 잠자지 않아야 주기 pull 이 돕니다 (시스템 설정 > 디스플레이/배터리)."
echo "  ⚠️ 여러 대 맥에서 동시에 켜지 마세요(중복). uninstall.sh 로 끌 수 있습니다."
echo "============================================================"
