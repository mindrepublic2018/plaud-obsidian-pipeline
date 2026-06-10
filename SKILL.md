---
name: plaud-obsidian-pipeline
description: Use when the user wants to set up, install, configure, or troubleshoot the PLAUD → Obsidian voice-memo automation on macOS — pulling PLAUD recordings without a subscription, transcribing locally with Whisper, and auto-creating Obsidian notes. Triggers include "PLAUD 음성메모 자동화 설치", "플라우드 옵시디언 파이프라인 설정", "set up plaud pipeline", "install plaud-obsidian".
---

# plaud-obsidian-pipeline

PLAUD 녹음을 **구독 없이(기기값만)** 빼와 로컬 Whisper 로 전사·요약해 Obsidian 노트로 자동화하는 macOS 파이프라인을 설치·설정·점검한다.

## 동작 개요
- launchd 2단계: `plaud_pull.py`(타이머, PLAUD 클라우드 pull) + `process_inbox.py`(폴더감시, 전사·요약).
- 전사: whisper.cpp 로컬. 요약: `claude -p`(있으면) / 없으면 전사 원문만 저장.
- 설정: 레포 루트 `config.env` (`scripts/_config.py` 가 해석).
- macOS 전용. 모바일은 볼트 동기화(Obsidian Sync 등)로 노트만 따라오는 뷰어.

## 설치 절차 (이 순서대로 진행)

1. **사전 확인 — 사용자에게 묻기**
   - PLAUD 계정이 있는지, 옵시디언 볼트 경로가 무엇인지.
   - Homebrew/node 설치 여부(없으면 안내). macOS 인지 확인(아니면 중단).

2. **설치 스크립트 실행**
   ```bash
   bash install.sh
   ```
   - `config.env` 가 없으면 스크립트가 대화형으로 볼트 경로/출력 폴더/언어를 물어 생성한다.
     비대화형 환경이면 먼저 `cp config.env.example config.env` 후 사용자가 값을 채우게 하라.
   - whisper 모델(~1.5GB) 다운로드가 포함되어 시간이 걸린다 → `run_in_background` 권장.

3. **사용자가 직접 해야 하는 단계 (Claude 가 대신 못 함 — 반드시 사용자에게 위임)**
   - `plaud login` — 브라우저 OAuth. 토큰은 `~/.plaud/tokens.json` 에 저장(레포 밖, 커밋 금지).
   - (선택) `claude` 로그인 — 요약을 쓰려면. 없으면 전사-only 폴백.
   - 모바일에서 보려면 볼트를 평소 방식(Obsidian Sync 등)으로 폰과 동기화.

4. **launchd 잡 로드**
   ```bash
   launchctl load -w ~/Library/LaunchAgents/com.plaud-obsidian.process.plist
   launchctl load -w ~/Library/LaunchAgents/com.plaud-obsidian.pull.plist
   ```

5. **검증**
   ```bash
   launchctl list | grep plaud-obsidian
   tail -n 40 logs/pipeline.log
   ```
   - pull 이 한 번 돌면 `logs/pipeline.log` 에 "전체 N개 / 신규 M개" 가 찍힌다.
   - 첫 녹음이 처리되면 `OUTPUT_DIR` 에 노트가 생성된다.

## 트러블슈팅
- **"plaud CLI 없음"**: `npm install -g @plaud-ai/cli` 후 `plaud login`.
- **"녹음 목록 비어있음/조회 실패"**: 토큰 만료 → `plaud login` 재실행.
- **"모델 없음"**: `install.sh` 의 모델 다운로드가 끝났는지 확인(`models/*.bin`).
- **노트는 안 생기고 전사만**: `claude` 미설치/미로그인 → 정상 폴백. 요약 원하면 Claude Code 설치.
- **중복 처리**: 여러 맥에서 동시에 켜둔 경우 → 한 대만 두고 나머지는 `bash uninstall.sh`.
- **주기 pull 안 됨**: 맥이 잠들면 안 됨(시스템 설정에서 잠자기 방지).

## 제거
```bash
bash uninstall.sh   # launchd 잡 내림 + plist 삭제 (볼트 노트는 보존)
```

자세한 배경·아키텍처·FAQ 는 `README.md` 참조.
