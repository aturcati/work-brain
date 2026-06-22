#!/usr/bin/env python3
# /// script
# dependencies = ["kuzu", "pyyaml"]
# requires-python = ">=3.9,<3.14"
# ///
"""
kb-graph canvas — write Obsidian Canvas JSON for entity + 1-hop neighbourhood.

Usage:
  uv run .agents/skills/kb-graph/canvas.py <Type> <slug> [--apply]

Default: dry-run prints `N nodes, M edges`. `--apply` writes `wiki/_maps/<slug>.canvas`.
Vault root auto-detected (walks up for CLAUDE.md).
"""
import argparse
import hashlib
import json
import math
import shutil
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (  # noqa: E402
    TYPE_TO_DIR, EDGE_WEIGHTS, DEFAULT_EDGE_WEIGHT,
    SKIP_DERIVED as SKIP_DIRS,
    find_vault_root, graph_db_path, acquire_inbox_lock, release_inbox_lock,
    parse_frontmatter,
)

TYPE_COLORS: dict[str, str] = {
    "Person":   "5",
    "Org":      "2",
    "Project":  "4",
    "Topic":    "3",
    "Decision": "6",
    "Meeting":  "1",
    "Source":   "4",
    "Artifact": "2",
    "Event":    "1",
}

# Heaviest-first — dedup keeps highest-weight edge when node is reachable via multiple types
EDGE_KEYS = [
    "decided", "sources", "authored", "works_at",
    "attended", "owns", "reports_to",
    "part_of", "instance_of", "related",
    "derived_from", "cites", "supersedes", "superseded_by",
    "contradicts", "confirms",
    "depends_on", "caused_by",
    "mentions",
]

SKIP_FILES = {"index.md", "overview.md", "log.md"}


class CanvasError(Exception):
    pass


@dataclass
class CanvasResult:
    slug: str
    type: str
    n_neighbors: int
    output_path: Path
    applied: bool = False




def find_node_type(vault: Path, slug: str) -> tuple[str, Path]:
    """Return (type, path) of the canonical wiki page with this slug."""
    wiki = vault / "wiki"
    for md in sorted(wiki.rglob("*.md")):
        rel = md.relative_to(wiki).parts
        if any(p in SKIP_DIRS for p in rel[:-1]):
            continue
        if rel[-1] in SKIP_FILES:
            continue
        fm = parse_frontmatter(md)
        if not fm:
            continue
        if str(fm.get("slug", "")).strip() == slug:
            node_type = str(fm.get("type", "")).strip()
            if node_type not in TYPE_TO_DIR:
                raise CanvasError(f"page {md} has unknown type: {node_type!r}")
            return node_type, md
    raise CanvasError(f"no canonical page found with slug={slug}")


def _collect_neighbors(
    conn,
    query: str,
    slug: str,
    edge_type: str,
    weight: float,
    direction: str,
    by_slug: dict[str, str],
    seen: set[str],
    out: list[dict],
) -> None:
    """Execute one direction of the neighbour query and append results to `out`.

    Kuzu raises RuntimeError when the rel table doesn't exist for a given
    (node_type, edge_type) pair — expected during incremental graph builds.
    Same suppression pattern as kb-query/query.py:132.
    """
    try:
        result = conn.execute(query, {"s": slug})
    except RuntimeError:
        return
    while result.has_next():
        neighbor_slug = result.get_next()[0]
        if not neighbor_slug or neighbor_slug in seen:
            continue
        neighbor_type = by_slug.get(neighbor_slug, "Unknown")
        if neighbor_type not in TYPE_TO_DIR:
            continue
        seen.add(neighbor_slug)
        out.append({
            "slug": neighbor_slug, "type": neighbor_type, "rel_type": edge_type,
            "weight": weight, "direction": direction,
            "path": Path(f"wiki/{TYPE_TO_DIR[neighbor_type]}/{neighbor_slug}.md"),
        })


def graph_neighbors(
    db_path: Path,
    node_type: str,
    slug: str,
    by_slug: dict[str, str],
) -> list[dict]:
    """Return deduped 1-hop neighbours with slug, type, rel_type, weight, direction, path."""
    if not db_path.exists():
        return []
    import kuzu  # noqa: PLC0415
    db = kuzu.Database(str(db_path), read_only=True)
    conn = kuzu.Connection(db)
    seen: set[str] = set()
    out: list[dict] = []
    for edge_type in EDGE_KEYS:
        weight = EDGE_WEIGHTS.get(edge_type, DEFAULT_EDGE_WEIGHT)
        q_out = f"MATCH (n:{node_type} {{slug: $s}})-[:{edge_type}]->(m) RETURN m.slug LIMIT 50"
        _collect_neighbors(conn, q_out, slug, edge_type, weight, "out", by_slug, seen, out)
        q_in = f"MATCH (m)-[:{edge_type}]->(n:{node_type} {{slug: $s}}) RETURN m.slug LIMIT 50"
        _collect_neighbors(conn, q_in, slug, edge_type, weight, "in", by_slug, seen, out)
    return out


def _by_slug_map(vault: Path) -> dict[str, str]:
    """Build {slug: type} for all canonical pages."""
    out: dict[str, str] = {}
    wiki = vault / "wiki"
    for md in sorted(wiki.rglob("*.md")):
        rel = md.relative_to(wiki).parts
        if any(p in SKIP_DIRS for p in rel[:-1]):
            continue
        if rel[-1] in SKIP_FILES:
            continue
        fm = parse_frontmatter(md)
        if not fm:
            continue
        slug = str(fm.get("slug", "")).strip()
        node_type = str(fm.get("type", "")).strip()
        if slug and node_type in TYPE_TO_DIR:
            out[slug] = node_type
    return out


