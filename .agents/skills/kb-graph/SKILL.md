---
name: kb-graph
description: "Use when knowledge-graph operations. Subcommands: extract, project, query, validate, suggest-merges, promote, canvas"
---

# /kb-graph

**Purpose:** Knowledge-graph operations. Subcommands: extract, project, query, validate, suggest-merges, promote, canvas.

**Reads:** wiki/, raw/, .kb/
**Writes:** wiki/, .kb/, wiki/_maps/ (canvas only)
**Idempotency:** `project` rebuilds `.kb/graph.kuzu` from frontmatter every run (derived, never authored).

## Subcommand index

| Subcommand | Purpose | Reads | Writes | Helper |
|---|---|---|---|---|
| `extract <path>` | Propose edges from a raw/wiki file | file under arg | `wiki/_inbox/edges.md` | (LLM, no helper) |
| `project` | Rebuild graph from frontmatter | `wiki/**` | `.kb/graph.kuzu` | `project.py` |
| `query <cypher-or-nl>` | Query the projected graph | `.kb/graph.kuzu` | — | `project.py` |
| `validate` | Check edges against closed vocab | `wiki/**` | — | `validate.py` |
| `suggest-merges` | Find likely duplicate entities | `wiki/**` | report | `suggest_merges.py` |
| `promote [--threshold]` | Confirm proposals into frontmatter | `wiki/_inbox/edges.md` | `wiki/**` | `promote.py` |
| `canvas <Type> <slug>` | Build an Obsidian canvas around a node | `.kb/graph.kuzu` | `*.canvas` | `canvas.py` |

## Subcommands

### /kb-graph extract <path>
Run closed-schema LLM extraction on a specific raw file. Append proposals to wiki/_inbox/edges.md. Update .kb/extract-state.json. Use to retry after extraction failure.

### /kb-graph project
Rebuild .kb/graph.kuzu from all frontmatter wikilinks in wiki/. Apply .kb/schema.cypher. Atomic: rebuild in temp DB, rename on success. Update .kb/aliases.json alias table.

### /kb-graph query <cypher-or-nl>
Run Cypher query against .kb/graph.kuzu or translate NL to Cypher via LLM and run.

### /kb-graph validate

Schema check over all wiki/ frontmatter. Reports only — no writes.

**Helper:** `.agents/skills/kb-graph/validate.py`

- [ ] **Run from vault root**
  ```bash
  uv run .agents/skills/kb-graph/validate.py
  ```
  Expected stdout (clean vault): `validate: ok — 0 issues`

- [ ] **Review output categories**
  - `[parse-error]` — file has invalid/missing frontmatter or unknown `type:` value
  - `[unknown-edge]` — YAML key not in closed edge vocabulary
  - `[dangling-link]` — wikilink target `.md` not found anywhere under `wiki/`
  - `[orphan-invariant]` — `Person` without `works_at`, or `Decision` without `sources`

- [ ] **Append to wiki/log.md** (only if issues were fixed as a result)
  ```
  ## [YYYY-MM-DD HH:MM] kb-graph validate | N issues found — <brief description of fixes>
  ```

### /kb-graph suggest-merges

**Helper:** `.agents/skills/kb-graph/suggest_merges.py`

Compares same-type canonical wiki pages by alias overlap + 3-gram Jaccard. Read-only. Embeddings deferred (alias half clears MVP backlog).

- [ ] **Run from vault root**
  ```bash
  uv run .agents/skills/kb-graph/suggest_merges.py --threshold 0.75
  ```
  Use `--threshold 0.6` to surface first-name-only suspects (broader recall).

- [ ] **Review output**
  Lines have format:
  ```
  0.75  alice  ~  alice-smith    (exact alias overlap)
  ```
  Each candidate is a pair worth inspecting. Take **no** action from this report directly — pass confirmed dups into `/kb-merge`.

- [ ] **Next step**
  For each accepted candidate run `/kb-merge <primary-slug> <secondary-slug>`.

#### Tests
```bash
uv run --with pytest --with pyyaml pytest .agents/skills/kb-graph/tests/test_suggest_merges.py -v
```

### /kb-graph promote [--threshold 0.7]

> **Invariant (AGENTS.md):** edge proposals are never auto-promoted; this subcommand is the only path into canonical frontmatter, and it is human-confirmed.

**Helper:** `.agents/skills/kb-graph/promote.py`

**Prerequisite:** Subject and object slugs in `wiki/_inbox/edges.md` must be canonical wiki pages (not stubs in `wiki/tofile/`). Run `/kb-link` first to promote any ready stubs, then `/kb-graph project` to refresh the graph.

