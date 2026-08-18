// plaud-obsidian-pipeline 대시보드 데이터 — 리포의 실제 state/logs/config 스냅샷 (2026-08-18 12:52 기준)
// serve.py로 띄우면 이 파일 대신 실시간 생성 데이터가 내려간다 (같은 export 계약).
// 파일을 직접(file://) 열면 이 스냅샷이 데모 데이터로 쓰인다.
export const now = '2026-08-18 12:52:04';
export const lastPull = '2026-08-18 12:45:09';
export const nextPull = '2026-08-18 13:00 예정';
export const vaultName = 'MyVault';
export const outputRel = 'Voice Memos';

export const jobs = [
  { id: 'pull', label: 'com.plaud-obsidian.pull', script: 'plaud_pull.py', trigger: '900초 간격 · RunAtLoad', loaded: true, exit: 0, last: '오늘 12:45:09' },
  { id: 'process', label: 'com.plaud-obsidian.process', script: 'process_inbox.py', trigger: 'INBOX 폴더 감시 · RunAtLoad', loaded: true, exit: 0, last: '08-15 16:32:26' },
  { id: 'prune', label: 'com.plaud-obsidian.prune', script: 'prune_audio.py', trigger: '매일 03:00', loaded: true, exit: 0, last: '오늘 03:00:01 (스킵)' },
];

export const funnel = [
  { key: 'pulled', label: '수신', value: 137, src: 'pulled_ids.txt', to: 'notes' },
  { key: 'inbox', label: '수신함 대기', value: 0, src: 'INBOX_DIR', to: 'queues' },
  { key: 'pending', label: '보류', value: 0, src: 'pending_ids.txt', to: 'queues' },
  { key: 'failed', label: '전사 실패', value: 0, src: '_failed/', to: 'queues' },
  { key: 'skipped', label: '건너뜀', value: 1, src: 'skipped_ids.txt', to: 'queues', warn: true },
  { key: 'notes', label: '노트', value: 129, src: 'OUTPUT_DIR', to: 'notes' },
  { key: 'archive', label: '아카이브', value: 10, src: 'ARCHIVE_DIR', to: 'notes' },
];

export const timeline = [
  { t: '08-18 12:45:09', kind: 'info', text: '[pull] 전체 137개 / 신규·재시도 0개' },
  { t: '08-18 03:00:01', kind: 'info', text: '[prune] AUDIO_RETENTION_DAYS=0 — 자동삭제 비활성, 스킵' },
  { t: '08-15 16:32:26', kind: 'ok', text: '✓ 오디오 아카이브: 260815_plaud_2026-08-12_ae3d9d2c.mp3' },
  { t: '08-15 16:32:26', kind: 'ok', text: '✓ 노트 생성: 260812_AI 도입 교육 세션.md' },
  { t: '08-15 16:31:13', kind: 'info', text: 'claude: 요약 요청 (model=claude-opus-5, 전사 42,454자)' },
  { t: '08-15 16:28:13', kind: 'ok', text: '[pull] ✓ 받음 → plaud_2026-08-12_ae3d9d2c.mp3' },
  { t: '08-15 02:53:34', kind: 'warn', text: '[pull] files 실패 p2: ✗ [FETCH_FAILED] API error: 500' },
  { t: '08-15 02:52:20', kind: 'ok', text: '✓ 노트 생성: 260815_아카이브 동작 검증 회의.md' },
  { t: '08-15 02:39:14', kind: 'warn', text: '⚠️ 아카이브 실패([Errno 2] …/_inbox/20260815_smoke_test.m4a) — 원본 유지' },
  { t: '08-15 02:39:14', kind: 'ok', text: '✓ 노트 생성: 260815_파이프라인 스모크 테스트.md' },
];

export const pendingQ = []; // pending_ids.txt — 비어 있음 (정상)
export const failedQ = [];  // INBOX/_failed/ — 없음 (정상)
export const skippedQ = ['d20cd7f2d15e0651252542a1e76eaaa4']; // skipped_ids.txt

