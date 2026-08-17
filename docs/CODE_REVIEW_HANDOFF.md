# 보안·파일 구성 코드리뷰 인수인계

## 범위

- 코드는 수정하지 않고 보안 및 파일 구성 관점만 검토함.
- 코드 파일은 변경하지 않았으며, 이 인수인계 문서만 추가함.
- `python3 -m unittest discover -s tests -v`: 73개 테스트 모두 통과.

## 우선순위 높은 이슈

### 1. 설정 전체 출력 시 API 키·토큰 노출 — High

근거: `scripts/_config.py:123-133`

`python3 scripts/_config.py`와 `--json`이 `config.env`의 API 키와 토큰을 포함한 전체 설정을 그대로 출력한다. 문서에서도 이 명령을 진단용으로 안내하고 있어 터미널 캡처, CI 로그, 지원 요청 과정에서 비밀값이 유출될 수 있다.

권장:

- 기본 출력에서는 키를 실제 값 대신 `configured: true` 등으로 마스킹
- 비밀값을 출력하는 별도 경로는 만들지 않거나 명시적 개발 전용 옵션으로 제한
- `config.env`와 키 파일의 권한을 `600`으로 검증

### 2. LLM 프롬프트 인젝션 및 출력 검증 부족 — High

근거: `scripts/process_inbox.py:182-200`, `scripts/process_inbox.py:402-415`, `scripts/process_inbox.py:362-368`

전사 내용이 Claude/GPT 입력에 그대로 들어간다. 악의적인 발화가 있으면 요약의 결정사항·액션 아이템을 조작하거나 임의 Markdown을 삽입할 수 있다. `parse_claude_output()`은 `---BODY---` 존재 여부만 확인하며, 화자 이름은 YAML frontmatter에 직접 삽입된다.

권장:

- 전사와 시스템 지시를 명확히 분리하고 전사를 비신뢰 데이터로 취급
- 제목·화자·본문을 각각 엄격히 검증
- YAML 값은 안전하게 quoting/직렬화
- `verified: true`는 사실 보증이 아닌 검증 모델 처리 완료 의미로 표현

### 3. 예측 가능한 `/tmp` 임시파일 — Medium/High

근거: `scripts/plaud_pull.py:190-199`, `scripts/process_inbox.py:287-309`

`/tmp/plaud_<id>.mp3`, `/tmp/voicememo_<name>_<timestamp>.wav`처럼 예측 가능한 경로를 사용한다. 같은 사용자 권한의 다른 프로세스가 심볼릭 링크를 미리 만들면 파일 덮어쓰기·잘못된 파일 처리 위험이 있다.

권장:

- `tempfile.mkdtemp()` 또는 `mkstemp()` 사용
- 임시 디렉터리 권한 `700`
- 다운로드 파일의 최대 크기와 일반 파일 여부 확인

### 4. 다운로드 URL·크기 검증 부족 — Medium

근거: `scripts/plaud_pull.py:150-164`

CLI 출력에서 `https://`로 시작하는 URL을 모두 허용하고 `curl -L`로 리다이렉트를 따라간다. CLI 변조나 출력 형식 변경 시 임의 원격 파일 다운로드, 디스크 소진, 데이터 오염 위험이 있다.

권장:

- 허용 호스트 제한
- 리다이렉트 정책 제한
- 최대 파일 크기 설정
- Content-Type 및 실제 오디오 형식 검증

### 5. 설치 의존성·모델 무결성 검증 부족 — Medium

근거: `install.sh:37-47`, `install.sh:109-113`, `README.md:70`

npm 패키지와 WhisperX가 버전 고정 없이 설치되고, Whisper 모델도 checksum 검증 없이 다운로드된다.

권장:

- npm/WhisperX 버전 고정
- 모델 SHA-256 검증
- lockfile 또는 검증된 릴리스 사용

## 파일 구성·신뢰성 이슈

- `scripts/process_inbox.py`가 전사 엔진, 프롬프트, 파싱, Markdown/YAML 생성, 파일 이동, 아카이브를 모두 담당한다. `config / ingestion / transcription / llm / note-rendering / archive` 정도로 분리하는 편이 보안 경계를 명확히 한다.
- `scripts/claude_summarize.py:106`이 standalone 실행 시 `process_inbox.PROMPT`를 역 import한다. 요약 모듈과 오케스트레이터의 결합도가 높다.
- 모듈 import 시점에 전역 설정과 바이너리를 탐색한다. 설정 변경·테스트·재사용성이 떨어진다.
- `scripts/process_inbox.py:421-430`에서 최종 노트를 임시 파일 없이 직접 작성하므로 실행 중단 시 부분 노트가 Obsidian에 보일 수 있다.
- `scripts/process_inbox.py:432-439`에서 노트 작성 후 오디오 이동이 실패하면 다음 실행에서 중복 노트와 API 비용이 발생할 수 있다.

## Git 보호 규칙 누락

근거: `.gitignore:25-31`

처리 대상에는 `.aiff`, `.aif`, `.ogg`, `.webm`, `.mp4`, `.m4v`도 포함되지만 `.gitignore`에는 일부 오디오 확장자만 있다. 개인 음성이 실수로 커밋될 수 있으므로 지원하는 모든 오디오 확장자를 제외해야 한다.

## 권장 처리 순서

1. 설정 출력 시 비밀값 마스킹
2. LLM 입력·출력 검증 및 YAML 안전 처리
3. 임시파일 안전성 개선
4. 다운로드 호스트·크기 검증
5. 의존성/모델 무결성 검증
6. 오디오 확장자 `.gitignore` 보완
7. `process_inbox.py` 기능 분리 및 원자적 노트 작성
