# Shared phase — Check provider config

Loaded by the orchestrator for every provider with `<provider>` substituted for the actual provider name.

### Phase 1 — Check provider config

- [ ] **Read providers config**
  ```bash
  cat ~/.config/work-brain/providers.toml
  ```
  Verify `[providers.<provider>]` section exists and `enabled = true`.
  If file absent: create it with:
  ```toml
  [providers.<provider>]
  enabled = true
  lookback_days = 7
  # backfill_from_date = "2024-01-01"   # set to trigger a historical backfill; remove after done
  ```

- [ ] **Determine `since` and collection mode**

  First, check if `backfill_from_date` is set in `[providers.<provider>]` config.

  **If `backfill_from_date` is set (backfill mode):**
  ```
  since = <backfill_from_date value, e.g. "2024-01-01T00:00:00Z">
  mode = "backfill"
  ```
  Print: `mode=backfill from=<since>`. After the full run completes successfully, remove `backfill_from_date` from providers.toml.

  **If `backfill_from_date` is not set (sync mode):**
  ```bash
  uv run .agents/skills/kb-collect/collect.py \
    --state-file raw/.collect-state.json \
    --provider <provider> \
    --action get-cursor
  ```
  Output `NONE` → `since` = today minus `lookback_days` in ISO format (e.g. `2026-05-06T00:00:00Z`).
  Output ISO datetime → `since` = that value.
  Print: `mode=sync from=<since>`.
