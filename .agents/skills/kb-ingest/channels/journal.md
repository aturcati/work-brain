# Channel handler — journal

> Phase 2 for the journal channel. The orchestrator runs the shared phases (lock-dedup, edge-extraction, move-state-cleanup, reindex-log) around this.

### Phase 2 — Journal handler

- [ ] **Read file content**
  Read `raw/inbox/journal/<file>.md`. Note `captured_at` date from frontmatter.

- [ ] **Extract entity mentions**
  Identify named entities in body text:
  - People → kebab-cased person slugs (e.g. "Sarah Chen" → `sarah-chen`)
  - Projects → kebab-cased project slugs
  - Orgs → kebab-cased org slugs
  - Topics → kebab-cased topic slugs

  For each candidate slug: check `wiki/<type>/<slug>.md`.
  - Exists → resolved entity (update page in staging below).
  - Missing → create stub at `wiki/tofile/<slug>.md`.

  **Stub format** for unresolved entities (example Person):
  ```markdown
  ---
  type: Person
  slug: sarah-chen
  aliases: ["Sarah Chen"]
  created: <captured_at>
  modified: <captured_at>
  status: active
  confidence: low
  sources: ["[[raw/journal/<YYYY>/<MM>/<file>.md]]"]
  ---
  <!-- stub: promote via /kb-link when ≥1 inbound wiki link + ≥1 raw mention -->
  ```

- [ ] **Create staging directory**
  Choose txn-id = `<YYYYMMDD-HHMM>` (e.g. `20260511-1200`).
  ```bash
  mkdir -p .kb-staging/<txn-id>/wiki/tofile
  mkdir -p .kb-staging/<txn-id>/wiki/decisions
  # mkdir -p for each entity type dir needed
  ```

- [ ] **Write staged wiki changes**

  For each **resolved entity**: write updated `wiki/<type>/<slug>.md` to `.kb-staging/<txn-id>/wiki/<type>/<slug>.md`. Changes:
  - Add raw path to `sources:` list if not present.
  - Update `modified:` to `captured_at` date.
  - Append bullet under `## Journal mentions` (create section if absent):
    ```
    - <captured_at>: <one-line summary of what the entry says about this entity> (from [[raw/journal/YYYY/MM/<file>]])
    ```

  For each **stub** (unresolved entity): write stub to `.kb-staging/<txn-id>/wiki/tofile/<slug>.md`.

  If decision language found ("decided to", "going with", "we will", "agreed to") — trigger phrases only nominate; create a stub only for actionable, org-level decisions (see meetings handler note):
  Write decision stub to `.kb-staging/<txn-id>/wiki/decisions/<captured_at>-<slugified-decision>.md`.

  **Validate invariant:** the stub's `sources:` needs ≥1 `wiki/` wikilink besides the raw path, and the page needs ≥1 inbound link from a canonical page (`tofile/`, `index.md`, `overview.md` don't count for `/kb-lint`). If the originating journal document has no `wiki/sources/` page, create one in the same staging txn and link the decision from it (precedent: `wiki/sources/planning-draft`).
  ```markdown
  ---
  type: Decision
  slug: <captured_at>-<slugified-decision>
  created: <captured_at>
  modified: <captured_at>
  status: active
  confidence: low
  sources: ["[[raw/journal/<YYYY>/<MM>/<file>.md]]"]
  ---
  <!-- Proposed from journal entry <captured_at>. Review and promote via /kb-graph promote. -->

  Decision language detected: "<quoted decision sentence>"

  Review and expand before promoting.
  ```

- [ ] **Atomic rename staging → wiki**
  ```bash
  cp -r .kb-staging/<txn-id>/wiki/. wiki/
  rm -rf .kb-staging/<txn-id>/
  ```
  On any error before this step: drop staging, quarantine source:
  ```bash
  rm -rf .kb-staging/<txn-id>/
  mkdir -p raw/quarantine/
  cp raw/inbox/journal/<file>.md raw/quarantine/<file>.md
  echo "kb-ingest error: <description>" > raw/quarantine/<file>.error.md
  ```

- [ ] **Update wiki/index.md**
  Add entries under appropriate section headers for any new pages or stubs created.

## Edge hints

Key edge types for journal:
- `(sarah-chen, works_at, acme, 0.55, "Sarah will take the lead on implementation")`
- `(dave-miller, works_at, acme, 0.55, "Dave is handling the simulation environment")`
- `(quantum-error-correction, related, surface-code, 0.85, "decided to go with the surface code approach")`
