# /// script
# requires-python = ">=3.9,<3.14"
# dependencies = []
# ///
"""
Rewrite stale raw/inbox/... sources in wiki pages to actual raw/<channel>/YYYY/MM/ paths.
Dry-run by default; pass --apply to write changes.
"""
import re
import sys
from pathlib import Path

VAULT = Path(__file__).parent.parent.parent.parent

def build_slug_index() -> dict[str, Path]:
    """slug (no .md) -> actual path relative to VAULT"""
    index: dict[str, Path] = {}
    for channel in ("meetings", "emails", "clippings", "chats", "docs"):
        channel_dir = VAULT / "raw" / channel
        if not channel_dir.exists():
            continue
        for f in channel_dir.rglob("*.md"):
            slug = f.stem
            rel = f.relative_to(VAULT)
            # last writer wins — shouldn't matter since slugs are unique
            index[slug] = rel
    return index

INBOX_RE = re.compile(r'\[\[raw/inbox/[^/]+/([^\]\.]+)(?:\.md)?\]\]')

def fix_file(path: Path, index: dict[str, Path], apply: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    changes = []
    def replace(m: re.Match) -> str:
        slug = m.group(1)
        if slug in index:
            new_link = f"[[{index[slug]}]]"
            if new_link != m.group(0):
                changes.append(f"  {m.group(0)} → {new_link}")
            return new_link
        # no match found — leave as-is
        return m.group(0)
    new_text = INBOX_RE.sub(replace, text)
    if changes and apply:
        path.write_text(new_text, encoding="utf-8")
    return changes

def main():
    apply = "--apply" in sys.argv
    index = build_slug_index()
    print(f"Slug index: {len(index)} entries")

    wiki_dir = VAULT / "wiki"
    total_files = total_changes = 0
    for f in sorted(wiki_dir.rglob("*.md")):
        changes = fix_file(f, index, apply)
        if changes:
            total_files += 1
            total_changes += len(changes)
            rel = f.relative_to(VAULT)
            print(f"\n{rel} ({len(changes)} change{'s' if len(changes)>1 else ''}):")
            for c in changes:
                print(c)

    print(f"\n{'Applied' if apply else 'Dry-run'}: {total_changes} replacements across {total_files} files")
    if not apply:
        print("Re-run with --apply to write changes")

if __name__ == "__main__":
    main()