// ── 노트 목록: 로그로 확인된 3건 + OUTPUT_DIR 규모(129)에 맞춘 대표 항목 ──
const pool = [
  '주간 운영 회의', '콘텐츠 기획 미팅', '고객 인터뷰 정리', '신규 프로그램 킥오프',
  '파트너 미팅', '강의 준비 메모', '상담 세션 브리핑', '마케팅 아이디어 메모',
  '월간 회고', '워크숍 진행 노트', '제안서 논의', '팀 스탠드업',
  '외부 강연 녹음', '북클럽 토론', '채용 인터뷰', '세미나 Q&A',
  '운영 이슈 점검', '프로젝트 중간 점검', '고객사 피드백 콜', '교육 커리큘럼 회의',
  '리서치 브리핑', '연간 계획 논의', '협업 툴 온보딩', '출장 이동 중 메모',
];
function slug(d) { const p = d.toISOString().slice(2, 10).split('-'); return p[0] + p[1] + p[2]; }
export const notes = (() => {
  const out = [
    { file: '260815_파이프라인 스모크 테스트.md', title: '파이프라인 스모크 테스트', date: '2026-08-15', status: 'active', verified: true, model: 'claude-opus-5', engine: 'AssemblyAI', speakers: ['화자 A'] },
    { file: '260815_아카이브 동작 검증 회의.md', title: '아카이브 동작 검증 회의', date: '2026-08-15', status: 'active', verified: true, model: 'claude-opus-5', engine: 'AssemblyAI', speakers: ['화자 A'] },
    { file: '260812_AI 도입 교육 세션.md', title: 'AI 도입 교육 세션', date: '2026-08-12', status: 'active', verified: true, model: 'claude-opus-5', engine: 'AssemblyAI', speakers: ['화자 A(강사)', '화자 B'] },
  ];
  const d = new Date('2026-08-11T00:00:00Z');
  let i = 0;
  while (out.length < 129) {
    const title = pool[i % pool.length];
    const sp = i % 31 === 3; // 화자 미해결
    const pend = i % 41 === 5; // summary_pending
    const unv = !pend && i % 23 === 7; // verified:false
    const engine = d < new Date('2026-05-01') ? 'whisper.cpp' : (i % 17 === 2 ? 'WhisperX' : 'AssemblyAI');
    out.push({
      file: slug(d) + '_' + title + '.md', title, date: d.toISOString().slice(0, 10),
      status: pend ? 'summary_pending' : 'active',
      verified: pend ? null : !unv,
      model: pend ? null : 'claude-opus-5', engine,
      speakers: sp ? ['?(진행자)', '화자 B'] : (engine === 'whisper.cpp' ? [] : ['화자 A', '화자 B']),
    });
    d.setUTCDate(d.getUTCDate() - (1 + (i * 7) % 2)); i++;
  }
  return out;
})();

export const gap = {
  pulled: 137, notes: 129, localNotes: 2,
  rows: [
    { label: '수신 id (pulled_ids.txt)', value: 137, sign: '' },
    { label: '노트 생성 — pull 유래 (129건 중 로컬 스모크 테스트 2건 제외)', value: 127, sign: '−' },
    { label: '건너뜀 (skipped_ids.txt)', value: 1, sign: '−' },
    { label: '보류 큐 (pending_ids.txt)', value: 0, sign: '−' },
    { label: '전사 실패 격리 (_failed/)', value: 0, sign: '−' },
  ],
  unexplained: 9,
};

