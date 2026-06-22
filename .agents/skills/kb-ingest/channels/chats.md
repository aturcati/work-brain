# Channel handler — chats

> Phase 2 for the chats channel. The orchestrator runs the shared phases (lock-dedup, edge-extraction, move-state-cleanup, reindex-log) around this.

### Phase 2 — Chats handler

- [ ] **Read frontmatter and body**

  Extract from frontmatter:
  - `captured_at` → date string (YYYY-MM-DD)
  - `provider` → `teams`, `slack`, or `synthetic`
  - `channel` → chat channel or conversation name
  - `title` → human-readable title
  - `participants[]` → list of display names or emails
  - `chat_key` → 16-hex content hash
  - `original_ref` → optional source URL or export path

  Body: chat messages in chronological order.

- [ ] **Derive identifiers**

  Use filename stem as `<slug>`. Compute:
  - `<captured-date>` = first 10 characters of `captured_at`.
  - `<archive-path>` = `raw/chats/<YYYY>/<MM>/<file>.md` (YYYY/MM from `<captured-date>`).
  - `<txn-id>` = `chats-<slug>` (e.g. `chats-2026-05-26-team-standup-chat`).

- [ ] **Create staging directories**
  ```bash
  txn_id=chats-<slug>
  mkdir -p .kb-staging/<txn_id>/wiki/sources
  mkdir -p .kb-staging/<txn_id>/wiki/tofile
  mkdir -p .kb-staging/<txn_id>/wiki/decisions
  ```

- [ ] **Check if Source page already exists**
  ```bash
  test -e "wiki/sources/<slug>.md" && echo EXISTS || echo NEW
  ```
  - EXISTS: append `## Re-ingest <captured-date>` divider + fresh summary to existing page; extend `sources:`. Skip new-page write below.
  - NEW: proceed.

- [ ] **Write staged Source page**

  Write `.kb-staging/<txn_id>/wiki/sources/<slug>.md`:
  ```markdown
  ---
  type: Source
  slug: <slug>
  created: <captured-date>
  modified: <captured-date>
  status: active
  channel: chats
  provider: <provider>
  captured_at: <captured_at>
  path: <archive-path>
  sources: ["[[<archive-path-without-.md-extension>]]"]
  tags: []
  ---

  ## Summary

  <1-3 paragraph LLM summary of the chat batch. Embed wikilinks [[wiki/<type>/<slug>]] for resolved entities. For unresolved entities, link to [[wiki/tofile/<slug>]] — promotion via /kb-link.>

  ## Original reference

  - **Title:** <title>
  - **Provider:** <provider>
  - **Channel:** <channel>
  - **Captured at:** <captured_at>
  - **Participants:** <comma-separated wikilinks or plain names>
  - **Raw archive:** [[raw/chats/<YYYY>/<MM>/<file>]]
  ```
  If `original_ref` present in raw frontmatter, also add:
  ```markdown
  - **Original ref:** <original_ref>
  ```
  (`original_ref` lives in the body — schema-lint rejects unknown frontmatter keys, per Phase H finding.)

- [ ] **Compute Person slugs from participants**

  **Skip non-person mailboxes first** — never create Person stubs for them (they false-qualify for `/kb-link` promotion later):
  - any local part starting with `meetingroom`
  - group/shared mailboxes: `software@`, `applicants@`, `team@`, `office@`, `ai@`, `info@`

  For each remaining participant (display name or email):
  - If email address: `slug = email.split("@")[0].replace(".", "-")`
  - If display name only: `slug = kebab-case of name`

  Resolve against `wiki/people/<slug>.md`:
  - Exists → resolved. Update: extend `sources:`, update `modified:`, append bullet under `## Chat mentions` (create section if absent):
    ```
    - <captured-date>: participated in "<title>" chat (from [[wiki/sources/<slug>]])
    ```
  - Missing → stub at `.kb-staging/<txn_id>/wiki/tofile/<slug>.md`:
    ```markdown
    ---
    type: Person
    slug: <slug>
    aliases: ["<display name>"]
    created: <captured-date>
    modified: <captured-date>
    status: active
    confidence: low
    sources: ["[[<archive-path-without-.md-extension>]]"]
    ---
    <!-- stub: promote via /kb-link when ≥1 inbound wiki link + ≥1 raw mention -->
    ```

- [ ] **Extract additional Topic / Project / Org mentions from body**

  Case-sensitive entity identification. For each:
  - Resolved page exists → planned update (extend `sources:`, append bullet under `## Chat mentions`).
  - Missing → stub at `.kb-staging/<txn_id>/wiki/tofile/<slug>.md` with matching `type:`.

- [ ] **Decision detection**

  Scan body for trigger phrases: `"Decision:"`, `"decided to"`, `"agreed to"`, `"going with"`, `"we will"`, `"we agreed"`.
  If found, write Decision stub to `.kb-staging/<txn_id>/wiki/decisions/<captured-date>-<slugified-decision>.md`:
  ```markdown
  ---
  type: Decision
  slug: <captured-date>-<slugified-decision>
  created: <captured-date>
  modified: <captured-date>
  status: active
  confidence: low
  sources: ["[[<archive-path-without-.md-extension>]]"]
  ---
  <!-- Proposed from chat batch <captured-date>. Review and promote via /kb-graph promote. -->

  Decision language detected: "<quoted decision sentence>"
  ```

- [ ] **Review staged diff**
  ```bash
  diff -ru wiki/ .kb-staging/chats-<slug>/wiki/ 2>/dev/null || true
  ```

- [ ] **Apply staged files**
  ```bash
  cp -r .kb-staging/chats-<slug>/wiki/. wiki/
  rm -rf .kb-staging/chats-<slug>/
  ```
  On error before this step: drop staging, quarantine source:
  ```bash
  rm -rf .kb-staging/chats-<slug>/
  mkdir -p raw/quarantine
  cp raw/inbox/chats/<file>.md raw/quarantine/<file>.md
  echo "kb-ingest chats error: <description>" > raw/quarantine/<file>.error.md
  ```

- [ ] **Update wiki/index.md**

  Add `- [[wiki/sources/<slug>]]` under `## Sources`. New Person/Topic stubs under `## tofile`. New Decisions under `## Decisions` (only canonical Decision pages, not stubs).

## Channel-specific steps

- [ ] **Scan chat inbox**
  ```bash
  ls raw/inbox/chats/*.md 2>/dev/null || echo "EMPTY"
  ```
  If EMPTY: release lock and stop.

- [ ] **Append to wiki/log.md**
  ```
  ## [YYYY-MM-DD HH:MM] kb-ingest | chats: 1 file (<slug>), <P> person stubs, <U> updated, <N> edge proposals
  ```

## Edge hints

- [ ] **Propose edges** using closed-vocab predicates.

  Patterns (verify each against `.kb/schema.cypher` before writing):
  - Topic mention: `(<topic-slug>, cites, <slug>, conf, "evidence")` — `cites` from Topic → Source only.
  - Decision created: `(<slug>, decided, <decision-slug>, conf, "evidence")` — `decided` FROM Source TO Decision.
  - Project mention: `(<project-slug>, related, <slug>, conf, "evidence")`.
  - Person/Org mentions: skip explicit edges — rely on body wikilinks → projection-time `mentions` harvest.

  Append to `wiki/_inbox/edges.md`:
  ```markdown
  ## <YYYY-MM-DD HH:MM> · raw/inbox/chats/<file>.md
  - (<topic-slug>, cites, <slug>, 0.80, "<evidence quote>")
  ```
  Count edges (N).
