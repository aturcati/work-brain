import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from undo import (
    discover_pages,
    strip_source_from_fm,
    strip_mention_lines,
    extract_edge_block,
    strip_index_entries,
    apply_undo,
    UndoError,
)


# ── helpers ──────────────────────────────────────────────

def _vault(tmp_path: Path) -> Path:
    (tmp_path / "CLAUDE.md").write_text("# fake")
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "log.md").write_text("# log\n")
    (tmp_path / "wiki" / "index.md").write_text("# index\n")
    (tmp_path / "wiki" / "_inbox").mkdir()
    (tmp_path / "wiki" / "_inbox" / "edges.md").write_text("# edges\n")
    (tmp_path / "raw").mkdir()
    (tmp_path / ".kb").mkdir()
    (tmp_path / "raw" / ".ingest-state.json").write_text("{}")
    (tmp_path / ".kb" / "extract-state.json").write_text("{}")
    return tmp_path


# ── discover_pages ───────────────────────────────────────

def test_discover_pages_classifies_sole_and_multi(tmp_path):
    v = _vault(tmp_path)
    wiki = v / "wiki"
    (wiki / "people").mkdir()
    (wiki / "people" / "alice.md").write_text(
        "---\ntype: Person\nslug: alice\nsources:\n  - \"[[raw/meetings/2026/05/foo.md]]\"\n---\n"
    )
    (wiki / "people" / "bob.md").write_text(
        "---\ntype: Person\nslug: bob\nsources:\n  - \"[[raw/meetings/2026/05/foo.md]]\"\n  - \"[[raw/meetings/2026/05/bar.md]]\"\n---\n"
    )
    (wiki / "people" / "carol.md").write_text(
        "---\ntype: Person\nslug: carol\nsources:\n  - \"[[raw/meetings/2026/05/bar.md]]\"\n---\n"
    )

    sole, multi = discover_pages(wiki, "raw/meetings/2026/05/foo.md")
    sole_names = sorted(p.name for p in sole)
    multi_names = sorted(p.name for p in multi)
    assert sole_names == ["alice.md"]
    assert multi_names == ["bob.md"]


def test_strip_source_from_fm_removes_link():
    fm = {"sources": ["[[raw/meetings/2026/05/foo.md]]", "[[raw/meetings/2026/05/bar.md]]"]}
    out = strip_source_from_fm(fm, "raw/meetings/2026/05/foo.md")
    assert out["sources"] == ["[[raw/meetings/2026/05/bar.md]]"]


def test_strip_source_from_fm_empty_list_removed():
    fm = {"sources": ["[[raw/meetings/2026/05/foo.md]]"], "type": "Person"}
    out = strip_source_from_fm(fm, "raw/meetings/2026/05/foo.md")
    assert "sources" not in out or out["sources"] == []


def test_strip_mention_lines_drops_lines_with_path_slug():
    body = (
        "## Journal mentions\n"
        "- 2026-05-11: foo (from [[raw/meetings/2026/05/foo.md]])\n"
        "- 2026-05-12: bar (from [[raw/meetings/2026/05/bar.md]])\n"
        "## Other\n"
        "Keep me.\n"
    )
    out = strip_mention_lines(body, "raw/meetings/2026/05/foo.md")
    assert "foo (from" not in out
    assert "bar (from" in out
    assert "Keep me" in out


def test_extract_edge_block_removes_block():
    text = (
        "# header\n\n"
        "## 2026-05-13 14:30 · raw/meetings/2026/05/foo.md\n"
        "- (alice, attended, m1, 0.9, \"evidence\")\n"
        "- (bob, attended, m1, 0.9, \"evidence\")\n\n"
        "## 2026-05-13 15:00 · raw/meetings/2026/05/bar.md\n"
        "- (carol, attended, m2, 0.9, \"x\")\n"
    )
    new, removed = extract_edge_block(text, "raw/meetings/2026/05/foo.md")
    assert "raw/meetings/2026/05/foo.md" not in new
    assert "(alice, attended, m1" not in new
    assert "raw/meetings/2026/05/bar.md" in new
    assert "(alice, attended, m1" in removed


