#!/usr/bin/env python3
# /// script
# dependencies = []
# ///
"""
Move a file from raw/inbox/<channel>/ to raw/<channel>/YYYY/MM/ (date-partitioned).
Creates destination dirs if absent. Prints destination path on stdout.

Usage:
  python move_file.py \
    --src raw/inbox/journal/2026-05-11-sample.md \
    --channel journal \
    --date 2026-05-11
"""
import argparse
import shutil
from pathlib import Path


def find_vault_root(start: Path) -> Path:
    """Walk up from start until a directory containing CLAUDE.md is found."""
    current = start.resolve()
    while current.parent != current:
        if (current / "CLAUDE.md").exists():
            return current
        current = current.parent
    raise FileNotFoundError("Could not find vault root (no CLAUDE.md found in any parent dir)")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--src", required=True)
    p.add_argument("--channel", required=True)
    p.add_argument("--date", required=True, help="YYYY-MM-DD from file frontmatter")
    args = p.parse_args()

    src = Path(args.src).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Source not found: {src}")

    parts = args.date.split("-")
    if len(parts) < 2:
        raise ValueError(f"Invalid date format (expected YYYY-MM-DD): {args.date}")
    year, month = parts[0], parts[1]

    vault_root = find_vault_root(src.parent)
    dest_dir = vault_root / "raw" / args.channel / year / month
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name

    if dest.exists():
        raise FileExistsError(
            f"Destination already exists: {dest} — rename source file to avoid collision"
        )
    shutil.move(str(src), str(dest))
    print(str(dest))


if __name__ == "__main__":
    main()
