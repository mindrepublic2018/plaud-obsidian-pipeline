# plaud-obsidian-pipeline

[English](README.en.md) | **한국어**

> PLAUD 녹음을 **구독 없이(기기값만)** 빼와, 전사(기본 **로컬 Whisper**, 옵션 **화자분리**)하고
> LLM 으로 **6섹션 회의록** 요약해 **Obsidian 노트**로 자동 생성하는 macOS 파이프라인.

PLAUD 과금은 **전사(STT)** 에만 붙고, **클라우드 저장·원본 오디오 다운로드는 무료**입니다.
공식 CLI(`plaud audio <id>`)로 원본 MP3 를 빼와 전사를 **로컬 Whisper** 로 돌리면, 전사 쿼터를
쓰지 않고 음성메모 → 노트 자동화를 **월 0원**으로 만들 수 있습니다.
화자분리(누가 말했는지)가 필요하면 AssemblyAI 키(클라우드) 또는 WhisperX(로컬)를 옵트인으로 켤 수 있습니다.

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
 │    전사 3단 체인: AssemblyAI(화자분리, 키 있을 때만) → WhisperX(로컬 화자분리, venv 있을 때만)
 │                  → whisper.cpp(항상 가능)
 │    → claude -p(6섹션 회의록 요약 + 화자 이름 추론) | 전사-only 폴백
 ▼
 OUTPUT_DIR/{YYMMDD}_{제목}.md     (+ 원본 오디오는 ARCHIVE_DIR 로 이동)
```

- **트리거 3종**: 타이머(pull) + 폴더감시(처리) + 일일 03:00(아카이브 정리, 옵트인). 별도 데몬 없이 macOS `launchd` 만 사용.
- **전사는 기본 100% 로컬**: whisper.cpp + `ggml-large-v3-turbo`. 인터넷·과금 0. 화자분리는 옵트인(아래 '전사 엔진 체인').
- **요약은 얇은 단계**: `claude -p`(헤드리스). 없거나 실패하면 전사 원문만 저장하는 폴백.
- **녹음일 기반 노트**: 파일명이 `{YYMMDD}_{제목}.md`(녹음일 기준) 라 파일 목록이 시간순으로 정렬되고,
  frontmatter `created` 도 녹음일로 찍힙니다.

---

## 전사 엔진 체인

`process_inbox.py` 는 세 엔진을 순서대로 시도하고, 실패하면 다음 티어로 폴백합니다.
**아무 설정도 안 하면 whisper.cpp 만 사용** — 기존과 동일한 100% 로컬 동작입니다.

| 순서 | 엔진 | 화자분리 | 켜는 법 | 비고 |
|---|---|---|---|---|
| 1 | [AssemblyAI](https://www.assemblyai.com) (클라우드, `universal-2`) | ✅ | `config.env` 에 `ASSEMBLYAI_API_KEY` 설정 | 유료 API. **오디오가 AssemblyAI 서버로 전송됨** |
| 2 | WhisperX + pyannote (로컬) | ✅ | 아래 WhisperX 셋업 + `HF_TOKEN` | 무료·로컬이지만 느림 (CPU 전사 + diarization) |
| 3 | whisper.cpp (로컬) | ❌ | 기본 — install.sh 가 설치 | 항상 가능한 최종 폴백 |

화자분리가 되면 노트에 `**[화자 A(김대표)]** ...` 형식의 **화자별 전문**이 붙고, claude 요약이
호칭·자기소개 같은 명확한 근거가 있을 때만 화자 이름을 추론해 라벨에 채웁니다.

### WhisperX 셋업 (선택 — 로컬 화자분리)

무겁습니다(torch 포함 수 GB). 클라우드 전송이 싫은데 화자분리는 필요할 때만 쓰세요.

```bash
# Python 3.11 설치 (권장 버전 — pyannote/torch 호환. 시스템 python3 와 별개로 설치됨)
brew install python@3.11

# 레포 루트에서 venv 생성 + whisperx 설치
$(brew --prefix python@3.11)/bin/python3.11 -m venv .venv-whisperx
.venv-whisperx/bin/pip install whisperx
```

1. [HuggingFace 토큰](https://huggingface.co/settings/tokens) 발급 후 `config.env` 에 `HF_TOKEN=hf_...` 설정
2. [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) 모델 페이지에서 라이선스 동의 (게이트 모델)
3. venv 가 감지되면 자동으로 2순위 티어로 사용됩니다. 테스트: `.venv-whisperx/bin/python scripts/whisperx_transcribe.py <오디오파일>`

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
git clone https://github.com/mindrepublic2018/plaud-obsidian-pipeline.git
cd plaud-obsidian-pipeline
bash install.sh
```

