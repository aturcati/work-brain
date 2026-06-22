#!/usr/bin/env python3
# /// script
# dependencies = ["pyyaml", "ruamel.yaml"]
# requires-python = ">=3.9,<3.14"
# ///
"""
kb-graph promote — promote edges from wiki/_inbox/edges.md into canonical frontmatter.

Usage:
  uv run .agents/skills/kb-graph/promote.py [--threshold 0.7] [--apply]

Default (dry-run): print promotable edges with proposed YAML additions.
--apply: write changes, clean edges.md, append to wiki/log.md.
Vault root auto-detected: walks up from __file__ until CLAUDE.md found.
"""
import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timezone
from ruamel.yaml import YAML as _YAML
import io as _io

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import TYPE_TO_DIR, find_vault_root, parse_frontmatter  # noqa: E402


# ─── Types ───────────────────────────────────────────────────

@dataclass
class Edge:
    subject: str
    predicate: str
    object_: str
    confidence: float
    evidence: str
    timestamp: str
    source_path: str
    raw_line: str = field(repr=False)


# ─── Parser ──────────────────────────────────────────────────

_HEADER_RE = re.compile(r'^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) · (.+?)\s*$')
_EDGE_RE   = re.compile(r'^- \((\S+),\s+(\S+),\s+(\S+),\s+([\d.]+),\s+"(.*)"\)\s*$')


def parse_edges_md(edges_path: Path) -> list[Edge]:
    """Parse wiki/_inbox/edges.md → list of Edge objects."""
    edges: list[Edge] = []
    current_ts = ""
    current_src = ""
    for line in edges_path.read_text(encoding="utf-8").splitlines():
        m = _HEADER_RE.match(line)
        if m:
            current_ts, current_src = m.group(1), m.group(2).strip()
            continue
        m = _EDGE_RE.match(line)
        if m:
            if not current_ts:  # orphan edge — no header seen yet, skip
                continue
            edges.append(Edge(
                subject=m.group(1),
                predicate=m.group(2),
                object_=m.group(3),
                confidence=float(m.group(4)),
                evidence=m.group(5),
                timestamp=current_ts,
                source_path=current_src,
                raw_line=line,
            ))
    return edges


# ─── Canonical slug resolver ─────────────────────────────────

_SKIP_DIRS  = {"_inbox", "tofile", "archive", "log-archive"}
_SKIP_FILES = {"index.md", "overview.md"}


def build_canonical_map(wiki_dir: Path) -> dict[str, tuple[str, Path]]:
    """Return {slug: (type, path)} for all non-stub canonical wiki pages."""
    result: dict[str, tuple[str, Path]] = {}
    for md in wiki_dir.rglob("*.md"):
        rel_parts = md.relative_to(wiki_dir).parts
        if any(p in _SKIP_DIRS for p in rel_parts[:-1]):
            continue
        if rel_parts[-1] in _SKIP_FILES or rel_parts[-1] == "log.md":
            continue
        fm = parse_frontmatter(md)
        if not fm:
            continue
        slug = str(fm.get("slug", "")).strip()
        ntype = str(fm.get("type", "")).strip()
        if slug and ntype in TYPE_TO_DIR:
            result[slug] = (ntype, md)
    return result


# ─── Filter + report ─────────────────────────────────────────

def filter_promotable(
    edges: list[Edge],
    canonical: dict[str, tuple[str, Path]],
    threshold: float,
) -> list[Edge]:
    """Return edges that pass confidence threshold AND have both slugs resolved."""
    result = []
    for e in edges:
        if e.confidence < threshold:
            continue
        if e.subject not in canonical:
            continue
        if e.object_ not in canonical:
            continue
        result.append(e)
    return result


def _wikilink(slug: str, canonical: dict[str, tuple[str, Path]]) -> str:
    ntype, _ = canonical[slug]
    dir_ = TYPE_TO_DIR[ntype]
    return f"[[wiki/{dir_}/{slug}]]"


def format_dry_run_report(
    promotable: list[Edge],
    canonical: dict[str, tuple[str, Path]],
) -> str:
    if not promotable:
        return "promote: nothing to promote (0 qualifying edges)"
    lines = [f"promote: {len(promotable)} edge(s) would be promoted\n"]
    for e in promotable:
        link = _wikilink(e.object_, canonical)
        lines.append(
            f"  {e.subject}  --[{e.predicate}]-->  {e.object_}\n"
            f"    confidence: {e.confidence}  source: {e.source_path}\n"
            f"    evidence: \"{e.evidence}\"\n"
            f"    + {e.subject}.{e.predicate}: {link}\n"
        )
    return "\n".join(lines)


