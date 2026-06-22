---
name: kb-init
description: Use when one-time vault scaffold — create directory structure, CLAUDE.md, skill stubs, .qmdignore, .kb/schema.cypher, and wiki stub files
---

# /kb-init

**Purpose:** One-time vault scaffold — create directory structure, CLAUDE.md, skill stubs, .qmdignore, .kb/schema.cypher, and wiki stub files.

**Reads:** nothing (greenfield)
**Writes:** full vault scaffold
**Idempotency:** aborts with "already initialised" if `CLAUDE.md` exists.

## Checklist

This skill has already run (bootstrap complete). Re-running is a no-op if vault is already scaffolded.

- [ ] Check vault root for existing CLAUDE.md — if present, abort with "already initialised"
- [ ] Create directory tree (raw/, wiki/, .kb/, .agents/skills/, views/, scripts/)
- [ ] Write CLAUDE.md from template
- [ ] Write .qmdignore
- [ ] Write .kb/schema.cypher from CLAUDE.md vocab
- [ ] Write wiki/index.md, wiki/log.md, wiki/overview.md, wiki/_inbox/edges.md
- [ ] Write empty state JSON files
- [ ] Write skill stubs
- [ ] Write scripts/qmd_reindex.sh
- [ ] Write views/ stubs
- [ ] Append to wiki/log.md: `## [YYYY-MM-DD HH:MM] kb-init | Bootstrap complete`
