#!/usr/bin/env python3
# /// script
# requires-python = '>=3.9,<3.14'
# dependencies = ['ruamel.yaml']
# ///
"""
kb-undo-ingest: reverse a completed ingest for one raw source file.

Usage:
  uv run .agents/skills/kb-undo-ingest/undo.py <raw-path> [--raw keep|delete|restore] [--apply]
"""
import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ruamel.yaml import YAML

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import SKIP_DERIVED, acquire_inbox_lock, dump_page, release_inbox_lock  # noqa: E402

SKIP_DIRS = SKIP_DERIVED - {"tofile"}  # undo must traverse tofile/ stubs to reverse them
SKIP_FILES = {"index.md", "overview.md", "log.md"}


class UndoError(Exception):
    """Raised when an ingest cannot be safely undone."""


@dataclass
class UndoResult:
    raw_path: str
    pages_to_delete: list[Path] = field(default_factory=list)
    pages_to_strip: list[Path] = field(default_factory=list)
    edges_removed: int = 0
    applied: bool = False


def find_vault_root(start: Path) -> Path:
    cur = start.resolve()
    if cur.is_file():
        cur = cur.parent
    while cur.parent != cur:
        if (cur / "CLAUDE.md").exists() and (cur / "wiki").is_dir() and (cur / "raw").is_dir():
            return cur
        cur = cur.parent
    raise UndoError("vault root not found")


