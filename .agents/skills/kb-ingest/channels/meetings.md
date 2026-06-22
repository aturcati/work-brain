# Channel handler — meetings

> Phase 2 for the meetings channel. The orchestrator runs the shared phases (lock-dedup, edge-extraction, move-state-cleanup, reindex-log) around this.

> **Processing order (invariant):** process plain meeting files BEFORE `source: meetgeek-api` files with a `-<6hex>` slug suffix, so the base Meeting page exists when `match.py` looks for it. Do NOT rely on glob order — it is exactly backwards: `…-3e5f75.md` sorts before `…april.md` because `-` (0x2D) < `.` (0x2E), and processing the MeetGeek file first creates a duplicate page.

### Phase 2 — Meetings handler

- [ ] **Read file frontmatter and body**

  Read `raw/inbox/meetings/<file>.md`. Extract from frontmatter:
  - `meeting_id` → canonical meeting slug (e.g. `2026-05-08-sprint-planning`)
  - `participants` → list of email addresses (already excludes room mailboxes)
  - `organizer` → organizer email
  - `captured_at` → YYYY-MM-DD date string
  - `has_transcript` → true/false

  From body:
  - Attendee display names from `**Attendees:**` line
  - Transcript text from `## Transcript` section

- [ ] **Detect MeetGeek source**

  Check: `fm.get("source") == "meetgeek-api"`.

  If True (MeetGeek file):
  1. `slug` = `fm["meeting_id"]` (already in frontmatter).
  2. Call `find_matching_meeting(slug, Path("wiki/meetings/"))` (`.agents/skills/kb-ingest/match.py`).
  3. **Match found** → merge path: do NOT create a new Meeting page. Instead, on the existing Meeting page:
     - Append `## Transcript (from MeetGeek, <captured_at>)` section with the full transcript body.
     - Add the raw path to `sources:` frontmatter if absent.
     - Run decision detection on the transcript text (trigger phrases: `"decided to"`, `"agreed to"`, `"going with"`, `"we will"`, `"we agreed"`). Create Decision stubs if triggered.
     - Write changes via `.kb-staging/<txn-id>/` atomic staging.
  4. **No match** → create path: proceed with the standard meetings handler flow to create a new Meeting wiki page (the page will have full transcript since `has_transcript: true`).

  If `source` is not `meetgeek-api` → skip this step and proceed normally.

- [ ] **Compute person slugs from participants**

  **Skip non-person mailboxes first** — never create Person stubs or `attended:` entries for them (they false-qualify for `/kb-link` promotion later):
  - any local part starting with `meetingroom`
  - group/shared mailboxes: `software@`, `applicants@`, `team@`, `office@`, `ai@`, `info@`
  - tenant accounts like `*@*.onmicrosoft.com`

  For each remaining email in `participants`:
  ```
  slug = email.split("@")[0].replace(".", "-")
  ```
  Examples:
  - `alice.smith@example.com` → `alice-smith`
  - `bob@example.com` → `bob`
  - `carol.jones@example.com` → `carol-jones`

  Map each slug to its display name from the `**Attendees:**` line (or use email local part if uncertain).

- [ ] **Resolve person pages**

  For each participant slug: check `wiki/people/<slug>.md`.
  - Exists → **resolved**: update page in staging (add raw path to `sources:` if not present; update `modified:` to `captured_at`)
  - Missing → **stub**: create `wiki/tofile/<slug>.md`:
    ```markdown
    ---
    type: Person
    slug: <slug>
    aliases: ["<display_name>"]
    created: <captured_at>
    modified: <captured_at>
    status: active
    confidence: low
    sources: ["[[raw/meetings/<YYYY>/<MM>/<file>.md]]"]
    ---
    <!-- stub: promote via /kb-link when ≥1 inbound wiki link + ≥1 raw mention -->
    ```

- [ ] **Check for existing meeting page**

  Check `wiki/meetings/<meeting_id>.md`.
  - **Absent** → create full page (follow new page steps below).
  - **Present** → merge: write the updated meeting page to `.kb-staging/<txn-id>/wiki/meetings/<meeting_id>.md` with these changes: add raw path to `sources:` if absent; add new person slugs to `attended:` if not present; if `has_transcript: true` and body has new content, append `## Transcript update (<captured_at>)` section. Also run decision detection on any newly appended transcript text — if trigger phrases found, create decision stub(s) in staging and add their slugs to `decided:` list.

- [ ] **Create staging directory**

  Choose `txn-id = <YYYYMMDD-HHMM>`.
  ```bash
  mkdir -p .kb-staging/<txn-id>/wiki/meetings
  mkdir -p .kb-staging/<txn-id>/wiki/tofile
  mkdir -p .kb-staging/<txn-id>/wiki/people   # only if resolved persons exist
  mkdir -p .kb-staging/<txn-id>/wiki/decisions  # only if decision stubs needed
  ```

