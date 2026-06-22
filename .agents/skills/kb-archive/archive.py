#!/usr/bin/env python3
# /// script
# dependencies = ["ruamel.yaml"]
# requires-python = ">=3.9,<3.14"
# ///
"""
kb-archive — move stale canonical page to wiki/archive/<type-plural>/<slug>.md,
replace original with a redirect stub.

Usage:
  uv run .agents/skills/kb-archive/archive.py <Type> <slug> [--force] [--apply]
"""
import argparse
import re
import shutil
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from ruamel.yaml import YAML as _YAML

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (  # noqa: E402
    TYPE_TO_DIR, find_vault_root, acquire_inbox_lock, release_inbox_lock,
)


class ArchiveError(Exception):
    pass


@dataclass
class ArchiveResult:
    type: str
    slug: str
    source_path: Path
    dest_path: Path
    applied: bool = False


# ── Pure helpers ──────────────────────────────────────────

def archive_path_for(type_dir: str, slug: str) -> Path:
    return Path("wiki") / "archive" / type_dir / f"{slug}.md"


def redirect_stub(type_: str, slug: str, type_dir: str, today: str) -> str:
    return (
        "---\n"
        f"type: {type_}\n"
        f"slug: {slug}\n"
        "status: archived\n"
        f"superseded_by:\n  - \"[[wiki/archive/{type_dir}/{slug}]]\"\n"
        f"modified: {today}\n"
        "---\n\n"
        f"This page was archived. See [[wiki/archive/{type_dir}/{slug}]].\n"
    )


def strip_canonical_from_index(index_text: str, type_dir: str, slug: str) -> str:
    """Remove any line containing a wikilink whose target is exactly
    `wiki/<type_dir>/<slug>` (with optional `.md`, `|alias`, or `#anchor`)."""
    pat = re.compile(
        r"\[\[wiki/" + re.escape(type_dir) + r"/" + re.escape(slug) + r"(?:\.md)?(?=[\]|#])"
    )
    kept = [line for line in index_text.splitlines(keepends=True) if not pat.search(line)]
    return "".join(kept)


def _read_yaml(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ArchiveError(f"no frontmatter in {path}")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ArchiveError(f"no frontmatter in {path}")
    _y = _YAML()
    _y.preserve_quotes = True
    fm = _y.load(parts[1])
    return (fm if isinstance(fm, dict) else {}), parts[2]


def apply_archive(
    vault: Path,
    type_: str,
    slug: str,
    dry_run: bool,
    force: bool = False,
    today: str | None = None,
) -> ArchiveResult:
    if type_ not in TYPE_TO_DIR:
        raise ArchiveError(f"unknown type: {type_}")
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    type_dir = TYPE_TO_DIR[type_]
    wiki = vault / "wiki"
    source_path = wiki / type_dir / f"{slug}.md"
    dest_path = vault / archive_path_for(type_dir, slug)

    if not source_path.exists():
        raise ArchiveError(f"page not found: {source_path}")
    if dest_path.exists():
        raise ArchiveError(f"archive destination already exists: {dest_path}")

    fm, _body = _read_yaml(source_path)
    status = str(fm.get("status", "")).strip().lower()
    if not force and status not in {"dormant", "archived"}:
        raise ArchiveError(
            f"page status is '{status or '<unset>'}' — only dormant/archived may be archived. "
            f"Use --force to override."
        )

    result = ArchiveResult(type=type_, slug=slug, source_path=source_path, dest_path=dest_path)

    print(f"\narchive: {type_}/{slug}")
    print(f"  source:  {source_path.relative_to(vault)}")
    print(f"  dest:    {dest_path.relative_to(vault)}")
    print(f"  status:  {status or '<unset>'}{' (forced)' if force else ''}")
    index_path = wiki / "index.md"
    if index_path.exists():
        idx_before = index_path.read_text(encoding="utf-8")
        idx_after = strip_canonical_from_index(idx_before, type_dir, slug)
        n_removed = len(idx_before.splitlines()) - len(idx_after.splitlines())
        print(f"  index:   {n_removed} line(s) to remove from wiki/index.md")
    print("\nredirect stub preview:\n")
    print(redirect_stub(type_, slug, type_dir, today).rstrip())

    if dry_run:
        return result

    # Apply via staging
    try:
        lock = acquire_inbox_lock(vault)
    except TimeoutError as exc:
        raise ArchiveError(str(exc)) from exc
    txn_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]
    staging = vault / ".kb-staging" / txn_id
    staging.mkdir(parents=True, exist_ok=True)
    commit_ok = False
    try:
        # 1. Stage the archived copy (full original file contents)
        staged_archive = staging / "archived.md"
        shutil.copy2(source_path, staged_archive)
        # 2. Stage the redirect stub for the original location
        staged_stub = staging / "stub.md"
        staged_stub.write_text(redirect_stub(type_, slug, type_dir, today), encoding="utf-8")
        # 3. Stage updated index.md (if present)
        staged_index: Path | None = None
        index_path = wiki / "index.md"
        if index_path.exists():
            idx_text = index_path.read_text(encoding="utf-8")
            new_idx = strip_canonical_from_index(idx_text, type_dir, slug)
            if new_idx != idx_text:
                staged_index = staging / "index.md"
                staged_index.write_text(new_idx, encoding="utf-8")
        # 4. Commit
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staged_archive), str(dest_path))
        shutil.move(str(staged_stub), str(source_path))
        if staged_index is not None:
            shutil.move(str(staged_index), str(index_path))
        # 5. Log entry — inside lock so concurrent kb-ingest can't interleave.
        log_path = wiki / "log.md"
        if log_path.exists():
            with log_path.open("a", encoding="utf-8") as f:
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
                f.write(f"\n## [{ts}] kb-archive | {type_}/{slug} archived\n")
        commit_ok = True
    finally:
        if commit_ok:
            shutil.rmtree(staging, ignore_errors=True)
        else:
            print(
                f"\narchive: ERROR mid-commit. Staging preserved at: {staging.relative_to(vault)}",
                file=sys.stderr,
            )
        release_inbox_lock(lock)

    result.applied = True
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("type")
    ap.add_argument("slug")
    ap.add_argument("--force", action="store_true",
                    help="override status check (only dormant/archived allowed by default)")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    vault = find_vault_root(Path(__file__).parent)
    try:
        apply_archive(
            vault, args.type, args.slug,
            dry_run=not args.apply, force=args.force,
        )
    except ArchiveError as e:
        print(f"archive: error: {e}", file=sys.stderr)
        return 2
    if not args.apply:
        print("\n(dry-run — re-run with --apply to commit)")
    else:
        print("\narchive: applied. Run /kb-graph project to refresh Kuzu.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
