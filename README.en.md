# plaud-obsidian-pipeline

**English** | [한국어](README.md)

> A macOS pipeline that pulls PLAUD recordings **without a subscription (device cost only)**,
> transcribes them (**local Whisper** by default, optional **speaker diarization**), summarizes them
> into **six-section meeting notes** with an LLM, and auto-creates **Obsidian notes**.

PLAUD only charges for **transcription (STT)** — **cloud storage and raw audio downloads are free**.
By pulling the original MP3 with the official CLI (`plaud audio <id>`) and running transcription
through **local Whisper**, you spend zero transcription quota and get voice-memo → note automation
for **$0/month**. If you need speaker diarization (who said what), you can opt in to an
AssemblyAI key (cloud) or WhisperX (local).

> ⚠️ This project uses only the PLAUD **official CLI** (`@plaud-ai/cli`). No unofficial reverse-engineered APIs.
> Pricing/ToS may change on PLAUD's side — verify against your own account.

---

## How it works

```
PLAUD recorder →(BT)→ PLAUD cloud (free storage)
 │
 │  [launchd timer · every 15 min]  scripts/plaud_pull.py
 │    plaud files → dedup new ids → plaud audio <id> → curl → atomic move into INBOX_DIR
 ▼
 INBOX_DIR (inside your Obsidian vault)
 │
 │  [launchd WatchPaths]  scripts/process_inbox.py
 │    3-tier transcription chain: AssemblyAI (diarized, only if key set)
 │      → WhisperX (local diarization, only if venv present) → whisper.cpp (always available)
 │    → claude -p (6-section meeting summary + speaker-name inference) | transcript-only fallback
 ▼
 OUTPUT_DIR/{YYMMDD}_{title}.md     (+ original audio moved to ARCHIVE_DIR)
```

- **Three triggers**: a timer (pull) + folder watch (process) + daily 03:00 (archive pruning, opt-in). No daemons — just macOS `launchd`.
- **Transcription is 100% local by default**: whisper.cpp + `ggml-large-v3-turbo`. No internet, no fees. Diarization is opt-in (see "Transcription engine chain").
- **Summarization is a thin layer**: `claude -p` (headless). If missing or failing, the raw transcript is saved instead.
- **Notes are dated by recording date**: filenames are `{YYMMDD}_{title}.md` so the file list sorts
  chronologically, and the frontmatter `created` field uses the recording date too.

---

## Transcription engine chain

`process_inbox.py` tries three engines in order, falling back to the next tier on failure.
**With no extra setup it uses whisper.cpp only** — the same fully-local behavior as before.

