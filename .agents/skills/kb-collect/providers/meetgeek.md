# Provider — meetgeek

The orchestrator runs `phases/config-check.md` before this checklist and `phases/report-log.md` after.

## API reference

**API base URL:** `https://api.meetgeek.ai/v1`
**Auth:** `Authorization: Bearer <api_key>` header. Key lives in the `MEETGEEK_API_TOKEN` env var.
**User-Agent:** the WAF rejects the default `python-urllib` UA with **403** while curl succeeds — Python scripts must send a curl-like `User-Agent` header (e.g. `curl/8.7.1`).
**List meetings endpoint:** `GET /v1/meetings` — cursor-paginated, `limit=50`, response has `{"meetings": [...], "pagination": {"next_cursor": "...", "previous_cursor": "..."}}`. Each meeting in the list contains: `meeting_id`, `title`, `timestamp_start_utc`, `timestamp_end_utc`.
**Meeting detail endpoint:** `GET /v1/meetings/<meeting_id>` — returns `host_email`, `participant_emails[]`.
**Transcript endpoint:** `GET /v1/meetings/<meeting_id>/transcript` — response `{"meeting_id": "...", "sentences": [{id, transcript, timestamp, speaker}], "pagination": {"next_cursor": "..."}}`. Paginated by `cursor` param.
**Summary endpoint:** `GET /v1/meetings/<meeting_id>/summary` — response `{"meeting_id": "...", "summary": "<HTML string>", "ai_insights": [...]}`. Strip HTML before use.

On 401: report auth failure and stop. User must refresh `api_key` in providers.toml.

---

Pulls meeting transcripts directly from the MeetGeek REST API, writes one file per meeting to `raw/inbox/meetings/`. Idempotency by `meetgeek_key(meeting_id)`. Slug uses the same `meeting_id_slug` function as Teams → enables automatic merge with existing Teams Meeting wiki pages on ingest.

### Phase 1 — Check provider config (provider-specific step)

- [ ] **Get cursor**
  ```bash
  uv run .agents/skills/kb-collect/collect.py \
    --state-file raw/.collect-state.json \
    --provider meetgeek \
    --action get-cursor
  ```
  Output `NONE` → `since` = today minus `lookback_days` (ISO datetime, e.g. `2026-04-27T00:00:00Z`).
  Output ISO datetime → `since` = that value.

### Phase 2 — Fetch meetings from API (paginated)

- [ ] **List meetings (cursor-paginated)**

  Call `GET https://api.meetgeek.ai/v1/meetings` with:
  - Header: `Authorization: Bearer <api_key>`
  - Query params: `limit=50` (no date filter; collect all and apply idempotency)

  Response shape: `{"meetings": [...], "pagination": {"next_cursor": "<string>", "previous_cursor": "<string>"}}`.

  Each meeting in the list contains only: `meeting_id`, `title`, `timestamp_start_utc`, `timestamp_end_utc`.

  Pagination loop: if `pagination.next_cursor` is non-empty AND the page has 50 results, repeat with `cursor=<next_cursor>` appended to query. Stop when `next_cursor` is empty or page returns fewer than 50 results.

  If the API returns a 401: report auth failure and stop. The user must refresh the API key in providers.toml.

### Phase 3 — Per-meeting detail fetch

Repeat the following block for each meeting from Phase 2:

- [ ] **Compute meeting slug and idempotency key**
  ```bash
  uv run .agents/skills/kb-collect/collect.py \
    --action meeting-id \
    --subject "<meeting.title>" \
    --start "<meeting.timestamp_start_utc>"
  ```
  Capture as `<slug>`.

  ```bash
  uv run .agents/skills/kb-collect/collect.py \
    --action meetgeek-key \
    --meeting-id "<meeting.meeting_id>"
  ```
  Capture as `<mgkey>`.

- [ ] **Idempotency check**
  ```bash
  uv run .agents/skills/kb-collect/collect.py \
    --state-file raw/.collect-state.json \
    --provider meetgeek \
    --action check-id \
    --meeting-id "<mgkey>"
  ```
  Output `SEEN` → skip this meeting, continue to next. Output `NEW` → proceed.

