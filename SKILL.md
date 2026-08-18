---
name: plaud-obsidian-pipeline
description: Use when the user wants to set up, install, configure, or troubleshoot the PLAUD → Obsidian voice-memo automation on macOS — pulling PLAUD recordings without a subscription, transcribing (local Whisper by default, optional speaker diarization via AssemblyAI or WhisperX), and auto-creating six-section meeting notes in Obsidian. Triggers include "PLAUD 음성메모 자동화 설치", "플라우드 옵시디언 파이프라인 설정", "화자분리 설정", "set up plaud pipeline", "install plaud-obsidian".
---

# plaud-obsidian-pipeline

PLAUD 녹음을 **구독 없이(기기값만)** 빼와 전사(기본 로컬 whisper.cpp, 옵션 화자분리)·6섹션 회의록 요약해 Obsidian 노트로 자동화하는 macOS 파이프라인을 설치·설정·점검한다.

## 동작 개요
- launchd 3잡: `plaud_pull.py`(타이머, PLAUD 클라우드 pull) + `process_inbox.py`(폴더감시, 전사·요약) + `prune_audio.py`(매일 03:00 아카이브 정리, `AUDIO_RETENTION_DAYS>0` 일 때만 동작).
- 전사 3단 체인: AssemblyAI(화자분리, `ASSEMBLYAI_API_KEY` 있을 때만) → WhisperX(로컬 화자분리, `.venv-whisperx` 있을 때만) → whisper.cpp(항상 가능). 아무 설정 없으면 100% 로컬.
- 요약: Claude API(`ANTHROPIC_API_KEY` 있으면) 6섹션 회의록 + 화자 이름 추론 / 없으면 전사 원문만 저장.
  `OPENAI_API_KEY` 까지 있으면 GPT 가 전사 대비 요약을 교차검증(사실오류·누락 교정, frontmatter `verified: true`).
  `verified: true` 는 교차검증 처리 완료 표시일 뿐 사실성 보증이 아님 — 중요 내용은 전문 대조 안내.
- 노트 파일명 `{YYMMDD}_{제목}.md` (YYMMDD = 녹음일 → 시간순 정렬).
- 설정: 레포 루트 `config.env` (`scripts/_config.py` 가 해석. 덤프 시 API 키는 `***` 마스킹,
  비밀 키는 `--get` 으로도 원문을 내주지 않음). **퍼미션 600 유지** — install.sh 가 생성·재실행 시
  조이고, 644 로 풀리면 스크립트가 stderr 로 경고한다.
- `INBOX_DIR` 이 볼트 안(기본값)이면 처리 전 오디오가 볼트 동기화로 클라우드에 올라간다.
  원치 않으면 볼트 밖(예: `~/Obsidian/_inbox`)으로 설정 + `install.sh` 재실행(WatchPaths 재생성).
- macOS 전용. 모바일은 볼트 동기화(Obsidian Sync 등)로 노트만 따라오는 뷰어.
- 관리 대시보드(선택): `python3 dashboard/serve.py` → `http://127.0.0.1:8791`. 읽기 전용
  (state/·logs/·config 실시간 조회, 시크릿은 설정됨/미설정만 표시). 조치 버튼은 UI 프로토타입 —
  실제 상태 파일은 바꾸지 않는다. 원격 접속은 `tailscale serve --bg --https=8443 http://127.0.0.1:8791`
  (tailnet 전용 — Funnel 금지), 상시 실행은 `dashboard/com.plaud-obsidian.dash.plist` 를
  `~/Library/LaunchAgents/` 에 복사 후 `launchctl load -w` (README '관리 대시보드' 참고 — 사용자가 직접 실행).

## 설치 절차 (이 순서대로 진행)

1. **사전 확인 — 사용자에게 묻기**
   - PLAUD 계정이 있는지, 옵시디언 볼트 경로가 무엇인지.
   - Homebrew/node 설치 여부(없으면 안내). macOS 인지 확인(아니면 중단).

2. **설치 스크립트 실행**
   ```bash
   bash install.sh
   ```
   - `config.env` 가 없으면 스크립트가 대화형으로 볼트 경로/출력 폴더/언어/API 키 3종(선택)을 물어 생성한다.
     비대화형 환경이면 먼저 `cp config.env.example config.env` 후 사용자가 값을 채우게 하라.
   - whisper 모델(~1.5GB) 다운로드가 포함되어 시간이 걸린다 → `run_in_background` 권장.
   - API 키를 물을 때는 반드시 프라이버시 트레이드오프를 함께 안내하라
     (AssemblyAI 키 → 오디오 전송, Anthropic 키 → 전사 텍스트 전송, OpenAI 키 → 전사+요약 전송.
     전부 비우면 100% 로컬 전사, 전사 원문만 저장).

