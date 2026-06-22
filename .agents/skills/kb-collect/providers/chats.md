# Provider — chats

The orchestrator runs `phases/config-check.md` before this checklist and `phases/report-log.md` after.

Collects manually exported Teams or Slack chat batches into `raw/inbox/chats/`. Idempotency by sha256 of file CONTENTS — re-collecting the same export (even after rename) is a no-op.

**Inputs:** one or more local markdown export paths supplied by the user, either inline (`/kb-collect chats <path1> <path2>`) or via a queue file `~/.config/work-brain/chats-queue.txt` (one absolute path per line, `#` comments allowed).

Do NOT call live Teams or Slack APIs in this phase — manual export only.

### Phase 1 — Check provider config (provider-specific step)

- [ ] **Resolve file list**
  - If user passed paths inline: use those.
  - Else, read `~/.config/work-brain/chats-queue.txt`, ignore empty lines and `#` comments. If file absent or empty: report `no files to collect` and stop.

### Phase 2 — Per-file processing loop

Repeat for each file path.

- [ ] **Validate file exists**
  ```bash
  test -f "<path>" || { echo "ERROR: not found: <path>"; continue; }
  ```

- [ ] **Compute chat key**
  ```bash
  uv run .agents/skills/kb-collect/collect.py \
    --action chat-key --path "<path>"
  ```
  Capture the 16-hex string as `<chat_key>`.

- [ ] **Idempotency check**
  ```bash
  uv run .agents/skills/kb-collect/collect.py \
    --state-file raw/.collect-state.json \
    --provider chats \
    --action check-id --meeting-id "<chat_key>"
  ```
  Output `SEEN` → skip. Output `NEW` → proceed.

- [ ] **Collect required metadata** from the user or a companion sidecar file:
  - `provider` — `teams`, `slack`, or `synthetic`
  - `captured_at` — ISO date string (YYYY-MM-DD) of the export or chat date
  - `channel` — name of the chat channel or conversation (e.g. `team-standup`, `general`)
  - `title` — human-readable title for the chat batch
  - `participants` — list of participant display names or emails
  - `original_ref` — optional source URL or export path

- [ ] **Compute filename slug**
  ```bash
  uv run .agents/skills/kb-collect/collect.py \
    --action chat-slug --date "<captured_at>" --title "<title>"
  ```
  Capture as `<slug>` (e.g. `2026-05-26-team-standup-chat`).

- [ ] **Check filename collision**
  ```bash
  test -e "raw/inbox/chats/<slug>.md" && echo COLLIDE || echo OK
  ```
  On COLLIDE: append `-<chat_key first 6 hex>` to slug for uniqueness.

- [ ] **Acquire inbox lock**
  ```bash
  uv run .agents/skills/kb-ingest/lock.py \
    --lock-file .kb/.inbox.lock --action acquire --timeout 5
  ```
  Expected: `ACQUIRED`. On `LOCK_TIMEOUT`: skip this file, report error.

- [ ] **Ensure inbox dir, write raw chat file**
  ```bash
  mkdir -p raw/inbox/chats
  ```
  Write `raw/inbox/chats/<slug>.md`:
  ```markdown
  ---
  source: chat
  provider: <teams|slack|synthetic>
  captured_at: <YYYY-MM-DD>
  channel: <channel-name>
  title: "<title>"
  chat_key: <chat_key>
  participants:
    - <participant 1>
    - <participant 2>
  original_ref: <source URL or export path>
  ---

  # <title>

  <chat messages in chronological order>
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
    --provider chats \
    --action record --meeting-id "<chat_key>"
  ```
  Expected: `RECORDED`.

### Notes

- Idempotency on file CONTENTS — renaming source exports does NOT trigger re-collect.
- `original_ref` stores the export path or source URL at collect time. Raw archive at `raw/chats/<YYYY>/<MM>/` is the durable copy after ingest.
- Live Teams or Slack API collection is deferred. Once the manual export path has passing tests and a successful smoke, extend this checklist with a live provider sub-section.
- Queue file format (one path per line, optional `#` comment):
  ```
  /path/to/teams-export-2026-05-26.md
  # below: slack export to process later
  /path/to/slack-general-2026-05-25.md
  ```
- `thread_slug` strips `[EXTERNAL]`, `Re:`, `Fwd:` etc. so reply chains collapse to a single slug; raw subject preserved in body.
