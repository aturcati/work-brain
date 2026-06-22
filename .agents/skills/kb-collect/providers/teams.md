# Provider — teams

The orchestrator runs `phases/config-check.md` before this checklist and `phases/report-log.md` after.

Fetches Teams meeting metadata (+ transcripts when enabled) into `raw/inbox/meetings/`.

**MCP tools used:** `mcp__claude_ai_Microsoft_365__outlook_calendar_search`, `mcp__claude_ai_Microsoft_365__read_resource`

### Phase 2 — Fetch calendar events

- [ ] **Fetch calendar events since `since` (paginated)**

  Compute `until` = today's date end-of-day in ISO format (e.g. `2026-05-13T23:59:59Z`).

  Collect all events using a pagination loop:
  1. Call `mcp__claude_ai_Microsoft_365__outlook_calendar_search` with:
    - `query`: `"*"`
    - `afterDateTime`: current `page_after` (initially = `since`)
    - `beforeDateTime`: `until`
    - `limit`: `25` (tool maximum — NOT 50)
    - `offset`: `0`, then the `nextOffset` value from the prior response
  2. Append results to `all_events`.
  3. If the response's final item carries `nextOffset`: pass it as `offset` and repeat.
  4. If no `nextOffset`: stop — all events collected.

  In sync mode this almost always completes in one page. In backfill mode over years of history, expect many pages.

  Each result has: `uri`, `subject`, `start`, `end`, `attendees[]`, `location`, `summary`, `organizer`.

- [ ] **Identify Teams meetings**

  A result IS a Teams meeting when its `summary` or `location` contains `"teams.microsoft.com"` OR `"Microsoft Teams"`.
  Skip events that have neither (in-person only meetings without Teams link).

### Phase 3 — Collect each Teams meeting

Repeat the following block for each Teams meeting event identified above:

- [ ] **Compute meeting_id**
  ```bash
  uv run .agents/skills/kb-collect/collect.py \
    --action meeting-id \
    --subject "<event.subject>" \
    --start "<event.start.dateTime>"
  ```
  Output: canonical `<meeting_id>` (e.g. `2026-05-08-sprint-planning`)

- [ ] **Idempotency check**
  ```bash
  uv run .agents/skills/kb-collect/collect.py \
    --state-file raw/.collect-state.json \
    --provider teams \
    --action check-id \
    --meeting-id <meeting_id>
  ```
  Output `SEEN` → skip this event, continue to next.
  Output `NEW` → proceed.

- [ ] **Fetch full event details**

  Call `mcp__claude_ai_Microsoft_365__read_resource` with `uri` = event's `uri` from search results.

  Extract from response:
  - `subject` → meeting title
  - `start.dateTime` → start ISO datetime (UTC)
  - `end.dateTime` → end ISO datetime (UTC)
  - `organizer.name` and `organizer.address` → display name + email
  - `attendees[]` where `type != "resource"` → human participants (exclude meeting room mailboxes)
  - `meetingTranscriptUrl` → transcript URI (may be absent)
  - `webLink` → original Outlook URL

- [ ] **Fetch transcript (if meetingTranscriptUrl present)**

  Call `mcp__claude_ai_Microsoft_365__read_resource` with `uri` = `meetingTranscriptUrl`.

  - Response has content → `has_transcript = true`, capture transcript text
  - Response is `NOT_FOUND` error → `has_transcript = false`, transcript_text = empty
  - `meetingTranscriptUrl` was absent in event detail → `has_transcript = false`, transcript_text = empty

- [ ] **Quality gate**

  Count attendees excluding resource/room mailboxes: `attendee_count` = number of attendees where `type != "resource"`.
  Count description words with the HTML-stripping helper — **never** raw `body.content.split()` (every Teams body contains a several-hundred-word HTML join block, which would make the <20-word branch unreachable):
  ```python
  description_word_count = meeting_description_word_count(
      event_detail.get("body", {}).get("content", "") or ""
  )
  ```

  Call:
  ```python
  is_low_quality_meeting(
      has_transcript=has_transcript,
      attendee_count=attendee_count,
      description_word_count=description_word_count,
  )
  ```
  (Python helpers in `.agents/skills/kb-collect/collect.py`)

  If `True` → record in state as SEEN (prevents re-evaluation on next sync):
  ```bash
  uv run .agents/skills/kb-collect/collect.py \
    --state-file raw/.collect-state.json \
    --provider teams \
    --action record \
    --meeting-id <meeting_id> \
    --cursor <start.dateTime>
  ```
  Print `SKIPPED (low-quality): <meeting_id>`. Continue to next event.

  If `False` → proceed to inbox lock.

- [ ] **Check filename collision**
  ```bash
  test -e "raw/inbox/meetings/<meeting_id>.md" && echo COLLIDE || echo OK
  ```
  On COLLIDE: if the existing file has `has_transcript: true` (e.g. a richer MeetGeek
  copy at the same slug), **skip the Teams write entirely** — record state and continue
  to the next event. Otherwise append `-teams` to the filename. Never overwrite.

- [ ] **Acquire inbox lock**
  ```bash
  uv run .agents/skills/kb-ingest/lock.py \
    --lock-file .kb/.inbox.lock --action acquire --timeout 5
  ```
  Expected: `ACQUIRED`. On `LOCK_TIMEOUT`: skip this event, do not proceed.

- [ ] **Write normalised file to raw/inbox/meetings/**

  Compute:
  - `captured_at` = `start.dateTime[:10]` (YYYY-MM-DD, UTC)
  - `start_time` = `start.dateTime[11:16]` (HH:MM)
  - `end_time` = `end.dateTime[11:16]`
  - Participant list = attendees where `type != "resource"` (both name and address)

  Write `raw/inbox/meetings/<meeting_id>.md` with this exact structure:

  ```markdown
  ---
  source: teams-calendar
  provider: teams
  captured_at: <YYYY-MM-DD>
  channel: meetings
  meeting_id: <meeting_id>
  participants:
    - <email1>
    - <email2>
  organizer: <organizer_email>
  start: "<start.dateTime>"
  end: "<end.dateTime>"
  original_ref: "<event.webLink>"
  has_transcript: <true|false>
  ---

  # <subject>

  **Date:** <YYYY-MM-DD> <HH:MM>–<HH:MM> UTC
  **Organizer:** <organizer_name> (<organizer_email>)
  **Attendees:** <comma-separated attendee display names, excluding rooms>

  ## Transcript

  <transcript_text if has_transcript is true>
  <"(no transcript available — transcription was not enabled for this meeting)" if has_transcript is false>
  ```

- [ ] **Release inbox lock**
  ```bash
  uv run .agents/skills/kb-ingest/lock.py \
    --lock-file .kb/.inbox.lock --action release
  ```
  Expected: `RELEASED`.

- [ ] **Record in state**
  ```bash
  uv run .agents/skills/kb-collect/collect.py \
    --state-file raw/.collect-state.json \
    --provider teams \
    --action record \
    --meeting-id <meeting_id> \
    --cursor <start.dateTime>
  ```
  Expected: `RECORDED`.

--- end of per-meeting block ---
