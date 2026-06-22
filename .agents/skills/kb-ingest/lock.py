#!/usr/bin/env python3
# /// script
# dependencies = []
# ///
"""
Advisory lock for .kb/.inbox.lock.

Uses atomic O_CREAT|O_EXCL file creation. Stale locks older than 300s are
auto-cleared. Suitable for Claude skill steps that run as separate subprocesses
(flock would release on process exit — incorrect for this use case).

The --lock-file argument is a LOGICAL name: the actual lock file lives outside
the vault, under $KB_LOCK_DIR (default ~/.cache/work-brain-locks/), keyed by
the sha256 of the logical path's absolute form. Vaults synced by OneDrive/
Dropbox/iCloud otherwise fight the sync client over the rapidly created and
deleted lock file — and a cloud-synced advisory lock is meaningless anyway
(sync lag makes it unsound across machines; it only serializes local
processes).

Usage:
  python lock.py --lock-file .kb/.inbox.lock --action acquire [--timeout 5]
  python lock.py --lock-file .kb/.inbox.lock --action release

acquire: prints ACQUIRED and exits 0; exits 1 with message on timeout.
release: deletes lock file; prints RELEASED.
"""
import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import physical_lock_path  # noqa: E402

STALE_SECONDS = 300


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--lock-file", required=True)
    p.add_argument("--action", required=True, choices=["acquire", "release"])
    p.add_argument("--timeout", type=int, default=5)
    args = p.parse_args()

    lock_path = physical_lock_path(args.lock_file)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # One-time migration: a legacy in-vault lock file must not keep a stale
    # claim alive (or confuse the sync client) after the redirect.
    legacy = Path(args.lock_file)
    if legacy.exists():
        legacy.unlink(missing_ok=True)

    if args.action == "release":
        lock_path.unlink(missing_ok=True)
        print("RELEASED")
        return

    for attempt in range(args.timeout):
        if lock_path.exists():
            age = time.time() - lock_path.stat().st_mtime
            if age > STALE_SECONDS:
                lock_path.unlink(missing_ok=True)

        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            ts = datetime.now(timezone.utc).isoformat()
            os.write(fd, ts.encode())
            os.close(fd)
            print("ACQUIRED")
            return
        except FileExistsError:
            if attempt < args.timeout - 1:
                time.sleep(1)

    print(
        f"LOCK_TIMEOUT: {lock_path} busy after {args.timeout}s — "
        "delete it manually if stale",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
