#!/usr/bin/env python3
# /// script
# dependencies = ["ruamel.yaml"]
# requires-python = ">=3.9,<3.14"
# ///
"""
kb-rename — rename canonical entity slug vault-wide.

Usage:
  uv run .agents/skills/kb-rename/rename.py <Type> <old-slug> <new-slug> [--apply]

Default: dry-run report. `--apply` writes via .kb-staging/<txn-id>/.
Vault root auto-detected (walks up for CLAUDE.md).
"""
import argparse
import io
import shutil
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from ruamel.yaml import YAML as _YAML

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (  # noqa: E402
    TYPE_TO_DIR, SKIP_DERIVED as SKIP_DIRS,
    find_vault_root, acquire_inbox_lock, release_inbox_lock, wikilink_pattern,
)

SKIP_FILES = {"index.md", "overview.md", "log.md"}


class RenameError(Exception):
    pass


@dataclass
class RenameResult:
    type: str
    old_slug: str
    new_slug: str
    referring_files: list[Path] = field(default_factory=list)
    total_replacements: int = 0
    applied: bool = False


def rewrite_wikilinks_in_text(
    text: str, type_dir: str, old_slug: str, new_slug: str
) -> tuple[str, int]:
    pat = wikilink_pattern(type_dir, old_slug)
    replacement = f"[[wiki/{type_dir}/{new_slug}"
    n = len(pat.findall(text))
    return pat.sub(replacement, text), n


def find_referring_files(wiki_dir: Path, type_dir: str, old_slug: str) -> list[Path]:
    pat = wikilink_pattern(type_dir, old_slug)
    self_path = wiki_dir / type_dir / f"{old_slug}.md"
    out = []
    for md in wiki_dir.rglob("*.md"):
        rel = md.relative_to(wiki_dir).parts
        if any(p in SKIP_DIRS for p in rel[:-1]):
            continue
        if rel[-1] in SKIP_FILES:
            continue
        if md.resolve() == self_path.resolve():
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if pat.search(text):
            out.append(md)
    return out


def build_renamed_frontmatter(
    fm: dict, new_slug: str, old_slug: str, original_name: str
) -> dict:
    out = dict(fm)
    out["slug"] = new_slug
    aliases = list(out.get("aliases") or [])
    for candidate in (old_slug, original_name):
        if candidate and candidate not in aliases:
            aliases.append(candidate)
    out["aliases"] = aliases
    return out


