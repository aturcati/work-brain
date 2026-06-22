# Channel handler — docs

> Phase 2 for the docs channel. The orchestrator runs the shared phases (lock-dedup, edge-extraction, move-state-cleanup, reindex-log) around this.

### Phase 2 — Docs handler

- [ ] **Read file frontmatter and body**

  Extract: `captured_at`, `original_ref` (absolute path), `title`, `file_key`, `file_type`. Body: converted markdown.

- [ ] **Compute Source slug**

  Slug = filename stem. Use as `wiki/sources/<slug>.md` filename.

- [ ] **Check if Source page already exists**

  ```bash
  test -e "wiki/sources/<slug>.md" && echo EXISTS || echo NEW
  ```
  - EXISTS: append new `sources:` entry + `## Re-ingest <captured_at>` divider with fresh summary. Skip new-page step.
  - NEW: proceed.

- [ ] **Extract entity mentions from body**

  People / Orgs / Topics / Projects per journal/meetings/clippings pattern. Resolve against `wiki/<type>/<slug>.md`; missing → stub at `wiki/tofile/<slug>.md`.

- [ ] **Create staging directory**

  ```bash
  txn_id=$(date -u +%Y%m%d-%H%M)
  mkdir -p .kb-staging/<txn_id>/wiki/sources
  mkdir -p .kb-staging/<txn_id>/wiki/tofile
  ```

- [ ] **Write staged Source page**

  Write `.kb-staging/<txn_id>/wiki/sources/<slug>.md`:
  ```markdown
  ---
  type: Source
  slug: <slug>
  created: <captured_at>
  modified: <captured_at>
  status: active
  channel: docs
  provider: file
  captured_at: <captured_at>
  path: raw/docs/<YYYY>/<MM>/<file>
  sources: ["[[raw/docs/<YYYY>/<MM>/<file>.md]]"]
  tags: []
  ---

  ## Summary

  <1-3 paragraph LLM summary of the body. Embed wikilinks `[[wiki/<type>/<slug>]]` for resolved entities. Unresolved → `[[wiki/tofile/<slug>]]`.>

  ## Original reference

  - **File:** <original_ref>
  - **Type:** <file_type>
  - **Captured:** <captured_at>
  - **Raw archive:** [[raw/docs/<YYYY>/<MM>/<file>]]
  ```

  (`original_ref` lives in the body — schema-lint rejects unknown frontmatter keys, per Phase H finding.)

- [ ] **Write staged stubs** (unresolved entities)

  Same stub format with `sources: ["[[raw/docs/<YYYY>/<MM>/<file>.md]]"]`.

- [ ] **Write staged updates** (resolved entities)

  Extend `sources:`, update `modified:`, append bullet under `## Docs` (create if absent):
  ```
  - <captured_at>: <one-line summary> (from [[wiki/sources/<slug>]])
  ```

- [ ] **Atomic rename staging → wiki**
  ```bash
  cp -r .kb-staging/<txn_id>/wiki/. wiki/
  rm -rf .kb-staging/<txn_id>/
  ```
  On error: drop staging, quarantine.

- [ ] **Update wiki/index.md**

  Add `- [[wiki/sources/<slug>]]` under `## Sources`. New stubs under `## tofile`.

## Channel-specific steps

- [ ] **Release lock**
  ```bash
  uv run .agents/skills/kb-ingest/lock.py \
    --lock-file .kb/.inbox.lock --action release
  ```

- [ ] **Append log entry**
  ```
  ## [YYYY-MM-DD HH:MM] kb-ingest | docs: 1 file (<slug>), <S> stubs created, <U> updated, <N> edge proposals
  ```

## Edge hints

- [ ] **Propose edges** using closed-vocab predicates.

  `cites` only from Topic / Decision / Artifact → Source. Org / Person / Project mentions left for projection-time `mentions` harvest.

  Append to `wiki/_inbox/edges.md`:
  ```markdown
  ## <YYYY-MM-DD HH:MM> · raw/inbox/docs/<file>.md
  - (<topic-slug>, cites, <slug>, 0.85, "<evidence quote>")
  ```
  Count edges (N).
