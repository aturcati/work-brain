# Provider — emails-outlook

The orchestrator runs `phases/config-check.md` before this checklist and `phases/report-log.md` after.

## API reference

**Outlook connector tools used:** `list_mail_folders`, `list_messages`, `fetch_message` only when full body is missing from list results.

**Tool-availability fallback (claude.ai M365 MCP):** when only `mcp__claude_ai_Microsoft_365__outlook_email_search` + `read_resource` are available (no `list_mail_folders`/`list_messages`/`fetch_message`):
- Folder enumeration → skip; search the common folders directly via `folderName` (`Inbox`, `Sent Items`, `Archive`).
- Message listing → `outlook_email_search` with `folderName` + `afterDateTime=<folder cursor>` + `order: oldest`; max **25 results/page**, paginate via `nextOffset`.
- `afterDateTime` is **inclusive** — the cursor-boundary message reappears every run; dedupe via the conversation-key SEEN check, do not treat it as new.
- Search results carry **no `conversationId`** — call `read_resource` on `mail:///messages/<id>` for any message that passes the domain + quality filters; the full message has `conversationId`, full body, and recipients.

Folder cursors are per-folder path keyed under `outlook.folder_cursors` in `raw/.collect-state.json`. One global cursor (`outlook.cursor`) is preserved for legacy compatibility.

Graph-shaped messages use `from.emailAddress`; Codex connector-shaped messages use `sender.emailAddress` — `coalesce_messages()` handles both.

---

Pulls Outlook messages from selected folders, keeps messages sent by `@acme.com`, groups by `conversationId` into threads, and writes one normalised markdown file per thread to `raw/inbox/emails/`. Backfill mode scans all selected folders; sync mode resumes from a per-folder cursor.

### Phase 1 — Check provider config and state (provider-specific steps)

- [ ] **Read state**
  ```bash
  cat raw/.collect-state.json
  ```
  Existing `outlook.seen_ids` remains the conversation-level dedup list. New sync runs also use `outlook.folder_cursors`, keyed by folder path.

### Phase 2 — Select Outlook folders

- [ ] **List mail folders**

  Call the Outlook connector `list_mail_folders` with:
  - `include_hidden_folders`: `false`
  - `top`: `500`

- [ ] **Filter folders**

  In-process: call `select_outlook_email_folders(folders)`.

  Include:
  - Inbox
  - Archive
  - Sent Items
  - all normal/custom folders

  Exclude:
  - Drafts
  - Junk Email
  - Deleted Items
  - hidden folders
  - any folder nested under an excluded folder

### Phase 3 — Fetch matching messages folder by folder

For each selected folder:

- [ ] **Get folder cursor**

  Backfill mode: ignore missing cursors and start from the oldest available messages in the folder.

  Sync mode: read the cursor with:
  ```python
  get_folder_cursor(state, "outlook", folder_path)
  ```
  Output `NONE` → no lower date bound for that folder. Output ISO datetime → list messages newer than that timestamp.

- [ ] **List messages with pagination**

  Call the Outlook connector `list_messages` with:
  - `folder_id`: selected folder id
  - `order_by`: `receivedDateTime asc`
  - `filter`: `receivedDateTime gt <folder_cursor>` only when a folder cursor exists
  - `top`: `100`
  - `skip`: `next_from_index` while `has_more=true`

  Each result should include at minimum: message id, subject, `conversationId` or fallback id, `receivedDateTime`, sender/from address, recipients, body or preview, and web link.

- [ ] **Filter sender domain**

  In-process: keep only messages where:
  ```python
  sender_matches_domain(message, "acme.com")
  ```

  This intentionally keeps Sent messages from the user's Acme account, including threads with external recipients. Those external participants are preserved as part of the conversation context.