def _read_yaml(path: Path) -> tuple[dict, str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise RenameError(f"no frontmatter in {path}")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise RenameError(f"no frontmatter in {path}")
    _y = _YAML()
    _y.preserve_quotes = True
    fm = _y.load(parts[1])
    return fm, parts[2], text


def _dump_yaml(fm) -> str:
    _y = _YAML()
    _y.preserve_quotes = True
    buf = io.StringIO()
    _y.dump(fm, buf)
    return buf.getvalue()


def _write_page(path: Path, fm: dict, body: str) -> None:
    yaml_text = _dump_yaml(fm)
    if not yaml_text.endswith("\n"):
        yaml_text += "\n"
    out = "---\n" + yaml_text + "---" + body
    path.write_text(out, encoding="utf-8")


def apply_rename(
    vault: Path, type_: str, old_slug: str, new_slug: str, dry_run: bool
) -> RenameResult:
    if type_ not in TYPE_TO_DIR:
        raise RenameError(f"unknown type: {type_}")
    type_dir = TYPE_TO_DIR[type_]
    wiki = vault / "wiki"
    old_path = wiki / type_dir / f"{old_slug}.md"
    new_path = wiki / type_dir / f"{new_slug}.md"
    if not old_path.exists():
        raise RenameError(f"old slug page not found: {old_path}")
    if new_path.exists():
        raise RenameError(f"new slug page already exists: {new_path}")
    # Block collision against any same-slug page anywhere
    for md in wiki.rglob(f"{new_slug}.md"):
        if md.resolve() != new_path.resolve():
            raise RenameError(f"slug collision elsewhere in vault: {md}")

    result = RenameResult(type=type_, old_slug=old_slug, new_slug=new_slug)
    referring = find_referring_files(wiki, type_dir, old_slug)
    result.referring_files = referring

    # Plan all rewrites
    rewrites: list[tuple[Path, str, int]] = []
    for ref in referring:
        text = ref.read_text(encoding="utf-8", errors="replace")
        new_text, n = rewrite_wikilinks_in_text(text, type_dir, old_slug, new_slug)
        if n:
            rewrites.append((ref, new_text, n))
            result.total_replacements += n

    # Plan the page rename itself
    fm, body, _ = _read_yaml(old_path)
    original_name = str(fm.get("name", "") or old_slug.replace("-", " ").title())
    new_fm = build_renamed_frontmatter(dict(fm), new_slug, old_slug, original_name)

    print(f"\nrename: {type_}/{old_slug} → {type_}/{new_slug}")
    print(f"  file: {old_path.relative_to(vault)} → {new_path.relative_to(vault)}")
    print(f"  referring files: {len(referring)}, total link replacements: {result.total_replacements}")
    for ref, _, n in rewrites:
        print(f"    - {ref.relative_to(vault)}  ({n} link(s))")

    if dry_run:
        return result

    # Acquire inbox lock so concurrent /kb-ingest cannot inject new wikilinks mid-rewrite.
    try:
        lock = acquire_inbox_lock(vault)
    except TimeoutError as exc:
        raise RenameError(str(exc)) from exc
    # Apply: stage all writes under .kb-staging/<txn-id>/
    txn_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]
    staging = vault / ".kb-staging" / txn_id
    staging.mkdir(parents=True, exist_ok=True)
    commit_ok = False
    try:
        # 1. Write the renamed page to staging
        staged_new = staging / "new_page.md"
        _write_page(staged_new, new_fm, body)
        # 2. Write each referring file's new text to staging
        ref_writes: list[tuple[Path, Path]] = []
        for i, (ref, new_text, _) in enumerate(rewrites):
            # Prefix index to avoid collisions if two referring paths flatten identically
            staged_ref = staging / f"{i:04d}__{ref.relative_to(vault).as_posix().replace('/', '__')}"
            staged_ref.write_text(new_text, encoding="utf-8")
            ref_writes.append((staged_ref, ref))
        # 3. Atomically apply
        # 3a. Move staged new page into place
        shutil.move(str(staged_new), str(new_path))
        # 3b. Remove old page
        old_path.unlink()
        # 3c. Overwrite each referring file
        for staged_ref, ref_target in ref_writes:
            shutil.move(str(staged_ref), str(ref_target))
        commit_ok = True
    finally:
        if commit_ok:
            # Success — clean up empty staging dir
            shutil.rmtree(staging, ignore_errors=True)
        else:
            # Failure — preserve staging dir for manual recovery; print path
            print(
                f"\nrename: ERROR mid-commit. Staging preserved at: {staging.relative_to(vault)}\n"
                f"  Vault may be in a partial state. Inspect staged files for recovery.",
                file=sys.stderr,
            )
        release_inbox_lock(lock)

    # 4. Log entry
    log_path = vault / "wiki" / "log.md"
    if log_path.exists():
        with log_path.open("a", encoding="utf-8") as f:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
            f.write(
                f"\n## [{ts}] kb-rename | {type_}/{old_slug} → {type_}/{new_slug}, "
                f"{result.total_replacements} link(s) updated in {len(referring)} file(s)\n"
            )

    result.applied = True
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("type")
    ap.add_argument("old_slug")
    ap.add_argument("new_slug")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    vault = find_vault_root(Path(__file__).parent)
    try:
        apply_rename(vault, args.type, args.old_slug, args.new_slug, dry_run=not args.apply)
    except RenameError as e:
        print(f"rename: error: {e}", file=sys.stderr)
        return 2
    if not args.apply:
        print("\n(dry-run — re-run with --apply to commit)")
    else:
        print("\nrename: applied. Run /kb-graph project to refresh Kuzu.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
