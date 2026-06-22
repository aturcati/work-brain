# Channel handler — emails

> Phase 2 for the emails channel. The orchestrator runs the shared phases (lock-dedup, edge-extraction, move-state-cleanup, reindex-log) around this.

### Phase 2 — Emails handler

- [ ] **Read frontmatter and body**

  Extract: `captured_at`, `subject`, `first_received`, `last_received`, `message_count`, `participants[]`, `original_ref`, `conversation_id`.
  Body: `## Messages` → chronological `###`-headed blocks.

- [ ] **Detect MeetGeek summary email**

  Check: `fm.get("meetgeek_summary") is True`.

  If True:
  1. Parse the raw email body for structured sections: `## Summary`, `## Transcript`, `## Action Items`. Extract each section's content.
  2. Compute slug from the email subject (after stripping "Meeting Summary:" prefix) + `first_received[:10]`:
     ```bash
     uv run .agents/skills/kb-collect/collect.py \
       --action meeting-id \
       --subject "<subject after stripping 'Meeting Summary:' prefix>" \
       --start "<first_received>"
     ```
  3. Call `find_matching_meeting(slug, Path("wiki/meetings/"))` (`.agents/skills/kb-ingest/match.py`).
  4. **Match found** → enrich existing Meeting page:
     - Append `## Transcript update (MeetGeek email, <captured_at>)` with transcript section content.
     - Append `## Action Items (<captured_at>)` with action items section content.
     - Add raw email path to `sources:` frontmatter.
     - Run decision detection on transcript content (trigger phrases: `"decided to"`, `"agreed to"`, `"going with"`, `"we will"`, `"we agreed"`). Create Decision stubs if triggered.
     - Write via `.kb-staging/<txn-id>/` atomic staging.
     - Create a Source page as normal so the email is still indexed.
  5. **No match** → create a Source page as normal (transcript content is preserved in the Source page body).

  If `meetgeek_summary` is False or absent → proceed with the standard emails handler flow.

- [ ] **Compute Source slug**

  Slug = filename stem, with any grown-thread update suffix `-u<YYYYMMDD>` stripped
  (e.g. `2026-05-08-draft-onboarding-doc-u20260610` → `2026-05-08-draft-onboarding-doc`).
  Update files therefore resolve to the EXISTING Source page and take the
  re-ingest path below.

- [ ] **Check existing Source page**

  ```bash
  test -e "wiki/sources/<slug>.md" && echo EXISTS || echo NEW
  ```
  EXISTS: append `## Re-ingest <captured_at>` divider + fresh summary; extend `sources:`. Skip new-page write.
  NEW: proceed.

- [ ] **Compute Person slugs from participants**

  **Skip non-person mailboxes first** — never create Person stubs for them (they false-qualify for `/kb-link` promotion later):
  - any local part starting with `meetingroom`
  - group/shared mailboxes: `software@`, `applicants@`, `team@`, `office@`, `ai@`, `info@`

  For each remaining email in `participants`:
  ```
  slug = email.split("@")[0].replace(".", "-")
  ```
  Resolve against `wiki/people/<slug>.md`; missing → stub at `wiki/tofile/<slug>.md`.

- [ ] **Extract additional Topic/Project/Org/Decision mentions from body**

  Case-sensitive identification. Resolve against `wiki/<type>/<slug>.md`; missing → stub.

- [ ] **Decision detection**

  Scan message bodies for trigger phrases: `"decided to"`, `"agreed to"`, `"going with"`, `"we will"`, `"we agreed"`. If found, write Decision stub:
  ```markdown
  ---
  type: Decision
  slug: <captured_at>-<slugified-decision>
  created: <captured_at>
  modified: <captured_at>
  status: active
  confidence: low
  sources: ["[[raw/emails/<YYYY>/<MM>/<file>.md]]"]
  ---
  <!-- Proposed from email thread <captured_at>. Review and promote via /kb-graph promote. -->

  Decision language detected in message from <from_email> at <received>: "<quoted sentence>"
  ```

- [ ] **Create staging directory**

  ```bash
  txn_id=$(date -u +%Y%m%d-%H%M)
  mkdir -p .kb-staging/<txn_id>/wiki/sources
  mkdir -p .kb-staging/<txn_id>/wiki/tofile
  mkdir -p .kb-staging/<txn_id>/wiki/decisions
  ```