def compute_layout(neighbors: list[dict], radius: float = 350.0) -> list[dict]:
    """Place neighbours on a circle. Sort heaviest first, ties alphabetically."""
    sorted_neighbors = sorted(neighbors, key=lambda n: (-n["weight"], n["slug"]))
    if not sorted_neighbors:
        return []
    out: list[dict] = []
    count = len(sorted_neighbors)
    for i, neighbor in enumerate(sorted_neighbors):
        angle = 2 * math.pi * i / count
        x = round(radius * math.cos(angle))
        y = round(radius * math.sin(angle))
        out.append({**neighbor, "x": x, "y": y})
    return out


def _node_id(path: Path) -> str:
    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:8]


def _edge_id(from_id: str, rel: str, to_id: str) -> str:
    return hashlib.sha256(f"{from_id}-{rel}-{to_id}".encode("utf-8")).hexdigest()[:8]


def build_canvas_json(seed: dict, neighbors_with_pos: list[dict]) -> dict:
    """Return Obsidian Canvas JSON dict for seed + 1-hop neighbours."""
    seed_path_str = str(seed["path"]).replace("\\", "/")
    seed_id = _node_id(Path(seed_path_str))
    nodes = [{
        "id": seed_id,
        "type": "file",
        "file": seed_path_str,
        "x": 0,
        "y": 0,
        "width": 240,
        "height": 80,
        "color": TYPE_COLORS.get(seed["type"], "0"),
    }]
    edges = []
    for neighbor in neighbors_with_pos:
        neighbor_path_str = str(neighbor["path"]).replace("\\", "/")
        neighbor_id = _node_id(Path(neighbor_path_str))
        nodes.append({
            "id": neighbor_id,
            "type": "file",
            "file": neighbor_path_str,
            "x": neighbor["x"],
            "y": neighbor["y"],
            "width": 240,
            "height": 80,
            "color": TYPE_COLORS.get(neighbor["type"], "0"),
        })
        if neighbor["direction"] == "out":
            edges.append({
                "id": _edge_id(seed_id, neighbor["rel_type"], neighbor_id),
                "fromNode": seed_id, "fromSide": "right",
                "toNode": neighbor_id, "toSide": "left",
                "label": neighbor["rel_type"],
            })
        else:
            edges.append({
                "id": _edge_id(neighbor_id, neighbor["rel_type"], seed_id),
                "fromNode": neighbor_id, "fromSide": "right",
                "toNode": seed_id, "toSide": "left",
                "label": neighbor["rel_type"],
            })
    return {"nodes": nodes, "edges": edges}


def apply_canvas(
    vault: Path,
    type_: str,
    slug: str,
    dry_run: bool,
    today: str | None = None,
) -> CanvasResult:
    if type_ not in TYPE_TO_DIR:
        raise CanvasError(f"unknown type: {type_}")
    canonical_type, canonical_path = find_node_type(vault, slug)
    if canonical_type != type_:
        raise CanvasError(f"slug {slug!r} is type {canonical_type}, not {type_}")

    by_slug = _by_slug_map(vault)
    db_path = graph_db_path(vault)
    neighbors = graph_neighbors(db_path, type_, slug, by_slug)
    laid_out = compute_layout(neighbors)
    seed = {
        "slug": slug,
        "type": type_,
        "path": canonical_path.relative_to(vault),
    }
    data = build_canvas_json(seed, laid_out)

    output_path = vault / "wiki" / "_maps" / f"{slug}.canvas"
    result = CanvasResult(
        slug=slug, type=type_, n_neighbors=len(neighbors), output_path=output_path,
    )

    print(f"\ncanvas: {type_}/{slug}")
    print(f"  output:    {output_path.relative_to(vault)}")
    print(f"  nodes:     {len(data['nodes'])} (1 seed + {len(neighbors)} neighbours)")
    print(f"  edges:     {len(data['edges'])}")

    if dry_run:
        return result

    try:
        lock = acquire_inbox_lock(vault)
    except TimeoutError as exc:
        raise CanvasError(str(exc)) from exc
    txn_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]
    staging = vault / ".kb-staging" / txn_id
    staging.mkdir(parents=True, exist_ok=True)
    commit_ok = False
    try:
        staged = staging / f"{slug}.canvas"
        staged.write_text(json.dumps(data, indent=2), encoding="utf-8")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staged), str(output_path))
        log_path = vault / "wiki" / "log.md"
        if log_path.exists():
            with log_path.open("a", encoding="utf-8") as f:
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
                f.write(f"\n## [{ts}] kb-graph canvas | {type_}/{slug} -> wiki/_maps/{slug}.canvas\n")
        commit_ok = True
    finally:
        if commit_ok:
            shutil.rmtree(staging, ignore_errors=True)
        else:
            print(
                f"\ncanvas: ERROR mid-commit. Staging preserved at: {staging.relative_to(vault)}",
                file=sys.stderr,
            )
        release_inbox_lock(lock)

    result.applied = True
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("type")
    parser.add_argument("slug")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    vault = find_vault_root(Path(__file__).parent)
    try:
        result = apply_canvas(vault, args.type, args.slug, dry_run=not args.apply)
    except CanvasError as exc:
        print(f"canvas: error: {exc}", file=sys.stderr)
        return 2
    if not args.apply:
        print("\n(dry-run — re-run with --apply to commit)")
    else:
        print(f"\ncanvas: applied. Open in Obsidian: {result.output_path.relative_to(vault)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
