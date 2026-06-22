---
name: kb-query
description: Use when hybrid search over wiki/ and raw/ with optional entity-anchored graph expansion
---

# /kb-query

**Purpose:** Hybrid search over wiki/ and raw/ with optional entity-anchored graph expansion.
Two modes: **plain** (BM25 + vector + rerank via qmd) and **entity-anchored** (NER → Kuzu graph expand → qmd merge).

**Reads:** wiki/, raw/ (citations), .kb/graph.kuzu (entity-anchored only)
**Writes:** wiki/threads/ (opt-in only)
**Idempotency:** read-only; no writes.

## qmd collections (one-time setup)

```bash
# From vault root:
qmd collection add wiki wiki
qmd collection add raw raw
qmd embed
```

## Plain query checklist (current — step 3)

- [ ] **Run search**
  ```bash
  qmd query "<query>" -c wiki -c raw
  ```
  `qmd query` auto-expands the query (BM25 + vector + rerank). Takes ~15–35s on first run (model load); ~5s after warmup.

- [ ] **Read results** — each result shows: collection path, score %, and a snippet. Ignore `wiki/tofile/` stubs and `wiki/_inbox/` entries unless specifically relevant.

- [ ] **Synthesise answer** — cite sources using vault-relative paths:
  - Wiki pages: `wiki/sources/annual-widget-spend.md`
  - Raw files: `raw/journal/2026/04/annual-widget-spend.md`

- [ ] **Offer thread filing** (opt-in) — if the answer is substantial, offer:
  ```
  File as wiki/threads/<slug>.md? (y/n)
  ```

## Fast BM25-only search (no rerank)

When speed matters or no LLM-assisted expansion is needed:
```bash
qmd search "<query>" -c wiki -c raw
```

## Entity-anchored checklist

Use when the query contains a person name, org, project, topic, or meeting title.

- [ ] **Check aliases.json exists**
  ```bash
  ls -la .kb/aliases.json
  ```
  If missing: run `uv run .agents/skills/kb-graph/project.py` first (it writes aliases.json on every projection).

- [ ] **Run entity-anchored query**
  ```bash
  uv run .agents/skills/kb-query/query.py "<query>" --top-k 10
  ```
  Takes ~5–20s (Kuzu open + qmd). On first qmd run after restart: ~35s for model load.

- [ ] **Read output**

  Output sections:
  - `ENTITY <slug> (<Type>) [phrase: "..."]` — matched entity with the query phrase that triggered it
  - `  NEIGHBOR <slug> (<Type>) via <edge_type> weight=<N>` — graph neighbours (sorted by edge weight)
  - `CANDIDATE <path> [graph:<edge> w=<N>]` — wiki page sourced from graph neighbourhood
  - `CANDIDATE <path> [qmd:<N>%]` — wiki page sourced from qmd (not already in graph set)
  - `NO_ENTITY_MATCH` — no entity found; only qmd CANDIDATE lines follow

  Edge weights: `works_at`/`sources`/`authored`/`decided` = 3.0 (strong signal); `attended`/most others = 1.0; `mentions` = 0.2 (weak).

- [ ] **Synthesise answer**

  Read each CANDIDATE page (graph candidates first — they're most relevant). Cite using vault-relative paths:
  - `wiki/meetings/2026-05-07-acme-cloud-scrum-review.md`
  - `raw/meetings/2026/05/2026-05-07-acme-cloud-scrum-review.md`

  Also cite the ENTITY's own page for biographical context (e.g. `wiki/people/alice-smith.md`).

- [ ] **Offer thread filing** (opt-in)
  If the answer is substantial (≥3 CANDIDATE pages read):
  ```
  File as wiki/threads/<slug>.md? (y/n)
  ```

## Reindex after ingest

After any `/kb-ingest` or `/kb-compile`:
```bash
bash scripts/qmd_reindex.sh
```
After `/kb-graph project` (or any structural wiki change):
```bash
uv run .agents/skills/kb-graph/project.py  # rebuilds graph.kuzu + aliases.json
```