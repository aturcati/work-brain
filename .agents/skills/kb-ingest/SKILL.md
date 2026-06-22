---
name: kb-ingest
description: "Use when process raw/inbox/ or a specified path: classify, normalise frontmatter, route into raw channel date-partitioned paths, fan out wiki edits via atomic staging, invoke closed-schema edge extraction, append proposals to wiki/_inbox/edges.md, trigger /kb-graph project"
---

# /kb-ingest

**Purpose:** Process raw/inbox/ (or specified path): classify, normalise frontmatter, route into raw/<channel>/<date-partitioned>/, fan out wiki edits via atomic staging, invoke closed-schema edge extraction, append proposals to wiki/_inbox/edges.md, trigger /kb-graph project.

**Reads:** raw/inbox/, raw/.ingest-state.json, .kb/extract-state.json, wiki/index.md
**Writes:** raw/<channel>/, wiki/ (via .kb-staging/), wiki/_inbox/edges.md, raw/.ingest-state.json, .kb/extract-state.json, wiki/log.md
**Idempotency:** `(raw_path, sha256)` in `raw/.ingest-state.json`; already-ingested files emit `SKIP`.

## Python helpers (stdlib only, uv run)

```bash
uv run .agents/skills/kb-ingest/state.py    # sha256 idempotency check/write
uv run .agents/skills/kb-ingest/lock.py     # advisory .kb/.inbox.lock acquire/release
uv run .agents/skills/kb-ingest/move_file.py  # move inbox file → raw/<channel>/YYYY/MM/
```

> **Invariants (see AGENTS.md → Operational invariants):**
> - `sources:` must cite the FINAL moved path `raw/<channel>/YYYY/MM/<file>.md`, never the inbox path.
> - Resolve provider slug suffixes (e.g. MeetGeek `-<6hex>`) via `match.py` before creating a page — avoids duplicates. Process plain files BEFORE suffixed MeetGeek files (glob order is backwards: `-` < `.`).
> - **Lock lifecycle:** multi-file runs hold ONE lock for the whole run and release once at the end; every failure/quarantine path must also release it. Do not follow the per-file acquire/release in the phase docs literally when processing batches.
> - **captured_at for frontmatter-less files** — precedence: filename date (`20260508_` → 2026-05-08) → frontmatter `created` → explicit date in content → file mtime. Derive in-process; NEVER rewrite the inbox file to inject frontmatter (raw is immutable by convention).

## Channel status

| Channel | Status |
|---|---|
| journal | ✅ Implemented |
| meetings | ✅ Implemented |
| clippings | ✅ Implemented |
| docs | ✅ Implemented |
| emails | ✅ Implemented (quality gate, MeetGeek summary detection) |
| chats | ✅ Implemented |

## How this skill runs

This skill dispatches by **lazy `Read`**: it loads only the files the current inbox needs. Do **not** pre-read all channels.

For each channel in `[journal, meetings, clippings, docs, emails, chats]`:

1. If `raw/inbox/<channel>/` has no `.md` files, skip the channel.
2. Otherwise run these files **in order**, substituting the active `<channel>` and per-file `<file>`:
   - `Read .agents/skills/kb-ingest/phases/lock-dedup.md` → run Phase 1.
   - `Read .agents/skills/kb-ingest/channels/<channel>.md` → run the Phase 2 handler.
   - `Read .agents/skills/kb-ingest/phases/edge-extraction.md` → run Phase 3 using the handler's edge hints.
   - `Read .agents/skills/kb-ingest/phases/move-state-cleanup.md` → run Phase 4.
   - `Read .agents/skills/kb-ingest/phases/reindex-log.md` → run Phase 5.

All five files share one lock cycle per channel. A journal-only run loads exactly five small files, never the other handlers.

## Idempotency re-run check

Run after every ingest (see `phases/move-state-cleanup.md` for the state writes):
```bash
uv run .agents/skills/kb-ingest/state.py --state-file raw/.ingest-state.json --raw-path <final-path> --action check
```
Already-ingested files emit `SKIP`.
