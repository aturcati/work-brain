# work-brain — LLM-maintained knowledge base

You are the maintainer of this knowledge base. Read `wiki/index.md` first on every operation. Follow these rules exactly.

## Prerequisites

- uv: `brew install uv` (runs inline-dep Python scripts — no venv activation needed)
- qmd: `brew install qmd` (BM25 + vector + rerank hybrid search)

Python packages declared per-script via PEP 723 inline headers — no pyproject.toml in the vault. Skills stay standalone uv run scripts — no venv, no installed packages. Shared pure-stdlib infrastructure lives in .agents/skills/common.py, imported via sys.path.insert (same pattern the test suite uses); no other cross-skill imports. Within a skill, split large helpers into sibling modules instead (see kb-lint core.py/checks.py, kb-collect quality.py).
Common deps: `kuzu` (graph projection), `markitdown` (PDF/docx → markdown).
`.agents/skills` is the authoritative project-local source for all work-brain skill runbooks, helpers, and tests. `/kb-*` operations must read `.agents/skills/<name>/SKILL.md` before acting.

Claude compatibility wrappers point back to the matching `.agents/skills/<name>/SKILL.md`; do not add helper implementations or tests under the Claude wrapper tree.

All skill Python helpers run as: `uv run .agents/skills/<name>/<helper>.py`

Vault-wide test run (pytest.ini sets importlib mode + testpaths; py3.14 cannot build kuzu):
`uv run --python 3.12 --with pytest --with pyyaml --with ruamel.yaml --with kuzu pytest -q`
Lint: `uvx ruff check .agents/skills/` (config in `ruff.toml`; `scripts/` excluded as archived one-offs).

## Layers

- `raw/` — immutable by convention. Read-only. Never modify files here.
- `wiki/` — LLM-owned synthesis layer. Every change is diff-reviewable.
- `wiki/log.md` — append an entry after every operation. Format: `## [YYYY-MM-DD HH:MM] <skill> | <one-line summary>`

## Frontmatter contract

Every wiki page carries YAML frontmatter. Empty edge lists may be omitted.

```yaml
---
# Identity
type: Person | Org | Project | Topic | Decision | Meeting | Thread | Source | Artifact | Event
slug: <kebab-case-id>
aliases: []
created: YYYY-MM-DD
modified: YYYY-MM-DD
last_verified: YYYY-MM-DD
status: active | dormant | archived
tags: []
confidence: high | medium | low

# Graph edges (closed vocabulary — see Graph schema)
# structural
part_of: []
instance_of: []
related: []
# agentic
works_at: []
attended: []
authored: []
owns: []
reports_to: []
# epistemic
sources: []
derived_from: []
cites: []
supersedes: []
contradicts: []
confirms: []
superseded_by: []
# causal
depends_on: []
caused_by: []
decided: []
mentions: []
---
```

Raw source pages use a thinner schema: `source`, `provider`, `captured_at`, `channel`, `participants`, `original_ref`.

## Identity keys

- **meeting_id** = `<ISO-date>-<slugified-title>` — ISO date (YYYY-MM-DD), then title lowercased, accents stripped, punctuation removed, spaces collapsed and replaced with hyphens. Example: `2026-04-12-q2-roadmap-review`
- **person slug** = kebab-cased canonical name. Collisions disambiguated as `firstname-lastname-org`. Example: `alice-smith-acme`
- **project key** = stable kebab slug assigned at creation. Renames only via `/kb-rename` — never edit the slug field by hand.

## Graph schema (closed vocabulary)

**Node types:** `Person`, `Org`, `Project`, `Topic`, `Decision`, `Meeting`, `Source`, `Artifact`, `Event`

Each node type = one canonical markdown page under `wiki/<type-plural>/` with `type:` and `slug:` frontmatter.

**Edge types (allowed YAML keys in frontmatter):**

| Category | Edge keys |
|---|---|
| Structural | `part_of`, `instance_of`, `related` |
| Agentic | `works_at`, `attended`, `authored`, `owns`, `reports_to` |
| Epistemic | `sources`, `derived_from`, `cites`, `supersedes`, `superseded_by`, `contradicts`, `confirms` |
| Causal | `depends_on`, `caused_by`, `decided`, `mentions` |

Edge values are wikilinks to canonical pages: `["[[wiki/people/alice-smith-acme]]"]`

Unknown edge keys are rejected by `/kb-graph validate`.

`mentions` is usually derived from body wikilinks at projection time — do not store in YAML unless explicitly material.