def test_extract_edge_block_no_match_unchanged():
    text = "# header\n## 2026 · raw/x.md\n- (a, b, c, 0.5, \"\")\n"
    new, removed = extract_edge_block(text, "raw/y.md")
    assert new == text
    assert removed == ""


def test_strip_index_entries_removes_matching_lines():
    text = "- [[wiki/people/alice]]\n- [[wiki/people/bob]]\n- [[wiki/people/carol]]\n"
    out = strip_index_entries(text, ["wiki/people/alice", "wiki/people/carol"])
    assert "[[wiki/people/alice]]" not in out
    assert "[[wiki/people/bob]]" in out
    assert "[[wiki/people/carol]]" not in out


# ── apply_undo end-to-end ────────────────────────────────

def test_apply_undo_dry_run_does_not_write(tmp_path):
    v = _vault(tmp_path)
    raw_path = "raw/meetings/2026/05/foo.md"
    raw_full = v / raw_path
    raw_full.parent.mkdir(parents=True, exist_ok=True)
    raw_full.write_text("raw content")
    state = {raw_path: {"sha256": "abc", "status": "done", "ts": "2026-05-13T14:30:00Z"}}
    (v / "raw" / ".ingest-state.json").write_text(json.dumps(state))

    wiki = v / "wiki"
    (wiki / "people").mkdir()
    (wiki / "people" / "alice.md").write_text(
        "---\ntype: Person\nslug: alice\nsources:\n  - \"[[" + raw_path + "]]\"\n---\nbody"
    )

    result = apply_undo(v, raw_path, raw_disposition="keep", dry_run=True)
    assert (wiki / "people" / "alice.md").exists()
    assert raw_full.exists()
    assert not result.applied
    assert any(p.name == "alice.md" for p in result.pages_to_delete)


def test_apply_undo_applies_sole_source_delete(tmp_path):
    v = _vault(tmp_path)
    raw_path = "raw/meetings/2026/05/foo.md"
    raw_full = v / raw_path
    raw_full.parent.mkdir(parents=True, exist_ok=True)
    raw_full.write_text("raw")
    (v / "raw" / ".ingest-state.json").write_text(json.dumps({
        raw_path: {"sha256": "abc", "status": "done", "ts": "now"}
    }))
    (v / ".kb" / "extract-state.json").write_text(json.dumps({
        raw_path: {"sha256": "abc", "status": "done", "edge_count": 2, "ts": "now"}
    }))

    wiki = v / "wiki"
    (wiki / "people").mkdir()
    (wiki / "people" / "alice.md").write_text(
        "---\ntype: Person\nslug: alice\nsources:\n  - \"[[" + raw_path + "]]\"\n---\n"
    )
    (wiki / "_inbox" / "edges.md").write_text(
        "# edges\n## 2026-05-13 14:30 · " + raw_path + "\n- (alice, attended, m1, 0.9, \"e\")\n"
    )

    result = apply_undo(v, raw_path, raw_disposition="delete", dry_run=False)
    assert result.applied
    assert not (wiki / "people" / "alice.md").exists()
    assert not raw_full.exists()
    state = json.loads((v / "raw" / ".ingest-state.json").read_text())
    assert raw_path not in state
    extract = json.loads((v / ".kb" / "extract-state.json").read_text())
    assert raw_path not in extract
    edges_text = (wiki / "_inbox" / "edges.md").read_text()
    assert raw_path not in edges_text


