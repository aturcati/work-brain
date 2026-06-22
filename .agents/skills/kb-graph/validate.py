#!/usr/bin/env python3
# /// script
# dependencies = [
#   "pyyaml",
# ]
# requires-python = ">=3.9,<3.14"
# ///
"""
kb-graph validate — report-only checks over wiki/ frontmatter.
Usage: uv run .agents/skills/kb-graph/validate.py
Vault root auto-detected: walks up from __file__ until CLAUDE.md found.
Exit 0 if no issues, exit 1 if any.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (  # noqa: E402
    EDGE_KEYS, EDGE_KEYS_SET, SKIP_STUBS as SKIP_DIRS, SKIP_NAMES,
    NODE_TYPES, find_vault_root, parse_frontmatter,
)

IDENTITY_KEYS = {
    "type", "slug", "aliases", "created", "modified", "last_verified",
    "status", "tags", "confidence",
    # Source thin-schema
    "date", "path", "channel", "captured_at", "provider", "source",
    "participants", "original_ref",
}

KNOWN_KEYS = EDGE_KEYS_SET | IDENTITY_KEYS


# ── helpers ───────────────────────────────────────────────────────────────────

def extract_wiki_slug(value: str) -> str | None:
    """Return slug from [[wiki/<type>/<slug>]] or [[wiki/<type>/<slug>|alias]].
    Returns None if not a wiki wikilink."""
    m = re.fullmatch(
        r"\[\[wiki/[^/\]]+/([^\]/|]+?)(?:\.md)?(?:\|[^\]]*)?\]\]",
        value.strip(),
    )
    return m.group(1) if m else None


def collect_pages(wiki_dir: Path, issues: list[str]) -> list[dict]:
    pages = []
    for md_path in sorted(wiki_dir.rglob("*.md")):
        rel  = md_path.relative_to(wiki_dir)
        parts = rel.parts
        # SKIP_DIRS and SKIP_NAMES checks must come BEFORE any parse-error reporting
        if any(p in SKIP_DIRS for p in parts[:-1]):
            continue
        fname = parts[-1]
        if fname in SKIP_NAMES or fname.startswith("log"):
            continue
        fm = parse_frontmatter(md_path)
        if fm is None:
            issues.append(f"[parse-error] wiki/{rel}: invalid or missing frontmatter")
            continue
        node_type = str(fm.get("type", ""))
        slug = str(fm.get("slug", ""))
        if node_type and node_type not in NODE_TYPES:
            issues.append(f"[parse-error] wiki/{rel}: unknown type={node_type!r}")
            continue
        if not slug:
            issues.append(f"[parse-error] wiki/{rel}: missing slug")
            continue
        if not node_type:
            issues.append(f"[parse-error] wiki/{rel}: invalid or missing frontmatter")
            continue
        pages.append({"path": md_path, "rel": str(rel), "type": node_type, "slug": slug, "fm": fm})
    return pages


def has_wikilink(values: list) -> bool:
    """Return True if at least one item in values is a wikilink."""
    return any(
        isinstance(v, str) and extract_wiki_slug(v) is not None
        for v in values
    )


def _normalise_tags(value) -> list[str]:
    if isinstance(value, str):
        raw_tags = [value]
    elif isinstance(value, list):
        raw_tags = value
    else:
        raw_tags = []
    return [tag.strip().lower() for tag in raw_tags if isinstance(tag, str)]


def person_requires_works_at(fm: dict) -> bool:
    """External people can be valid without a works_at edge."""
    return "external" not in _normalise_tags(fm.get("tags"))


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    vault    = find_vault_root(Path(__file__).resolve().parent)
    wiki_dir = vault / "wiki"

    issues_parse:    list[str] = []

    print("Collecting wiki pages...", file=sys.stderr)
    pages = collect_pages(wiki_dir, issues_parse)
    print(f"  {len(pages)} pages with frontmatter", file=sys.stderr)

    # Pre-build set of all *.md stems under wiki/ (for dangling-link check)
    all_stems: set[str] = {p.stem for p in wiki_dir.rglob("*.md")}

    issues_unknown:  list[str] = []
    issues_dangling: list[str] = []
    issues_orphan:   list[str] = []

    for page in pages:
        rel  = page["rel"]
        fm   = page["fm"]
        ptype = page["type"]
        slug  = page["slug"]

        # ── Check 1: unknown edge keys ─────────────────────────────────────
        for key in fm:
            if key not in KNOWN_KEYS:
                issues_unknown.append(
                    f"[unknown-edge] wiki/{rel}: key={key}"
                )

        # ── Check 2: dangling wikilinks ────────────────────────────────────
        for edge_key in EDGE_KEYS:
            val = fm.get(edge_key)
            if not val:
                continue
            items: list = val if isinstance(val, list) else [val]
            for item in items:
                if not isinstance(item, str):
                    continue
                target_slug = extract_wiki_slug(item)
                if target_slug is None:
                    continue  # not a wikilink — skip
                if target_slug not in all_stems:
                    issues_dangling.append(
                        f"[dangling-link] wiki/{rel}: edge={edge_key} target={target_slug}"
                    )

        # ── Check 3: orphan Person (no works_at wikilink) ─────────────────
        if ptype == "Person" and person_requires_works_at(fm):
            val = fm.get("works_at")
            items = val if isinstance(val, list) else ([val] if val else [])
            if not has_wikilink(items):
                issues_orphan.append(
                    f"[orphan-invariant] Person/{slug}: no works_at edge"
                )

        # ── Check 4: orphan Decision (no sources wikilink) ────────────────
        # Skip archived redirect stubs — they're minimal by design (status: archived)
        if ptype == "Decision" and fm.get("status") != "archived":
            val = fm.get("sources")
            items = val if isinstance(val, list) else ([val] if val else [])
            if not has_wikilink(items):
                issues_orphan.append(
                    f"[orphan-invariant] Decision/{slug}: no sources edge"
                )

    # ── Output ────────────────────────────────────────────────────────────────
    all_issues = issues_parse + issues_unknown + issues_dangling + issues_orphan
    for line in all_issues:
        print(line)

    n = len(all_issues)
    j = len(issues_parse)
    k = len(issues_unknown)
    d = len(issues_dangling)
    m = len(issues_orphan)

    if n == 0:
        print("validate: ok — 0 issues")
    else:
        print(
            f"validate: {n} issues found "
            f"({j} parse-error, {k} unknown-edge, {d} dangling-link, {m} orphan-invariant)"
        )

    sys.exit(0 if n == 0 else 1)


if __name__ == "__main__":
    main()
