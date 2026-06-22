# Shared phase — Report and log

Loaded by the orchestrator for every provider after the main fetch phase completes.

### Phase N — Report

- [ ] **Print summary**

  After processing all events/items:
  ```
  kb-collect <provider>: N item(s) collected, M skipped (already seen)
  ```

- [ ] **Print summary line** — `<provider>: <N> items collected, <M> skipped (seen), <K> errors`.

- [ ] **Append to wiki/log.md**
  ```
  ## [YYYY-MM-DD HH:MM] kb-collect | <provider>: N items collected
  ```

- [ ] **Append log entry**
  ```
  ## [YYYY-MM-DD HH:MM] kb-collect | <provider>: N item(s) collected
  ```