def test_apply_undo_multi_source_strips_only(tmp_path):
    v = _vault(tmp_path)
    raw_path = "raw/meetings/2026/05/foo.md"
    other_path = "raw/meetings/2026/05/bar.md"
    raw_full = v / raw_path
    raw_full.parent.mkdir(parents=True, exist_ok=True)
    raw_full.write_text("raw")
    (v / "raw" / ".ingest-state.json").write_text(json.dumps({
        raw_path: {"sha256": "a", "status": "done", "ts": "now"}
    }))

    wiki = v / "wiki"
    (wiki / "people").mkdir()
    (wiki / "people" / "bob.md").write_text(
        "---\ntype: Person\nslug: bob\nsources:\n"
        "  - \"[[" + raw_path + "]]\"\n"
        "  - \"[[" + other_path + "]]\"\n---\n"
        "## Journal mentions\n"
        "- 2026-05-11: foo (from [[" + raw_path + "]])\n"
        "- 2026-05-10: bar (from [[" + other_path + "]])\n"
    )

    apply_undo(v, raw_path, raw_disposition="keep", dry_run=False)
    text = (wiki / "people" / "bob.md").read_text()
    assert raw_path not in text
    assert other_path in text
    assert "bar (from" in text


def test_apply_undo_rejects_unknown_raw_path(tmp_path):
    v = _vault(tmp_path)
    with pytest.raises(UndoError):
        apply_undo(v, "raw/never/seen.md", raw_disposition="keep", dry_run=True)


def test_apply_undo_restore_moves_raw_to_inbox(tmp_path):
    v = _vault(tmp_path)
    raw_path = "raw/meetings/2026/05/foo.md"
    raw_full = v / raw_path
    raw_full.parent.mkdir(parents=True, exist_ok=True)
    raw_full.write_text("raw")
    (v / "raw" / ".ingest-state.json").write_text(json.dumps({
        raw_path: {"sha256": "a", "status": "done", "ts": "now"}
    }))

    apply_undo(v, raw_path, raw_disposition="restore", dry_run=False)
    assert not raw_full.exists()
    restored = v / "raw" / "inbox" / "meetings" / "foo.md"
    assert restored.exists()


def test_apply_undo_rejects_non_done_status(tmp_path):
    v = _vault(tmp_path)
    raw_path = "raw/meetings/2026/05/foo.md"
    raw_full = v / raw_path
    raw_full.parent.mkdir(parents=True, exist_ok=True)
    raw_full.write_text("raw")
    (v / "raw" / ".ingest-state.json").write_text(json.dumps({
        raw_path: {"sha256": "a", "status": "pending", "ts": "now"}
    }))
    with pytest.raises(UndoError):
        apply_undo(v, raw_path, raw_disposition="keep", dry_run=True)


def test_apply_undo_writes_log_entry(tmp_path):
    v = _vault(tmp_path)
    raw_path = "raw/meetings/2026/05/foo.md"
    raw_full = v / raw_path
    raw_full.parent.mkdir(parents=True, exist_ok=True)
    raw_full.write_text("raw")
    (v / "raw" / ".ingest-state.json").write_text(json.dumps({
        raw_path: {"sha256": "a", "status": "done", "ts": "now"}
    }))
    apply_undo(v, raw_path, raw_disposition="keep", dry_run=False)
    log_text = (v / "wiki" / "log.md").read_text()
    assert "kb-undo-ingest | reverted" in log_text
    assert raw_path in log_text


def test_apply_undo_strips_index_entries_only_exact_match(tmp_path):
    v = _vault(tmp_path)
    raw_path = "raw/meetings/2026/05/foo.md"
    raw_full = v / raw_path
    raw_full.parent.mkdir(parents=True, exist_ok=True)
    raw_full.write_text("raw")
    (v / "raw" / ".ingest-state.json").write_text(json.dumps({
        raw_path: {"sha256": "a", "status": "done", "ts": "now"}
    }))
    wiki = v / "wiki"
    (wiki / "people").mkdir()
    (wiki / "people" / "alice.md").write_text(
        "---\ntype: Person\nslug: alice\nsources:\n  - \"[[" + raw_path + "]]\"\n---\n"
    )
    # index has both exact-match alice and unrelated alice-smith
    (wiki / "index.md").write_text(
        "- [[wiki/people/alice]]\n"
        "- [[wiki/people/alice-smith]]\n"
    )
    apply_undo(v, raw_path, raw_disposition="keep", dry_run=False)
    idx = (wiki / "index.md").read_text()
    assert "[[wiki/people/alice]]" not in idx
    assert "[[wiki/people/alice-smith]]" in idx, "exact-match must NOT remove longer prefix sibling"
