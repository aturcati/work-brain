---
name: kb-lint
description: Use when health check across wiki/ and raw/. Reports only — never auto-fixes. Regenerates wiki/overview.md at end of each pass
---

# /kb-lint

**Purpose:** Health check across wiki/ and raw/. Reports only — never auto-fixes. Regenerates wiki/overview.md at end of each pass.

**Reads:** wiki/, raw/, raw/.ingest-state.json
**Writes:** views/lint-report.md, wiki/overview.md
**Idempotency:** read-only; regenerates `wiki/overview.md` deterministically.

## Checks

| Check | Report section |
|---|---|
| Orphan pages (no inbound links) | ## Orphans |
| Broken wikilinks (target missing) | ## Broken links |
| Schema violations (unknown frontmatter keys) | ## Schema violations |
| Stale last_verified (> 90 days) | ## Stale pages |
| Unresolved contradicts: pairs | ## Contradictions |
| Pages > 2 000 tokens | ## Bloated pages |
| raw/ file mtime drift (file modified after ingest) | ## Raw drift |
| wiki/log.md size (> 1 000 entries or > 1 MB) | ## Log rotation needed |
| wiki/_inbox/edges.md depth (> 500 entries or > 500 KB) | ## Edges rotation needed |
| Decision pages without sources: | ## Graph invariants |
| Person pages without works_at: | ## Graph invariants |
| Journal entries > 30 days with no entity update | ## Unprocessed journal entries |
| Stale action items (- [ ] > 30 days old) | ## Stale action items |

## Run

```bash
uv run .agents/skills/kb-lint/lint.py
```

Optional override for testing:
```bash
uv run .agents/skills/kb-lint/lint.py --today 2026-05-13
```

## Checklist

- [ ] Run lint script (above)
- [ ] Read `views/lint-report.md` — note which sections have findings
- [ ] Read `wiki/overview.md` — verify page counts and last ingest dates are current
- [ ] Act on high-priority findings (broken links, schema violations, log/edges rotation)
- [ ] Defer or accept low-priority findings (orphans, stale pages) if intentional

## Outputs

| File | Content |
|---|---|
| `views/lint-report.md` | Full findings, one section per check |
| `wiki/overview.md` | Page counts, last ingest per channel, top 5 stale, open actions |
| `wiki/log.md` | Appended: `## [YYYY-MM-DD HH:MM] kb-lint \| N issues found across 13 checks` |

## Tests

```bash
uv run --with pytest pytest .agents/skills/kb-lint/tests/test_lint.py -v
```
