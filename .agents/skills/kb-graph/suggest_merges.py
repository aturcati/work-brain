#!/usr/bin/env python3
# /// script
# dependencies = ["pyyaml"]
# requires-python = ">=3.9,<3.14"
# ///
"""
kb-graph suggest-merges — find duplicate entity candidates.

Compares same-type canonical wiki pages by alias overlap and string similarity.
Read-only; emits ranked candidate pairs. Embeddings deferred (see PLAN.md:464).

Usage:
  uv run .agents/skills/kb-graph/suggest_merges.py [--threshold 0.75]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import SKIP_DERIVED as SKIP_DIRS, find_vault_root, parse_frontmatter  # noqa: E402

SKIP_FILES = {"index.md", "overview.md", "log.md"}


def normalise(s: str) -> str:
    return s.strip().strip('"').strip("'").lower()


def page_terms(page: dict) -> set[str]:
    terms = {normalise(str(page["slug"]))}
    for a in (page.get("aliases") or []):
        if isinstance(a, str):
            terms.add(normalise(a))
    return {t for t in terms if t}


def char_3grams(s: str) -> set[str]:
    s = s.replace(" ", "")
    if len(s) < 3:
        return {s} if s else set()
    return {s[i:i+3] for i in range(len(s) - 2)}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _has_first_token_match(shorts: set[str], terms: set[str]) -> bool:
    """True if any single-token element in `shorts` matches the first token
    (split on '-' or ' ') of any term in `terms`."""
    for s in shorts:
        for t in terms:
            if t.split("-")[0] == s or t.split(" ")[0] == s:
                return True
    return False


def score_pair(a: dict, b: dict, ngram_threshold: float = 0.75) -> tuple[float, str]:
    if a["type"] != b["type"]:
        return 0.0, ""
    if a["slug"] == b["slug"]:
        return 0.0, ""
    terms_a = page_terms(a)
    terms_b = page_terms(b)
    # 1. Exact alias overlap → 1.0
    if terms_a & terms_b:
        return 1.0, "exact alias overlap"
    # 2. Char 3-gram Jaccard over concatenated terms
    grams_a = {g for t in terms_a for g in char_3grams(t)}
    grams_b = {g for t in terms_b for g in char_3grams(t)}
    score = jaccard(grams_a, grams_b)
    if score >= ngram_threshold:
        return score, f"3-gram jaccard {score:.2f}"
    # 3. First-token prefix (single-word slug appears as first word of multi-word slug)
    short_a = {t for t in terms_a if "-" not in t and " " not in t}
    short_b = {t for t in terms_b if "-" not in t and " " not in t}
    if _has_first_token_match(short_a, terms_b) or _has_first_token_match(short_b, terms_a):
        return 0.6, "first-name match"
    return 0.0, ""


def find_candidates(pages: list[dict], threshold: float) -> list[tuple[str, str, float, str]]:
    # Pass user threshold to score_pair so 3-gram gate respects it (capped at 0.75
    # to keep first-name-match branch reachable; below 0.75 the n-gram branch
    # may still emit if jaccard >= user threshold).
    ngram_gate = min(threshold, 0.75)
    out = []
    for i, a in enumerate(pages):
        for b in pages[i+1:]:
            score, reason = score_pair(a, b, ngram_threshold=ngram_gate)
            if score >= threshold:
                slug_a, slug_b = sorted([a["slug"], b["slug"]])
                out.append((slug_a, slug_b, score, reason))
    out.sort(key=lambda r: (-r[2], r[0], r[1]))
    return out


def collect_pages(wiki_dir: Path) -> list[dict]:
    pages = []
    for md in sorted(wiki_dir.rglob("*.md")):
        rel = md.relative_to(wiki_dir).parts
        if any(p in SKIP_DIRS for p in rel[:-1]):
            continue
        if rel[-1] in SKIP_FILES:
            continue
        fm = parse_frontmatter(md)
        if not fm:
            continue
        slug = fm.get("slug")
        ntype = fm.get("type")
        if not slug or not ntype:
            continue
        pages.append({
            "slug": str(slug),
            "type": str(ntype),
            "aliases": fm.get("aliases") or [],
            "path": md,
        })
    return pages


def format_report(cands: list[tuple]) -> str:
    if not cands:
        return "suggest-merges: no candidates above threshold"
    lines = [f"suggest-merges: {len(cands)} candidate pair(s)\n"]
    for a, b, score, reason in cands:
        lines.append(f"  {score:.2f}  {a}  ~  {b}    ({reason})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.75)
    args = ap.parse_args(argv)
    vault = find_vault_root(Path(__file__).parent)
    pages = collect_pages(vault / "wiki")
    cands = find_candidates(pages, args.threshold)
    print(format_report(cands))
    return 0


if __name__ == "__main__":
    sys.exit(main())
