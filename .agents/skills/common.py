"""Shared infrastructure for work-brain skill helpers.

Import pattern (add after all other imports in each skill file):

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from common import find_vault_root, TYPE_TO_DIR, EDGE_KEYS  # noqa: E402

Pure stdlib at module level — importing common forces zero PEP 723 deps.
`import yaml` is deferred inside parse_frontmatter_text only.
"""
from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Node types ──────────────────────────────────────────────────────────────

TYPE_TO_DIR: dict[str, str] = {
    "Person": "people",
    "Org": "orgs",
    "Project": "projects",
    "Topic": "topics",
    "Decision": "decisions",
    "Meeting": "meetings",
    "Source": "sources",
    "Artifact": "artifacts",
    "Event": "events",
}
NODE_TYPES: frozenset[str] = frozenset(TYPE_TO_DIR)

# ── Edge vocabulary — canonical order matches AGENTS.md frontmatter contract ─

EDGE_KEYS: tuple[str, ...] = (
    "part_of", "instance_of", "related",
    "works_at", "attended", "authored", "owns", "reports_to",
    "sources", "derived_from", "cites", "supersedes", "superseded_by",
    "contradicts", "confirms",
    "depends_on", "caused_by", "decided", "mentions",
)
EDGE_KEYS_SET: frozenset[str] = frozenset(EDGE_KEYS)

EDGE_WEIGHTS: dict[str, float] = {
    "decided": 3.0,
    "sources": 3.0,
    "authored": 3.0,
    "works_at": 3.0,
    "mentions": 0.2,
}
DEFAULT_EDGE_WEIGHT: float = 1.0

# ── Skip-dir tiers — named semantic scopes, NOT a single unified set ─────────
# Each tier is intentionally different; do not collapse to one constant.

SKIP_STUBS: frozenset[str] = frozenset({"_inbox", "tofile"})
# lint/validate/link: must inspect archive/ (archived pages still need valid frontmatter)

SKIP_NONGRAPH: frozenset[str] = SKIP_STUBS | {"archive"}
# graph/project: exclude archived nodes from the projected graph

SKIP_DERIVED: frozenset[str] = SKIP_NONGRAPH | {"log-archive", "_maps"}
# merge/rename/thread/suggest-merges: full vault traversal exclusions

SKIP_NAMES: frozenset[str] = frozenset({"overview.md", "index.md"})

_LOCK_STALE_SECONDS = 300


# ── Functions ────────────────────────────────────────────────────────────────


def find_vault_root(start: Path) -> Path:
    """Walk up from start until a directory containing CLAUDE.md is found."""
    current = start.resolve()
    while current.parent != current:
        if (current / "CLAUDE.md").exists():
            return current
        current = current.parent
    raise FileNotFoundError("Cannot find vault root (CLAUDE.md not found)")


def parse_frontmatter_text(text: str) -> dict | None:
    """Parse YAML frontmatter from a markdown string. yaml import is deferred."""
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        import yaml  # deferred: importing common must force zero PEP 723 deps
        fm = yaml.safe_load(parts[1])
        return fm if isinstance(fm, dict) else None
    except Exception:
        return None


def parse_frontmatter(path: Path) -> dict | None:
    """Read file at path and parse its YAML frontmatter."""
    return parse_frontmatter_text(path.read_text(encoding="utf-8", errors="replace"))


def graph_db_path(vault: Path) -> Path:
    """Physical Kuzu DB location outside the cloud-synced vault.

    KB_GRAPH_DIR env var overrides the default ~/.cache/work-brain-graph/.
    Keyed by sha256 of the resolved vault path so multiple vaults don't clash.
    """
    base = Path(os.environ.get("KB_GRAPH_DIR") or Path.home() / ".cache" / "work-brain-graph")
    digest = hashlib.sha256(str(Path(vault).resolve()).encode("utf-8")).hexdigest()[:16]
    d = base / digest
    d.mkdir(parents=True, exist_ok=True)
    return d / "graph.kuzu"


def physical_lock_path(logical: str) -> Path:
    """Map a logical lock name to a file outside any cloud-synced tree.

    KB_LOCK_DIR env var overrides the default ~/.cache/work-brain-locks/.
    Never returns a path inside the vault — synced advisory locks are unsound.
    """
    lock_dir = Path(
        os.environ.get("KB_LOCK_DIR") or Path.home() / ".cache" / "work-brain-locks"
    )
    digest = hashlib.sha256(str(Path(logical).resolve()).encode("utf-8")).hexdigest()[:16]
    return lock_dir / f"{digest}.lock"


def acquire_inbox_lock(vault: Path, timeout: int = 5) -> Path:
    """Acquire the inbox advisory lock. Returns the physical lock path.

    Uses atomic O_CREAT|O_EXCL — correct for skills that run as separate
    subprocesses (flock releases on process exit, which is incorrect here).
    Raises TimeoutError if the lock cannot be acquired within `timeout` seconds.
    """
    logical = str(vault.resolve() / ".kb" / ".inbox.lock")
    lock_path = physical_lock_path(logical)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # Migration: remove any legacy in-vault lock file
    legacy = vault / ".kb" / ".inbox.lock"
    if legacy.exists():
        legacy.unlink(missing_ok=True)

    for attempt in range(timeout):
        if lock_path.exists():
            age = time.time() - lock_path.stat().st_mtime
            if age > _LOCK_STALE_SECONDS:
                lock_path.unlink(missing_ok=True)
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.write(fd, datetime.now(timezone.utc).isoformat().encode())
            os.close(fd)
            return lock_path
        except FileExistsError:
            if attempt < timeout - 1:
                time.sleep(1)

    raise TimeoutError(
        f"Inbox lock busy after {timeout}s — delete {lock_path} manually if stale"
    )


def release_inbox_lock(lock: Path) -> None:
    """Release the inbox advisory lock."""
    lock.unlink(missing_ok=True)
