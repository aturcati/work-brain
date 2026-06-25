# Channel handler — clippings

> Phase 2 for the clippings channel. The orchestrator runs the shared phases (lock-dedup, edge-extraction, move-state-cleanup, reindex-log) around this.

### Phase 2 — Clippings handler

- [ ] **Read file frontmatter and body**

  Extract from frontmatter:
  - `captured_at` → date string
  - `original_ref` → URL
  - `title` → human-readable title
  - `url_key` → 16-hex idempotency key

  Body: full converted markdown from markitdown.

- [ ] **Compute Source slug**

  The slug = the filename stem (e.g. `2026-05-24-widgetco-v2-launch`). Use this as the canonical `wiki/sources/<slug>.md` filename.

  **Manual drops (Obsidian Web Clipper) arrive with spaces/punctuation in the filename** (e.g. `WidgetCo Launch Retrospective.md`). Kebab-slugify the stem for the `wiki/sources/<slug>.md` page name, but the **raw archive keeps its original filename** — `move_file.py` preserves it, so `sources:`/raw-path wikilinks cite the spaced path verbatim: `"[[raw/clippings/<YYYY>/<MM>/WidgetCo Launch Retrospective.md]]"`. Wikilinks tolerate spaces; do not rename the raw file.

- [ ] **Check if Source page already exists**

  ```bash
  test -e "wiki/sources/<slug>.md" && echo EXISTS || echo NEW
  ```
  - EXISTS: pre-existing Source page. Update `sources:` list in frontmatter to include the final moved path (append `[[raw/clippings/<YYYY>/<MM>/<file>.md]]` if absent), update `modified:` to today. Append a divider `\n\n---\n\n## Re-ingest <captured_at>\n` then a fresh summary of the new body. Skip step "Create new Source page" below.
  - NEW: proceed.

- [ ] **Extract entity mentions from body**

  Identify named entities (case-sensitive). For each candidate slug, check `wiki/<type>/<slug>.md` existence as in journal/meetings handlers:
  - Person → kebab-cased canonical name
  - Org → kebab-cased canonical name
  - Topic → kebab-cased canonical name
  - Project → kebab-cased project slug

  For each: resolved (page exists) → planned update. Unresolved → planned stub at `wiki/tofile/<slug>.md`.

- [ ] **Create staging directory**

  ```bash
  txn_id=$(date -u +%Y%m%d-%H%M)
  mkdir -p .kb-staging/<txn_id>/wiki/sources
  mkdir -p .kb-staging/<txn_id>/wiki/tofile
  # mkdir -p for each entity type dir needed
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
  channel: clippings
  provider: url
  captured_at: <captured_at>
  path: raw/clippings/<YYYY>/<MM>/<file>
  sources: ["[[raw/clippings/<YYYY>/<MM>/<file>.md]]"]
  tags: []
  ---

  ## Summary

  <1-3 paragraph LLM summary of the body. Embed wikilinks `[[wiki/<type>/<slug>]]` for every resolved entity. For unresolved entities, link to `[[wiki/tofile/<slug>]]` — promotion via /kb-link will rewrite.>

  **Note:** the URL belongs in the body's "Original reference" section below, NOT in frontmatter — `original_ref` is not in the canonical wiki schema and would trigger `/kb-lint` schema-violation warnings.

  ## Original reference

  - **URL:** <url>
  - **Captured:** <captured_at>
  - **Raw archive:** [[raw/clippings/<YYYY>/<MM>/<file>]]
  ```

  (After move in Phase 4, the staging-written `sources:` and the raw-path wikilink will be stale by one path level — `wiki/_inbox/edges.md` and `/kb-link` already tolerate this, same as journal/meetings handlers do.)

- [ ] **Write staged stubs** (unresolved entities)

  Same stub format used by journal/meetings, with `sources: ["[[raw/clippings/<YYYY>/<MM>/<file>.md]]"]`:
  ```markdown
  ---
  type: <Type>
  slug: <slug>
  aliases: ["<original display form>"]
  created: <captured_at>
  modified: <captured_at>
  status: active
  confidence: low
  sources: ["[[raw/clippings/<YYYY>/<MM>/<file>.md]]"]
  ---
  <!-- stub: promote via /kb-link when ≥1 inbound wiki link + ≥1 raw mention -->
  ```

- [ ] **Write staged updates** (resolved entities)

  For each resolved entity page: rewrite the page in staging with:
  - `sources:` extended by `"[[raw/clippings/<YYYY>/<MM>/<file>.md]]"` if not already present.
  - `modified:` set to `<captured_at>`.
  - Body section `## Clippings` (create if absent) appended with bullet:
    ```
    - <captured_at>: <one-line summary of what this clipping says about the entity> (from [[wiki/sources/<slug>]])
    ```

- [ ] **Atomic rename staging → wiki**

  ```bash
  cp -r .kb-staging/<txn_id>/wiki/. wiki/
  rm -rf .kb-staging/<txn_id>/
  ```
  On error before this step: drop staging, quarantine source:
  ```bash
  rm -rf .kb-staging/<txn_id>/
  mkdir -p raw/quarantine
  cp raw/inbox/clippings/<file>.md raw/quarantine/<file>.md
  echo "kb-ingest error: <description>" > raw/quarantine/<file>.error.md
  ```

- [ ] **Update wiki/index.md**

  Add `- [[wiki/sources/<slug>]]` under the existing `## Sources` section (create section if absent). Add any new stubs under `## tofile`. Add any new resolved entity pages under their type sections (typically only if the entity was newly promoted out of `tofile/` in the same session — rare).

## Channel-specific steps

- [ ] **Append log entry**
  ```
  ## [YYYY-MM-DD HH:MM] kb-ingest | clippings: 1 file (<slug>), <S> stubs created, <U> updated, <N> edge proposals
  ```

## Edge hints

- [ ] **Propose edges** using only closed-vocab predicates.

  Common patterns for clippings:
  - For each Topic entity mentioned: `(<topic-slug>, cites, <clip-slug>, <conf>, "<evidence ≤60 chars>")`. Schema allows `cites FROM Topic TO Source`.
  - For each Decision entity mentioned: `(<decision-slug>, cites, <clip-slug>, <conf>, "<evidence>")`.
  - For each Artifact mentioned: `(<artifact-slug>, cites, <clip-slug>, <conf>, "<evidence>")`.
  - For Org / Person / Project mentions: skip cites (not in schema). The `mentions` edge is derived at projection time from body wikilinks.

  Append to `wiki/_inbox/edges.md`:
  ```markdown
  ## <YYYY-MM-DD HH:MM> · raw/inbox/clippings/<file>.md
  - (<topic-slug>, cites, <clip-slug>, 0.85, "<evidence quote>")
  - ...
  ```
  Count edges proposed (N).
