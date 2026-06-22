# Shared phase — Reindex and log

### Phase 5 — Reindex and log

- [ ] **Reindex qmd** (skip if qmd not yet initialised)
  ```bash
  bash scripts/qmd_reindex.sh 2>/dev/null || echo "qmd not initialised — skipping (normal at this stage)"
  ```

- [ ] **/kb-graph project** — deferred to build sequence step 3. Skip for now.

- [ ] **Append to wiki/log.md**
  ```
  ## [<YYYY-MM-DD HH:MM>] kb-ingest | <channel>: 1 file, <N_entities> entity pages updated/stubbed, <N_edges> edge proposals
  ```
