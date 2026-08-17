# 보안 / 파일 구성 코드리뷰

- 날짜: 2026-08-17
- 리뷰어: Grok (이 세션)
- 대상: `plaud-obsidian-pipeline` 저장소 전체 (`main` = `origin/main`, 작업 트리 깨끗했던 시점 기준)
- 범위: 보안 + 디렉터리/git 추적 경계. 기능 버그·요약 품질은 제외.
- 코드 변경: 없음. 이 문서만 추가.

관련 문서: `docs/CODE_REVIEW_HANDOFF.md` (같은 날 다른 패스의 인수인계). 이 파일이 본 세션의 정본이다.

## 전제

공개 GitHub 레포(`mindrepublic2018/plaud-obsidian-pipeline`, MIT) + 개인 맥 launchd.
원격 공격면은 작고, **로컬 비밀·녹음·볼트 동기화**가 실제 위험이다.

한 줄 평가: 비밀 분리·gitignore·원자적 핸드오프·클라우드 옵트인 고지는 잘 되어 있다. 다만 **이 머신에서 살아 있는 API 키 3개가 `config.env` 모드 `0644`로 열려 있고**, 문서화된 설정 덤프가 그 키를 그대로 찍는다. 파일 구성은 “레포 = 설치본”이라 코드·비밀·1.5GB 모델·런타임 상태가 한 트리에 섞인다.

키 값은 이 문서에 넣지 않는다. 존재 여부와 권한만 기록한다.

---

## 잘 된 점

- 시크릿은 git에 없다. `config.env` / 키 파일 / `state/` / `logs/` / `models/` / 오디오가 `.gitignore`에 있고, 히스토리에도 `config.env` 커밋이 없다.
- 키를 로그에 안 남긴다. `_llm.py`가 헤더를 로그하지 않고, `pipeline.log`에서 Anthropic/OpenAI/HF 키 패턴 0건.
- 서브프로세스는 리스트 인자만. `shell=True` 없음. `plaud` / `curl` / `ffmpeg` / `whisper-cli` 모두 절대경로 후보.
- 핸드오프가 원자적이다. `/tmp` 다운로드 후 `shutil.move` → inbox. state는 `os.replace`. 락은 non-blocking `flock`.
- 실패 분류가 분명하다. pending → skip, 전사 3회 → `_failed/`. 클라우드 단계 실패해도 전사는 남긴다.
- 기본값은 로컬. 키 없으면 whisper.cpp만. README 프라이버시 절이 전송 조건을 명시한다.
- PLAUD OAuth는 레포 밖 (`~/.plaud`). launchd plist에도 키가 없다. 잡은 사용자 권한이다.
- 아카이브 기본 위치가 볼트 밖 (`~/Obsidian/_audio-archive`). 노트만 볼트에 남긴다.
- 삭제 기본 off. `AUDIO_RETENTION_DAYS=0`. `uninstall.sh`는 노트/설정을 지우지 않는다.
- 신규 `config.env`는 `chmod 600` (`install.sh:78`). 문제는 그 이후다.

---

## 보안 이슈

### 1. `config.env`가 world-readable — 실제 키 3개가 들어 있음

**Severity: bug**  
**File:** `config.env` (현재 `0644`), `install.sh:78`

이 워크스페이스의 `config.env`에 `ASSEMBLYAI_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`가 모두 설정되어 있고, 파일 모드는 `-rw-r--r--`이다. `install.sh`는 **새로 만들 때만** `chmod 600` 한다. 이미 있는 파일을 쓰거나, 예제를 복사하거나, 에디터로 저장하면 umask `022` 때문에 `0644`가 된다.

같은 맥의 다른 로컬 계정(게스트 포함)이 키를 읽을 수 있다. 레포가 공개라서, 실수로 `git add -f config.env` 하면 피해가 바로 공개 히스토리로 간다.

**지금 할 일 (코드 변경 아님):**

```bash
chmod 600 config.env
```

설치 스크립트는 기존 파일이 있어도 600을 다시 걸고, 문서에 “편집 후에도 600 유지”를 적는 편이 맞다.

### 2. `_config.py` 기본 출력이 API 키 전체 덤프

**Severity: bug**  
**File:** `scripts/_config.py:123-133`, `CLAUDE.md`의 sanity-check 커맨드

`python3 scripts/_config.py`와 `--json`은 해석된 설정 **전부**를 stdout에 찍는다. 키 이름에 `API_KEY`/`TOKEN`이 있어도 마스킹이 없다. 문서가 이 명령을 점검용으로 안내하므로, 터미널 스크롤·스크린샷·이슈 첨부·에이전트 로그로 키가 새기 쉽다. `install.sh`의 `--get` 경로는 경로만 가져와서 괜찮다.

