# plaud-obsidian-pipeline — 설계 스펙

- 날짜: 2026-06-10
- 상태: 승인됨 (구현 대기)
- 목표: 개인용 PLAUD→Obsidian 음성메모 자동화를 **공개 GitHub 레포 + Claude Code 스킬**로 일반화 배포

## 1. 목적과 범위

PLAUD 녹음기를 **구독 없이(기기값만)** 사용해, 원본 오디오를 PLAUD 클라우드에서 당겨와
로컬 Whisper로 전사하고 LLM으로 요약해 Obsidian 노트로 자동 생성하는 파이프라인을,
**누구나 자기 맥 + 자기 옵시디언 볼트에 설치**할 수 있도록 패키징한다.

핵심 통찰(원본 위키에서): PLAUD 과금은 **전사(STT)**에만 붙고 **클라우드 저장·원본 다운로드는 무료**.
공식 CLI(`plaud audio <id>`)로 원본 MP3를 빼와 로컬 Whisper로 전사하면 구독 0원.

### 범위에 포함
- macOS launchd 기반 2단계 자동화(타이머 pull + 폴더감시 처리)
- 대화형 설치 스크립트 + config 파일 기반 일반화
- Claude Code 스킬(SKILL.md)로 설치 오케스트레이션
- 사람용 README 온보딩(모바일 동기화 설명 포함)
- 개인정보 완전 제거

### 범위에서 제외 (YAGNI)
- 요약 엔진 멀티 백엔드(OpenAI/Ollama 선택) — `claude -p` + 전사 폴백만
- Linux/Windows 지원 — macOS 전용(launchd 의존)
- iOS 단독 실행 — 불가(뷰어 역할만)

## 2. 결정 사항 (확정)

| 항목 | 결정 |
|---|---|
| 배포 형태 | 공개 GitHub 레포 + `SKILL.md` (코드+온보딩+스킬 한 레포) |
| 요약 엔진 | `claude -p` 기본 + Claude Code 없으면 전사-only 폴백(자동 감지) |
| 설정 방식 | `config.env` 파일 + 대화형 `install.sh`(없으면 질문해서 생성) |
| 레포 이름 | `plaud-obsidian-pipeline` |
| 출력 폴더 기본값 | `Voice Memos` (config로 변경 가능) |
| 전사 언어 기본값 | `ko` (config로 변경 가능) |
| 라이선스 | MIT |

## 3. 레포 구조

```
plaud-obsidian-pipeline/
├── SKILL.md              # Claude Code 스킬 (frontmatter + 온보딩 가이드)
├── README.md             # 사람용 온보딩 (아키텍처/요구사항/설치/트러블슈팅/모바일)
├── LICENSE               # MIT
├── install.sh            # 대화형 설치 (의존성→config→모델→launchd→load)
├── uninstall.sh          # launchd 잡 unload/제거 (볼트 노트는 보존)
├── config.env.example    # 모든 설정값 + 주석
├── .gitignore            # config.env, logs/, models/, *.mp3, *_ids.txt, .lock
└── scripts/
    ├── _config.py        # config.env 공통 로더 (KEY=VALUE 파싱, ~ 확장)
    ├── plaud_pull.py     # 일반화 (config 읽음)
    └── process_inbox.py  # 일반화 (config 읽음)
```

## 4. 설정 (`config.env`)

`config.env.example`를 복사해 `config.env` 생성(install.sh가 대화형으로 자동 생성).
`config.env`는 `.gitignore` 처리.

| 키 | 기본값 | 설명 |
|---|---|---|
| `VAULT_PATH` | (필수, 설치 시 질문) | 옵시디언 볼트 루트 경로 |
| `INBOX_DIR` | `$VAULT_PATH/_inbox` | 오디오 착지 폴더(폴더감시 대상) |
| `OUTPUT_DIR` | `$VAULT_PATH/Voice Memos` | 생성 노트 출력 폴더 |
| `ARCHIVE_DIR` | `$HOME/Obsidian/_audio-archive` | 처리 후 오디오 보관 |
| `WHISPER_MODEL` | `ggml-large-v3-turbo.bin` | whisper.cpp 모델 파일명 |
| `WHISPER_LANG` | `ko` | 전사 언어 |
| `PULL_INTERVAL` | `900` | pull 주기(초) |
| `SUMMARY_PROMPT_FILE` | (비움→내장 프롬프트) | 요약 프롬프트 커스텀 경로 |

실행 위치(모호성 제거):
- 스크립트는 **clone한 레포 디렉터리에서 in-place 실행**한다(복사 안 함). launchd plist의 `ProgramArguments`는
  그 레포 내 스크립트 절대경로를 가리킨다. `config.env`는 레포 루트(스크립트 옆)에 위치.
- 따라서 사용자는 레포를 영구적인 위치(예: `~/plaud-obsidian-pipeline`)에 두고, 그 경로를 옮기면 재설치 필요.
  install.sh는 자신의 위치를 기준으로 plist를 생성한다.