**Edge weights for `/kb-query` graph expansion:**
- Heavy (weight 3): `decided`, `sources`, `authored`, `works_at`
- Default (weight 1): `part_of`, `instance_of`, `related`, `attended`, `owns`, `reports_to`, `derived_from`, `cites`, `supersedes`, `superseded_by`, `contradicts`, `confirms`, `depends_on`, `caused_by`
- Light (weight 0.2): `mentions`

## Conventions

- One canonical page per entity; aliases via `aliases:` frontmatter.
- Never overwrite existing wiki content when new sources arrive. Contradictions are tracked via `contradicts:` + `superseded_by:` + `last_verified:` frontmatter. `/kb-lint` surfaces both sides of any contradiction.
- Inbox writes and inbox reads are serialised via `.kb/.inbox.lock`. Never write to `raw/inbox/` without holding this lock. `.kb/.inbox.lock` is a LOGICAL name: `lock.py` maps it to `~/.cache/work-brain-locks/<sha16>.lock` (`KB_LOCK_DIR` overrides) so no lock file ever lands in the cloud-synced vault — synced advisory locks fight the sync client and are unsound across machines anyway.
- Page > 2 000 tokens → propose `/kb-refactor` split. Do not split inline.
- `last_verified` older than 90 days → flagged by `/kb-lint`.
- Never auto-create wikilink targets. Drop unresolved links as stubs in `wiki/tofile/<proposed-slug>.md`.
- Cite raw paths in every wiki edit via `sources:` frontmatter.
- LLM-extracted edges are *proposals* only. They land in `wiki/_inbox/edges.md` under `## <YYYY-MM-DD HH:MM> · <raw-path>`. Never auto-promote to canonical frontmatter. Promotion via `/kb-graph promote` (diff-first, human-confirmed).
- `.kb/graph.kuzu` is always derived. Never read it as source of truth. It is a LOGICAL name: the physical 70MB Kuzu DB lives in `~/.cache/work-brain-graph/<sha16>/graph.kuzu` (`KB_GRAPH_DIR` overrides; `graph_db_path()` in the kb-graph/kb-query/kb-thread helpers) — rewriting it inside the cloud-synced vault on every projection caused constant sync churn.
- Log rotation: `wiki/log.md` > 1 000 entries or > 1 MB → rotate to `wiki/log-archive/YYYY-MM.md`.
- Edges rotation: `wiki/_inbox/edges.md` > 500 entries or > 500 KB → rotate to `wiki/_inbox/edges-archive/YYYY-MM.md`.
- Scripted frontmatter edits must match the target file's existing YAML list indentation style (`- x` vs `  - x`) — mixing styles inside one list breaks the YAML parse.

## Diff strategy

- *Fan-out skills* (`kb-ingest`, `kb-compile`): emit ONE consolidated diff per source → atomic commit via `.kb-staging/<txn-id>/` → on success rename into `wiki/`. On failure: drop staging, move source to `raw/quarantine/` with sibling `.error.md`, log error.
- *Maintenance skills* (`kb-rename`, `kb-merge`, `kb-refactor`, `kb-archive`): require per-batch confirmation when touching > 5 files.
- *Read skills* (`kb-query`, `kb-lint`, `kb-status`): no writes, no diff.

## Idempotency state files

| File | Guards |
|---|---|
| `raw/.ingest-state.json` | `(raw_path, sha256) → {status, ts}` — prevents double-ingest |
| `.kb/extract-state.json` | `(raw_path, sha256) → {status, edge_count, ts}` — prevents double-extraction |
| `raw/.collect-state.json` | Per-provider `{cursor, last_seen_at}` — incremental collection |

Rerunning any skill on already-processed input is a no-op (checked before any write).

## Operational invariants (hard-won)

These are contract-level rules learned from production ingests. Skill checklists must uphold them; they are not optional style.