- [ ] **Value-recovery for inbound-external threads** (before discarding domain-filtered mail)

  A message that fails the sender-domain filter (inbound-only external, no own-domain sender in-window) is **not** automatically noise. Before dropping, check whether its sender **domain** or its `_strip_email_prefixes(subject)` matches an existing `wiki/sources/` slug or a canonical entity (a known vendor, sales contact, or tracked thread). If it matches, `read_resource`/`fetch_message` the body and decide by **content value**, not by the mechanical filter:
  - Vendor counter-offer / status update on a tracked Decision or Source → **keep** (write a new Source `related:` to the existing one, or a `## Re-ingest` if same `conversationId`).
  - Genuine automated/marketing noise → drop.

  Apply the same value judgement to threads the quality gate would *keep* but that carry no KB value (e.g. one-off internal talk/event invites that would only spawn orphan stubs) — skip and don't record, so they stay re-evaluable. Surface every such keep/drop decision in the run summary; a silent drop on the mechanical filter is a capture gap (e.g. a vendor Enterprise counter-offer on a tracked non-renewal Decision).

- [ ] **Fetch full body only when needed**

  If the list result does not include usable body text, call `fetch_message` for that message id and attach the full body as `body_text`.

  On `NOT_FOUND`: skip that message, continue.

- [ ] **Record folder cursor after successful folder processing**

  After all selected messages from the folder are processed and raw files are written, record the highest `receivedDateTime` seen in that folder:
  ```python
  state = record_folder_cursor(state, "outlook", folder_path, latest_received)
  ```

### Phase 4 — Coalesce + per-thread loop

- [ ] **Group messages into threads**

  In-process: call `coalesce_messages(messages)` (Python helper from Task 1) to group by `conversationId` and sort chronologically. Each thread dict has: `conversation_id`, `subject`, `first_received`, `last_received`, `message_count`, `participants` (email list), `messages_sorted`.

Repeat for each thread:

- [ ] **Quality gate**

  Call:
  ```python
  email_quality_tier(thread)
  ```
  (Python helper in `.agents/skills/kb-collect/collect.py`)

  - Returns `"drop"` → skip thread entirely. Do NOT record in `seen_ids` (allows re-evaluation if filter rules change). Print `DROPPED (quality): <subject>`.
  - Returns `"triage"` → call the LLM with this prompt:
    ```
    Is this a real human professional email conversation or automated/notification content?
    Subject: <thread["subject"]>
    Body preview (first 200 chars): <thread["messages_sorted"][0].get("body_text", "")[:200]>
    Answer only: REAL or NOISE
    ```
    `NOISE` → treat as drop (not recorded in `seen_ids`).
    `REAL` → proceed as keep.
  - Returns `"keep"` → proceed.

- [ ] **Check if MeetGeek summary**

  For threads that passed the quality gate, call:
  ```python
  is_meetgeek_summary(thread)
  ```
  (Python helper in `.agents/skills/kb-collect/collect.py`)

  If `True` → set `meetgeek_summary: true` in the raw file frontmatter.
  If `False` → no change; frontmatter has no `meetgeek_summary` key.

- [ ] **Compute conversation_key**
  ```bash
  uv run .agents/skills/kb-collect/collect.py \
    --action conversation-key --conversation-id "<conversation_id>"
  ```

- [ ] **Idempotency check** (pass `last_received` so grown threads are detected)
  ```bash
  uv run .agents/skills/kb-collect/collect.py \
    --state-file raw/.collect-state.json \
    --provider outlook \
    --action check-id --meeting-id "<conv_key>" \
    --last-received "<thread.last_received>"
  ```
  Output `SEEN` → skip. Output `NEW` → proceed. Output `GROWN` → the conversation
  gained replies since last collection: proceed, but include ONLY the new messages
  (`receivedDateTime > stored thread_last`) in the file body, and use the grown-thread
  filename below.

  Legacy caveat: conversations recorded before `thread_last` existed always report
  `SEEN` — growth detection starts after their next `record` writes a baseline.

- [ ] **Compute thread slug**
  ```bash
  uv run .agents/skills/kb-collect/collect.py \
    --action thread-slug --first-received "<first_received>" --subject "<subject>"
  ```
  **GROWN thread:** append an update suffix to the slug: `<slug>-u<YYYYMMDD>` (date
  from the new `last_received`). The original raw file is immutable; the update lands
  as a sibling file. `/kb-ingest` strips the `-u<YYYYMMDD>` suffix when computing the
  Source slug, so the update appends a `## Re-ingest` section to the existing Source
  page instead of creating a duplicate.

