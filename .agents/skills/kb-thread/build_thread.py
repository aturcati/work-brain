#!/usr/bin/env python3
# /// script
# dependencies = ["kuzu", "pyyaml"]
# requires-python = ">=3.9,<3.14"
# ///
"""
kb-thread build_thread - gather graph + qmd inputs for narrative thread.

Usage:
  uv run .agents/skills/kb-thread/build_thread.py <slug> [--top-k 10]

Read-only. Prints a structured markdown block for Claude to weave into a thread.
Vault root auto-detected by walking up for CLAUDE.md.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (  # noqa: E402
    TYPE_TO_DIR, SKIP_DERIVED as SKIP_DIRS,
    find_vault_root, graph_db_path, parse_frontmatter,
)

SKIP_FILES = {"index.md", "overview.md", "log.md"}

_LINK_RE = re.compile(r"\[\[(raw/[^\]|#]+?)(?:\.md)?(?:[|#][^\]]*)?\]\]")
_QMD_PATH_RE = re.compile(r"^qmd://(wiki|raw)/([^:]+):(\d+)(?:\s+.*)?$")
_QMD_SCORE_RE = re.compile(r"Score:\s+(\d+)%")


class BuildThreadError(Exception):
    pass




def resolve_entity(vault: Path, slug: str) -> tuple[str, Path]:
    wiki = vault / "wiki"
    for md in wiki.rglob("*.md"):
        rel_parts = md.relative_to(wiki).parts
        if rel_parts[-1] in SKIP_FILES:
            continue
        if any(part in SKIP_DIRS for part in rel_parts[:-1]):
            continue
        fm = parse_frontmatter(md)
        if not fm:
            continue
        if str(fm.get("slug", "")).strip() != slug:
            continue
        node_type = str(fm.get("type", "")).strip()
        if node_type not in TYPE_TO_DIR:
            raise BuildThreadError(f"page {md} has unknown type: {node_type!r}")
        return node_type, md
    raise BuildThreadError(f"no canonical page found with slug={slug}")


def read_sources(page_path: Path) -> list[str]:
    fm = parse_frontmatter(page_path)
    if not fm:
        return []
    out: list[str] = []
    for source in fm.get("sources") or []:
        match = _LINK_RE.match(str(source).strip().strip('"').strip("'"))
        if not match:
            continue
        path = match.group(1)
        if not path.endswith(".md"):
            path += ".md"
        out.append(path)
    return out


def dedupe_citations(*lists: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for citations in lists:
        for citation in citations:
            if citation in seen:
                continue
            seen.add(citation)
            out.append(citation)
    return out


def graph_1hop(vault: Path, node_type: str, slug: str) -> list[dict]:
    db_path = graph_db_path(vault)
    if not db_path.exists():
        return []

    kb_query_path = vault / ".claude" / "skills" / "kb-query"
    sys.path.insert(0, str(kb_query_path))
    try:
        from query import graph_expand, load_aliases
    finally:
        sys.path.pop(0)

    # Read-only helper — degrade to empty result on any aliases/graph error
    # (malformed JSON, missing keys, Kuzu schema mismatch) rather than crash.
    try:
        aliases = load_aliases(vault / ".kb" / "aliases.json")
        by_slug = aliases.get("by_slug")
        if not isinstance(by_slug, dict):
            by_slug = {
                entry["slug"]: entry["type"]
                for entry in aliases.get("entities", [])
                if "slug" in entry and "type" in entry
            }
        return graph_expand(db_path, slug, node_type, by_slug, hops=1)
    except (json.JSONDecodeError, KeyError, OSError):
        return []


def qmd_search(query: str, top_k: int = 10) -> list[dict]:
    cmd = ["qmd", "search", query, "--top-k", str(top_k), "-c", "wiki", "-c", "raw"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    if proc.returncode != 0:
        return []

    hits: list[dict] = []
    current: dict | None = None
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        path_match = _QMD_PATH_RE.match(stripped)
        if path_match:
            current = {"path": f"{path_match.group(1)}/{path_match.group(2)}", "score": 0}
            inline_score = _QMD_SCORE_RE.search(stripped)
            if inline_score:
                current["score"] = int(inline_score.group(1))
            hits.append(current)
            continue
        if current is not None:
            score_match = _QMD_SCORE_RE.search(stripped)
            if score_match:
                current["score"] = int(score_match.group(1))
    return hits[:top_k]


def format_inputs(
    entity: dict,
    neighbors: list[dict],
    citations: list[str],
    qmd_hits: list[dict],
) -> str:
    lines: list[str] = [
        "## Entity",
        "",
        f"- **Type:** {entity['type']}",
        f"- **Slug:** {entity['slug']}",
        "",
        "## Graph 1-hop neighbours",
        "",
    ]

    if neighbors:
        for neighbor in sorted(neighbors, key=lambda item: (-item["weight"], item["slug"])):
            direction = neighbor.get("direction", "?")
            lines.append(
                f"- `{neighbor['slug']}` ({neighbor['type']}) - "
                f"`{neighbor['rel_type']}` weight={neighbor['weight']} dir={direction}"
            )
    else:
        lines.append("(none)")

    lines.extend(["", "## Citations", ""])
    if citations:
        lines.extend(f"- [[{citation}]]" for citation in citations)
    else:
        lines.append("(none)")

    lines.extend(["", "## qmd top-10 hits", ""])
    if qmd_hits:
        lines.extend(f"- [[{hit['path']}]] - score {hit['score']}%" for hit in qmd_hits)
    else:
        lines.append("(none)")

    lines.extend([
        "",
        "## Drafting guidance",
        "",
        (
            "Weave the above into a narrative thread page. Cite every claim with either a "
            "wiki page or a raw archive path. Suggested section order: Overview, Key "
            "sources, Related entities, Open questions. Keep the page under 2000 tokens "
            "or `/kb-lint` will flag it for refactor."
        ),
    ])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("slug")
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args(argv)

    try:
        vault = find_vault_root(Path(__file__).parent)
        node_type, page_path = resolve_entity(vault, args.slug)
    except (BuildThreadError, FileNotFoundError) as exc:
        print(f"build_thread: error: {exc}", file=sys.stderr)
        return 2

    entity_sources = read_sources(page_path)
    neighbors = graph_1hop(vault, node_type, args.slug)
    neighbor_source_lists: list[list[str]] = []
    for neighbor in neighbors:
        neighbor_dir = TYPE_TO_DIR.get(neighbor.get("type", ""))
        if not neighbor_dir:
            continue
        neighbor_path = vault / "wiki" / neighbor_dir / f"{neighbor['slug']}.md"
        if neighbor_path.exists():
            neighbor_source_lists.append(read_sources(neighbor_path))

    citations = dedupe_citations(entity_sources, *neighbor_source_lists)
    hits = qmd_search(args.slug.replace("-", " "), top_k=args.top_k)
    print(format_inputs(
        {"slug": args.slug, "type": node_type},
        neighbors,
        citations,
        hits,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
