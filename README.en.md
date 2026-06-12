# plaud-obsidian-pipeline

**English** | [한국어](README.md)

> A macOS pipeline that pulls PLAUD recordings **without a subscription (device cost only)**,
> transcribes them with **local Whisper**, summarizes with an LLM, and auto-creates **Obsidian notes**.

PLAUD only charges for **transcription (STT)** — **cloud storage and raw audio downloads are free**.
By pulling the original MP3 with the official CLI (`plaud audio <id>`) and running transcription
through **local Whisper**, you spend zero transcription quota and get voice-memo → note automation
for **$0/month**.

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
 │    ffmpeg (16k wav) → whisper-cli (transcribe) → claude -p (summarize) | transcript-only fallback
 ▼
 OUTPUT_DIR/{title}_{YYMMDD}.md     (+ original audio moved to ARCHIVE_DIR)
```

- **Two triggers**: a timer (pull) + folder watch (process). No daemons — just macOS `launchd`.
- **Transcription is 100% local**: whisper.cpp + `ggml-large-v3-turbo`. No internet, no fees.
- **Summarization is a thin layer**: `claude -p` (headless). If missing or failing, the raw transcript is saved instead.

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
2. If `config.env` is missing, **interactively** asks for your vault path / output folder / language and creates it
3. Downloads the whisper model (~1.5GB)
4. Generates 2 launchd plists (pointing at this repo's location)

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
```

Verify:
```bash
launchctl list | grep plaud-obsidian
tail -f logs/pipeline.log
```

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

Values may use `~`, `$HOME`, and `$VAULT_PATH`.
Check that your config resolves correctly: `python3 scripts/_config.py`.

> The built-in summary prompt is written in Korean. For other languages, point
> `SUMMARY_PROMPT_FILE` at your own prompt (keep the `TITLE: ... ---BODY---` output format).

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
| Note has transcript only, no summary | `claude` not installed / not logged in → normal fallback. Install Claude Code for summaries |
| Same recording processed twice | Multiple Macs running it → keep one, run `bash uninstall.sh` on the rest |
| Periodic pull not running | Mac is asleep → disable sleep in System Settings |
| Audio sits in `_inbox/_failed/` | Auto-quarantined after 3 consecutive failed transcriptions (prevents retry loops). Inspect the file, move it back to `_inbox` to retry |

Logs: `logs/pipeline.log`, `logs/launchd.err.log`, `logs/plaudpull.err.log`.
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

- **Recordings, transcripts, and notes all stay on your Mac/vault.** Transcription is local Whisper; only the (optional) summary uses Claude.
- The PLAUD OAuth token is stored in `~/.plaud/tokens.json` and is **never part of this repo**.
- `config.env`, logs, models, audio, and state files are all `.gitignore`d.

## Development / Tests

```bash
python3 -m unittest discover -s tests   # stdlib only, no dependencies
```

## License

MIT — see `LICENSE`.
