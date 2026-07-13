#!/bin/bash
# ============================================================
# plaud-obsidian-pipeline — 제거 스크립트
# launchd 잡을 내리고 plist 를 삭제합니다.
# 볼트 노트/오디오 아카이브/모델/상태파일은 그대로 둡니다(수동 삭제).
# ============================================================
set -uo pipefail

LA="$HOME/Library/LaunchAgents"
LABEL_PULL="com.plaud-obsidian.pull"
LABEL_PROC="com.plaud-obsidian.process"
LABEL_PRUNE="com.plaud-obsidian.prune"

for label in "$LABEL_PROC" "$LABEL_PULL" "$LABEL_PRUNE"; do
  plist="$LA/$label.plist"
  if [ -f "$plist" ]; then
    echo "▶ unload $label"
    launchctl unload -w "$plist" 2>/dev/null || true
    rm -f "$plist"
    echo "  ✓ 제거: $plist"
  else
    echo "▷ 없음(건너뜀): $plist"
  fi
done

echo ""
echo "✅ launchd 잡 제거 완료."
echo "ℹ️  볼트 노트·오디오 아카이브·whisper 모델·config.env 는 보존되었습니다."
echo "    완전 삭제하려면 레포 폴더와 모델/로그를 직접 지우세요."
