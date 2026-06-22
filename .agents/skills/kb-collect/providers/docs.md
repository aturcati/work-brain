# Provider — docs

The orchestrator runs `phases/config-check.md` before this checklist and `phases/report-log.md` after.

Converts a local file (PDF, DOCX, PPTX, XLSX, EPUB) via the `markitdown` skill into a markdown file under `raw/inbox/docs/`. Idempotency by sha256 of file CONTENTS — re-collecting the same file (even after rename) is a no-op.

**Inputs:** one or more local file paths supplied by the user, either inline (`/kb-collect docs <path1> <path2>`), via a queue file `~/.config/work-brain/docs-queue.txt` (one absolute path per line, `#` comments allowed), **or any non-`.md` files already sitting in `raw/inbox/docs/`** (manual drops are implicit collect inputs).

**Skill used:** `markitdown` — handles PDF, DOCX, PPTX, XLSX, EPUB, plus images (OCR) and audio.

### Phase 1 — Check provider config (provider-specific step)

- [ ] **Resolve file list**
  - If user passed paths inline: use those.
  - Else, read `~/.config/work-brain/docs-queue.txt`, ignore empty lines and `#` comments. If file absent or empty: report `no files to collect` and stop.

### Phase 2 — Per-file processing loop

Repeat for each file path.

- [ ] **Validate file exists**
  ```bash
  test -f "<path>" || { echo "ERROR: not found: <path>"; continue; }
  ```

- [ ] **Compute file key**
  ```bash
  uv run .agents/skills/kb-collect/collect.py \
    --action file-key --path "<path>"
  ```
  Capture the 16-hex string as `<file_key>`.

- [ ] **Idempotency check**
  ```bash
  uv run .agents/skills/kb-collect/collect.py \
    --state-file raw/.collect-state.json \
    --provider docs \
    --action check-id --meeting-id "<file_key>"
  ```
  Output `SEEN` → skip. Output `NEW` → proceed.

- [ ] **Detect file type**
  By extension (lowercase): `.pdf` → `pdf`, `.docx` → `docx`, `.pptx` → `pptx`, `.xlsx` → `xlsx`, `.epub` → `epub`. Other extensions: warn and skip.

- [ ] **Fetch via markitdown skill**
  Invoke the `markitdown` skill with the file path. Capture: converted markdown body + title (fall back to `Path(path).stem` if absent).

  On error: log and move to next file.

- [ ] **Compute filename slug**
  ```bash
  uv run .agents/skills/kb-collect/collect.py \
    --action file-slug --path "<path>" --title "<title>"
  ```
  Capture as `<slug>`.

- [ ] **Check filename collision**
  ```bash
  test -e "raw/inbox/docs/<slug>.md" && echo COLLIDE || echo OK
  ```
  On COLLIDE: append `-<file_key first 6 hex>` to slug.

- [ ] **Acquire inbox lock**
  ```bash
  uv run .agents/skills/kb-ingest/lock.py \
    --lock-file .kb/.inbox.lock --action acquire --timeout 5
  ```

- [ ] **Ensure inbox dir, write raw doc file**
  ```bash
  mkdir -p raw/inbox/docs
  ```
  Write `raw/inbox/docs/<slug>.md`:
  ```markdown
  ---
  source: docs
  provider: file
  captured_at: <YYYY-MM-DD today UTC>
  channel: docs
  original_ref: <absolute path>
  title: "<title>"
  file_key: <file_key>
  file_type: <pdf|docx|pptx|xlsx|epub>
  ---

  # <title>

  <markdown body from markitdown>
  ```

- [ ] **Release lock**
  ```bash
  uv run .agents/skills/kb-ingest/lock.py \
    --lock-file .kb/.inbox.lock --action release
  ```

- [ ] **Record state**
  ```bash
  uv run .agents/skills/kb-collect/collect.py \
    --state-file raw/.collect-state.json \
    --provider docs \
    --action record --meeting-id "<file_key>"
  ```

### Notes

- Idempotency on file CONTENTS — renaming source docs does NOT trigger re-collect.
- `original_ref` stores the path at collect time. Raw archive at `raw/docs/<YYYY>/<MM>/` is the durable copy.
- **Binary disposition:** after conversion, move the original binary out of the inbox to `raw/assets/<filename>` and set `original_ref` to that path — `/kb-ingest` only processes `.md` files and would leave the binary stranded.
- Markitdown refuses password-protected PDFs — surface error, do NOT write empty files.
