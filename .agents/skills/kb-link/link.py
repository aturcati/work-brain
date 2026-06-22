#!/usr/bin/env python3
# /// script
# dependencies = [
#   "pyyaml",
# ]
# requires-python = ">=3.9,<3.14"
# ///
"""
kb-link report — tofile/ promotion readiness.
Usage: uv run .agents/skills/kb-link/link.py
Vault root auto-detected: walks up from __file__ until CLAUDE.md found.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import SKIP_STUBS as SKIP_DIRS, SKIP_NAMES, find_vault_root, parse_frontmatter  # noqa: E402


def normalise(s: str) -> str:
    return s.strip().strip('"').lower()


def slug_variants(slug: str) -> set[str]:
    """Derive raw-text search variants from a kebab slug.

    person slugs come from emails (alice.smith@… → alice-smith) or display
    names (Alice Smith → alice-smith); raw files contain the spaced name or
    the dotted email local part, never the hyphenated slug itself.
    """
    variants = {slug}
    if "-" in slug:
        variants.add(slug.replace("-", " "))   # "alice smith"
        variants.add(slug.replace("-", "."))   # "alice.smith" (email local)
    return variants


def main() -> None:
    vault = find_vault_root(Path(__file__).parent)
    tofile_dir = vault / "wiki" / "tofile"
    wiki_dir = vault / "wiki"
    raw_dir = vault / "raw"

    # Step 1 — Load stubs
    stubs: list[dict] = []
    for stub_path in sorted(tofile_dir.glob("*.md")):
        fm = parse_frontmatter(stub_path)
        if fm is None:
            continue
        slug = normalise(str(fm.get("slug", stub_path.stem)))
        raw_aliases = fm.get("aliases") or []
        if isinstance(raw_aliases, str):
            raw_aliases = [raw_aliases]
        aliases = {normalise(a) for a in raw_aliases}
        search_terms = slug_variants(slug) | aliases
        stubs.append({
            "slug": slug,
            "type": str(fm.get("type", "Unknown")),
            "search_terms": search_terms,
        })

    if not stubs:
        print("No stubs found in wiki/tofile/")
        sys.exit(0)

    # Step 2 — Count inbound wiki links from wiki/ (excluding tofile/).
    # Scope MUST match kb-lint's orphan check (SKIP_STUBS + SKIP_NAMES from common)
    # — otherwise stubs qualify here but become orphans the moment they are promoted.
    slug_inbound_files: dict[str, set[Path]] = {s["slug"]: set() for s in stubs}
    for wiki_file in wiki_dir.rglob("*.md"):
        if any(part in SKIP_DIRS for part in wiki_file.relative_to(wiki_dir).parts[:-1]):
            continue
        if wiki_file.name in SKIP_NAMES or wiki_file.name.startswith("log"):
            continue
        try:
            text = wiki_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for stub in stubs:
            pattern = f"[[wiki/tofile/{stub['slug']}"
            if pattern in text:
                slug_inbound_files[stub["slug"]].add(wiki_file)

    # Convert to distinct file counts
    slug_inbound: dict[str, int] = {s["slug"]: len(slug_inbound_files[s["slug"]]) for s in stubs}

    # Step 3 — Check raw mentions (case-insensitive substring)
    slug_raw: dict[str, bool] = {s["slug"]: False for s in stubs}
    raw_texts = []
    for raw_file in raw_dir.rglob("*.md"):
        try:
            raw_texts.append(raw_file.read_text(encoding="utf-8", errors="replace").lower())
        except OSError:
            pass
    for stub in stubs:
        slug_raw[stub["slug"]] = any(
            term in rt for term in stub["search_terms"] for rt in raw_texts
        )

    # Step 4 — Output table
    col_slug = max(len(s["slug"]) for s in stubs)
    col_slug = max(col_slug, 4)
    col_type = max(len(s["type"]) for s in stubs)
    col_type = max(col_type, 4)

    print("tofile/ promotion report")
    print("========================")
    header = f"{'SLUG':<{col_slug}}  {'TYPE':<{col_type}}  {'INBOUND':>7}  {'RAW':>3}  PROMOTE?"
    print(header)

    promote_count = 0
    for stub in stubs:
        slug = stub["slug"]
        inbound = slug_inbound[slug]
        raw_yes = slug_raw[slug]
        promotes = inbound >= 1 and raw_yes
        if promotes:
            promote_count += 1
        raw_str = "yes" if raw_yes else "no"
        promote_str = "✓ PROMOTE" if promotes else "-"
        print(f"{slug:<{col_slug}}  {stub['type']:<{col_type}}  {inbound:>7}  {raw_str:>3}  {promote_str}")

    total = len(stubs)
    not_ready = total - promote_count
    print()
    print(f"{total} stubs total | {promote_count} promote | {not_ready} not ready")
    sys.exit(0)


if __name__ == "__main__":
    main()
