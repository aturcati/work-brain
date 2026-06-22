# Provider — clippings

The orchestrator runs `phases/config-check.md` before this checklist and `phases/report-log.md` after.

Fetches a URL (web page, blog post, PDF, docx, YouTube transcript) via the `markitdown` skill and drops it as a markdown file in `raw/inbox/clippings/`. Idempotency by canonical URL hash.

**Inputs:** one or more URLs supplied by the user, either inline (`/kb-collect clippings <url1> <url2>`) or via a queue file `~/.config/work-brain/clippings-queue.txt` (one URL per line, comments after `#`).

**Skill used:** `markitdown` — supports HTML, PDF, DOCX, PPTX, XLSX, images (OCR), YouTube URLs, EPub.

### Phase 1 — Check provider config (provider-specific step)

- [ ] **Resolve URL list**
  - If user passed URLs inline: use those.
  - Else, read `~/.config/work-brain/clippings-queue.txt`, ignore empty lines and `#` comments. If file is absent or empty: report `no URLs to collect` and stop.

### Phase 2 — Per-URL processing loop

Repeat the following block for each URL.

- [ ] **Compute URL key**
  ```bash
  uv run .agents/skills/kb-collect/collect.py \
    --action url-key --url "<url>"
  ```
  Capture the 16-hex string as `<url_key>`.

- [ ] **Idempotency check**
  ```bash
  uv run .agents/skills/kb-collect/collect.py \
    --state-file raw/.collect-state.json \
    --provider clippings \
    --action check-id --meeting-id "<url_key>"
  ```
  Output `SEEN` → skip this URL, continue to next.
  Output `NEW` → proceed.
  (Re-uses the `check-id` / `meeting-id` action names from the Teams provider — they are generic over arbitrary string IDs.)

- [ ] **Fetch URL via markitdown skill**
  Invoke the `markitdown` skill with the URL. Capture:
  - The converted markdown body.
  - The page title (markitdown returns it; fall back to the URL's last path segment if absent).

  If markitdown reports an error: log it, move to the next URL.

- [ ] **Compute filename slug**
  ```bash
  uv run .agents/skills/kb-collect/collect.py \
    --action url-slug --url "<url>" --title "<title>"
  ```
  Capture the output as `<slug>` (e.g. `2026-05-24-claude-4-5-is-here`).

- [ ] **Check filename collision**
  ```bash
  test -e "raw/inbox/clippings/<slug>.md" && echo COLLIDE || echo OK
  ```
  On COLLIDE: append `-<url_key first 6 hex>` to slug for uniqueness.

- [ ] **Acquire inbox lock**
  ```bash
  uv run .agents/skills/kb-ingest/lock.py \
    --lock-file .kb/.inbox.lock --action acquire --timeout 5
  ```
  Expected: `ACQUIRED`. On `LOCK_TIMEOUT`: skip this URL, report error.

- [ ] **Write raw clipping file**
  Write `raw/inbox/clippings/<slug>.md` with this content:
  ```markdown
  ---
  source: clippings
  provider: url
  captured_at: <YYYY-MM-DD today UTC>
  channel: clippings
  original_ref: <url>
  title: "<title>"
  url_key: <url_key>
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
    --provider clippings \
    --action record --meeting-id "<url_key>"
  ```
  Expected: `RECORDED`.

### Notes

- The raw `url_key` field lives in the raw frontmatter so future ingest passes can verify cross-collect provenance without re-hashing.
- Markitdown will refuse URLs behind auth or paywalls; surface the error to the user, do NOT silently write empty files.
- Queue file format (one URL per line, optional `#` comment):
  ```
  https://www.anthropic.com/news/claude-4-5
  # below: paper to read later
  https://arxiv.org/abs/2411.12345
  ```
