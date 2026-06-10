# plaud-obsidian-pipeline

> PLAUD 녹음을 **구독 없이(기기값만)** 빼와, **로컬 Whisper** 로 전사하고 LLM 으로 요약해
> **Obsidian 노트**로 자동 생성하는 macOS 파이프라인.

PLAUD 과금은 **전사(STT)** 에만 붙고, **클라우드 저장·원본 오디오 다운로드는 무료**입니다.
공식 CLI(`plaud audio <id>`)로 원본 MP3 를 빼와 전사를 **로컬 Whisper** 로 돌리면, 전사 쿼터를
쓰지 않고 음성메모 → 노트 자동화를 **월 0원**으로 만들 수 있습니다.

> ⚠️ 본 프로젝트는 PLAUD **공식 CLI**(`@plaud-ai/cli`)만 사용합니다. 비공식 역공학 API 는 쓰지 않습니다.
> 과금/약관 정책은 PLAUD 측 변경에 따라 달라질 수 있으니 본인 계정 기준으로 확인하세요.

---

## 동작 방식

```
PLAUD 녹음 →(BT)→ PLAUD 클라우드(무료 저장)
 │
 │  [launchd 타이머 · 기본 15분]  scripts/plaud_pull.py
 │    plaud files → 신규 id dedup → plaud audio <id> → curl → INBOX_DIR 로 원자적 이동
 ▼
 INBOX_DIR (옵시디언 볼트 안)
 │
 │  [launchd WatchPaths]  scripts/process_inbox.py
 │    ffmpeg(16k wav) → whisper-cli(전사) → claude -p(요약) | 전사-only 폴백
 ▼
 OUTPUT_DIR/{제목}_{YYMMDD}.md     (+ 원본 오디오는 ARCHIVE_DIR 로 이동)
```

- **트리거 2종**: 타이머(pull) + 폴더감시(처리). 별도 데몬 없이 macOS `launchd` 만 사용.
- **전사 100% 로컬**: whisper.cpp + `ggml-large-v3-turbo`. 인터넷·과금 0.
- **요약은 얇은 단계**: `claude -p`(헤드리스). 없거나 실패하면 전사 원문만 저장하는 폴백.

---

## 요구사항

