#!/usr/bin/env python3
# /// script
# dependencies = [
#   "kuzu",
#   "pyyaml",
# ]
# requires-python = ">=3.9,<3.14"
# ///
"""
kb-query entity-anchored search.
Usage: uv run .agents/skills/kb-query/query.py "<query>" [--hops 1] [--top-k 10] [--collections wiki raw]
Vault root auto-detected via CLAUDE.md walk.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import find_vault_root, graph_db_path  # noqa: E402


EDGE_WEIGHTS: dict[str, float] = {
    "decided": 3.0,
    "sources": 3.0,
    "authored": 3.0,
    "works_at": 3.0,
    "mentions": 0.2,
}

DEFAULT_EDGE_WEIGHT: float = 1.0

# Ordered heaviest-first so that the seen-set dedup keeps the highest-weight edge
# when a neighbour is reachable via multiple relationship types.
EDGE_KEYS = [
    "decided", "sources", "authored", "works_at",            # weight 3.0
    "attended", "owns", "reports_to",                        # weight 1.0
    "part_of", "instance_of", "related",
    "derived_from", "cites", "supersedes", "superseded_by",
    "contradicts", "confirms",
    "depends_on", "caused_by",
    "mentions",                                               # weight 0.2
]

_QMD_PATH_RE = re.compile(r"^qmd://(wiki|raw)/(.*?):\d+")
_QMD_SCORE_RE = re.compile(r"Score:\s+(\d+)%")




def load_aliases(aliases_path: Path) -> dict:
    """Load .kb/aliases.json. Returns {"by_alias": {...}, "by_slug": {...}}."""
    if not aliases_path.exists():
        return {"by_alias": {}, "by_slug": {}}
    return json.loads(aliases_path.read_text(encoding="utf-8"))


def find_matches(query: str, aliases: dict) -> list[dict]:
    """Greedy n-gram alias scan. Returns list of {phrase, slug, type} dicts."""
    by_alias = aliases.get("by_alias", {})
    tokens = re.findall(r"[\w-]+", query.lower())
    matches: list[dict] = []
    i = 0
    while i < len(tokens):
        matched = False
        for n in range(min(4, len(tokens) - i), 0, -1):
            phrase = " ".join(tokens[i : i + n])
            hit = by_alias.get(phrase)
            if hit:
                matches.append({"phrase": phrase, "slug": hit["slug"], "type": hit["type"]})
                i += n
                matched = True
                break
        if not matched:
            i += 1
    return matches


def parse_qmd_output(stdout: str) -> list[dict]:
    """Parse qmd query stdout → list of {path, score} dicts (score 0–100)."""
    results: list[dict] = []
    current_path: str | None = None
    for line in stdout.splitlines():
        m = _QMD_PATH_RE.match(line)
        if m:
            current_path = m.group(1) + "/" + m.group(2)
            results.append({"path": current_path, "score": 0})
            continue
        if current_path is not None:
            sm = _QMD_SCORE_RE.search(line)
            if sm and results:
                results[-1]["score"] = int(sm.group(1))
    return results


def graph_expand(
    db_path: Path,
    slug: str,
    node_type: str,
    by_slug: dict[str, str],
    hops: int = 1,
) -> list[dict]:
    """Return 1-hop graph neighbours of (node_type, slug) with edge type and weight."""
    import kuzu  # noqa: PLC0415
    db = kuzu.Database(str(db_path), read_only=True)
    conn = kuzu.Connection(db)
    seen: set[str] = set()
    neighbors: list[dict] = []
    for edge_type in EDGE_KEYS:
        weight = EDGE_WEIGHTS.get(edge_type, DEFAULT_EDGE_WEIGHT)
        q = f"MATCH (n:{node_type} {{slug: $s}})-[:{edge_type}]-(m) RETURN m.slug LIMIT 50"
        try:
            result = conn.execute(q, {"s": slug})
            while result.has_next():
                row = result.get_next()
                neighbor_slug = row[0]
                if not neighbor_slug or neighbor_slug in seen:
                    continue
                seen.add(neighbor_slug)
                neighbor_type = by_slug.get(neighbor_slug, "Unknown")
                neighbors.append({
                    "slug": neighbor_slug,
                    "type": neighbor_type,
                    "rel_type": edge_type,
                    "weight": weight,
                })
        except Exception:
            pass  # rel type not valid for this node type combination — expected
    return sorted(neighbors, key=lambda x: -x["weight"])


def print_entity_results(entity: dict, neighbors: list[dict]) -> None:
    print(f"ENTITY {entity['slug']} ({entity['type']}) [phrase: \"{entity['phrase']}\"]")
    for n in neighbors:
        print(f"  NEIGHBOR {n['slug']} ({n['type']}) via {n['rel_type']} weight={n['weight']}")


TYPE_TO_DIR: dict[str, str] = {
    "Person": "people", "Org": "orgs", "Project": "projects",
    "Topic": "topics", "Decision": "decisions", "Meeting": "meetings",
    "Source": "sources", "Artifact": "artifacts", "Event": "events",
}

_SKIP_PATH_PREFIXES = ("wiki/tofile/", "wiki/_inbox/", "wiki/log")


def run_qmd(query: str, collections: list[str], top_k: int) -> list[dict]:
    """Run `qmd query` subprocess → list of {path, score} dicts."""
    cmd = ["qmd", "query", query, "--top-k", str(top_k)]
    for c in collections:
        cmd += ["-c", c]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            return []
        return parse_qmd_output(proc.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def merge_and_print(
    entity_matches: list[dict],
    all_neighbors: dict[str, list[dict]],
    qmd_results: list[dict],
) -> None:
    """Print ENTITY/NEIGHBOR blocks then CANDIDATE lines (graph first, then qmd-only)."""
    graph_paths: dict[str, str] = {}  # path → annotation

    for entity in entity_matches:
        neighbors = all_neighbors.get(entity["slug"], [])
        print_entity_results(entity, neighbors)
        for n in neighbors:
            type_dir = TYPE_TO_DIR.get(n["type"], "unknown")
            wiki_path = f"wiki/{type_dir}/{n['slug']}.md"
            if wiki_path not in graph_paths:
                graph_paths[wiki_path] = f"graph:{n['rel_type']} w={n['weight']}"

    # Print graph candidates first
    for path, annotation in graph_paths.items():
        if not any(path.startswith(p) for p in _SKIP_PATH_PREFIXES):
            print(f"CANDIDATE {path} [{annotation}]")

    # Then qmd-only results
    for r in qmd_results:
        path = r["path"]
        if path in graph_paths:
            continue
        if any(path.startswith(p) for p in _SKIP_PATH_PREFIXES):
            continue
        print(f"CANDIDATE {path} [qmd:{r['score']}%]")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="kb-query entity-anchored search")
    parser.add_argument("query", help="Query string")
    parser.add_argument("--hops", type=int, default=1)
    parser.add_argument("--top-k", type=int, default=10)  # consumed by qmd stage
    parser.add_argument("--collections", nargs="+", default=["wiki", "raw"])  # consumed by qmd stage
    args = parser.parse_args()

    vault = find_vault_root(Path(__file__).resolve().parent)
    aliases = load_aliases(vault / ".kb" / "aliases.json")
    db_path = graph_db_path(vault)

    matches = find_matches(args.query, aliases)

    all_neighbors: dict[str, list[dict]] = {}
    if matches:
        for entity in matches:
            all_neighbors[entity["slug"]] = graph_expand(
                db_path, entity["slug"], entity["type"], aliases["by_slug"], args.hops
            )
    else:
        print("NO_ENTITY_MATCH")

    qmd_results = run_qmd(args.query, args.collections, args.top_k)
    merge_and_print(matches, all_neighbors, qmd_results)


if __name__ == "__main__":
    main()
