---
name: kb-undo-ingest
description: "Use when reverse a completed ingest for a specified raw file: remove wiki edits that were derived exclusively from that file, delete or restore the moved raw file, clear state-file entries so the file can be re-ingested if needed"
---

# /kb-undo-ingest

**Purpose:** Reverse a completed ingest for a specified raw file: remove wiki edits that were derived exclusively from that file, delete or restore the moved raw file, clear state-file entries so the file can be re-ingested if needed.

**Status:** ✅ Implemented.

**Reads:** raw/, wiki/, raw/.ingest-state.json, .kb/extract-state.json, wiki/index.md, wiki/_inbox/edges.md, wiki/log.md
**Writes:** wiki/ (deletions/edits), raw/.ingest-state.json, .kb/extract-state.json, wiki/index.md, wiki/_inbox/edges.md, wiki/log.md
**Idempotency:** no-op if the raw file has no `done` entry in the state files.

## Usage

```
/kb-undo-ingest <raw-path>
```

`<raw-path>` is the final (post-move) path in `raw/<channel>/YYYY/MM/<file>.md`.

## Run

**Helper:** `.agents/skills/kb-undo-ingest/undo.py`

- [ ] **Dry-run**
  ```bash
  uv run .agents/skills/kb-undo-ingest/undo.py <raw-path>
  ```
  Replace `<raw-path>` with the post-move path, e.g. `raw/meetings/2026/05/2026-05-11-foo.md`.

  Review output: pages to delete (sole-source), pages to strip (multi-source), edge proposals to remove.

- [ ] **Confirm with user.** Show dry-run output.

- [ ] **Apply** (choose raw disposition)
  ```bash
  uv run .agents/skills/kb-undo-ingest/undo.py <raw-path> --raw keep --apply
  # or --raw delete   (remove the raw file entirely)
  # or --raw restore  (move back to raw/inbox/<channel>/ for re-ingest)
  ```

- [ ] **Refresh graph + reindex**
  ```bash
  uv run .agents/skills/kb-graph/project.py
  bash scripts/qmd_reindex.sh
  ```

## Tests

```bash
uv run --with pytest --with pyyaml --with ruamel.yaml pytest .agents/skills/kb-undo-ingest/tests/test_undo.py -v
```

## Manual checklist (reference)

### Phase 1 — Identify scope
- [ ] Read `raw/.ingest-state.json`; confirm entry for `<raw-path>` exists and `status = done`. If absent: report "not found in ingest state — nothing to undo" and stop.
- [ ] Read `wiki/index.md` and `wiki/log.md` to identify pages and decisions created by this ingest.
- [ ] Read `wiki/_inbox/edges.md` to identify edge proposal block for this raw path.

### Phase 2 — Confirm with user
- [ ] List all wiki pages, tofile stubs, decision stubs, and edge blocks that will be removed.
- [ ] Ask for confirmation before proceeding. Abort if denied.

### Phase 3 — Remove wiki artifacts
- [ ] Delete tofile stubs and decision stubs created exclusively from this file (check `sources:` frontmatter — skip pages with multiple sources).
- [ ] For resolved entity pages that were *updated* (not created) by this ingest: remove the dated bullet under `## Journal mentions` and the raw path from `sources:` frontmatter.
- [ ] Remove edge proposal block from `wiki/_inbox/edges.md`.
- [ ] Remove entry from `wiki/index.md`.

### Phase 4 — Clear state files
- [ ] Remove entry from `raw/.ingest-state.json` for `<raw-path>`.
- [ ] Remove entry from `.kb/extract-state.json` for `<raw-path>`.

### Phase 5 — Handle raw file
- [ ] Offer two options: (a) delete `<raw-path>`, (b) restore to `raw/inbox/<channel>/` for re-ingest.
- [ ] Execute chosen option.

### Phase 6 — Log
- [ ] Append to `wiki/log.md`:
  ```
  ## [YYYY-MM-DD HH:MM] kb-undo-ingest | reverted ingest of <raw-path>
  ```

## Constraints

- Never remove a wiki page whose `sources:` list contains more than one entry — only remove the reference from that file; leave the page.
- Never touch `raw/` files other than the target and the inbox restoration.
- Full atomicity not required (undo is inherently manual triage); but prefer staging via `.kb-staging/<txn-id>/` for wiki edits when touching > 3 pages.