| Order | Engine | Diarization | How to enable | Notes |
|---|---|---|---|---|
| 1 | [AssemblyAI](https://www.assemblyai.com) (cloud, `universal-2`) | ✅ | Set `ASSEMBLYAI_API_KEY` in `config.env` | Paid API. **Audio is sent to AssemblyAI servers** |
| 2 | WhisperX + pyannote (local) | ✅ | WhisperX setup below + `HF_TOKEN` | Free and local, but slow (CPU transcription + diarization) |
| 3 | whisper.cpp (local) | ❌ | Default — installed by install.sh | Always-available final fallback |

When diarization succeeds, the note gets a **per-speaker transcript** in the form
`**[Speaker A(Kim)]** ...`, and the claude summary fills in speaker names only when there is
clear evidence (self-introductions, titles, forms of address) in the transcript.

### WhisperX setup (optional — local diarization)

Heavy (several GB including torch). Use it only when you want diarization without sending audio to the cloud.

```bash
# Install Python 3.11 (recommended version — pyannote/torch compatibility; separate from system python3)
brew install python@3.11

# From the repo root, create the venv and install whisperx
$(brew --prefix python@3.11)/bin/python3.11 -m venv .venv-whisperx
.venv-whisperx/bin/pip install whisperx
```

1. Create a [HuggingFace token](https://huggingface.co/settings/tokens) and set `HF_TOKEN=hf_...` in `config.env`
2. Accept the license on the [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) model page (gated model)
3. Once the venv exists it is used automatically as tier 2. Test: `.venv-whisperx/bin/python scripts/whisperx_transcribe.py <audio-file>`

---

## Requirements

- **macOS** (depends on launchd — this pipeline runs on a Mac only)
- [Homebrew](https://brew.sh)
- Node.js (`brew install node`) — for the official PLAUD CLI
- A PLAUD account + recorder
- (Optional) [Claude Code](https://claude.com/claude-code) — for the summary step. Without it, only transcripts are saved.

---

## Install

```bash
git clone https://github.com/mindrepublic2018/plaud-obsidian-pipeline.git
cd plaud-obsidian-pipeline
bash install.sh
```

What `install.sh` does:
1. Installs brew dependencies (`whisper-cpp`, `ffmpeg`) + `@plaud-ai/cli`
2. If `config.env` is missing, **interactively** asks for your vault path / output folder / language / AssemblyAI key (optional) and creates it
3. Downloads the whisper model (~1.5GB)
4. Generates 3 launchd plists (pull/process/prune — pointing at this repo's location)

> The scripts run **in place from this cloned repo folder** (nothing is copied).
> If you move the repo, re-run `bash install.sh`.

### Manual steps after install

```bash
# (Required) PLAUD login — browser OAuth; tokens are stored in ~/.plaud (outside the repo)
plaud login

# (Optional) For summaries, install and log in to Claude Code. Otherwise only transcripts are saved.

# Load the launchd jobs
launchctl load -w ~/Library/LaunchAgents/com.plaud-obsidian.process.plist
launchctl load -w ~/Library/LaunchAgents/com.plaud-obsidian.pull.plist
launchctl load -w ~/Library/LaunchAgents/com.plaud-obsidian.prune.plist   # archive pruning (opt-in)
```

Verify:
```bash
launchctl list | grep plaud-obsidian
tail -f logs/pipeline.log
```

**Quick smoke test**: copy any audio file (m4a/mp3/...) into `INBOX_DIR` (default
`$VAULT_PATH/_inbox`). Transcription starts within a minute or two (look for "처리 시작" in
`logs/pipeline.log`), and a note appears in `OUTPUT_DIR` when it finishes — an instant way to
confirm the pipeline works, no PLAUD recorder needed.

---

## Configuration (`config.env`)

See `config.env.example`. `install.sh` generates it automatically; edit it any time.

| Key | Default | Description |
|---|---|---|
| `VAULT_PATH` | (required) | Obsidian vault root path |
| `INBOX_DIR` | `$VAULT_PATH/_inbox` | Where audio lands (watched by launchd) |
| `OUTPUT_DIR` | `$VAULT_PATH/Voice Memos` | Where generated notes go |
| `ARCHIVE_DIR` | `$HOME/Obsidian/_audio-archive` | Where original audio is kept after processing |
| `WHISPER_LANG` | `ko` | Transcription language (en/ja/...) |
| `WHISPER_MODEL` | `ggml-large-v3-turbo.bin` | whisper model filename |
| `PULL_INTERVAL` | `900` | Pull interval in seconds |
| `SUMMARY_PROMPT_FILE` | (built-in prompt) | Path to a custom summary prompt file |
| `CLAUDE_MODEL` | `sonnet` | Model for `claude -p` summaries |
| `ASSEMBLYAI_API_KEY` | (empty) | If set, cloud transcription+diarization becomes tier 1 ⚠️ audio leaves your machine |
| `HF_TOKEN` | (empty) | HuggingFace token for local WhisperX diarization |
| `AUDIO_RETENTION_DAYS` | `0` | Days to keep archived audio. 0 = never auto-delete |

Values may use `~`, `$HOME`, and `$VAULT_PATH`.
Check that your config resolves correctly: `python3 scripts/_config.py`.

> The built-in summary prompt is written in Korean and produces a six-section meeting note
> (agenda / key discussion / decisions / action items / next steps / overall tone memo).
> For other languages, point `SUMMARY_PROMPT_FILE` at your own prompt — keep the
> `TITLE: ... ---SPEAKERS--- ... ---BODY---` output contract (the SPEAKERS block is optional).

---

## Viewing on mobile (iPhone/Android)

This pipeline runs on **one awake Mac**. Phones are viewers only — notes accumulate in your
vault (`OUTPUT_DIR`) and reach mobile Obsidian through **whatever vault sync you already use**.

- **Recommended**: [Obsidian Sync](https://obsidian.md/sync)
- **Alternatives**: iCloud Drive, Syncthing, etc. (the pipeline is sync-agnostic)
- Use **exactly one** sync method — stacking several causes split-brain conflicts.

> If the Mac sleeps, periodic pulls stop. Run it on an always-on Mac (e.g. a desktop) with sleep disabled.

---

## Health checks / Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| `plaud CLI missing` | `npm install -g @plaud-ai/cli` → `plaud login` |
| `recording list empty / query failed` | Token expired → re-run `plaud login` |
| `model missing` | Check that `install.sh`'s download finished (`models/*.bin`) |
| Note has transcript only, no summary | `claude` not installed / not logged in → normal fallback. Install Claude Code for summaries. **An outdated CLI also causes this** — the summary call uses the `--tools`/`--no-session-persistence` flags, so old versions fall back silently → run `claude update` and retry (check for "claude 실패" in `logs/pipeline.log`) |
| Same recording processed twice | Multiple Macs running it → keep one, run `bash uninstall.sh` on the rest |
| Periodic pull not running | Mac is asleep → disable sleep in System Settings |
| Audio sits in `_inbox/_failed/` | Auto-quarantined after 3 consecutive failed transcriptions (prevents retry loops). Inspect the file, move it back to `_inbox` to retry |
| Repeated `audio not ready — will retry` logs | Long recordings take time to process on PLAUD's servers → normal. Retried for ~24h (96 attempts) before being permanently skipped |
| No speaker diarization | No AssemblyAI key and no WhisperX venv → whisper.cpp fallback (no diarization) is the expected behavior. See "Transcription engine chain" |
| Archived audio disappears | With `AUDIO_RETENTION_DAYS` > 0, audio older than the retention window is deleted daily at 03:00 (opt-in). Originals remain in PLAUD cloud |

Logs: `logs/pipeline.log`, `logs/launchd.err.log`, `logs/plaudpull.err.log`, `logs/prune.out.log`.
Runtime state (pulled recording ids, fail counts, locks) lives in the repo's `state/` folder (never committed).

---

## Uninstall

```bash
bash uninstall.sh   # unloads launchd jobs + removes plists (vault notes are preserved)
```

To remove models/logs/state as well, delete the repo folder.
To delete PLAUD tokens: `rm -rf ~/.plaud`.

---

## Privacy / Security

- **With the default configuration, recordings, transcripts, and notes all stay on your Mac/vault.** Transcription is local Whisper; only the (optional) summary uses Claude.
- **Only if you set `ASSEMBLYAI_API_KEY`** is audio sent to AssemblyAI servers for transcription.
  Leave the key empty (default) and audio never leaves your machine. Check AssemblyAI's data
  retention policy against your own account settings. The WhisperX tier keeps diarization 100% local too.
- The PLAUD OAuth token is stored in `~/.plaud/tokens.json` and is **never part of this repo**.
- API keys (`config.env`, `.assemblyai_key`, `.hf_token`), logs, models, audio, and state files are all `.gitignore`d.

## Development / Tests

```bash
python3 -m unittest discover -s tests   # stdlib only, no dependencies
```

## License

MIT — see `LICENSE`.
