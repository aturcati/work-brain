# Shared phase — Edge extraction

> Channel-specific edge hints are supplied by the channel handler (`channels/<channel>.md`).
> This file owns the mechanics; the handler owns the per-channel edge vocabulary hints.

### Phase 3 — Edge extraction

- [ ] **Extraction idempotency check** (uses inbox path)
  ```bash
  uv run .agents/skills/kb-ingest/state.py \
    --state-file .kb/extract-state.json \
    --raw-path raw/inbox/<channel>/<file>.md \
    --action check
  ```
  Output `SKIP` → skip extraction. Output sha256 → proceed.

- [ ] **Extract closed-schema edges**
  Re-read the file. Propose edges using only edge types from CLAUDE.md Graph schema.

  Format per edge:
  ```
  (subject_slug, predicate, object_slug, confidence_0_to_1, "evidence quote ≤60 chars")
  ```

  Allowed predicates: `part_of`, `instance_of`, `related`, `works_at`, `attended`, `authored`,
  `owns`, `reports_to`, `sources`, `derived_from`, `cites`, `supersedes`, `superseded_by`,
  `contradicts`, `confirms`, `depends_on`, `caused_by`, `decided`, `mentions`.

  **Endpoint-type constraints** — check before proposing (closed vocab alone doesn't catch e.g. `works_at → Topic`):

  | Predicate | Subject | Object |
  |---|---|---|
  | `works_at`, `reports_to` | Person | Org / Person |
  | `attended` | Meeting | Person (also Person → Meeting on person pages) |
  | `authored`, `owns` | Person | any non-Person |
  | `cites`, `sources`, `derived_from` | any | Source |
  | `decided` | Meeting / Project / Topic | Decision |
  | `part_of`, `instance_of`, `related`, `depends_on`, `caused_by`, `mentions`, `supersedes`, `superseded_by`, `contradicts`, `confirms` | any | any |

  Type-mismatched proposals (e.g. `(carol, works_at, meetgeek)` where meetgeek is a Topic) are never promotable — don't propose them.

  Append to `wiki/_inbox/edges.md`:
  ```markdown
  ## <YYYY-MM-DD HH:MM> · raw/inbox/<channel>/<file>.md
  ```
  Count edges proposed (N).

- [ ] **Extraction state write is deferred to Phase 4** (after the move, keyed by FINAL path).
  Writing it here with the inbox path leaves a dangling key once the file moves —
  this corrupted 139/142 extract-state entries before the 2026-06-10 remap. Carry
  `edge_count=<N>` forward to Phase 4.