- [ ] **Write staged Source page**

  Write `.kb-staging/<txn_id>/wiki/sources/<slug>.md`:
  ```markdown
  ---
  type: Source
  slug: <slug>
  created: <first_received[:10]>
  modified: <captured_at>
  status: active
  channel: emails
  provider: outlook
  captured_at: <captured_at>
  path: raw/emails/<YYYY>/<MM>/<file>
  sources: ["[[raw/emails/<YYYY>/<MM>/<file>.md]]"]
  tags: []
  ---

  ## Summary

  <1-3 paragraph LLM summary citing participants by wikilink, key topics, decisions. [[wiki/people/<slug>]] for resolved, [[wiki/tofile/<slug>]] for unresolved.>

  ## Original reference

  - **Subject:** <subject>
  - **Conversation:** <message_count> message(s), <first_received> → <last_received>
  - **Participants:** <comma-separated wikilinks>
  - **Raw archive:** [[raw/emails/<YYYY>/<MM>/<file>]]
  - **Outlook:** <original_ref>
  ```

  (`original_ref` in body, not frontmatter — schema-lint rejects unknown keys.)

- [ ] **Write staged Person stubs / updates**

  Stub (unresolved):
  ```markdown
  ---
  type: Person
  slug: <slug>
  aliases: ["<display name from email>"]
  created: <captured_at>
  modified: <captured_at>
  status: active
  confidence: low
  sources: ["[[raw/emails/<YYYY>/<MM>/<file>.md]]"]
  ---
  <!-- stub: promote via /kb-link when ≥1 inbound wiki link + ≥1 raw mention -->
  ```

  Resolved-update: extend `sources:`, update `modified:`, append bullet under `## Email mentions` (create if absent):
  ```
  - <first_received[:10]>: participated in "<subject>" (<message_count> msgs) (from [[wiki/sources/<slug>]])
  ```

- [ ] **Write staged Topic / Project / Org / Decision stubs and updates**

  Same pattern as clippings/docs. Stubs into `wiki/tofile/`. Resolved entity updates extend `sources:` and append bullet under `## Email mentions`.

- [ ] **Atomic rename staging → wiki**

  ```bash
  cp -r .kb-staging/<txn_id>/wiki/. wiki/
  rm -rf .kb-staging/<txn_id>/
  ```
  On error: drop staging, quarantine source.

- [ ] **Update wiki/index.md**

  Add `- [[wiki/sources/<slug>]]` under `## Sources`. New Person/Topic stubs under `## tofile`. New Decisions under `## Decisions`.

## Channel-specific steps

- [ ] **Move raw file** (use `first_received[:10]` as date)
  ```bash
  uv run .agents/skills/kb-ingest/move_file.py \
    --src raw/inbox/emails/<file>.md \
    --channel emails \
    --date <first_received[:10]>
  ```

- [ ] **Release lock**
  ```bash
  uv run .agents/skills/kb-ingest/lock.py \
    --lock-file .kb/.inbox.lock --action release
  ```

- [ ] **Append log entry**
  ```
  ## [YYYY-MM-DD HH:MM] kb-ingest | emails: 1 thread (<slug>), <P> person stubs, <U> updated, <N> edge proposals
  ```

## Edge hints

- [ ] **Propose edges** using closed-vocab predicates.

  Patterns:
  - Topic mention: `(<topic-slug>, cites, <thread-slug>, conf, "evidence")`.
  - Decision created: `(<thread-slug>, decided, <decision-slug>, conf, "evidence")` — `decided FROM Source TO Decision`.
  - Project mention: `(<project-slug>, related, <thread-slug>, conf, "evidence")` (fallback if `cites` not in schema for that pair).
  - Person/Org mentions: skip explicit edges, rely on body wikilinks → projection-time `mentions` harvest.

  Verify each proposal against `.kb/schema.cypher` before writing.

  Append to `wiki/_inbox/edges.md`:
  ```markdown
  ## <YYYY-MM-DD HH:MM> · raw/inbox/emails/<file>.md
  - (<topic-slug>, cites, <thread-slug>, 0.85, "<evidence quote>")
  ```
  Count edges (N).