3. **사용자가 직접 해야 하는 단계 (Claude 가 대신 못 함 — 반드시 사용자에게 위임)**
   - `plaud login` — 브라우저 OAuth. 토큰은 `~/.plaud/tokens.json` 에 저장(레포 밖, 커밋 금지).
   - (선택) API 키 발급 — 요약(`ANTHROPIC_API_KEY`)·교차검증(`OPENAI_API_KEY`)을 쓰려면 각 콘솔에서
     사용자가 직접 발급해 `config.env` 에 넣어야 한다(Claude 가 대신 발급 못 함). 없으면 전사-only 폴백.
   - (선택) 로컬 화자분리(WhisperX): HuggingFace 토큰 발급 + pyannote 게이트 모델 라이선스 동의는
     사용자가 브라우저에서 직접 해야 한다. venv 생성(`python3.11 -m venv .venv-whisperx` +
     `pip install whisperx`)은 Claude 가 대신 실행 가능 (README 'WhisperX 셋업' 절).
   - 모바일에서 보려면 볼트를 평소 방식(Obsidian Sync 등)으로 폰과 동기화.

4. **launchd 잡 로드**
   ```bash
   launchctl load -w ~/Library/LaunchAgents/com.plaud-obsidian.process.plist
   launchctl load -w ~/Library/LaunchAgents/com.plaud-obsidian.pull.plist
   launchctl load -w ~/Library/LaunchAgents/com.plaud-obsidian.prune.plist
   ```

5. **검증**
   ```bash
   launchctl list | grep plaud-obsidian
   tail -n 40 logs/pipeline.log
   ```
   - pull 이 한 번 돌면 `logs/pipeline.log` 에 "전체 N개 / 신규 M개" 가 찍힌다.
   - 첫 녹음이 처리되면 `OUTPUT_DIR` 에 노트가 생성된다.
   - **스모크 테스트**: 아무 오디오 파일을 `INBOX_DIR` 에 복사하면 PLAUD 녹음 없이도 전사→노트
     생성을 즉시 확인할 수 있다. 사용자에게 짧은 테스트 오디오를 넣어보게 하라.

## 트러블슈팅
- **"plaud CLI 없음"**: `npm install -g @plaud-ai/cli` 후 `plaud login`.
- **"녹음 목록 비어있음/조회 실패"**: 토큰 만료 → `plaud login` 재실행.
- **"모델 없음"**: `install.sh` 의 모델 다운로드가 끝났는지 확인(`models/*.bin`).
- **노트는 안 생기고 전사만** (`status: summary_pending`): `ANTHROPIC_API_KEY` 미설정 → 정상 폴백. 요약 원하면 config.env 에 키 설정. 키가 있는데도 폴백되면 `logs/pipeline.log` 의 "claude: HTTP ..." 로그로 진단 — 401 은 키 오타, 429/529 는 일시 과부하(자동 재시도).
- **frontmatter `verified: false`**: `OPENAI_API_KEY` 미설정 또는 GPT 호출 실패 — Claude 요약이 그대로 저장된 정상 동작. 로그의 "gpt: ..." 라인으로 진단.
- **중복 처리**: 여러 맥에서 동시에 켜둔 경우 → 한 대만 두고 나머지는 `bash uninstall.sh`.
- **주기 pull 안 됨**: 맥이 잠들면 안 됨(시스템 설정에서 잠자기 방지).
- **오디오가 `_inbox/_failed/` 에 있음**: 전사 3회 연속 실패로 자동 격리된 것. 파일을 확인하고 다시 `_inbox` 로 옮기면 재시도된다.
- **"audio 미준비 — 재시도 예정" 반복**: 긴 녹음의 서버 처리 대기 — 정상. 약 24시간(96회) 후에도 안 되면 영구 스킵된다(`state/pending_ids.txt`).
- **화자분리가 안 됨**: AssemblyAI 키·WhisperX venv 둘 다 없으면 whisper.cpp 폴백(화자분리 없음)이 정상 동작. 로그의 "전사 엔진:" 라인으로 어떤 티어가 쓰였는지 확인.
- 런타임 상태(받은 id·실패 카운트·pending 재시도·락)는 레포 `state/` 폴더. v1 루트 상태파일은 스크립트가 자동 마이그레이션.

## 제거
```bash
bash uninstall.sh   # launchd 잡 내림 + plist 삭제 (볼트 노트는 보존)
```

자세한 배경·아키텍처·FAQ 는 `README.md` 참조.