`install.sh` 가 하는 일:
1. brew 의존성(`whisper-cpp`, `ffmpeg`) + `@plaud-ai/cli` 설치
2. `config.env` 가 없으면 **대화형**으로 볼트 경로/출력 폴더/언어/AssemblyAI 키(선택)를 물어 생성
3. whisper 모델(~1.5GB) 다운로드
4. launchd plist 3개 생성 (pull/process/prune — 이 레포 위치 기준)

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
launchctl load -w ~/Library/LaunchAgents/com.plaud-obsidian.prune.plist   # 아카이브 정리(옵트인)
```

검증:
```bash
launchctl list | grep plaud-obsidian
tail -f logs/pipeline.log
```

**빠른 스모크 테스트**: 아무 오디오 파일(m4a/mp3 등)을 `INBOX_DIR`(기본 `$VAULT_PATH/_inbox`)에
복사해 보세요. 1~2분 내 전사가 시작되고(`logs/pipeline.log` 에 "처리 시작" 로그), 끝나면
`OUTPUT_DIR` 에 노트가 생깁니다 — PLAUD 녹음기 없이도 파이프라인 동작을 바로 확인할 수 있습니다.

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
| `CLAUDE_MODEL` | `sonnet` | `claude -p` 요약 모델 |
| `ASSEMBLYAI_API_KEY` | (없음) | 설정 시 클라우드 전사+화자분리를 1순위 사용 ⚠️오디오 외부 전송 |
| `HF_TOKEN` | (없음) | WhisperX 로컬 화자분리용 HuggingFace 토큰 |
| `AUDIO_RETENTION_DAYS` | `0` | 아카이브 오디오 보관일. 0 = 자동삭제 안 함 |

값은 `~`, `$HOME`, `$VAULT_PATH` 를 쓸 수 있습니다.
설정이 잘 해석되는지 확인: `python3 scripts/_config.py`.

> 내장 요약 프롬프트는 6섹션 회의록(안건/주요 논의/결정사항/액션 아이템/다음 단계/전반 톤 메모)을
> 생성합니다. 커스텀 프롬프트(`SUMMARY_PROMPT_FILE`)는 `TITLE: ... ---SPEAKERS--- ... ---BODY---`
> 출력 계약을 지켜야 합니다 (SPEAKERS 블록은 생략 가능).

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
| 노트 없이 전사만 저장됨 | `claude` 미설치/미로그인 → 정상 폴백. 요약 원하면 Claude Code 설치. **구버전 CLI 도 원인** — 요약 호출이 `--tools`/`--no-session-persistence` 플래그를 쓰므로 오래된 버전이면 조용히 폴백됨 → `claude update` 후 재시도 (`logs/pipeline.log` 의 "claude 실패" 로그로 확인) |
| 같은 녹음이 중복 처리 | 여러 맥에서 동시에 켜둠 → 한 대만 두고 나머지 `bash uninstall.sh` |
| 주기 pull 안 됨 | 맥이 잠듦 → 시스템 설정에서 잠자기 방지 |
| 오디오가 `_inbox/_failed/` 에 있음 | 전사 3회 연속 실패 시 자동 격리(무한 재시도 방지). 파일 확인 후 다시 `_inbox` 로 옮기면 재시도 |
| `audio 미준비 — 재시도 예정` 로그 반복 | 긴 녹음은 PLAUD 서버 처리에 시간이 걸림 → 정상. 약 24시간(96회) 재시도 후에도 안 되면 영구 스킵 |
| 화자분리가 안 됨 | AssemblyAI 키 또는 WhisperX venv 미설정 → whisper.cpp 폴백(화자분리 없음)이 정상. '전사 엔진 체인' 참고 |
| 아카이브 오디오가 사라짐 | `AUDIO_RETENTION_DAYS` > 0 설정 시 보관기한 초과분을 매일 03:00 자동삭제(옵트인). 원본은 PLAUD 클라우드에 남음 |

로그: `logs/pipeline.log`, `logs/launchd.err.log`, `logs/plaudpull.err.log`, `logs/prune.out.log`.
런타임 상태(받은 녹음 id, 실패 카운트, 락)는 레포의 `state/` 폴더에 저장됩니다(커밋 안 됨).

---

## 제거

```bash
bash uninstall.sh   # launchd 잡 내림 + plist 삭제 (볼트 노트는 보존)
```

모델/로그/상태파일까지 지우려면 레포 폴더를 통째로 삭제하세요.
PLAUD 토큰 삭제: `rm -rf ~/.plaud`.

---

## 프라이버시 / 보안

- **기본 설정에서 녹음·전사·노트는 전부 본인 맥/볼트에 머뭅니다.** 전사는 로컬 Whisper, 요약만 Claude(선택) 사용.
- **`ASSEMBLYAI_API_KEY` 를 설정한 경우에만** 오디오가 전사를 위해 AssemblyAI 서버로 전송됩니다.
  키를 비워두면(기본) 오디오는 외부로 나가지 않습니다. AssemblyAI 의 데이터 보존 정책은 본인 계정
  설정으로 확인하세요. WhisperX 티어는 화자분리도 100% 로컬입니다.
- PLAUD OAuth 토큰은 `~/.plaud/tokens.json` 에 저장되며 이 레포에 **포함되지 않습니다**.
- API 키(`config.env`, `.assemblyai_key`, `.hf_token`), 로그, 모델, 오디오, 상태파일은 모두
  `.gitignore` 처리되어 커밋되지 않습니다.

## 개발 / 테스트

```bash
python3 -m unittest discover -s tests   # 의존성 없이 stdlib 만으로 실행
```

## 라이선스

MIT — `LICENSE` 참조.
