"""kb-lint core — constants, page collection, wikilink helpers.

Imported by lint.py (orchestrator) and checks.py. Not run directly;
dependencies come from lint.py's PEP 723 header.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (  # noqa: E402
    NODE_TYPES,  # noqa: F401 — re-exported for checks.py
    SKIP_STUBS as SKIP_DIRS,
    SKIP_NAMES,
    find_vault_root,  # noqa: F401 — re-exported for lint.py (from core import *)
    parse_frontmatter_text,  # noqa: F401 — re-exported for checks.py
)

# ── Constants ──────────────────────────────────────────────────────────────

ALLOWED_KEYS = {
    # Identity
    "type", "slug", "aliases", "created", "modified", "last_verified",
    "status", "tags", "confidence",
    # Structural
    "part_of", "instance_of", "related",
    # Agentic
    "works_at", "attended", "authored", "owns", "reports_to",
    # Epistemic
    "sources", "derived_from", "cites", "supersedes", "superseded_by",
    "contradicts", "confirms",
    # Causal
    "depends_on", "caused_by", "decided", "mentions",
    # Source / Meeting channel specific
    "date", "path", "channel", "captured_at", "provider",
    # Meeting specific
    "has_transcript", "organizer", "participants",
}

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

STALE_DAYS = 90
ACTION_STALE_DAYS = 30
JOURNAL_BACKLOG_DAYS = 30
TOKEN_LIMIT = 2000          # approx tokens; 1 token ≈ 4 chars
LOG_LINE_LIMIT = 1000
LOG_SIZE_LIMIT = 1024 * 1024  # 1 MB
EDGES_ENTRY_LIMIT = 500
EDGES_SIZE_LIMIT = 500 * 1024  # 500 KB


# ── Core helpers ───────────────────────────────────────────────────────────

def extract_body(raw_text: str) -> str:
    """Return text after the closing --- of frontmatter."""
    if raw_text.startswith("---"):
        parts = raw_text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return raw_text.strip()


def parse_wikilinks(text: str) -> list[str]:
    """Extract [[...]] wikilink targets, strip .md extension, return paths.

    Obsidian piped aliases ([[path|alias]]) and heading anchors ([[path#sec]])
    keep only the path part — consistent with kb-graph/project.py and
    common.wikilink_pattern, which both already tolerate `|`/`#`.
    """
    results = []
    for m in _WIKILINK_RE.finditer(text):
        target = m.group(1).strip()
        target = target.split("|", 1)[0].split("#", 1)[0].strip()
        if not target:  # bare same-page heading link [[#section]]
            continue
        if target.endswith(".md"):
            target = target[:-3]
        results.append(target)
    return results


def _all_wikilink_text(page: dict) -> str:
    """Concatenate all text that might contain wikilinks for a page."""
    parts = [page["body"]]
    fm = page.get("fm") or {}
    for val in fm.values():
        if isinstance(val, str):
            parts.append(val)
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    parts.append(item)
    return " ".join(parts)


def build_link_graph(pages: list[dict]) -> dict[str, set[str]]:
    """Return inbound link map: slug → set of slugs that link to it."""
    inbound: dict[str, set[str]] = {p["slug"]: set() for p in pages if p["slug"]}
    for page in pages:
        if not page["slug"]:
            continue
        for link in parse_wikilinks(_all_wikilink_text(page)):
            target_slug = link.split("/")[-1]
            if target_slug not in inbound:
                inbound[target_slug] = set()
            inbound[target_slug].add(page["slug"])
    return inbound


def collect_pages(wiki_dir: Path) -> list[dict]:
    """Collect all wiki pages (excluding stubs/inbox/log/index/overview).
    Pages with YAML parse errors have fm=None."""
    pages = []
    for md_path in sorted(wiki_dir.rglob("*.md")):
        rel = md_path.relative_to(wiki_dir)
        parts = rel.parts
        if any(p in SKIP_DIRS for p in parts[:-1]):
            continue
        fname = parts[-1]
        if fname in SKIP_NAMES or fname.startswith("log"):
            continue
        raw_text = md_path.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter_text(raw_text)
        body = extract_body(raw_text)
        pages.append({
            "path": md_path,
            "type": str(fm.get("type", "")) if fm else "",
            "slug": str(fm.get("slug", "")) if fm else "",
            "fm": fm,   # None if YAML parse error
            "body": body,
        })
    return pages


# ── Finding helper ────────────────────────────────────────────────────────

def _finding(check: str, path, message: str) -> dict:
    return {"check": check, "path": str(path), "message": message}