**제안:** `*_KEY` / `*_TOKEN` / `HF_TOKEN`은 `***`로 가리고, `--get KEY`로 비밀을 꺼낼 때만 원문을 주거나 아예 막는다.

### 3. 설치 중 API 키를 화면에 그대로 입력

**Severity: suggestion**  
**File:** `install.sh:60-68`

`read -r -p`라서 키가 터미널에 보인다. `read -s`가 아니다. 어깨 너머·화면 공유·터미널 로그에 남는다.

### 4. 녹음이 `/tmp`에 `0644`로 잠시 풀린다

**Severity: suggestion**  
**File:** `scripts/plaud_pull.py:190-199`, `scripts/process_inbox.py:287-307`

- pull: `/tmp/plaud_{fid}.mp3` → inbox로 `move`
- 전사: `/tmp/voicememo_{basename}_{ts}.wav`

macOS `/tmp`는 `1777`이고, 생성 파일은 umask `022`라 `0644`다. 처리 중에 다른 로컬 사용자가 원본 녹음을 읽을 수 있다. 경로도 예측 가능하다 (`plaud_<32hex>.mp3`). `tempfile.mkstemp` + `0o600`, 또는 `state/tmp`처럼 700 디렉터리를 쓰는 편이 맞다.

### 5. 기본 inbox가 동기화되는 볼트 안

**Severity: suggestion**  
**File:** `scripts/_config.py:82-83`, `README.md:26`

기본 `INBOX_DIR=$VAULT_PATH/_inbox`. 이 머신에서는:

- inbox: `~/Obsidian/Mindrepublic/_inbox`
- 노트: `~/Obsidian/Mindrepublic/Voice Memos`
- 아카이브: `~/Obsidian/_audio-archive` (볼트 밖 — 이쪽은 맞음)

오디오가 처리되기 전까지 **볼트 동기화(Obsidian Sync 등)로 클라우드에 올라간다.** 지금은 AssemblyAI 키도 켜져 있어서, 한 파일이 (1) PLAUD 클라우드 → (2) 볼트 동기화 → (3) AssemblyAI → (4) 전사는 Anthropic/OpenAI 로 갈 수 있다. `_failed/`도 inbox 아래라 실패 녹음이 볼트에 남는다.

inbox 기본값을 볼트 밖(`~/Obsidian/_inbox`)으로 두거나, 볼트 동기화 제외에 `_inbox`를 넣는 쪽이 경계가 분명하다. **기본값 변경은 기존 사용자 경로를 깨므로, 문서 경고 + 신규 설치 기본값만 바꾸는 편이 안전하다.**

### 6. 공개 레포인데 백업 env가 ignore되지 않음

**Severity: suggestion**  
**File:** `.gitignore:1-6`

무시되는 것: `config.env`, `.assemblyai_key`, `.anthropic_key`, `.openai_key`, `.hf_token`  
안 막히는 것: `config.env.bak`, `config.env.local`, `.env`, `config.env.save`

처리 대상 오디오 확장자 중 `.aiff` `.aif` `.ogg` `.webm` `.mp4` `.m4v`도 `.gitignore`에 없다 (`docs/CODE_REVIEW_HANDOFF.md`와 동일 지적).

공개 MIT 레포에서 `cp config.env config.env.bak` 후 커밋하는 실수가 가장 흔한 유출이다.

### 7. 다운로드 URL 검증 없음 (`curl -L`)

**Severity: suggestion**  
**File:** `scripts/plaud_pull.py:150-164`

`plaud audio` stdout에서 **첫 `https://` 줄**을 그대로 받는다. 호스트 허용 목록이 없고 `-L`로 리다이렉트를 따른다. 공식 CLI를 믿는 설계라 단독일 때는 수긍이 가지만, CLI 출력 포맷이 바뀌거나 앞에 다른 https 줄이 끼면 임의 URL로 GET이 나간다. S3/CloudFront 호스트 allowlist + 리다이렉트 제한 + 최대 파일 크기가 안전하다.

### 8. 모델 다운로드에 무결성 검사가 없고, 파일명으로 경로가 열린다

**Severity: suggestion**  
**File:** `install.sh:109-113`, `scripts/_config.py:94`

