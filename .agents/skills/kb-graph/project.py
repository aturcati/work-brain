#!/usr/bin/env python3
# /// script
# dependencies = [
#   "kuzu",
#   "pyyaml",
# ]
# requires-python = ">=3.9,<3.14"
# ///
"""
kb-graph project — rebuild .kb/graph.kuzu from wiki/ frontmatter.
Usage: uv run .agents/skills/kb-graph/project.py
Vault root auto-detected: walks up from __file__ until CLAUDE.md found.
"""
import json
import re
import sys
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (  # noqa: E402
    EDGE_KEYS, SKIP_NONGRAPH as SKIP_DIRS, SKIP_NAMES,
    find_vault_root, parse_frontmatter, graph_db_path,
)

# Per-type columns — must match .kb/schema.cypher exactly
NODE_COLUMNS: dict[str, list[str]] = {
    "Person":   ["slug", "aliases", "status", "tags", "confidence", "created", "modified", "last_verified"],
    "Org":      ["slug", "aliases", "status", "tags", "confidence", "created", "modified", "last_verified"],
    "Project":  ["slug", "aliases", "status", "tags", "confidence", "created", "modified", "last_verified"],
    "Topic":    ["slug", "aliases", "status", "tags", "confidence", "created", "modified", "last_verified"],
    "Decision": ["slug", "status", "tags", "confidence", "created", "modified", "last_verified"],
    "Meeting":  ["slug", "date", "status", "tags", "confidence", "created", "modified"],
    "Source":   ["slug", "path", "channel", "captured_at", "provider"],
    "Artifact": ["slug", "aliases", "status", "created", "modified"],
    "Event":    ["slug", "date", "status", "created", "modified"],
}

ARRAY_COLS = {"aliases", "tags"}


def remove_db(path: Path) -> None:
    """Remove a Kuzu DB regardless of whether it is a file or directory."""
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def extract_wiki_slug(value: str) -> str | None:
    """Return slug from [[wiki/<type>/<slug>]] or [[wiki/<type>/<slug>|alias]]. Returns None if not a wiki wikilink."""
    m = re.fullmatch(r"\[\[wiki/[^/\]]+/([^\]/|]+?)(?:\.md)?(?:\|[^\]]*)?\]\]", value.strip())
    return m.group(1) if m else None


def collect_pages(wiki_dir: Path) -> list[dict]:
    pages = []
    for md_path in sorted(wiki_dir.rglob("*.md")):
        rel = md_path.relative_to(wiki_dir)
        parts = rel.parts
        if any(p in SKIP_DIRS for p in parts[:-1]):
            continue
        fname = parts[-1]
        if fname in SKIP_NAMES or fname.startswith("log"):
            continue
        fm = parse_frontmatter(md_path)
        if fm is None:
            continue
        node_type = str(fm.get("type", ""))
        slug = str(fm.get("slug", ""))
        if node_type not in NODE_COLUMNS or not slug:
            continue
        pages.append({"path": md_path, "type": node_type, "slug": slug, "fm": fm})
    return pages


def build_node_props(fm: dict, node_type: str) -> dict:
    props: dict = {}
    for col in NODE_COLUMNS[node_type]:
        val = fm.get(col)
        if col in ARRAY_COLS:
            if isinstance(val, list):
                props[col] = [str(v) for v in val]
            elif val:
                props[col] = [str(val)]
            else:
                props[col] = []
        else:
            props[col] = str(val) if val is not None else ""
    return props


def _strip_line_comments(text: str) -> str:
    """Drop `//` line comments from a Cypher schema file."""
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("//"))


def parse_rel_combos(schema_path: Path) -> set[tuple[str, str, str]]:
    clean = _strip_line_comments(schema_path.read_text())
    combos: set[tuple[str, str, str]] = set()
    for rel_name, body in re.findall(r"CREATE REL TABLE (\w+)\s*\(([^;]+)\)", clean, re.DOTALL):
        for from_t, to_t in re.findall(r"FROM\s+(\w+)\s+TO\s+(\w+)", body):
            combos.add((from_t, rel_name, to_t))
    return combos


def apply_schema(conn, schema_path: Path) -> None:
    clean = _strip_line_comments(schema_path.read_text())
    for stmt in clean.split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)


def build_aliases(pages: list[dict]) -> dict:
    """Build alias lookup maps from a pages list (as returned by collect_pages)."""
    by_alias: dict[str, dict] = {}
    by_slug: dict[str, str] = {}
    for page in pages:
        slug, node_type = page["slug"], page["type"]
        entry = {"slug": slug, "type": node_type}
        slug_key = slug.lower()
        if slug_key in by_alias and by_alias[slug_key]["slug"] != slug:
            sys.stderr.write(f"[warn] alias collision on slug key '{slug_key}' (overwriting {by_alias[slug_key]['slug']} with {slug})\n")
        by_alias[slug_key] = entry
        by_slug[slug] = node_type
        aliases = page["fm"].get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        for alias in aliases:
            if isinstance(alias, str) and alias.strip():
                key = alias.strip().lower()
                if key in by_alias and by_alias[key]["slug"] != slug:
                    sys.stderr.write(f"[warn] alias collision on key '{key}' (overwriting {by_alias[key]['slug']} with {slug})\n")
                by_alias[key] = entry
    return {"by_alias": by_alias, "by_slug": by_slug}


