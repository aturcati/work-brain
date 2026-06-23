#!/usr/bin/env python3
# /// script
# dependencies = ["ruamel.yaml"]
# requires-python = ">=3.9,<3.14"
# ///
"""
kb-merge — fold secondary canonical page into primary.

Usage:
  uv run .agents/skills/kb-merge/merge.py <Type> <primary-slug> <secondary-slug> [--apply]

Default: dry-run report. `--apply` writes via .kb-staging/<txn-id>/.
Vault root auto-detected (walks up for CLAUDE.md).
"""
import argparse
import re
import shutil
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from ruamel.yaml import YAML as _YAML

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (  # noqa: E402
    TYPE_TO_DIR, EDGE_KEYS, SKIP_DERIVED as SKIP_DIRS,
    find_vault_root, acquire_inbox_lock, release_inbox_lock,
    wikilink_pattern, dump_page,
)

SKIP_FILES = {"index.md", "overview.md", "log.md"}


class MergeError(Exception):
    pass


@dataclass
class MergeResult:
    type: str
    primary_slug: str
    secondary_slug: str
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


def _is_self_reference(value: object, type_dir: str, primary_slug: str, secondary_slug: str) -> bool:
    text = str(value)
    for slug in (primary_slug, secondary_slug):
        if wikilink_pattern(type_dir, slug).match(text):
            return True
    return False


def merge_frontmatter(
    primary_fm: dict,
    secondary_fm: dict,
    primary_slug: str,
    secondary_slug: str,
    today: str,
) -> dict:
    type_ = str(primary_fm.get("type") or secondary_fm.get("type") or "")
    type_dir = TYPE_TO_DIR.get(type_, "")
    out: dict = {"type": type_, "slug": primary_slug}

    aliases = list(primary_fm.get("aliases") or [])
    aliases.extend(list(secondary_fm.get("aliases") or []))
    aliases.append(secondary_slug)
    out["aliases"] = list(dict.fromkeys(aliases))

    for key in (
        "created", "last_verified", "status", "tags", "confidence",
        "name", "date", "captured_at", "provider", "channel", "path",
    ):
        if key in primary_fm:
            out[key] = primary_fm[key]
        elif key in secondary_fm:
            out[key] = secondary_fm[key]

    out["modified"] = today

    for key in EDGE_KEYS:
        values = list(primary_fm.get(key) or []) + list(secondary_fm.get(key) or [])
        if not values:
            continue
        merged = [
            item for item in dict.fromkeys(values)
            if not _is_self_reference(item, type_dir, primary_slug, secondary_slug)
        ]
        if merged:
            out[key] = merged

    return out


_SECTION_RE = re.compile(r"^(## .+?)$", re.MULTILINE)


def _split_sections(body: str) -> list[tuple[str, str]]:
    parts = _SECTION_RE.split(body)
    if not parts:
        return []
    sections = [("", parts[0])]
    for i in range(1, len(parts), 2):
        section_body = parts[i + 1] if i + 1 < len(parts) else ""
        sections.append((parts[i], section_body))
    return sections


def merge_body(primary_body: str, secondary_body: str, secondary_slug: str) -> str:
    if not secondary_body.strip():
        return primary_body

    primary_headings = {
        heading.strip()
        for heading, _ in _split_sections(primary_body)
        if heading
    }
    sec_sections = [(h, b) for h, b in _split_sections(secondary_body) if h]
    new_sections = [
        (h, b) for h, b in sec_sections if h.strip() not in primary_headings
    ]
    if not new_sections:
        return primary_body

    out = primary_body.rstrip() + "\n\n"
    out += f"## From merged page: {secondary_slug}\n\n"
    for heading, section_body in new_sections:
        out += heading + section_body
        if not section_body.endswith("\n"):
            out += "\n"
    return out


def count_dropped_sections(primary_body: str, secondary_body: str) -> int:
    """Return number of secondary `##` sections silently dropped because the
    heading already exists in primary. Used for dry-run disclosure."""
    if not secondary_body.strip():
        return 0
    primary_headings = {
        h.strip() for h, _ in _split_sections(primary_body) if h
    }
    return sum(
        1 for h, _ in _split_sections(secondary_body)
        if h and h.strip() in primary_headings
    )


