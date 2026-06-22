---
name: kb-rename
description: "Use when rename canonical entity slug. Rewrites slug field, all wikilinks, and aliases: entries vault-wide. Triggers /kb-graph project after completion"
---

# /kb-rename

**Purpose:** Rename canonical entity slug. Rewrites slug field, all wikilinks, and aliases: entries vault-wide. Triggers /kb-graph project after completion.

**Reads:** wiki/
**Writes:** wiki/ (diff-first), wiki/log.md
**Idempotency:** no-op if the target slug already matches the requested name.

## Run

**Helper:** `.agents/skills/kb-rename/rename.py`

- [ ] **Dry-run**
  ```bash
  uv run .agents/skills/kb-rename/rename.py <Type> <old-slug> <new-slug>
  ```
  Review output: file count, total replacements, list of referring files.

- [ ] **Confirm with user** if touching > 5 files (per CLAUDE.md rule). Show dry-run output.

- [ ] **Apply**
  ```bash
  uv run .agents/skills/kb-rename/rename.py <Type> <old-slug> <new-slug> --apply
  ```
  Atomically rewrites all wikilinks via `.kb-staging/<txn-id>/`. Old slug added to `aliases:` on renamed page. Log entry appended.

- [ ] **Refresh graph**
  ```bash
  uv run .agents/skills/kb-graph/project.py
  ```

- [ ] **Validate**
  ```bash
  uv run .agents/skills/kb-graph/validate.py
  ```

## Tests

```bash
uv run --with pytest --with pyyaml --with ruamel.yaml pytest .agents/skills/kb-rename/tests/test_rename.py -v
```

## Manual checklist

- [ ] Validate old-slug exists as a canonical page; new-slug does not conflict
- [ ] Find all files referencing [[wiki/<type>/old-slug]] in body or frontmatter
- [ ] Show consolidated diff: slug field change + all wikilink rewrites + aliases update on referring pages
- [ ] Require confirmation when touching > 5 files
- [ ] On confirm: apply all writes atomically
- [ ] Add old-slug to aliases: on the renamed page
- [ ] Run /kb-graph project
- [ ] Append to wiki/log.md: `## [YYYY-MM-DD HH:MM] kb-rename | <old-slug> → <new-slug>, <N> references updated`