def main() -> None:
    vault = find_vault_root(Path(__file__).resolve().parent)
    wiki_dir = vault / "wiki"
    schema_path = vault / ".kb" / "schema.cypher"
    tmp_db = graph_db_path(vault).with_suffix(".kuzu.tmp")
    final_db = graph_db_path(vault)

    if not schema_path.exists():
        print(f"ERROR: {schema_path} not found", file=sys.stderr)
        sys.exit(1)

    if tmp_db.exists():
        remove_db(tmp_db)

    import kuzu  # noqa: PLC0415 — inside main so uv resolves dep first

    try:
        rel_combos = parse_rel_combos(schema_path)

        print("Collecting wiki pages...", file=sys.stderr)
        pages = collect_pages(wiki_dir)
        print(f"  {len(pages)} projectable pages", file=sys.stderr)

        print("Creating temp Kuzu DB...", file=sys.stderr)
        db = kuzu.Database(str(tmp_db))
        conn = kuzu.Connection(db)
        apply_schema(conn, schema_path)

        # Pass 1 — insert nodes
        print("Inserting nodes...", file=sys.stderr)
        slug_to_type: dict[str, str] = {}
        node_count = 0
        warn_count = 0
        for page in pages:
            ntype, slug = page["type"], page["slug"]
            props = build_node_props(page["fm"], ntype)
            cols = NODE_COLUMNS[ntype]
            param_clause = ", ".join(f"{c}: ${c}" for c in cols)
            try:
                conn.execute(f"CREATE (:{ntype} {{{param_clause}}})", parameters=props)
                slug_to_type[slug] = ntype
                node_count += 1
            except Exception as exc:
                print(f"[warn] node insert failed {ntype}/{slug}: {exc}", file=sys.stderr)
                warn_count += 1

        # Pass 2 — insert edges
        print("Inserting edges...", file=sys.stderr)
        edge_count = 0
        edge_skip = 0
        for page in pages:
            subj_type, subj_slug = page["type"], page["slug"]
            for edge_key in EDGE_KEYS:
                val = page["fm"].get(edge_key)
                if not val:
                    continue
                items: list = val if isinstance(val, list) else [val]
                for item in items:
                    if not isinstance(item, str):
                        continue
                    obj_slug = extract_wiki_slug(item)
                    if obj_slug is None:
                        edge_skip += 1
                        continue
                    obj_type = slug_to_type.get(obj_slug)
                    if obj_type is None:
                        edge_skip += 1
                        continue
                    if (subj_type, edge_key, obj_type) not in rel_combos:
                        edge_skip += 1
                        continue
                    q = (
                        f"MATCH (a:{subj_type} {{slug: $s}}), (b:{obj_type} {{slug: $o}}) "
                        f"CREATE (a)-[:{edge_key}]->(b)"
                    )
                    try:
                        conn.execute(q, parameters={"s": subj_slug, "o": obj_slug})
                        edge_count += 1
                    except Exception as exc:
                        print(f"[warn] edge insert failed ({subj_slug})-[{edge_key}]->({obj_slug}): {exc}", file=sys.stderr)
                        edge_skip += 1
                        warn_count += 1

        if warn_count > 0:
            del conn
            del db
            remove_db(tmp_db)
            print(f"ERROR: {warn_count} insert warning(s) — DB not committed. Fix warnings and re-run.", file=sys.stderr)
            sys.exit(1)

        del conn
        del db

        # Atomic rename: remove existing, move temp into place
        if final_db.exists():
            remove_db(final_db)
        shutil.move(str(tmp_db), str(final_db))

        print(f"nodes={node_count} edges={edge_count} skipped={edge_skip}")

        # Write alias lookup table
        aliases_path = vault / ".kb" / "aliases.json"
        aliases_tmp = aliases_path.with_suffix(".json.tmp")
        aliases_data = build_aliases(pages)
        aliases_tmp.write_text(json.dumps(aliases_data, ensure_ascii=False, indent=2), encoding="utf-8")
        aliases_tmp.replace(aliases_path)
        print(f"aliases={len(aliases_data['by_slug'])} pages indexed", file=sys.stderr)

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        if tmp_db.exists():
            remove_db(tmp_db)
        aliases_tmp = vault / ".kb" / "aliases.json.tmp"
        if aliases_tmp.exists():
            aliases_tmp.unlink()
        sys.exit(1)


if __name__ == "__main__":
    main()
