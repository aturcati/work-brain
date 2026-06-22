#!/usr/bin/env python3
# /// script
# dependencies = []
# ///
"""
Idempotency state file helper for kb-ingest and kb-graph extract.

Usage:
  Check (prints sha256 hex if not yet recorded, or "SKIP" if already recorded):
    python state.py --state-file raw/.ingest-state.json \
                   --raw-path raw/inbox/journal/2026-05-11-sample.md \
                   --action check

  Write entry (prints "WRITTEN"):
    python state.py --state-file raw/.ingest-state.json \
                   --raw-path raw/journal/2026/05/2026-05-11-sample.md \
                   --action write --status done --extra edge_count=3
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_state(state_file: Path) -> dict:
    if state_file.exists():
        return json.loads(state_file.read_text())
    return {}


def save_state(state_file: Path, state: dict) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(state_file)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--state-file", required=True)
    p.add_argument("--raw-path", required=True)
    p.add_argument("--action", required=True, choices=["check", "write"])
    p.add_argument("--status", default="done")
    p.add_argument("--extra", nargs="*", default=[])
    args = p.parse_args()

    state_file = Path(args.state_file)
    raw_path = Path(args.raw_path)

    if not raw_path.exists():
        print(f"ERROR: {raw_path} not found", file=sys.stderr)
        sys.exit(1)

    digest = sha256_file(raw_path)
    state = load_state(state_file)
    key = str(raw_path)

    if args.action == "check":
        print("SKIP" if key in state else digest)
        return

    # write
    entry: dict = {
        "sha256": digest,
        "status": args.status,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    for kv in (args.extra or []):
        k, v = kv.split("=", 1)
        try:
            entry[k] = int(v)
        except ValueError:
            entry[k] = v
    state[key] = entry
    save_state(state_file, state)
    print("WRITTEN")


if __name__ == "__main__":
    main()
