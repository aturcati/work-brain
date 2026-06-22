# /// script
# dependencies = ["pytest", "pyyaml"]
# ///
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (  # noqa: E402
    DEFAULT_EDGE_WEIGHT,
    EDGE_KEYS,
    EDGE_KEYS_SET,
    EDGE_WEIGHTS,
    NODE_TYPES,
    SKIP_DERIVED,
    SKIP_NAMES,
    SKIP_NONGRAPH,
    SKIP_STUBS,
    TYPE_TO_DIR,
    acquire_inbox_lock,
    find_vault_root,
    parse_frontmatter_text,
    physical_lock_path,
    release_inbox_lock,
)

VAULT = Path(__file__).resolve().parent.parent.parent.parent  # work-brain root


# ── Lock ─────────────────────────────────────────────────────────────────────


def test_lock_physical_path_not_in_vault():
    lock = physical_lock_path(str(VAULT / ".kb" / ".inbox.lock"))
    assert not str(lock).startswith(str(VAULT)), (
        f"Lock path {lock} is inside vault {VAULT} — would sync to cloud storage"
    )
    assert lock.suffix == ".lock"


def test_acquire_release_lock(tmp_path):
    lock = acquire_inbox_lock(tmp_path)
    assert lock.exists()
    release_inbox_lock(lock)
    assert not lock.exists()


def test_acquire_lock_idempotent_after_release(tmp_path):
    lock = acquire_inbox_lock(tmp_path)
    release_inbox_lock(lock)
    lock2 = acquire_inbox_lock(tmp_path)
    release_inbox_lock(lock2)


# ── Frontmatter ───────────────────────────────────────────────────────────────


def test_parse_frontmatter_text_valid():
    text = "---\ntype: Person\nslug: test-person\n---\nBody text"
    fm = parse_frontmatter_text(text)
    assert fm is not None
    assert fm["type"] == "Person"
    assert fm["slug"] == "test-person"


def test_parse_frontmatter_text_no_frontmatter():
    assert parse_frontmatter_text("No frontmatter here") is None


def test_parse_frontmatter_text_malformed_yaml():
    assert parse_frontmatter_text("---\n: bad: yaml:\n---\n") is None


def test_parse_frontmatter_text_empty_block():
    assert parse_frontmatter_text("---\n---\n") is None


# ── Constants ─────────────────────────────────────────────────────────────────


def test_edge_keys_tuple_and_set_match():
    assert set(EDGE_KEYS) == EDGE_KEYS_SET


def test_edge_keys_count():
    assert len(EDGE_KEYS) == 19, f"Expected 19 edge keys, got {len(EDGE_KEYS)}"


def test_node_types_matches_type_to_dir():
    assert NODE_TYPES == frozenset(TYPE_TO_DIR)
    assert len(TYPE_TO_DIR) == 9


def test_edge_weights_subset_of_edge_keys():
    assert set(EDGE_WEIGHTS).issubset(EDGE_KEYS_SET)


def test_default_edge_weight():
    assert DEFAULT_EDGE_WEIGHT == 1.0


def test_skip_tier_subset_ordering():
    assert SKIP_STUBS < SKIP_NONGRAPH < SKIP_DERIVED


def test_skip_stubs_contents():
    assert "_inbox" in SKIP_STUBS
    assert "tofile" in SKIP_STUBS
    assert "archive" not in SKIP_STUBS  # archive must be visible to lint/validate


def test_skip_nongraph_excludes_archive():
    assert "archive" in SKIP_NONGRAPH


def test_skip_derived_full():
    assert "log-archive" in SKIP_DERIVED
    assert "_maps" in SKIP_DERIVED


def test_skip_names():
    assert "overview.md" in SKIP_NAMES
    assert "index.md" in SKIP_NAMES


# ── Vault root ────────────────────────────────────────────────────────────────


def test_find_vault_root():
    root = find_vault_root(Path(__file__))
    assert (root / "CLAUDE.md").exists()
    assert root == VAULT