def redirect_stub(
    type_: str,
    secondary_slug: str,
    primary_slug: str,
    primary_type_dir: str,
    today: str,
) -> str:
    return (
        "---\n"
        f"type: {type_}\n"
        f"slug: {secondary_slug}\n"
        "status: merged\n"
        f"superseded_by:\n  - \"[[wiki/{primary_type_dir}/{primary_slug}]]\"\n"
        f"modified: {today}\n"
        "---\n\n"
        f"This page was merged into [[wiki/{primary_type_dir}/{primary_slug}]].\n"
    )


def _read_yaml(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise MergeError(f"no frontmatter in {path}")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise MergeError(f"no frontmatter in {path}")
    yaml = _YAML()
    yaml.preserve_quotes = True
    fm = yaml.load(parts[1])
    if not isinstance(fm, dict):
        raise MergeError(f"frontmatter is not a mapping in {path}")
    return fm, parts[2]


def _find_page_by_slug(wiki: Path, type_: str, slug: str) -> Path | None:
    preferred = wiki / TYPE_TO_DIR[type_] / f"{slug}.md"
    if preferred.exists():
        return preferred
    for type_dir in TYPE_TO_DIR.values():
        candidate = wiki / type_dir / f"{slug}.md"
        if candidate.exists():
            return candidate
    return None


def _plan_referring_rewrites(
    wiki: Path,
    type_dir: str,
    secondary_slug: str,
    primary_slug: str,
    primary_path: Path,
    secondary_path: Path,
) -> tuple[list[Path], list[tuple[Path, str, int]]]:
    pat = wikilink_pattern(type_dir, secondary_slug)
    referring: list[Path] = []
    rewrites: list[tuple[Path, str, int]] = []
    for md in wiki.rglob("*.md"):
        rel = md.relative_to(wiki).parts
        if any(part in SKIP_DIRS for part in rel[:-1]):
            continue
        if rel[-1] in SKIP_FILES:
            continue
        if md.resolve() in (primary_path.resolve(), secondary_path.resolve()):
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if pat.search(text):
            new_text, n = rewrite_wikilinks_in_text(
                text, type_dir, secondary_slug, primary_slug
            )
            referring.append(md)
            rewrites.append((md, new_text, n))
    return referring, rewrites


def apply_merge(
    vault: Path,
    type_: str,
    primary_slug: str,
    secondary_slug: str,
    dry_run: bool,
    today: str | None = None,
) -> MergeResult:
    if type_ not in TYPE_TO_DIR:
        raise MergeError(f"unknown type: {type_}")
    if primary_slug == secondary_slug:
        raise MergeError("primary and secondary slugs are identical")

    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    type_dir = TYPE_TO_DIR[type_]
    wiki = vault / "wiki"
    primary_path = _find_page_by_slug(wiki, type_, primary_slug)
    secondary_path = _find_page_by_slug(wiki, type_, secondary_slug)
    if primary_path is None:
        raise MergeError(f"primary page not found: {primary_slug}")
    if secondary_path is None:
        raise MergeError(f"secondary page not found: {secondary_slug}")

    p_fm, p_body = _read_yaml(primary_path)
    s_fm, s_body = _read_yaml(secondary_path)
    if str(p_fm.get("type")) != str(s_fm.get("type")):
        raise MergeError(
            f"type mismatch: primary={p_fm.get('type')} secondary={s_fm.get('type')}"
        )
    if str(p_fm.get("type")) != type_:
        raise MergeError(f"type arg {type_} doesn't match page type {p_fm.get('type')}")

    merged_fm = merge_frontmatter(
        dict(p_fm), dict(s_fm), primary_slug, secondary_slug, today
    )
    merged_body = merge_body(p_body, s_body, secondary_slug)
    stub = redirect_stub(type_, secondary_slug, primary_slug, type_dir, today)
    referring, rewrites = _plan_referring_rewrites(
        wiki, type_dir, secondary_slug, primary_slug, primary_path, secondary_path
    )
    total = sum(n for _, _, n in rewrites)
    result = MergeResult(
        type=type_,
        primary_slug=primary_slug,
        secondary_slug=secondary_slug,
        referring_files=referring,
        total_replacements=total,
    )

    print(f"\nmerge: {type_}/{secondary_slug} → {type_}/{primary_slug}")
    print(f"  external references: {len(referring)} file(s), {total} link replacement(s)")
    for ref, _, n in rewrites:
        print(f"    - {ref.relative_to(vault)}  ({n} link(s))")
    print(f"  primary frontmatter merged ({len(merged_fm)} keys)")
    print(
        "  primary body appended sections from secondary: "
        f"{'yes' if 'From merged page' in merged_body else 'no'}"
    )
    dropped = count_dropped_sections(p_body, s_body)
    if dropped:
        print(
            f"  WARNING: {dropped} secondary section(s) silently dropped due to heading "
            f"collision with primary — content under those headings will be LOST. "
            f"Review primary first to ensure overlap is intentional."
        )
    print("\nredirect stub preview:\n")
    print(stub.rstrip())

    if dry_run:
        return result

    try:
        lock = acquire_inbox_lock(vault)
    except TimeoutError as exc:
        raise MergeError(str(exc)) from exc
    txn_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]
    staging = vault / ".kb-staging" / txn_id
    commit_ok = False
    try:
        staging.mkdir(parents=True, exist_ok=True)

        staged_primary = staging / "primary.md"
        staged_primary.write_text(dump_page(merged_fm, merged_body), encoding="utf-8")

        staged_secondary = staging / "secondary.md"
        staged_secondary.write_text(stub, encoding="utf-8")

        ref_writes: list[tuple[Path, Path]] = []
        for i, (ref, new_text, _) in enumerate(rewrites):
            staged_ref = staging / f"{i:04d}__{ref.relative_to(vault).as_posix().replace('/', '__')}"
            staged_ref.write_text(new_text, encoding="utf-8")
            ref_writes.append((staged_ref, ref))

        log_writes: list[tuple[Path, Path]] = []
        log_path = vault / "wiki" / "log.md"
        if log_path.exists():
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
            log_text = log_path.read_text(encoding="utf-8")
            log_text += (
                f"\n## [{ts}] kb-merge | {secondary_slug} → {primary_slug} "
                f"({total} link(s) in {len(referring)} file(s))\n"
            )
            staged_log = staging / "log.md"
            staged_log.write_text(log_text, encoding="utf-8")
            log_writes.append((staged_log, log_path))

        shutil.move(str(staged_primary), str(primary_path))
        shutil.move(str(staged_secondary), str(secondary_path))
        for staged_ref, ref_target in ref_writes:
            shutil.move(str(staged_ref), str(ref_target))
        for staged_log, log_target in log_writes:
            shutil.move(str(staged_log), str(log_target))
        commit_ok = True
    finally:
        if commit_ok:
            shutil.rmtree(staging, ignore_errors=True)
        else:
            print(
                f"\nmerge: ERROR mid-commit. Staging preserved at: {staging.relative_to(vault)}\n"
                "  Vault may be in a partial state. Inspect staged files for recovery.",
                file=sys.stderr,
            )
        release_inbox_lock(lock)

    result.applied = True
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("type")
    ap.add_argument("primary_slug")
    ap.add_argument("secondary_slug")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    vault = find_vault_root(Path(__file__).parent)
    try:
        apply_merge(
            vault,
            args.type,
            args.primary_slug,
            args.secondary_slug,
            dry_run=not args.apply,
        )
    except MergeError as exc:
        print(f"merge: error: {exc}", file=sys.stderr)
        return 2

    if not args.apply:
        print("\n(dry-run — re-run with --apply to commit)")
    else:
        print("\nmerge: applied. Run /kb-graph project to refresh Kuzu.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
