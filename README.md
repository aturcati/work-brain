# work-brain

Personal knowledge base maintained by Claude. Built on the LLM-wiki pattern.

## How it works

- **You** drop sources into `raw/inbox/<channel>/` (or run `/kb-collect` to pull from providers)
- **Claude** runs `/kb-ingest` to classify, normalise, and fan out into `wiki/`
- **You** browse the result in Obsidian; ask questions via `/kb-query`; review edge proposals via `/kb-graph promote`

Three rules make this safe to run unattended:

1. **Raw is immutable.** Sources land in `raw/`, are never edited, and every wiki claim cites the raw path it came from.
2. **Writes are diff-first and idempotent.** Each skill stages changes, shows one diff, and re-running on already-processed input is a no-op.
3. **The graph is derived, not authored.** Edges live in YAML frontmatter; `.kb/graph.kuzu` is rebuilt from it. LLM-extracted edges are *proposals* until you promote them.

## First run

```text
1. /kb-collect            # pull recent meetings/emails into raw/inbox/  (or drop files yourself)
2. /kb-ingest             # classify inbox → fan out wiki pages + queue edge proposals
3. /kb-graph promote      # review proposed edges; confirm the good ones into frontmatter
4. /kb-query "what did we decide about X?"   # entity-anchored hybrid search
5. /kb-lint               # health check; regenerates wiki/overview.md
```

Steps 1–2 are the daily loop. Steps 3–5 are periodic. Nothing writes to the wiki without a diff you can review.

## Worked example — a week of use

A realistic loop showing how the pieces fit. Commands are what you type to Claude; the indented notes are what happens.

**Monday — capture the week's meetings.**
```text
/kb-collect
  → pulls 6 new MeetGeek transcripts + 3 Outlook threads into raw/inbox/
  → reports: "meetings: 6 new, emails: 3 new, 0 duplicates (idempotent skip)"
```

**Monday — distil them into the wiki.**
```text
/kb-ingest
  → classifies each file, shows ONE consolidated diff per source, then commits:
      • updates wiki/people/carol-jones.md  (+ "## Meeting mentions" bullet, new source)
      • creates wiki/meetings/2026-05-25-q2-roadmap-review.md
      • creates wiki/tofile/error-budget.md     (stub — new topic, not yet canonical)
      • queues 14 edge proposals in wiki/_inbox/edges.md
```
You skim the diff in Obsidian. Raw files moved to `raw/meetings/2026/05/`; the wiki cites those final paths.

**Tuesday — ask, don't dig.**
```text
/kb-query "what did we decide about the Q2 error budget?"
  → NER finds the `error-budget` topic + `q2-roadmap-review` meeting
  → expands the graph one hop (decided / attended edges), reranks with qmd
  → answers with citations to the exact raw transcript lines
```

**Wednesday — promote the good edges.**
```text
/kb-graph promote
  → shows the 14 queued proposals as a diff:
      (q2-roadmap-review) --decided--> (adopt-error-budget-slo)   conf 0.82  ✓ confirm
      (carol-jones)   --works_at--> (acme)                   conf 0.55  ✓ confirm
      (sarah)            --works_at--> (acme)                   conf 0.40  ✗ skip (too weak)
  → you confirm the strong ones; they land in frontmatter; graph reprojects
```

**Thursday — handle a contradiction.** A new transcript says the SLO target moved from 99.9% to 99.95%. Ingest does **not** overwrite — it records `contradicts:` + `superseded_by:` + a fresh `last_verified:`. `/kb-lint` later surfaces both sides so you decide which is current.

**Friday — review health and build a narrative.**
```text
/kb-status                       # dashboard: inbox depth, lint debt, last ingest per channel
/kb-lint                         # full health pass; regenerates wiki/overview.md
/kb-thread "error budget rollout"   # weaves raw + wiki into wiki/threads/error-budget-rollout.md
```

The skill you reach for most is `/kb-query`. The two that keep the vault healthy are `/kb-lint` (run after every big ingest) and `/kb-graph promote` (don't let proposals pile up).

## Layers

| Layer | Path | Owner |
|---|---|---|
| Raw sources | `raw/` | Immutable — never edited |
| Synthesis wiki | `wiki/` | Claude |
| Schema + rules | `CLAUDE.md` | You + Claude (co-evolved) |

## Slash commands

| Command | What it does |
|---|---|
| `/kb-collect` | Pull from email, Teams, calendar, web URLs |
| `/kb-ingest` | Process inbox → wiki |
| `/kb-query` | Ask questions with graph-enhanced retrieval |
| `/kb-graph promote` | Review and promote LLM-proposed edges |
| `/kb-lint` | Health check — orphans, stale, contradictions |
| `/kb-status` | Dashboard — counts, inbox depth, log size |
| `/kb-thread` | Build narrative for a topic |

## Prerequisites

```bash
brew install uv    # Python script runner (PEP 723 inline deps)
brew install qmd   # Hybrid search (BM25 + vector + rerank)
```

## Channels

Drop files into `raw/inbox/<channel>/`:

| Channel | Source type |
|---|---|
| `journal/` | Daily notes, fleeting thoughts |
| `meetings/` | Transcripts, minutes |
| `emails/` | Email threads (markdown) |
| `chats/` | Slack / Teams exports |
| `clippings/` | Web articles (Obsidian Web Clipper) |
| `docs/` | PDFs, Word docs (markitdown converts) |

## Schema

See `CLAUDE.md` for the full frontmatter contract, graph vocabulary, identity keys, and conventions.