# ─── Apply ───────────────────────────────────────────────────

def _read_page(path: Path) -> tuple[object, str]:
    """Return (ruamel CommentedMap frontmatter, full_text). Raises ValueError if no valid frontmatter."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"No valid frontmatter in {path}")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"No valid frontmatter in {path}")
    _yaml = _YAML()
    _yaml.preserve_quotes = True
    fm = _yaml.load(parts[1])
    if not isinstance(fm, dict):
        raise ValueError(f"Frontmatter is not a dict in {path}")
    return fm, text


def _write_page(path: Path, fm: object, original_text: str) -> None:
    parts = original_text.split("---", 2)
    _yaml = _YAML()
    buf = _io.StringIO()
    _yaml.dump(fm, buf)
    new_yaml = buf.getvalue()
    path.write_text(f"---\n{new_yaml}---{parts[2]}", encoding="utf-8")


def _add_edge_to_fm(fm: dict, predicate: str, link: str) -> bool:
    """Add link to fm[predicate] list. Returns True if changed."""
    current = fm.get(predicate)
    if current is None:
        lst: list = []
    elif isinstance(current, list):
        lst = [str(v) for v in current]
    else:
        lst = [str(current)]
    if link in lst:
        return False
    lst.append(link)
    fm[predicate] = lst
    return True


def apply_promotions(
    promotable: list[Edge],
    canonical: dict[str, tuple[str, Path]],
    edges_md: Path,
    log_md: Path,
) -> int:
    """Apply promotable edges. Returns count of edges actually written."""
    promoted_lines: set[str] = set()
    written = 0

    for e in promotable:
        _subj_type, subj_path = canonical[e.subject]
        link = _wikilink(e.object_, canonical)
        fm, text = _read_page(subj_path)
        changed = _add_edge_to_fm(fm, e.predicate, link)
        if changed:
            _write_page(subj_path, fm, text)
            written += 1
        promoted_lines.add(e.raw_line)

    if promoted_lines:
        original = edges_md.read_text(encoding="utf-8")
        kept = [
            line for line in original.splitlines()
            if line not in promoted_lines
        ]
        edges_md.write_text("\n".join(kept) + "\n", encoding="utf-8")

    if written > 0:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        entry = f"\n## [{ts}] kb-graph promote | {written} edge(s) promoted into frontmatter\n"
        with log_md.open("a", encoding="utf-8") as f:
            f.write(entry)

    return written


# ─── CLI ─────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Promote edges from _inbox/edges.md into frontmatter.")
    parser.add_argument("--threshold", type=float, default=0.7, help="Minimum confidence (default 0.7)")
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    args = parser.parse_args()

    vault = find_vault_root(Path(__file__).resolve().parent)
    edges_md = vault / "wiki" / "_inbox" / "edges.md"
    log_md   = vault / "wiki" / "log.md"

    if not edges_md.exists():
        print("promote: edges.md not found — nothing to do")
        return

    edges = parse_edges_md(edges_md)
    canonical = build_canonical_map(vault / "wiki")
    promotable = filter_promotable(edges, canonical, args.threshold)

    if not args.apply:
        unresolvable = [
            e for e in edges
            if e.confidence >= args.threshold
            and (e.subject not in canonical or e.object_ not in canonical)
        ]
        print(format_dry_run_report(promotable, canonical))
        if unresolvable:
            print(f"\nSkipped (unresolved slugs, confidence >= {args.threshold}):")
            for e in unresolvable:
                missing = []
                if e.subject not in canonical:
                    missing.append(f"subject '{e.subject}'")
                if e.object_ not in canonical:
                    missing.append(f"object '{e.object_}'")
                print(f"  ({e.subject}, {e.predicate}, {e.object_}) — {', '.join(missing)} not in wiki/")
        print("\nRe-run with --apply to write changes.")
        return

    n = apply_promotions(promotable, canonical, edges_md, log_md)
    print(f"promote: {n} edge(s) promoted. Re-run /kb-graph project to refresh Kuzu.")


if __name__ == "__main__":
    main()