- [ ] **Fetch meeting detail**

  Call `GET https://api.meetgeek.ai/v1/meetings/<meeting.meeting_id>` with the Bearer header.

  Extract: `host_email`, `participant_emails[]`.

- [ ] **Fetch transcript**

  Call `GET https://api.meetgeek.ai/v1/meetings/<meeting.meeting_id>/transcript` with the Bearer header.

  Response shape: `{"meeting_id": "...", "sentences": [{id, transcript, timestamp, speaker}], "pagination": {"next_cursor": "..."}}`.

  Pagination: if `pagination.next_cursor` is non-empty, repeat with `cursor=<next_cursor>` until empty. Accumulate all `sentences` across pages.

  `has_transcript` = `len(sentences) > 0`.

- [ ] **Fetch summary**

  Call `GET https://api.meetgeek.ai/v1/meetings/<meeting.meeting_id>/summary` with the Bearer header.

  Response shape: `{"meeting_id": "...", "summary": "<HTML string>", "ai_insights": [...]}`.

  Strip HTML tags from `summary` before use (e.g. via `html.parser.HTMLParser`). Do not use HTML markup in the output file. An empty `summary` is valid — write `(no summary available)`.

  Extract action items from `ai_insights[]`: for each item in `ai_insights`, if `item["label"]` contains `"action"` or `"next"` (case-insensitive), append `item["items"][].text` to the action items list.

  **Shape caveat:** `ai_insights` items are sometimes plain strings, not `{label, items}` dicts. Guard with `isinstance(item, dict)` and skip strings — an unguarded `item["label"]` crashes the whole summary parse and loses the summary text.

### Phase 4 — Per-meeting write loop

For each meeting that passed idempotency check and had detail/transcript/summary fetched:

- [ ] **Check filename collision**
  ```bash
  test -e "raw/inbox/meetings/<slug>.md" && echo COLLIDE || echo OK
  ```
  On COLLIDE: append `-<mgkey first 6 hex>` to slug.

- [ ] **Acquire inbox lock**
  ```bash
  uv run .agents/skills/kb-ingest/lock.py \
    --lock-file .kb/.inbox.lock --action acquire --timeout 5
  ```

- [ ] **Write raw meeting file**

  Compute:
  - `captured_at` = `timestamp_start_utc[:10]` (YYYY-MM-DD)
  - `start_hhmm` = `timestamp_start_utc[11:16]`
  - `end_hhmm` = `timestamp_end_utc[11:16]`
  - `all_participants` = deduplicated list: `[host_email] + participant_emails`
  - `organizer` = `host_email` (or empty string if absent)

  Write `raw/inbox/meetings/<slug>.md`:
  ```markdown
  ---
  source: meetgeek-api
  provider: meetgeek
  captured_at: <captured_at>
  channel: meetings
  meeting_id: <slug>
  meetgeek_id: <meeting.meeting_id>
  participants:
    - <email for each in all_participants>
  organizer: <host_email>
  start: "<meeting.timestamp_start_utc>"
  end: "<meeting.timestamp_end_utc>"
  original_ref: "https://app.meetgeek.ai/meeting/<meeting.meeting_id>"
  has_transcript: <true|false>
  ---

  # <meeting.title>

  **Date:** <captured_at> <start_hhmm>–<end_hhmm> UTC
  **Attendees:** <comma-separated emails from all_participants>

  ## Summary

  <HTML-stripped summary text, or "(no summary available)" if empty>

  ## Action Items

  <bullet list of extracted action item texts, or "(none)" if empty>

  ## Transcript

  <For each sentence: "**<sentence.speaker>:** <sentence.transcript>", separated by blank lines>
  <"(no transcript available)" if has_transcript is false>
  ```

- [ ] **Release lock**
  ```bash
  uv run .agents/skills/kb-ingest/lock.py \
    --lock-file .kb/.inbox.lock --action release
  ```

- [ ] **Record state**
  ```bash
  uv run .agents/skills/kb-collect/collect.py \
    --state-file raw/.collect-state.json \
    --provider meetgeek \
    --action record \
    --meeting-id "<mgkey>" \
    --cursor "<meeting.timestamp_start_utc>"
  ```
