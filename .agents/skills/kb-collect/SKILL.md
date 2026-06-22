---
name: kb-collect
description: Use when pull material from configured external providers (email, chat, calendar, transcripts, URL). Normalise to markdown. Drop into raw/inbox/<channel>/
---

# /kb-collect

**Purpose:** Pull material from configured external providers (email, chat, calendar, transcripts, URL). Normalise to markdown. Drop into raw/inbox/<channel>/.

**Reads:** ~/.config/work-brain/providers.toml, raw/.collect-state.json
**Writes:** raw/inbox/<channel>/, raw/.collect-state.json
**Idempotency:** per-provider cursor/seen-ids in `raw/.collect-state.json`; already-seen items emit `SEEN`. Outlook threads also track `thread_last` (conv_key → last_received): a seen conversation with newer replies emits `GROWN` and is re-collected as a `<slug>-u<YYYYMMDD>.md` update file.

## Python helper

```bash
uv run .agents/skills/kb-collect/collect.py  # cursor/ID state management
```

## Provider status

| Provider | Channel | Status |
|---|---|---|
| teams | meetings | ✅ Implemented (quality gate + backfill) |
| url | clippings | ✅ Implemented |
| file | docs | ✅ Implemented |
| outlook | emails | ✅ Implemented (quality gate + MeetGeek detection) |
| manual | chats | ✅ Implemented |
| meetgeek | meetings | ✅ Implemented |
| (journal) | journal | ❌ No collector — manual drop into `raw/inbox/journal/` only; tell the user when journals are requested |

## How this skill runs

Dispatches by **lazy `Read`** — load only the provider(s) requested.

1. Determine which provider(s) to collect (user arg, or all configured in `## Provider status`).
2. For each provider in `[teams, clippings, docs, emails-outlook, chats, meetgeek]`:
   - `Read .agents/skills/kb-collect/phases/config-check.md` → run the config/state check.
   - `Read .agents/skills/kb-collect/providers/<provider>.md` → run its fetch loop (provider API facts are in that file's `## API reference`).
   - `Read .agents/skills/kb-collect/phases/report-log.md` → run the summary + `wiki/log.md` append.

A single-provider run never loads the other providers' fetch loops.

## Idempotency re-run check

Per-provider cursor/seen-ids live in `raw/.collect-state.json` (see `collect.py`). Re-running over the same cursor range emits `SEEN` for already-collected items and writes 0 new files.