- [ ] **Write staged meeting page** (new page case)

  Write `.kb-staging/<txn-id>/wiki/meetings/<meeting_id>.md`:

  ```markdown
  ---
  type: Meeting
  slug: <meeting_id>
  date: <captured_at>
  status: active
  tags: []
  confidence: medium
  created: <captured_at>
  modified: <captured_at>
  sources: ["[[raw/meetings/<YYYY>/<MM>/<file>.md]]"]
  attended:
    - "[[wiki/people/<slug1>]]"
    - "[[wiki/tofile/<slug2>]]"
  decided: []
  ---

  <One-line summary of meeting purpose inferred from title and attendee context.>

  ## Attendees

  <Comma-separated display names of non-room participants.>

  ## Transcript

  <If has_transcript is false: "(no transcript available — transcription was not enabled for this meeting)".>
  <If has_transcript is true and the transcript is SHORT (< ~1,500 tokens): inline it here.>
  <If has_transcript is true and LONGER: do NOT inline. Write it to a staged
   `wiki/artifacts/<meeting_id>-transcript.md` (type: Artifact, tags: [transcript],
   sources: ["[[wiki/meetings/<meeting_id>]]"]) and put here only:
   "Full transcript: [[wiki/artifacts/<meeting_id>-transcript]]".
   Keep any MeetGeek summary / action items ON the meeting page.
   Inline long transcripts trip the /kb-lint bloat check and force an immediate /kb-refactor.>
  ```

  **Decision detection**: scan transcript/body text for trigger phrases: `"decided to"`, `"agreed to"`, `"going with"`, `"we will"`, `"we agreed"`.

  Trigger phrases only NOMINATE candidate sentences — create a stub **only if** the sentence states an actionable, org-level decision (a who + a what, e.g. tool adopted, plan approved, date committed). Conversational matches ("we will have a good base", a candidate's "I decided to…" anecdote) are noise: skip them and note "trigger phrases conversational only" in the log. The vault previously accumulated 18 orphan decision stubs from literal matching.

  **Speaker guard:** never create a Decision from a sentence whose transcript speaker is a room/mailbox label (`Meeting Room*`, `meetingroom*`, group mailboxes) — diarization attributes room audio to these labels and the resulting stubs are always junk (source of the 18 orphans deleted 2026-06-11). A Decision slug must reference a real person speaker or omit the speaker entirely.

  If a real decision is found: create decision stub at `.kb-staging/<txn-id>/wiki/decisions/<captured_at>-<slugified-decision>.md`:
  ```markdown
  ---
  type: Decision
  slug: <captured_at>-<slugified-decision>
  created: <captured_at>
  modified: <captured_at>
  status: active
  confidence: low
  sources: ["[[raw/meetings/<YYYY>/<MM>/<file>.md]]"]
  ---
  <!-- Proposed from meeting <meeting_id>. Review and promote via /kb-graph promote. -->

  Decision language detected: "<quoted decision sentence from transcript>"
  ```

  If decision stub created: replace `decided: []` with `decided: ["[[wiki/decisions/<decision-slug>]]"]` in meeting page frontmatter.

  **Validate invariant:** a Decision's `sources:` needs ≥1 `wiki/` wikilink (raw paths alone fail `/kb-graph validate`). Include the Meeting page itself: `sources: ["[[wiki/meetings/<meeting_id>]]", "[[raw/meetings/<YYYY>/<MM>/<file>.md]]"]`. The `decided:` backlink from the meeting also satisfies the `/kb-lint` orphan check.

- [ ] **Write staged person pages/stubs**

  Resolved persons: updated `wiki/people/<slug>.md` → `.kb-staging/<txn-id>/wiki/people/<slug>.md`.
  Unresolved: stubs → `.kb-staging/<txn-id>/wiki/tofile/<slug>.md`.

  **Provenance invariant:** in bulk/scripted generation, each stub's `sources:` must cite the SPECIFIC file that entity was observed in — never one shared constant for the whole batch (this exact mistake mis-sourced 2 stubs in the 2026-06-03 run and 191 paths historically).

- [ ] **Atomic rename staging → wiki**
  ```bash
  cp -r .kb-staging/<txn-id>/wiki/. wiki/
  rm -rf .kb-staging/<txn-id>/
  ```
  On any error before this step: drop staging, quarantine source:
  ```bash
  rm -rf .kb-staging/<txn-id>/
  mkdir -p raw/quarantine/
  cp raw/inbox/meetings/<file>.md raw/quarantine/<file>.md
  echo "kb-ingest meetings error: <description>" > raw/quarantine/<file>.error.md
  ```

- [ ] **Update wiki/index.md**

  Under `## Meetings`: **new page case only** — add `- [<meeting_id>](meetings/<meeting_id>.md) — <title>, <captured_at>`. Skip this if merging with an existing page (entry already present).
  Under `## People`: add entries for any new person stubs created (both new-page and merge cases).

## Edge hints

Key edge types for meetings:
- `(meeting_id, attended, person_slug, 0.95, "listed as meeting participant")`  — one per non-room attendee
- `(meeting_id, decided, decision_slug, 0.80, "<trigger phrase quoted>")` — only if decision stub was created
- `(meeting_id, mentions, topic_slug, confidence, "topic discussed in meeting")` — for named topics in transcript

Example:
```
- (2026-05-08-sprint-planning, attended, alice-smith, 0.95, "listed as meeting participant")
- (2026-05-08-sprint-planning, attended, carol-jones, 0.95, "listed as meeting participant")
```