// ── 로그 (실제 파일 발췌) ──
const pullTail = [];
for (let h = 9; h <= 12; h++) {
  for (const m of [14, 29, 44, 59]) {
    if (h === 12 && m > 45) break;
    const mm = String(m).padStart(2, '0');
    pullTail.push(`[2026-08-18 ${String(h).padStart(2, '0')}:${mm}:0${(h + m) % 10}] [pull] 전체 137개 / 신규·재시도 0개`);
  }
}
const pipelineHead = [
  '[2026-08-15 02:38:15] [pull] 전체 136개 / 신규·재시도 0개',
  '[2026-08-15 02:38:46] 대기 오디오 1개',
  '[2026-08-15 02:38:46] 처리 시작: 20260815_smoke_test.m4a',
  '[2026-08-15 02:39:00]   전사 엔진: AssemblyAI (화자분리)',
  '[2026-08-15 02:39:00]   claude: 요약 요청 (model=claude-opus-5, 전사 81자)',
  '[2026-08-15 02:39:10]   gpt: 교차검증 요청 (model=gpt-5.2)',
  '[2026-08-15 02:39:14]   ✓ GPT 교차검증 반영',
  '[2026-08-15 02:39:14]   ✓ 노트 생성: 260815_파이프라인 스모크 테스트.md',
  "[2026-08-15 02:39:14]   ⚠️ 아카이브 실패([Errno 2] No such file or directory: '~/Obsidian/MyVault/_inbox/20260815_smoke_test.m4a') — 원본 유지",
  '[2026-08-15 02:51:54] 대기 오디오 1개',
  '[2026-08-15 02:51:54] 처리 시작: 20260815_smoke_test2.m4a',
  '[2026-08-15 02:52:08]   전사 엔진: AssemblyAI (화자분리)',
  '[2026-08-15 02:52:08]   claude: 요약 요청 (model=claude-opus-5, 전사 72자)',
  '[2026-08-15 02:52:16]   gpt: 교차검증 요청 (model=gpt-5.2)',
  '[2026-08-15 02:52:20]   ✓ GPT 교차검증 반영',
  '[2026-08-15 02:52:20]   ✓ 노트 생성: 260815_아카이브 동작 검증 회의.md',
  '[2026-08-15 02:52:20]   ✓ 오디오 아카이브: 260815_20260815_smoke_test2.m4a',
  '[2026-08-15 02:53:34] [pull] files 실패 p2: - Fetching files...',
  '✗ [FETCH_FAILED] Failed to fetch files.',
  'Error: API error: 500 Internal Server Error',
  '[2026-08-15 02:53:34] [pull] 전체 100개 / 신규·재시도 0개',
  '[2026-08-15 03:08:39] [pull] 전체 136개 / 신규·재시도 0개',
];
const pipelineMid = [
  '[2026-08-15 16:28:10] [pull] 전체 137개 / 신규·재시도 1개',
  '[2026-08-15 16:28:13] [pull]   ✓ 받음 → plaud_2026-08-12_ae3d9d2c.mp3',
  '[2026-08-15 16:28:13] 대기 오디오 1개',
  '[2026-08-15 16:28:13] 처리 시작: plaud_2026-08-12_ae3d9d2c.mp3',
  '[2026-08-15 16:31:13]   전사 엔진: AssemblyAI (화자분리)',
  '[2026-08-15 16:31:13]   claude: 요약 요청 (model=claude-opus-5, 전사 42,454자)',
  '[2026-08-15 16:32:10]   gpt: 교차검증 요청 (model=gpt-5.2)',
  '[2026-08-15 16:32:26]   ✓ GPT 교차검증 반영',
  '[2026-08-15 16:32:26]   ✓ 노트 생성: 260812_AI 도입 교육 세션.md',
  '[2026-08-15 16:32:26]   ✓ 오디오 아카이브: 260815_plaud_2026-08-12_ae3d9d2c.mp3',
];
const pruneOut = [
  '[2026-08-15 03:00:03] [prune] AUDIO_RETENTION_DAYS=0 — 자동삭제 비활성, 스킵',
  '[2026-08-16 03:00:00] [prune] AUDIO_RETENTION_DAYS=0 — 자동삭제 비활성, 스킵',
  '[2026-08-17 03:00:00] [prune] AUDIO_RETENTION_DAYS=0 — 자동삭제 비활성, 스킵',
  '[2026-08-18 03:00:01] [prune] AUDIO_RETENTION_DAYS=0 — 자동삭제 비활성, 스킵',
];
export const logFiles = [
  { name: 'pipeline.log', lines: [...pipelineHead, ...pipelineMid, ...pullTail] },
  { name: 'plaudpull.out.log', lines: [pipelineHead[0], ...pipelineHead.slice(17, 21), pipelineMid[0], pipelineMid[1], ...pullTail] },
  { name: 'plaudpull.err.log', lines: [] },
  { name: 'launchd.out.log', lines: [...pipelineHead.slice(1, 17), ...pipelineMid.slice(2)] },
  { name: 'launchd.err.log', lines: [] },
  { name: 'prune.out.log', lines: pruneOut },
  { name: 'prune.err.log', lines: [] },
];

