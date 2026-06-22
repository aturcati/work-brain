---
name: kb-compile
description: Use when rebuild affected wiki pages from a scoped set of raw entries. Idempotent. Re-runs extraction over scoped raw set. Use to recover from failed ingest or to refresh synthesis from raw sources
---

# /kb-compile

**Purpose:** Rebuild affected wiki pages from a scoped set of raw entries. Idempotent. Re-runs extraction over scoped raw set. Use to recover from failed ingest or to refresh synthesis from raw sources.

**Reads:** raw/<scoped-set>, wiki/, wiki/index.md
**Writes:** wiki/ (via .kb-staging/), wiki/_inbox/edges.md, .kb/extract-state.json, wiki/log.md
**Idempotency:** compares current wiki page hash vs regenerated; unchanged pages skipped.

## Conventions
- Idempotent: compares current wiki page hash against what would be generated; skips unchanged pages.
- Emit ONE consolidated diff before committing (same as kb-ingest).
- Use .kb-staging/ atomicity.
- **Invariant (AGENTS.md):** `sources:` cites the final moved path, never an inbox path.

## Checklist

- [ ] Read wiki/index.md to identify currently existing pages for scoped entities
- [ ] For each raw file in scope: re-run extraction and synthesis
- [ ] Compute diff against existing wiki pages — skip unchanged
- [ ] Write changed pages to .kb-staging/<txn-id>/; atomic rename on success
- [ ] Re-run edge extraction over scoped set; append net-new proposals to wiki/_inbox/edges.md
- [ ] Update .kb/extract-state.json
- [ ] Run /kb-graph project
- [ ] Append to wiki/log.md: `## [YYYY-MM-DD HH:MM] kb-compile | Recompiled <N> raw files → <M> wiki pages updated`