- [ ] **Step 1 — dry-run (report)**
  ```bash
  uv run .agents/skills/kb-graph/promote.py --threshold 0.7
  ```
  Review output:
  - `promote: N edge(s) would be promoted` — show to user for review
  - `Skipped (unresolved slugs ...)` — edges whose subject or object is still a `tofile/` stub; resolve stubs first

  Notes:
  - Duplicate proposals of the same edge are safe — `--apply` dedupes into one frontmatter entry.
  - Edges already present in frontmatter are consumed from the queue as no-ops (apply count may be far below the dry-run count — that's normal after an ingest that wrote `attended:` lists directly).
  - **Stale proposals:** entries whose target was deliberately deleted (e.g. mailbox stubs) or whose predicate violates the endpoint-type table (`phases/edge-extraction.md`) will never resolve — prune them from `wiki/_inbox/edges.md` with user confirmation when they survive 2+ promote runs.

- [ ] **Step 2 — confirm with user**
  Show the dry-run output. Wait for explicit user approval before proceeding.

- [ ] **Step 3 — apply**
  ```bash
  uv run .agents/skills/kb-graph/promote.py --threshold 0.7 --apply
  ```
  Expected: `promote: N edge(s) promoted. Re-run /kb-graph project to refresh Kuzu.`

- [ ] **Step 4 — rebuild graph**
  ```bash
  uv run .agents/skills/kb-graph/project.py
  ```
  Expected: `nodes=N edges=M skipped=K` (M should be higher than before promotion)

- [ ] **Step 5 — validate**
  ```bash
  uv run .agents/skills/kb-graph/validate.py
  ```
  Expected: `validate: ok — 0 issues`

- [ ] **Step 6 — verify log**
  Check `wiki/log.md` for a new entry:
  `## [YYYY-MM-DD HH:MM] kb-graph promote | N edge(s) promoted into frontmatter`

### /kb-graph canvas <Type> <slug>

**Helper:** `.agents/skills/kb-graph/canvas.py`

Generates `wiki/_maps/<slug>.canvas` (Obsidian Canvas JSON) showing the entity + 1-hop graph neighbours laid out on a circle. Edge labels = relation type. Node colours by type.

- [ ] **Dry-run**
  ```bash
  uv run .agents/skills/kb-graph/canvas.py <Type> <slug>
  ```
  Prints node + edge counts. No writes.

- [ ] **Apply**
  ```bash
  uv run .agents/skills/kb-graph/canvas.py <Type> <slug> --apply
  ```
  Writes `wiki/_maps/<slug>.canvas` atomically via `.kb-staging/`. Log entry appended.

- [ ] **Open in Obsidian**
  Navigate to `wiki/_maps/<slug>.canvas`. Obsidian renders the canvas natively.

#### Tests

```bash
uv run --with pytest --with kuzu --with pyyaml pytest .agents/skills/kb-graph/tests/test_canvas.py -v
```

## /kb-graph project — checklist

**Helper:** `.agents/skills/kb-graph/project.py`

- [ ] **Run from vault root**
  ```bash
  uv run .agents/skills/kb-graph/project.py
  ```
  Expected stdout: `nodes=N edges=M skipped=K`

- [ ] **Verify output**
  ```bash
  uv run --python 3.13 --with kuzu python -c "
  import kuzu
  db = kuzu.Database('.kb/graph.kuzu')
  conn = kuzu.Connection(db)
  r = conn.execute('MATCH (n) RETURN n.slug LIMIT 20')
  while r.has_next(): print(r.get_next())
  "
  ```

- [ ] **Append to wiki/log.md**
  ```
  ## [YYYY-MM-DD HH:MM] kb-graph project | N nodes, M edges projected
  ```

## Notes

- `.kb/graph.kuzu` is always derived. Rebuild is idempotent and safe to re-run at any time.
- Skipped edges: non-wiki values in frontmatter (raw paths) and edges pointing to `wiki/tofile/` stubs are expected skips — not errors.
- On any failure: `.kb/graph.kuzu.tmp` is deleted automatically; existing `.kb/graph.kuzu` is untouched.
- When new entity pages are promoted from `wiki/tofile/` to canonical `wiki/<type>/`, re-run `/kb-graph project` to include them.
- kuzu 0.11.3 stores DB as a single file (not directory). The `--python 3.13` flag is required since kuzu 0.11.3 has no Python 3.14 wheel.