`WHISPER_MODEL`을 `models/` 아래에 붙인 뒤 checksum 없이 HuggingFace에서 `curl -L -o` 한다. `../`가 들어가면 `os.path.join`이 레포 밖으로 나간다. 로컬 config라 원격 RCE는 아니지만, 설치 경로 쓰기는 닫는 편이 맞다. npm/`whisperx`도 버전 핀이 없다.

### 9. LLM이 만든 화자 이름이 YAML에 그대로 들어감

**Severity: suggestion**  
**File:** `scripts/process_inbox.py:365-368`

파일명 `slugify`는 경로 문자를 지우지만, frontmatter `speakers`는 이스케이프하지 않는다. 전사/프롬프트 인젝션으로 `]\nmalicious: ...` 같은 값이 오면 YAML이 깨지거나 필드가 추가된다. 노트 본문 조작은 이 파이프라인의 잔여 위험이기도 하다 (`parse_claude_output`은 `---BODY---` 존재만 확인).

### 10. inbox 심링크를 따라감

**Severity: nit**  
**File:** `scripts/process_inbox.py:464-471`

확장자만 보고 열고, 심링크 여부를 보지 않는다. inbox에 심링크를 두면 읽을 수 있는 아무 오디오나 전사·업로드·아카이브 대상이 된다. `os.path.islink`면 건너뛰는 가드면 충분하다.

### 11. launchd plist XML에 경로를 이스케이프 없이 삽입

**Severity: nit**  
**File:** `install.sh:122-163`

`$INBOX_DIR` / `$PY` / `$REPO`를 plist XML에 그대로 넣는다. 경로에 `</string>`이 있으면 plist가 깨지거나 키가 주입된다. 자기 머신 설정이라 심각도는 낮다.

### 12. 아카이브·로그·state도 `0755`/`0644`

**Severity: nit**  
**File:** `state/`, `logs/`, `~/Obsidian/_audio-archive`

아카이브 mp3가 `-rw-r--r--`이다. 회의 원본이다. `state/pulled_ids.txt`는 녹음 ID. 로그에는 파일명·엔진명만 있었고 키는 없었다. 디렉터리 `0700`, 파일 `0600`이 개인 녹음 파이프라인에는 맞다.

---

## 파일 구성

의도된 모델은 **클론한 레포가 곧 설치본**이다. launchd가 이 트리의 스크립트를 직접 가리킨다. 단순하지만 경계가 흐리다.

```
레포 (git)                          런타임 (gitignore, 같은 트리)
├── scripts/  tests/  install.sh    ├── config.env      ← 시크릿 (리뷰 시점 0644)
├── README.md SKILL.md CLAUDE.md    ├── state/          ← 녹음 ID, 락
├── config.env.example              ├── logs/           ← launchd + pipeline
└── docs/superpowers/specs/...      └── models/*.bin    ← 1.5GB
                                          ↑ 코드와 섞임

볼트
├── _inbox/          ← 기본 inbox (동기화됨) + _failed/
└── Voice Memos/     ← 전사 전문 포함 노트

볼트 밖
└── ~/Obsidian/_audio-archive/   ← 잘 분리됨
```

1. **코드·비밀·모델·상태가 한 폴더.** 폴더를 복사·압축·백업하면 키와 1.5GB bin과 녹음 ID가 같이 간다. 설정은 `~/Library/Application Support/plaud-obsidian/`가 일반적이지만, 지금 설계는 in-place를 고수한다. 이번 패치에서 레이아웃을 옮기지 말 것.
2. **inbox만 볼트 안, 아카이브는 밖.** 노트는 볼트에 있어야 하니 `OUTPUT_DIR`은 맞다. inbox를 볼트에 둔 건 WatchPaths + “드롭하면 처리” 때문인데, 동기화·용량·클라우드 복사 비용이 생긴다.
3. **`docs/superpowers/specs/`가 살아 있는 설계와 어긋난다.** 2026-06-10 스펙은 `claude -p`, launchd 2개, 파일명 `{제목}_{YYMMDD}.md`를 말한다. 현재는 Claude API + GPT, 잡 3개, `{YYMMDD}_{제목}.md`다. 에이전트가 이 파일을 읽으면 잘못된 구조를 따른다.
4. **문서 4개가 같은 이야기를 반복한다.** `README.md` / `README.en.md` / `SKILL.md` / `CLAUDE.md`. 경로·폴백을 바꿀 때 네 곳을 같이 고쳐야 한다 (프로젝트 규칙).
5. **실행 비트가 들쭉날쭉하다.** `plaud_pull.py` / `process_inbox.py` / `_config.py`는 `+x`, 나머지 모듈은 아니다. launchd는 `python3 script.py`라 동작에는 문제 없다.
6. **권한 계약이 테스트에 없다.** `_parse_file` / 경로 파생은 잘 커버한다. 키 마스킹, `chmod 600`, inbox가 볼트 안인지, `/tmp` 파일 모드는 없다.
7. **노트 쓰기는 원자적이 아니다.** state는 `os.replace`, 노트는 `open(fpath, "w")`. 볼트 동기화가 중간 파일을 집어갈 수 있다. 노트 작성 후 오디오 이동이 실패하면 다음 실행에서 중복 노트·API 비용이 난다.