- **macOS** (launchd 의존 — 이 파이프라인은 맥에서만 실행됩니다)
- [Homebrew](https://brew.sh)
- Node.js (`brew install node`) — PLAUD 공식 CLI 설치용
- PLAUD 계정 + 녹음기
- (선택) [Claude Code](https://claude.com/claude-code) — 요약 단계용. 없으면 전사만 저장.

---

## 설치

```bash
git clone https://github.com/<your-account>/plaud-obsidian-pipeline.git
cd plaud-obsidian-pipeline
bash install.sh
```

`install.sh` 가 하는 일:
1. brew 의존성(`whisper-cpp`, `ffmpeg`) + `@plaud-ai/cli` 설치
2. `config.env` 가 없으면 **대화형**으로 볼트 경로/출력 폴더/언어를 물어 생성
3. whisper 모델(~1.5GB) 다운로드
4. launchd plist 2개 생성 (이 레포 위치 기준)

> 스크립트는 **clone 한 이 레포 폴더에서 그대로 실행**됩니다(복사하지 않음).
> 레포를 다른 곳으로 옮기면 `bash install.sh` 를 다시 실행하세요.

### 설치 후 직접 할 단계

```bash
# (필수) PLAUD 로그인 — 브라우저 OAuth, 토큰은 ~/.plaud 에 저장(레포 밖)
plaud login

# (선택) 요약을 쓰려면 Claude Code 설치 후 로그인. 없으면 전사 원문만 저장됨.

# launchd 잡 로드
launchctl load -w ~/Library/LaunchAgents/com.plaud-obsidian.process.plist
launchctl load -w ~/Library/LaunchAgents/com.plaud-obsidian.pull.plist
```

검증:
```bash
launchctl list | grep plaud-obsidian
tail -f logs/pipeline.log
```

---

## 설정 (`config.env`)

`config.env.example` 를 참고하세요. install.sh 가 자동 생성하며, 언제든 직접 편집 가능합니다.

| 키 | 기본값 | 설명 |
|---|---|---|
| `VAULT_PATH` | (필수) | 옵시디언 볼트 루트 경로 |
| `INBOX_DIR` | `$VAULT_PATH/_inbox` | 오디오 착지 폴더(launchd 감시) |
| `OUTPUT_DIR` | `$VAULT_PATH/Voice Memos` | 생성 노트 폴더 |
| `ARCHIVE_DIR` | `$HOME/Obsidian/_audio-archive` | 처리 후 원본 오디오 보관 |
| `WHISPER_LANG` | `ko` | 전사 언어 (en/ja 등) |
| `WHISPER_MODEL` | `ggml-large-v3-turbo.bin` | whisper 모델 파일명 |
| `PULL_INTERVAL` | `900` | pull 주기(초) |
| `SUMMARY_PROMPT_FILE` | (내장 프롬프트) | 요약 프롬프트 커스텀 파일 경로 |

값은 `~`, `$HOME`, `$VAULT_PATH` 를 쓸 수 있습니다.
설정이 잘 해석되는지 확인: `python3 scripts/_config.py`.

---

## 모바일(아이폰/안드로이드)에서 보기

이 파이프라인은 **깨어 있는 맥 한 대**에서 돌아갑니다. 폰에서는 실행되지 않습니다(뷰어).
노트는 볼트 폴더(`OUTPUT_DIR`)에 쌓이고, 모바일 옵시디언에는 **평소 쓰는 볼트 동기화**로 자동 반영됩니다.

- **권장**: [Obsidian Sync](https://obsidian.md/sync)
- **대안**: iCloud Drive, Syncthing 등 (이 파이프라인은 동기화 방식과 무관)
- 동기화는 **하나로만** — 여러 동기화를 겹치면 충돌(split-brain)이 납니다.

> 맥이 잠들면 주기 pull 이 멈춥니다. 항상 켜두는 맥(예: 데스크톱)에서 운영하고 잠자기를 끄세요.

---

## 동작 점검 / 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| `plaud CLI 없음` | `npm install -g @plaud-ai/cli` → `plaud login` |
| `녹음 목록 비어있음/조회 실패` | 토큰 만료 → `plaud login` 재실행 |
| `모델 없음` | `install.sh` 의 다운로드가 끝났는지(`models/*.bin`) 확인 |
| 노트 없이 전사만 저장됨 | `claude` 미설치/미로그인 → 정상 폴백. 요약 원하면 Claude Code 설치 |
| 같은 녹음이 중복 처리 | 여러 맥에서 동시에 켜둠 → 한 대만 두고 나머지 `bash uninstall.sh` |
| 주기 pull 안 됨 | 맥이 잠듦 → 시스템 설정에서 잠자기 방지 |

로그: `logs/pipeline.log`, `logs/launchd.err.log`, `logs/plaudpull.err.log`.

---

## 제거

```bash
bash uninstall.sh   # launchd 잡 내림 + plist 삭제 (볼트 노트는 보존)
```

모델/로그/상태파일까지 지우려면 레포 폴더를 통째로 삭제하세요.
PLAUD 토큰 삭제: `rm -rf ~/.plaud`.

---

## 프라이버시 / 보안

- **녹음·전사·노트는 전부 본인 맥/볼트에 머뭅니다.** 전사는 로컬 Whisper, 요약만 Claude(선택) 사용.
- PLAUD OAuth 토큰은 `~/.plaud/tokens.json` 에 저장되며 이 레포에 **포함되지 않습니다**.
- `config.env`, 로그, 모델, 오디오, 상태파일은 모두 `.gitignore` 처리되어 커밋되지 않습니다.

## 라이선스

MIT — `LICENSE` 참조.