런타임 동작:
- `_config.py`가 레포 루트의 `config.env`를 읽어 dict로 제공, 미지정 키는 기본값 적용, `~`/`$HOME` 확장.
- `process_inbox.py`는 `claude` CLI를 자동 감지 — 있으면 요약, 없거나 실패하면 전사 원문만 노트로 저장(기존 폴백 유지).

## 5. 아키텍처 (기존 동작 유지)

```
PLAUD 녹음 →(BT)→ PLAUD 클라우드(무료)
 → [launchd StartInterval] plaud_pull.py
     plaud files → pulled_ids로 dedup → plaud audio <id> → curl → INBOX 원자적 이동
 → [launchd WatchPaths(INBOX)] process_inbox.py
     ffmpeg(16k wav) → whisper-cli(WHISPER_LANG) → (claude -p 요약 | 전사 폴백)
     → OUTPUT_DIR/{제목}_{YYMMDD}.md → 오디오 ARCHIVE_DIR 이동
```

- launchd 라벨(중립): `com.plaud-obsidian.pull`, `com.plaud-obsidian.process`
- plist는 `install.sh`가 `$HOME` + config 기준으로 생성
- 동시실행 방지 락(`.lock`), state파일 dedup(`pulled_ids.txt`/`skipped_ids.txt`), 원자적 이동 유지

## 6. `install.sh` 흐름

1. macOS 확인(아니면 경고·중단), Homebrew 확인
2. brew 의존성: `whisper-cpp`, `ffmpeg`
3. node 확인 + `npm install -g @plaud-ai/cli`
4. `config.env` 없으면 **대화형 질문**: 볼트 경로 / 출력 폴더명 / 전사 언어 → `config.env` 작성
5. 디렉터리 생성(INBOX, OUTPUT_DIR, ARCHIVE_DIR, models, logs)
6. whisper 모델(~1.5GB) 없으면 HuggingFace에서 다운로드
7. launchd plist 2개 생성($HOME+config 기준, 중립 라벨)
8. **사용자 직접 단계 안내**: `plaud login`(브라우저 OAuth), `claude` 로그인(요약용, 선택)
9. `launchctl load -w` 양쪽
10. 검증 출력: `launchctl list | grep plaud-obsidian`, 로그 tail 안내

## 7. SKILL.md

- frontmatter: `name: plaud-obsidian-pipeline`, `description`에 트리거("PLAUD 음성메모 자동화 설치", "플라우드 옵시디언 파이프라인 설정" 등)
- 본문: Claude가 `install.sh`를 실행하고, **자기가 못 하는 대화형 단계(브라우저 OAuth)는 사용자에게 위임**, 설치 후 검증·트러블슈팅을 안내. 깊은 내용은 README 참조.

## 8. 모바일 (sync-agnostic)

- 처리는 **깨어있는 맥**에서만 발생. iOS는 launchd/폴더감시가 없어 실행 불가 = **뷰어**.
- 노트는 볼트 폴더(`OUTPUT_DIR`)에 쌓이고, 모바일 옵시디언은 **사용자가 이미 쓰는 볼트 동기화**로 자동 반영.
  - 권장: Obsidian Sync. 대안: iCloud Drive, Syncthing 등. (파이프라인은 sync 방식과 무관)
- README에 "한 대에서만 실행(여러 맥이면 중복 방지로 한쪽 launchd 끔)" 명시.

## 9. 개인정보 스크럽 체크리스트 (구현·검증)

- [ ] 기존 개인 볼트명 → `VAULT_PATH`/config로 치환
- [ ] 기존 개인 출력 폴더명 → `OUTPUT_DIR`로 치환
- [ ] 기존 개인 launchd 라벨 → `com.plaud-obsidian.*`
- [ ] `pulled_ids.txt`/`skipped_ids.txt` 레포 미포함(설치 시 빈 파일 생성, gitignore)
- [ ] `~/.plaud/tokens.json`(OAuth 시크릿) 레포 미포함 — `plaud login`으로 각자 생성
- [ ] logs/, models/(*.bin), *.mp3 레포 미포함(gitignore)
- [ ] 기존 머신 이전(migration) 서사 → 일반 설치 가이드로 재작성
- [ ] 최종 검증: 레포 루트에서 개인 식별 문자열(이전 볼트명·계정명·머신명) grep → 0건

## 10. 테스트/검증

- `shellcheck install.sh uninstall.sh`
- `python3 -m py_compile scripts/*.py`
- `_config.py` 단위 테스트: 기본값/오버라이드/`~` 확장 파싱
- 드라이런: 임시 볼트 디렉터리로 config 생성 → plist 생성 로직 검증(실제 launchctl load 없이)
- 개인정보 grep 검증(9번 마지막 항목) CI 또는 수동
- 수동 E2E: 실제 PLAUD 계정으로 1건 pull→전사→노트 생성 확인(배포 전 1회)