- **`sources:` cites the FINAL path, never the inbox path.** Ingest moves a file from `raw/inbox/<channel>/<file>.md` to `raw/<channel>/YYYY/MM/<file>.md`. Wiki frontmatter and body citations must reference the destination path, even though the move happens in a later phase. Inbox-path citations break the moment the file moves — this single mistake required correcting 191 source paths across 179 pages. `/kb-lint` flags broken `sources:` paths.
- **Resolve provider slug suffixes before creating a page.** Some providers (e.g. MeetGeek transcripts) append a `-<6 hex chars>` suffix to the title slug. Strip the suffix and check for the base slug before writing a new page, or you create a duplicate of an entity that already exists. Generalise: when a candidate slug differs from an existing one only by a provider-generated suffix, treat it as the same entity (see `kb-ingest/match.py`).
- **Multiple MeetGeek recordings of the same meeting.** MeetGeek can produce 2–3 recordings per meeting (e.g. primary, duplicate suffix, declined). Handling by case: (a) a `-<6hex>` variant whose base slug matches an existing page → merge into primary (add its raw path to the primary's `sources:`; no new wiki page); (b) a variant with a genuinely different slug (e.g. `declined-<title>`) → own wiki Meeting page with `related: ["[[wiki/meetings/<primary-slug>]]"]`; (c) never create a stub for the merge-case variant — it has no independent identity. Failure mode: naive ingest creates a duplicate Meeting page for case (a) when match.py runs after the suffixed file instead of before it.
- **`works_at` inference on Person promotion.** When promoting a Person stub to canonical, infer `works_at: ["[[wiki/orgs/acme]]"]` if the entity's observed email is `@acme.com` or `@acme.onmicrosoft.com`. External persons (tag `external`) intentionally omit `works_at` — do not add it. This is an inference rule, not a hard constraint; `/kb-graph validate` only flags missing `works_at` when no `external` tag is present.
- **Stub → canonical promotion criterion.** A `wiki/tofile/<slug>.md` stub graduates to a canonical page only when it has **≥1 inbound wiki link AND ≥1 raw mention**. Below that threshold it stays a stub. Promotion is via `/kb-link`, diff-first.
- **Edge proposals are never auto-promoted.** LLM extraction appends to `wiki/_inbox/edges.md`; only `/kb-graph promote` writes them into canonical frontmatter, human-confirmed. Promote in batches and re-run `/kb-graph project` after.
- **Lint debt is the health signal.** Track the `/kb-lint` issue count over time; orphans and stale `last_verified` dominate. Drive it toward zero after each large ingest, not later.
- **Teams-before-MeetGeek ordering.** In meetings ingest, process plain files before `-<6hex>`-suffixed MeetGeek files so `match.py` finds the base page to merge into. Naive glob order is backwards (`-` 0x2D sorts before `.` 0x2E), so `…-3e5f75.md` comes first and creates a duplicate page.
- **Transcripts live in `wiki/artifacts/<slug>-transcript.md`,** not inline in Meeting pages (anything over ~1,500 tokens). The Meeting page keeps summary/action items and links the artifact. Inline transcripts immediately trip the `/kb-lint` bloat check.
- **Never stub mailboxes.** Meeting rooms and group mailboxes (`meetingroom*`, `software@`, `applicants@`, `team@`, `office@`, `ai@`) are not Persons — exclude them from `participants`, `attended:`, and `wiki/tofile/`. They otherwise false-qualify for `/kb-link` promotion.
- **Per-stub provenance.** Every stub's `sources:` cites the exact file the entity was observed in — never a shared constant in bulk-generation scripts. Same failure class as the inbox-path mistake above.
- **Decision pages need a wiki-source anchor at creation.** `/kb-graph validate` requires ≥1 `wiki/` wikilink in a Decision's `sources:` (raw paths alone fail), and `/kb-lint` requires ≥1 inbound link from a canonical page (links from `tofile/`, `index.md`, `overview.md` don't count). Create/link a `wiki/sources/` page for the originating document at the same time as the Decision stub.
- **MeetGeek API rejects the python-urllib User-Agent** (403 behind WAF). Send a curl-like `User-Agent` header from Python scripts; curl itself works unmodified.
- **Grown email threads re-collect via `thread_last`**. `check-id --last-received` compares against the per-conversation baseline in `outlook.thread_last` and prints `GROWN` when newer replies exist; the update is written as a sibling `<slug>-u<YYYYMMDD>.md` file (raw stays immutable) and `/kb-ingest` strips that suffix so it appends a `## Re-ingest` section to the existing Source page. Always pass `--last-received` on `record` — conversations without a baseline fall back to `SEEN` and stay blind to growth.
- **End every fan-out run with `/kb-lint` + `/kb-graph validate`** and drive findings to zero before reporting done. These two checks caught every self-inflicted defect in the 2026-06-03 mass ingest (11→0, then 8→0).

## Workflows

See `.agents/skills/<name>/SKILL.md` for each skill's purpose and checklist.

## Tag taxonomy

Controlled tags — add new tags here before use in frontmatter:

```
external — non-org person or outside contact; may intentionally omit `works_at` when the affiliation is unknown, not applicable, or would be misleading.
```