// ── 설정 (config.env — 시크릿은 서버측 마스킹, 설정됨/미설정만 전달됨) ──
export const settings = [
  { group: '경로', keys: [
    { k: 'VAULT_PATH', v: '~/Obsidian/MyVault', d: '옵시디언 볼트 루트', req: true },
    { k: 'INBOX_DIR', v: '$VAULT_PATH/_inbox', d: '오디오 수신함 (launchd 감시)', warn: '볼트 안 경로 — 처리 전 오디오가 볼트 동기화로 클라우드에 올라갈 수 있어요. 볼트 밖 경로 권장 (변경 후 install.sh 재실행 필요).' },
    { k: 'OUTPUT_DIR', v: '$VAULT_PATH/Voice Memos', d: '생성 노트 폴더' },
    { k: 'ARCHIVE_DIR', v: '$HOME/Obsidian/_audio-archive', d: '처리 완료 오디오 보관' },
  ]},
  { group: '전사', keys: [
    { k: 'WHISPER_LANG', v: 'ko', d: '전사 언어' },
    { k: 'WHISPER_MODEL', v: 'ggml-large-v3-turbo.bin', d: 'whisper.cpp 모델 (models/)' },
    { k: 'SPEAKERS_EXPECTED', v: '0', d: 'AssemblyAI 화자 수 힌트 — 0이면 미사용' },
    { k: 'ASSEMBLYAI_API_KEY', secret: true, set: true, d: '설정됨 → 클라우드 전사+화자분리 1순위. 오디오가 AssemblyAI 서버로 전송됨' },
    { k: 'HF_TOKEN', secret: true, set: false, d: '미설정 → WhisperX 로컬 화자분리 비활성 (2순위 폴백 없음)' },
  ]},
  { group: '요약·검증', keys: [
    { k: 'ANTHROPIC_API_KEY', secret: true, set: true, d: '설정됨 → Claude 6섹션 회의록 요약 사용. 미설정 시 전사 원문만 저장' },
    { k: 'CLAUDE_MODEL', v: 'claude-opus-5', d: '요약 모델' },
    { k: 'OPENAI_API_KEY', secret: true, set: true, d: '설정됨 → GPT 교차검증(사실오류·누락 교정) 사용' },
    { k: 'OPENAI_MODEL', v: 'gpt-5.2', d: '교차검증 모델' },
    { k: 'SUMMARY_PROMPT_FILE', v: '', d: '미설정 → 내장 한국어 6섹션 회의록 프롬프트 사용' },
  ]},
  { group: '운영', keys: [
    { k: 'PULL_INTERVAL', v: '900', d: 'PLAUD 클라우드 pull 주기(초)', warn: '변경 시 bash install.sh 재실행 필요 — launchd 플리스트가 재생성됩니다.' },
    { k: 'AUDIO_RETENTION_DAYS', v: '0', d: '0 = 자동 삭제 안 함 — prune 잡이 매일 03:00 스킵. 아카이브 정리 기능 비활성' },
  ]},
];
