---
name: kb-link
description: Use when report promotion candidates from `wiki/tofile/` and suggest backlinks. Promotion is diff-first and human-confirmed
---

# /kb-link

**Purpose:** Report promotion candidates from `wiki/tofile/` and suggest backlinks. Promotion is diff-first and human-confirmed.

**Reads:** wiki/, wiki/tofile/, raw/
**Writes:** wiki/, wiki/tofile/, wiki/index.md (on promotion only)
**Idempotency:** promotion is diff-first and human-confirmed; re-running re-proposes the same candidates.

> **Invariant (AGENTS.md):** a `wiki/tofile/` stub promotes to canonical only with ≥1 inbound wiki link AND ≥1 raw mention.

## Helper

`.agents/skills/kb-link/link.py`

## Step 1 — Run report

```bash
cd <vault-root> && uv run .agents/skills/kb-link/link.py
```

Output: table of stubs with inbound link count, raw mention flag, and PROMOTE? verdict.

Promotion criteria: **inbound ≥ 1** AND **raw mention = yes**.

Inbound links are counted with the same scope as `/kb-lint`'s orphan check (links from `tofile/`, `_inbox/`, `index.md`, `overview.md`, `log*` do NOT count) — so a promoted page is guaranteed not to become an instant orphan.

> Batch rule (AGENTS.md): promotions touching > 5 files require explicit per-batch user confirmation. Script bulk runs (page generation, stub deletion, vault-wide link rewrite, index update) instead of editing by hand; cite each stub's own source files, never a shared constant.

## Step 2 — Promote qualifying stubs

For each stub marked `✓ PROMOTE`:

- [ ] Read the stub frontmatter (slug, type, aliases, sources)
- [ ] Read the raw source files cited in `sources:` to gather content
- [ ] Write `wiki/<type-plural>/<slug>.md` with:
  - Full frontmatter (copy from stub, add `last_verified`, upgrade `confidence: low` if evidence supports)
  - Body: 2–4 sentence summary of the entity + `## Journal mentions` section citing raw paths
- [ ] Delete `wiki/tofile/<slug>.md`
- [ ] Rewrite inbound `[[wiki/tofile/<slug>]]` wikilinks vault-wide to the canonical path (they break the moment the stub is deleted)
- [ ] Add entry to `wiki/index.md` under the correct type section
- [ ] Remove the tofile entry from `wiki/index.md` if present
- [ ] Re-run `/kb-graph project` to refresh `.kb/graph.kuzu`
- [ ] Re-run `/kb-graph promote` dry-run — newly promoted stubs may unblock previously-skipped edge proposals (edges logged as `Skipped (unresolved slugs)` during ingest land in `wiki/_inbox/edges.md` and wait; promotion of their subject/object stub is the only thing that unblocks them)

> **Stub deletion is part of promotion, whatever the route.** Bulk/scripted promotions (kb-graph promote follow-ups, ad-hoc page generation) MUST also delete the tofile stub and rewrite its inbound links — skipping this left 114 stale duplicate stubs in the queue by 2026-06-11. `/kb-lint` flags tofile stubs whose slug already exists as a canonical page.

**Type-plural mapping:** Person→people, Org→orgs, Project→projects, Topic→topics, Decision→decisions, Meeting→meetings, Source→sources, Artifact→artifacts, Event→events

## Step 3 — Update not-ready stubs

For stubs not yet qualifying:
- [ ] Check: does the stub have useful aliases? If the raw file uses different terminology, add aliases to the stub frontmatter.
- [ ] Re-run `link.py` to verify updated aliases resolve the raw-mention gap.

## Step 4 — Log

```
## [YYYY-MM-DD HH:MM] kb-link | N stubs promoted: <slug-list>; M not ready
```

## Checklist (backlink suggestions)

- [ ] Scan wiki/ pages with zero inbound links from other wiki pages (orphan candidates)
- [ ] For each: suggest 1–2 relevant pages that could link back
- [ ] Propose new entity pages for wikilinks that appear in wiki/ body text but have no target in wiki/ and no stub in wiki/tofile/
