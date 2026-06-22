# work-brain — repository structure

This repo publishes the **structure and code** of an LLM-maintained personal
knowledge base. All actual knowledge content (`raw/`, `wiki/`), local caches,
and machine state stay private and are excluded via `.gitignore`.

## Layers

| Layer | Role | In repo? |
|---|---|---|
| `raw/` | Immutable captured sources (email, chat, meetings, docs, journal) | ❌ private |
| `wiki/` | LLM-owned synthesis layer (canonical entity pages, graph edges) | ❌ private |
| `.agents/skills/` | Skill runbooks, Python helpers, and test suites — the engine | ✅ committed |
| `.kb/` | Derived graph + state; only `schema.cypher` is published | partial |
| `views/` | Obsidian query definitions (`.base`) | ✅ committed |
| `docs/` | Design history and plans | ❌ private |

## Committed tree

```
.
├── AGENTS.md            # full operating contract (layers, schema, invariants)
├── CLAUDE.md            # → AGENTS.md
├── README.md            # overview
├── pytest.ini           # importlib mode, testpaths
├── ruff.toml            # lint config
├── .qmdignore           # qmd search excludes
├── .kb/
│   └── schema.cypher    # closed-vocabulary graph schema (node + edge types)
├── views/               # *.base — Obsidian query views
└── .agents/skills/
    ├── common.py        # shared pure-stdlib infra (TYPE_TO_DIR, EDGE_KEYS, locks)
    ├── tests_common/    # tests for common.py
    ├── kb-collect/      # pull from external providers → raw/inbox/
    ├── kb-ingest/       # classify, route, fan out wiki edits (atomic staging)
    ├── kb-compile/      # rebuild wiki pages from a scoped raw set
    ├── kb-graph/        # extract / project / query / validate / promote / canvas
    ├── kb-query/        # hybrid search + entity-anchored graph expansion
    ├── kb-thread/       # build narrative across raw/ + wiki/
    ├── kb-link/         # tofile/ stub → canonical promotion candidates
    ├── kb-lint/         # health check across wiki/ + raw/
    ├── kb-status/       # dashboard (inbox depth, lint debt, channels)
    ├── kb-merge/        # fold duplicate entity pages
    ├── kb-rename/       # rename canonical slug vault-wide
    ├── kb-refactor/     # split bloated pages, harmonise frontmatter
    ├── kb-archive/      # move stale pages to wiki/archive/ + redirect stub
    ├── kb-undo-ingest/  # reverse a completed ingest
    └── kb-init/         # one-time vault scaffold
```

Each skill directory carries a `SKILL.md` runbook, helper `*.py` modules, and a
`tests/` suite. Run the full suite (Python 3.12 — 3.14 cannot build kuzu):

```
uv run --python 3.12 --with pytest --with pyyaml --with ruamel.yaml --with kuzu pytest -q
```

## Private layout (structure only — contents never published)

```
raw/{inbox,emails,chats,meetings,docs,clippings,journal,assets,quarantine}/YYYY/MM/
wiki/{people,orgs,projects,topics,decisions,meetings,sources,artifacts,threads,tofile}/
wiki/{_inbox,_maps,archive,log-archive}/
```

**Bootstrapping these:** `/kb-init` generates the whole scaffold (this layout + `CLAUDE.md` + schema + skills) in an *empty* directory — it aborts if `CLAUDE.md` already exists. In a clone the framework is already present, so create just the runtime directories with the `mkdir` in [README.md](README.md#getting-started).

See `AGENTS.md` for the full frontmatter contract, identity keys, graph schema,
and operational invariants.