def _read_yaml(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise UndoError(f"missing frontmatter: {path}")
    parts = text.split("---", 2)
    if len(parts) != 3:
        raise UndoError(f"unterminated frontmatter: {path}")
    yaml = YAML()
    yaml.preserve_quotes = True
    fm = yaml.load(parts[1]) or {}
    if not isinstance(fm, dict):
        raise UndoError(f"frontmatter is not a mapping: {path}")
    return fm, parts[2]


def _sources_links(fm: dict) -> list[str]:
    sources = fm.get("sources") or []
    if not isinstance(sources, list):
        return []
    return [str(source).strip().strip('"').strip("'") for source in sources]


def _normalise_link(raw_path: str) -> str:
    value = str(raw_path).strip().strip('"').strip("'")
    if value.startswith("[[") and value.endswith("]]"):
        value = value[2:-2].strip()
    return f"[[{value}]]"


def discover_pages(wiki_dir: Path, raw_path: str) -> tuple[list[Path], list[Path]]:
    target = _normalise_link(raw_path)
    sole_source_pages: list[Path] = []
    multi_source_pages: list[Path] = []

    for page in sorted(wiki_dir.rglob("*.md")):
        rel_parts = page.relative_to(wiki_dir).parts
        if rel_parts[-1] in SKIP_FILES:
            continue
        if any(part in SKIP_DIRS for part in rel_parts[:-1]):
            continue
        try:
            fm, _body = _read_yaml(page)
        except UndoError:
            continue

        sources = _sources_links(fm)
        if target not in sources:
            continue
        if len(sources) == 1:
            sole_source_pages.append(page)
        else:
            multi_source_pages.append(page)

    return sole_source_pages, multi_source_pages


def strip_source_from_fm(fm: dict, raw_path: str) -> dict:
    target = _normalise_link(raw_path)
    out = dict(fm)
    sources = [
        source for source in (out.get("sources") or [])
        if _normalise_link(str(source)) != target
    ]
    if sources:
        out["sources"] = sources
    else:
        out.pop("sources", None)
    return out


def strip_mention_lines(body: str, raw_path: str) -> str:
    return "".join(
        line for line in body.splitlines(keepends=True) if raw_path not in line
    )


def extract_edge_block(edges_text: str, raw_path: str) -> tuple[str, str]:
    header = re.compile(
        rf"^## \d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}} · {re.escape(raw_path)}\s*$",
        re.MULTILINE,
    )
    match = header.search(edges_text)
    if not match:
        return edges_text, ""

    next_header = re.search(r"^## ", edges_text[match.end():], re.MULTILINE)
    end = match.end() + next_header.start() if next_header else len(edges_text)
    removed = edges_text[match.start():end]
    return edges_text[:match.start()] + edges_text[end:], removed


def strip_index_entries(index_text: str, page_paths: list[str]) -> str:
    """Remove lines containing a wikilink whose target exactly matches one of
    `page_paths` (with optional `.md` suffix, optional `|alias` or `#anchor`).

    Substring matching would cause false positives — e.g. `wiki/people/alice`
    would match `[[wiki/people/alice-smith]]`. Use exact wikilink-form regex.
    """
    patterns: list[re.Pattern] = []
    for page_path in page_paths:
        no_suffix = str(page_path).removesuffix(".md").removeprefix("wiki/")
        # Match [[wiki/<path>]], [[wiki/<path>.md]], [[wiki/<path>|...]], [[wiki/<path>#...]]
        # plus bare-prefix forms without leading "wiki/".
        for prefix in (f"wiki/{no_suffix}", no_suffix):
            patterns.append(re.compile(
                r"\[\[" + re.escape(prefix) + r"(?:\.md)?(?=[\]|#])"
            ))
    kept: list[str] = []
    for line in index_text.splitlines(keepends=True):
        if any(p.search(line) for p in patterns):
            continue
        kept.append(line)
    return "".join(kept)


def _strip_state(path: Path, raw_path: str) -> bool:
    if not path.exists():
        return False
    data = json.loads(path.read_text(encoding="utf-8") or "{}")
    if raw_path not in data:
        return False
    del data[raw_path]
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    return True


def _infer_channel(raw_path: str) -> str:
    parts = Path(raw_path).parts
    if len(parts) < 2 or parts[0] != "raw":
        raise UndoError(f"cannot infer channel from raw path: {raw_path}")
    return parts[1]


def _dispose_raw(vault: Path, raw_path: str, disposition: str) -> str:
    full = vault / raw_path
    if disposition == "keep":
        return "kept"
    if disposition == "delete":
        if full.exists():
            full.unlink()
        return "deleted"
    if disposition == "restore":
        if not full.exists():
            raise UndoError(f"raw file not found for restore: {raw_path}")
        channel = _infer_channel(raw_path)
        target_dir = vault / "raw" / "inbox" / channel
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / full.name
        if target.exists():
            raise UndoError(f"restore target already exists: {target.relative_to(vault)}")
        shutil.move(str(full), str(target))
        return f"restored to {target.relative_to(vault)}"
    raise UndoError(f"unknown raw disposition: {disposition}")


def apply_undo(
    vault: Path,
    raw_path: str,
    raw_disposition: str = "keep",
    dry_run: bool = True,
) -> UndoResult:
    if raw_disposition not in {"keep", "delete", "restore"}:
        raise UndoError(f"unknown raw disposition: {raw_disposition}")

    state_path = vault / "raw" / ".ingest-state.json"
    extract_state_path = vault / ".kb" / "extract-state.json"
    wiki_dir = vault / "wiki"
    edges_path = wiki_dir / "_inbox" / "edges.md"
    index_path = wiki_dir / "index.md"
    log_path = wiki_dir / "log.md"

    if not state_path.exists():
        raise UndoError("raw/.ingest-state.json not found")
    state = json.loads(state_path.read_text(encoding="utf-8") or "{}")
    entry = state.get(raw_path)
    if not entry:
        raise UndoError(f"{raw_path} not found in ingest state")
    if entry.get("status") != "done":
        raise UndoError(f"{raw_path} is not marked done in ingest state")

    sole_source_pages, multi_source_pages = discover_pages(wiki_dir, raw_path)
    edges_text = edges_path.read_text(encoding="utf-8") if edges_path.exists() else ""
    _new_edges_text, removed_edge_block = extract_edge_block(edges_text, raw_path)
    edge_count = sum(1 for line in removed_edge_block.splitlines() if line.lstrip().startswith("-"))

    result = UndoResult(
        raw_path=raw_path,
        pages_to_delete=sole_source_pages,
        pages_to_strip=multi_source_pages,
        edges_removed=edge_count,
    )

    extract_state = {}
    if extract_state_path.exists():
        extract_state = json.loads(extract_state_path.read_text(encoding="utf-8") or "{}")

    print(f"undo-ingest plan for {raw_path}")
    print(f"  pages to DELETE: {len(sole_source_pages)}")
    for page in sole_source_pages:
        print(f"    - {page.relative_to(vault)}")
    print(f"  pages to STRIP: {len(multi_source_pages)}")
    for page in multi_source_pages:
        print(f"    - {page.relative_to(vault)}")
    print(f"  edge proposals to remove: {edge_count}")
    if removed_edge_block:
        start = edges_text[:edges_text.find(removed_edge_block)].count("\n") + 1
        end = start + removed_edge_block.count("\n")
        print(f"    - {edges_path.relative_to(vault)}:{start}-{end}")
    print("  state entries to remove:")
    print("    - raw/.ingest-state.json")
    if raw_path in extract_state:
        print("    - .kb/extract-state.json")
    print(f"  raw file disposition: {raw_disposition}")

    if dry_run:
        return result

    # Serialise against kb-ingest via inbox lock.
    try:
        lock = acquire_inbox_lock(vault)
    except TimeoutError as exc:
        raise UndoError(str(exc)) from exc
    try:
        # 1. Raw disposition FIRST — if it fails (e.g. restore conflict), state
        #    files remain consistent so the user can retry without losing context.
        raw_status = _dispose_raw(vault, raw_path, raw_disposition)

        # 2. Delete sole-source pages
        deleted_index_paths = [
            str(page.relative_to(vault).with_suffix("")) for page in sole_source_pages
        ]
        for page in sole_source_pages:
            page.unlink()

        # 3. Strip multi-source pages
        for page in multi_source_pages:
            fm, body = _read_yaml(page)
            new_fm = strip_source_from_fm(fm, raw_path)
            new_body = strip_mention_lines(body, raw_path)
            page.write_text(dump_page(new_fm, new_body), encoding="utf-8")

        # 4. Edges + index
        if edges_path.exists() and removed_edge_block:
            new_edges_text, _ = extract_edge_block(edges_path.read_text(encoding="utf-8"), raw_path)
            edges_path.write_text(new_edges_text, encoding="utf-8")
        if index_path.exists() and deleted_index_paths:
            new_index_text = strip_index_entries(index_path.read_text(encoding="utf-8"), deleted_index_paths)
            index_path.write_text(new_index_text, encoding="utf-8")

        # 5. State files LAST — only clear after all wiki + raw mutations succeeded.
        _strip_state(state_path, raw_path)
        _strip_state(extract_state_path, raw_path)

        # 6. Log
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        log_path.open("a", encoding="utf-8").write(
            f"\n## [{ts}] kb-undo-ingest | reverted {raw_path} "
            f"({len(sole_source_pages)} deleted, {len(multi_source_pages)} stripped, "
            f"{edge_count} edge proposal(s) removed; raw: {raw_status})\n"
        )
    finally:
        release_inbox_lock(lock)

    result.applied = True
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reverse a completed KB ingest.")
    parser.add_argument("raw_path")
    parser.add_argument("--raw", choices=["keep", "delete", "restore"], default="keep")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    try:
        vault = find_vault_root(Path(__file__))
        apply_undo(vault, args.raw_path, raw_disposition=args.raw, dry_run=not args.apply)
    except UndoError as exc:
        print(f"undo-ingest: error: {exc}", file=sys.stderr)
        return 2

    if args.apply:
        print("undo-ingest: applied")
    else:
        print("dry-run only; re-run with --apply to modify files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