- [ ] **Check filename collision**
  ```bash
  test -e "raw/inbox/emails/<slug>.md" && echo COLLIDE || echo OK
  ```
  On COLLIDE: append `-<conv_key first 6 hex>`.

- [ ] **Acquire inbox lock**
  ```bash
  uv run .agents/skills/kb-ingest/lock.py \
    --lock-file .kb/.inbox.lock --action acquire --timeout 5
  ```

- [ ] **Write raw thread file**

  Write `raw/inbox/emails/<slug>.md`:
  ```markdown
  ---
  source: emails
  provider: outlook
  captured_at: <YYYY-MM-DD today UTC>
  channel: emails
  conversation_id: <conversation_id>
  conversation_key: <conv_key>
  subject: "<subject>"
  first_received: <first_received>
  last_received: <last_received>
  message_count: <message_count>
  participants:
    - <participant_email_1>
    - <participant_email_2>
  original_ref: "<webLink of last message>"
  ---

  # <subject>

  **Thread:** <first_received> → <last_received> · <message_count> message(s)
  **Participants:** <comma-separated display names>

  ## Messages

  ### <message.receivedDateTime> · <message.from.name> (<message.from.address>)
  **To:** <comma-separated to display names>
  **Cc:** <comma-separated cc display names>     <!-- omit if empty -->

  <message.body_text>

  ---

  ### <next message ...>
  ...
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
    --provider outlook \
    --action record --meeting-id "<conv_key>" --cursor "<last_received>" \
    --last-received "<last_received>"
  ```
  This preserves the legacy global `outlook.cursor` for compatibility. Folder-specific sync uses `outlook.folder_cursors`. `--last-received` writes the per-conversation baseline in `outlook.thread_last` that makes future `GROWN` detection work — never omit it.

### Phase 5 — Save state, summary, and log

- [ ] **Persist folder cursors**

  Save the updated `raw/.collect-state.json` after all thread records and folder cursor updates are complete. Expected state shape:
  ```json
  {
    "outlook": {
      "seen_ids": ["<conv_key>"],
      "cursor": "<latest thread last_received, legacy compatibility>",
      "folder_cursors": {
        "Inbox": "<latest received in Inbox>",
        "Archive": "<latest received in Archive>",
        "Sent Items": "<latest received in Sent Items>",
        "Projects/AI": "<latest received in custom folder>"
      },
      "last_seen_at": "<write timestamp>"
    }
  }
  ```

- [ ] **Print summary** — `emails: <N> threads collected, <M> skipped (seen), <F> folders scanned, <K> errors`.

- [ ] **Append log entry**
  ```
  ## [YYYY-MM-DD HH:MM] kb-collect | emails: N thread(s) collected from F folder(s), sender domain acme.com
  ```

### Notes

- Backfill mode is the recommended first run for this mailbox. Sync mode should start only after the backfill output has been reviewed.
- Idempotency uses `conversationId` (Microsoft's stable GUID). Re-collecting a thread that grew with new replies is currently a no-op — future `--force` flag (or a per-conversation `last_received` compare) will allow re-collect. **Until then this is a known capture gap**: when a SEEN conversation visibly has newer messages than its recorded cursor, say so in the run summary so the replies aren't silently lost (e.g. the 2026-06 AI-guidelines review replies).
- Folder cursors are per folder path because one global Outlook cursor can miss older unprocessed messages in another folder.
- Connector compatibility: if the available Outlook connector omits `conversationId`, `coalesce_messages()` falls back to `conversation_id`, then message `id`. The message-id fallback collects a one-message thread instead of dropping the message.
- Connector compatibility: `coalesce_messages()` accepts Graph-shaped `from.emailAddress` and Codex connector-shaped `sender.emailAddress` when building participant lists.
- `original_ref` stores `webLink` of latest message — opens conversation in Outlook web.
- Drafts, Deleted Items, Junk Email, and hidden folders are out of scope.
