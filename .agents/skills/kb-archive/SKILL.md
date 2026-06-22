---
name: kb-archive
description: Use when move stale page to wiki/archive/<type>/<slug>.md with a redirect stub at the original path. Updates wiki/index.md. Triggers /kb-graph project
---

# /kb-archive

**Purpose:** Move stale page to wiki/archive/<type>/<slug>.md with a redirect stub at the original path. Updates wiki/index.md. Triggers /kb-graph project.

**Reads:** wiki/
**Writes:** wiki/ (diff-first), wiki/log.md
**Idempotency:** no-op if the page is already under `wiki/archive/`.

## Run

**Helper:** `.agents/skills/kb-archive/archive.py`

- [ ] **Dry-run**
  ```bash
  uv run .agents/skills/kb-archive/archive.py <Type> <slug>
  ```
  Shows: source/dest paths, current status, index lines to remove, redirect stub preview.

- [ ] **Confirm with user.** Always touches > 1 file (page + index).

- [ ] **Apply**
  ```bash
  uv run .agents/skills/kb-archive/archive.py <Type> <slug> --apply
  # add --force to bypass the dormant/archived status check
  ```
  Atomic via `.kb-staging/<txn-id>/`. Inbox lock acquired. Page moves to `wiki/archive/<type-dir>/<slug>.md`. Redirect stub at original path. Index updated.

- [ ] **Refresh graph**
  ```bash
  uv run .agents/skills/kb-graph/project.py
  ```
  Archive copy is skipped (`SKIP_DIRS` includes `archive`). Only the redirect stub at the original path projects — with `status: archived` and a `superseded_by` edge.

- [ ] **Validate**
  ```bash
  uv run .agents/skills/kb-graph/validate.py
  ```

## Tests

```bash
uv run --with pytest --with ruamel.yaml pytest .agents/skills/kb-archive/tests/test_archive.py -v
```

## Manual checklist

- [ ] Accept slug to archive; confirm page exists and status is dormant or archived
- [ ] Show diff: archive destination path + redirect stub at original path + wiki/index.md removal
- [ ] On confirm: move file to wiki/archive/<type>/<slug>.md; write redirect stub
- [ ] Update wiki/index.md to remove or flag entry
- [ ] Run /kb-graph project
- [ ] Append to wiki/log.md: `## [YYYY-MM-DD HH:MM] kb-archive | <slug> archived`
