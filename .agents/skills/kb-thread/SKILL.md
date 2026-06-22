---
name: kb-thread
description: Use when build narrative across raw/ and wiki/ for a topic or question. File result as wiki/threads/<slug>.md with full citations
---

# /kb-thread

**Purpose:** Build narrative across raw/ and wiki/ for a topic or question. File result as wiki/threads/<slug>.md with full citations.

**Reads:** wiki/, raw/, .kb/graph.kuzu, .qmd/index.db
**Writes:** wiki/threads/<slug>.md, wiki/index.md, wiki/log.md
**Idempotency:** re-running overwrites the same `wiki/threads/<slug>.md` from current sources.

## Run

**Data-gathering helper:** `.agents/skills/kb-thread/build_thread.py`

- [ ] **Gather inputs**
  ```bash
  uv run --python 3.13 .agents/skills/kb-thread/build_thread.py <slug>
  ```
  Captures: entity type + slug, graph 1-hop neighbours (sorted by edge weight), citation paths, qmd top-10 hits. Output is structured markdown — read it.

- [ ] **Compose the thread page**
  Open `wiki/threads/<slug>.md` (create if absent) and write a narrative weaving the inputs together. Use this frontmatter shape:
  ```yaml
  ---
  type: Topic            # threads use Topic type by convention
  slug: <slug>           # or `thread-<topic-slug>` to disambiguate from entity page
  created: <today>
  modified: <today>
  status: active
  tags: ["thread"]
  related: ["[[wiki/<type>/<entity-slug>]]"]
  sources: [<list of raw paths cited in body>]
  ---

  # <Entity Display Name> — Thread

  ## Overview
  …
  ## Key sources
  …
  ## Related entities
  …
  ## Open questions
  …
  ```

- [ ] **Atomic save**
  Write the thread page directly to `wiki/threads/<slug>.md`. If the slug collides with an existing entity page (rare), prefix with `thread-`.

- [ ] **Update wiki/index.md**
  Append under a `## Threads` section (create if absent):
  ```
  - [[wiki/threads/<slug>]] — <1-line description>
  ```

- [ ] **Append log entry**
  ```
  ## [YYYY-MM-DD HH:MM] kb-thread | <slug> created (<N> neighbours, <M> citations)
  ```

## Tests

```bash
uv run --python 3.13 --with pytest --with pyyaml --with kuzu pytest .agents/skills/kb-thread/tests/test_build_thread.py -v
```

## Manual checklist

- [ ] Accept topic slug or free-form question
- [ ] Run /kb-query to gather relevant pages and raw sources
- [ ] Traverse graph neighbourhood for related entities
- [ ] Synthesise narrative with citations (wiki pages + raw paths)
- [ ] Show draft thread page; wait for confirmation
- [ ] On confirm: write wiki/threads/<slug>.md; update wiki/index.md
- [ ] Append to wiki/log.md: `## [YYYY-MM-DD HH:MM] kb-thread | <slug> created`
