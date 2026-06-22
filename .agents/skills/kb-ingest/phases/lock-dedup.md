# Shared phase — Lock and dedup

> Loaded by the kb-ingest orchestrator for every channel. Replace `<channel>` and `<file>` with the active values.

### Phase 1 — Lock and dedup

- [ ] **Acquire inbox lock**
  ```bash
  uv run .agents/skills/kb-ingest/lock.py \
    --lock-file .kb/.inbox.lock --action acquire --timeout 5
  ```
  Expected: `ACQUIRED`. On `LOCK_TIMEOUT`: stop, report error, do not proceed.

- [ ] **Scan inbox**
  ```bash
  ls raw/inbox/<channel>/*.md 2>/dev/null || echo "EMPTY"
  ```
  If EMPTY: release lock and stop.

- [ ] **Idempotency check** (for each file, using inbox path)
  ```bash
  uv run .agents/skills/kb-ingest/state.py \
    --state-file raw/.ingest-state.json \
    --raw-path raw/inbox/<channel>/<file>.md \
    --action check
  ```
  Output `SKIP` → skip this file. Output sha256 hex → proceed.
