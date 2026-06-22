# Shared phase — Move, state, cleanup

### Phase 4 — Move, state, cleanup

- [ ] **Move raw file out of inbox**
  Use `captured_at` date from frontmatter:
  ```bash
  uv run .agents/skills/kb-ingest/move_file.py \
    --src raw/inbox/<channel>/<file>.md \
    --channel <channel> \
    --date <captured_at>
  ```
  Note printed destination path (e.g. `…/raw/<channel>/2026/05/<file>.md`).
  If exit code 1 (FileExistsError — destination collision): first sha256-compare inbox file vs destination.
  - **Identical** (e.g. leftover from a `/kb-undo-ingest`): delete the inbox copy (`trash`) and proceed to the state write below — no quarantine.
  - **Different**: quarantine source (same pattern as staging failure above) and release lock.

- [ ] **Write ingest state** (uses FINAL path — after move)
  ```bash
  uv run .agents/skills/kb-ingest/state.py \
    --state-file raw/.ingest-state.json \
    --raw-path raw/<channel>/<YYYY>/<MM>/<file>.md \
    --action write --status done
  ```

- [ ] **Write extraction state** (uses FINAL path — `edge_count` carried from Phase 3)
  ```bash
  uv run .agents/skills/kb-ingest/state.py \
    --state-file .kb/extract-state.json \
    --raw-path raw/<channel>/<YYYY>/<MM>/<file>.md \
    --action write --status done --extra edge_count=<N>
  ```

- [ ] **Release inbox lock**
  ```bash
  uv run .agents/skills/kb-ingest/lock.py \
    --lock-file .kb/.inbox.lock --action release
  ```
  Expected: `RELEASED`.