---

## 우선순위 (구현 시)

사용자 전역 규칙: **명시적 동의 없이 파일·폴더·데이터를 삭제하지 말 것.** `docs/superpowers` 정리는 삭제가 아니라 아카이브/주석 처리로.

| 순위 | 항목 | 이유 |
|---|---|---|
| 지금 | `chmod 600 config.env` | 키 3개가 이미 `0644`. 코드 변경 아님. |
| 1 | `_config.py` 덤프에서 키 마스킹 + 테스트 | 문서화된 명령이 유출 경로 |
| 2 | 기존 config에도 `chmod 600` (install.sh) + gitignore에 `config.env.*` / `.env` / 누락 오디오 확장자 | 공개 레포 |
| 3 | `/tmp` 오디오 `0600` + 예측 불가 경로 (`tempfile`) | 녹음 원문 |
| 4 | inbox를 볼트 밖으로 (또는 문서에 동기화 위험 경고). 기존 사용자 경로 깨지 말 것 | Sync + AssemblyAI + LLM이 겹침 |
| 5 | 설치 시 `read -s`, 모델 checksum, 다운로드 호스트 제한 | 설치/공급망 |
| 6 | speakers YAML 이스케이프, 노트 원자적 작성, inbox 심링크 거부 | 노트 무결성 |
| 7 | 낡은 `docs/superpowers` 스펙에 “구식” 표시. 삭제하지 말 것 | 구성 드리프트 |

## 구현 시 지켜야 할 프로젝트 규칙

- Python은 stdlib only. 예외는 `.venv-whisperx`의 `whisperx_transcribe.py`뿐.
- `scripts/_config.py`가 경로/설정의 단일 진실 공급원. 이미 있는 키를 하드코딩하지 말 것.
- 사용자 가시 동작(경로, 폴백, 트러블슈팅)이 바뀌면 `README.md` **그리고** `SKILL.md`를 같이 수정. 영문 README도 맞출 것.
- 테스트할 로직은 순수 함수로 추출하고 `tests/`에 추가. `python3 -m unittest discover -s tests`.
- 문서·로그·주석은 한국어.
- 가드된 import (`assemblyai_transcribe`, `claude_summarize`, `gpt_verify`)를 풀지 말 것.
- 키 값을 로그에 남기지 말 것.
- 커밋은 사용자가 요청하기 전에는 하지 말 것.

---

## 부록: 보안 리뷰어 교차검증 (같은 날, 코드 변경 없음)

전용 보안 리뷰어(`oh-my-claudecode:security-reviewer`)가 같은 트리를 다시 읽었다. **Critical 0 / High 2 / Medium 6 / Low 5.** 위 본문과 결론이 같다. 아래만 보강.

추가·정밀화:

- `$HOME` 은 현재 `750`, 인터랙티브 계정 1명 → 다른 로컬 계정이 오늘은 `config.env`에 닿지 못한다. 그래도 파일 모드 `644`는 틀렸다. 홈을 `755`로 바꾸거나 레포를 zip하면 키가 나간다.
- `--get ANTHROPIC_API_KEY` 도 키 원문을 찍는다. 마스킹뿐 아니라 비밀 키 `--get` 거부가 맞다.
- 키 파일 리더(`_api_key` / `load()`)는 모드 `600`을 강제하지 않는다.
- `~/.plaud/tokens.json` 은 CLI 소유, 모드 `644`. `$HOME` 이 `750`이라 오늘은 막혀 있다.
- 설치된 `@plaud-ai/cli` 는 `0.3.8`, npm lockfile 없음, `npm audit` 불가.
- inbox 기본값을 `state/inbox` 로 두라는 대안이 있다. **기존 사용자 `WatchPaths`를 깨므로 신규 설치 기본값 + 문서 경고만** 하는 편이 안전하다.
- 이 트리가 `644` 비밀과 함께 복사·백업된 적이 있으면 키 3종을 로테이션하라.

즉시 운영 조치(코드 아님): `chmod 600 config.env`. `python3 scripts/_config.py` 출력을 붙이지 말 것.
