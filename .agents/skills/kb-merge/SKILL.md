---
name: kb-merge
description: Use when resolve identity collision — fold two canonical pages for the same entity into one. Merge aliases, edges, sources, body content. Redirect stub replaces the merged page
---

# /kb-merge

**Purpose:** Resolve identity collision — fold two canonical pages for the same entity into one. Merge aliases, edges, sources, body content. Redirect stub replaces the merged page.

**Reads:** wiki/
**Writes:** wiki/ (diff-first), wiki/log.md
**Idempotency:** no-op if one of the two pages is already a redirect stub to the other.

## Run

**Helper:** `.agents/skills/kb-merge/merge.py`

- [ ] **Dry-run**
  ```bash
  uv run .agents/skills/kb-merge/merge.py <Type> <primary-slug> <secondary-slug>
  ```
  Shows: merged frontmatter key count, body sections to append, external reference count, redirect stub preview.

- [ ] **Confirm with user** (per CLAUDE.md maintenance-skill rule; always touches > 1 file).

- [ ] **Apply**
  ```bash
  uv run .agents/skills/kb-merge/merge.py <Type> <primary-slug> <secondary-slug> --apply
  ```
  Atomic via `.kb-staging/<txn-id>/`. Secondary page becomes redirect stub (`status: merged`, `superseded_by: [[primary]]`).

- [ ] **Refresh graph + validate**
  ```bash
  uv run .agents/skills/kb-graph/project.py
  uv run .agents/skills/kb-graph/validate.py
  ```

## Tests

```bash
uv run --with pytest --with pyyaml --with ruamel.yaml pytest .agents/skills/kb-merge/tests/test_merge.py -v
```

## Manual checklist

- [ ] Accept two slugs: primary (kept) and secondary (merged into primary)
- [ ] Show combined frontmatter diff: merged aliases, union of all edge lists, union of sources
- [ ] Show combined body diff: append non-duplicate sections from secondary into primary
- [ ] Show redirect stub for secondary: `See [[wiki/<type>/primary-slug]]`
- [ ] Show all wikilink rewrites pointing secondary → primary
- [ ] Require confirmation (always touches > 1 file)
- [ ] On confirm: apply all writes; run /kb-graph project
- [ ] Append to wiki/log.md: `## [YYYY-MM-DD HH:MM] kb-merge | <secondary> → <primary>`
