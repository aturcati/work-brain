---
name: kb-refactor
description: Use when split bloated pages (> 2 000 tokens), propose merges of near-duplicate pages, harmonise frontmatter schema. Diff-first — no writes without human confirmation
---

# /kb-refactor

**Purpose:** Split bloated pages (> 2 000 tokens), propose merges of near-duplicate pages, harmonise frontmatter schema. Diff-first — no writes without human confirmation.

**Reads:** wiki/
**Writes:** wiki/ (diff-first, confirmed only)
**Idempotency:** diff-first; declined diffs leave the vault unchanged.

## Checklist

- [ ] Identify target page (user-specified or largest page from kb-lint report)
- [ ] For split: propose section boundaries; show diff of resulting child pages + updated parent
- [ ] For merge proposal: show combined page diff + redirect stub for the merged page
- [ ] For frontmatter harmonise: show before/after YAML diff
- [ ] Present diff to user; wait for confirmation
- [ ] On confirm: apply writes; update wiki/index.md; run /kb-graph project
- [ ] Append to wiki/log.md: `## [YYYY-MM-DD HH:MM] kb-refactor | <operation> on <slug>`
