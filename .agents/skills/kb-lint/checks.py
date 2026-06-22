"""kb-lint checks — every check_* function returns a list of findings.

Imported by lint.py. Not run directly.
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path

from core import (  # noqa: F401
    NODE_TYPES, ALLOWED_KEYS, STALE_DAYS, ACTION_STALE_DAYS,
    JOURNAL_BACKLOG_DAYS, TOKEN_LIMIT, LOG_LINE_LIMIT, LOG_SIZE_LIMIT,
    EDGES_ENTRY_LIMIT, EDGES_SIZE_LIMIT,
    parse_wikilinks, _all_wikilink_text, _finding, parse_frontmatter_text,
)

# ── Checks 1–3 ────────────────────────────────────────────────────────────

def check_orphans(pages: list[dict], link_graph: dict[str, set[str]]) -> list[dict]:
    findings = []
    for page in pages:
        if not page["slug"] or page["type"] == "Source":
            continue
        if not link_graph.get(page["slug"]):
            findings.append(_finding("orphans", page["path"],
                                     "no inbound wikilinks (orphan page)"))
    return findings


def check_broken_links(pages: list[dict], vault: Path) -> list[dict]:
    # Wikilinks in this vault are vault-relative paths (e.g. wiki/people/foo, raw/meetings/...)
    findings = []
    for page in pages:
        if page["fm"] is None:
            continue
        for link in parse_wikilinks(_all_wikilink_text(page)):
            target = vault / (link + ".md")
            if not target.exists():
                findings.append(_finding("broken_links", page["path"],
                                         f"broken wikilink: [[{link}]]"))
    return findings


def check_schema_violations(pages: list[dict]) -> list[dict]:
    findings = []
    for page in pages:
        if page["fm"] is None:
            findings.append(_finding("schema_violations", page["path"],
                                     "YAML frontmatter parse error"))
            continue
        node_type = page["fm"].get("type", "")
        if node_type not in NODE_TYPES:
            findings.append(_finding("schema_violations", page["path"],
                                     f"unknown type: '{node_type}'"))
        unknown = [k for k in page["fm"] if k not in ALLOWED_KEYS]
        for k in unknown:
            findings.append(_finding("schema_violations", page["path"],
                                     f"unknown frontmatter key: '{k}'"))
    return findings


# ── Checks 4–6 ────────────────────────────────────────────────────────────

def check_stale_last_verified(pages: list[dict], today: datetime.date) -> list[dict]:
    findings = []
    for page in pages:
        if page["fm"] is None:
            continue
        lv = page["fm"].get("last_verified")
        if not lv:
            continue
        try:
            lv_date = datetime.date.fromisoformat(str(lv))
        except ValueError:
            continue
        if (today - lv_date).days > STALE_DAYS:
            findings.append(_finding("stale_pages", page["path"],
                                     f"last_verified {lv} is {(today - lv_date).days} days ago (>{STALE_DAYS})"))
    return findings


def check_contradictions(pages: list[dict]) -> list[dict]:
    # Build slug → set of contradicted slugs
    contradicts_map: dict[str, set[str]] = {}
    for page in pages:
        if page["fm"] is None or not page["slug"]:
            continue
        targets = page["fm"].get("contradicts") or []
        if isinstance(targets, str):
            targets = [targets]
        contradicts_map[page["slug"]] = {
            link.split("/")[-1]
            for link in parse_wikilinks(" ".join(str(t) for t in targets))
        }

    slug_to_page = {p["slug"]: p for p in pages if p["slug"]}
    findings = []
    for slug, targets in contradicts_map.items():
        for target in targets:
            reverse = contradicts_map.get(target, set())
            if slug not in reverse:
                page = slug_to_page.get(slug)
                path = page["path"] if page else slug
                findings.append(_finding("contradictions", path,
                                         f"one-sided contradicts: {slug} → {target} (no reverse)"))
    return findings


def check_bloated_pages(pages: list[dict]) -> list[dict]:
    findings = []
    for page in pages:
        if page["fm"].get("type") == "Artifact":
            continue  # Artifacts (e.g. transcripts) are expected to exceed token limit
        approx_tokens = len(page["body"]) // 4
        if approx_tokens > TOKEN_LIMIT:
            findings.append(_finding("bloated_pages", page["path"],
                                     f"~{approx_tokens} tokens (>{TOKEN_LIMIT}) — propose /kb-refactor split"))
    return findings


# ── Checks 7–9 ────────────────────────────────────────────────────────────

def check_log_rotation(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    text = log_path.read_text(encoding="utf-8", errors="replace")
    line_count = len(text.splitlines())
    byte_count = len(text.encode("utf-8"))
    findings = []
    if line_count > LOG_LINE_LIMIT:
        findings.append(_finding("log_rotation", log_path,
                                 f"wiki/log.md has {line_count} lines (>{LOG_LINE_LIMIT}) — rotate to log-archive/"))
    elif byte_count > LOG_SIZE_LIMIT:  # report only the first exceeded threshold
        findings.append(_finding("log_rotation", log_path,
                                 f"wiki/log.md is {byte_count // 1024}KB (>1MB) — rotate to log-archive/"))
    return findings


def check_edges_rotation(edges_path: Path) -> list[dict]:
    if not edges_path.exists():
        return []
    text = edges_path.read_text(encoding="utf-8", errors="replace")
    entry_count = sum(1 for line in text.splitlines() if line.startswith("- ("))
    byte_count = len(text.encode("utf-8"))
    findings = []
    if entry_count > EDGES_ENTRY_LIMIT:
        findings.append(_finding("edges_rotation", edges_path,
                                 f"edges.md has {entry_count} entries (>{EDGES_ENTRY_LIMIT}) — rotate to edges-archive/"))
    elif byte_count > EDGES_SIZE_LIMIT:  # report only the first exceeded threshold
        findings.append(_finding("edges_rotation", edges_path,
                                 f"edges.md is {byte_count // 1024}KB (>500KB) — rotate to edges-archive/"))
    return findings


def check_raw_drift(vault: Path, state_path: Path) -> list[dict]:
    if not state_path.exists():
        return []
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        return []
    findings = []
    for rel_path, meta in state.items():
        if meta.get("status") != "done":
            continue
        file_path = vault / rel_path
        if not file_path.exists():
            continue
        try:
            ingest_ts = datetime.datetime.fromisoformat(meta["ts"]).timestamp()
        except (KeyError, ValueError):
            continue
        file_mtime = os.path.getmtime(file_path)
        if file_mtime > ingest_ts + 1.0:
            findings.append(_finding("raw_drift", rel_path,
                                     "raw file modified after ingest (mtime drift)"))
    return findings


# ── Checks 10–13 ──────────────────────────────────────────────────────────

def check_decision_sources(pages: list[dict]) -> list[dict]:
    findings = []
    for page in pages:
        if page["type"] != "Decision" or page["fm"] is None:
            continue
        if page["fm"].get("status") == "archived":
            continue  # archived redirect stubs are intentionally minimal
        sources = page["fm"].get("sources") or []
        if not sources:
            findings.append(_finding("graph_invariants", page["path"],
                                     "Decision page has no sources"))
    return findings


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


def check_person_works_at(pages: list[dict]) -> list[dict]:
    findings = []
    for page in pages:
        if page["type"] != "Person" or page["fm"] is None:
            continue
        if not person_requires_works_at(page["fm"]):
            continue
        works_at = page["fm"].get("works_at") or []
        if not works_at:
            findings.append(_finding("graph_invariants", page["path"],
                                     "Person page has no works_at"))
    return findings


def check_stale_action_items(pages: list[dict], today: datetime.date) -> list[dict]:
    findings = []
    for page in pages:
        if page["fm"] is None:
            continue
        if "- [ ]" not in page["body"]:
            continue
        modified_str = page["fm"].get("modified") or page["fm"].get("created") or ""
        if not modified_str:
            continue
        try:
            modified = datetime.date.fromisoformat(str(modified_str))
        except ValueError:
            continue
        age = (today - modified).days
        if age > ACTION_STALE_DAYS:
            count = page["body"].count("- [ ]")
            findings.append(_finding("stale_action_items", page["path"],
                                     f"{count} open action item(s), page not modified for {age} days"))
    return findings


def check_unprocessed_journal(
    vault: Path, state_path: Path, today: datetime.date
) -> list[dict]:
    """Flag journal files in raw/inbox/journal/ older than JOURNAL_BACKLOG_DAYS."""
    findings = []
    # inbox files are unprocessed by definition — successful ingest moves them to raw/<channel>/

    inbox_journal = vault / "raw" / "inbox" / "journal"
    if inbox_journal.exists():
        for f in sorted(inbox_journal.rglob("*.md")):
            raw_text = f.read_text(encoding="utf-8", errors="replace")
            fm = parse_frontmatter_text(raw_text)
            captured_at = str(fm.get("captured_at", "")) if fm else ""
            try:
                cap_date = datetime.date.fromisoformat(captured_at)
                age = (today - cap_date).days
            except ValueError:
                continue
            if age > JOURNAL_BACKLOG_DAYS:
                findings.append(_finding("unprocessed_journal",
                                         str(f.relative_to(vault)),
                                         f"journal file in inbox {age} days old — run /kb-ingest"))
    return findings


def check_decision_date(pages: list[dict]) -> list[dict]:
    """Decision pages must carry a date: field (the decision date, not created:)."""
    findings = []
    for page in pages:
        if page["fm"] is None or page["type"] != "Decision":
            continue
        if page["fm"].get("status") == "archived":
            continue  # archived redirect stubs are intentionally minimal
        if not page["fm"].get("date"):
            findings.append(_finding("decision_date", page["path"],
                                     "Decision page missing date: field"))
    return findings


_CANONICAL_DIRS = ["people", "orgs", "projects", "topics", "decisions",
                   "meetings", "sources", "artifacts", "events"]


def check_duplicate_stubs(wiki_dir: Path) -> list[dict]:
    """A tofile stub whose slug already exists as a canonical page is a
    promotion leftover — promotion must delete the stub (kb-link Step 2)."""
    findings = []
    tofile = wiki_dir / "tofile"
    if not tofile.is_dir():
        return findings
    for stub in sorted(tofile.glob("*.md")):
        for d in _CANONICAL_DIRS:
            if (wiki_dir / d / stub.name).exists():
                findings.append(_finding("duplicate_stubs", stub,
                                         f"stub duplicates canonical wiki/{d}/{stub.name} — delete after promotion"))
                break
    return findings


