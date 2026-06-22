import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from build_thread import (
    resolve_entity,
    read_sources,
    dedupe_citations,
    format_inputs,
    BuildThreadError,
)


def test_resolve_entity_finds_canonical_page(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    wiki = tmp_path / "wiki"
    (wiki / "people").mkdir(parents=True)
    (wiki / "people" / "alice.md").write_text(
        "---\ntype: Person\nslug: alice\n---\nbody"
    )
    ntype, path = resolve_entity(tmp_path, "alice")
    assert ntype == "Person"
    assert path.name == "alice.md"


def test_resolve_entity_skips_tofile_stubs(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    wiki = tmp_path / "wiki"
    (wiki / "tofile").mkdir(parents=True)
    (wiki / "tofile" / "ghost.md").write_text(
        "---\ntype: Topic\nslug: ghost\n---\n"
    )
    with pytest.raises(BuildThreadError):
        resolve_entity(tmp_path, "ghost")


def test_resolve_entity_skips_archive(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    wiki = tmp_path / "wiki"
    (wiki / "archive" / "people").mkdir(parents=True)
    (wiki / "archive" / "people" / "old.md").write_text(
        "---\ntype: Person\nslug: old\n---\n"
    )
    with pytest.raises(BuildThreadError):
        resolve_entity(tmp_path, "old")


def test_resolve_entity_raises_when_not_found(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    (tmp_path / "wiki").mkdir()
    with pytest.raises(BuildThreadError):
        resolve_entity(tmp_path, "ghost")


# ── read_sources ────────────────────────────────────────────

def test_read_sources_returns_raw_paths(tmp_path):
    p = tmp_path / "page.md"
    p.write_text(
        "---\n"
        "type: Source\n"
        "slug: x\n"
        "sources:\n"
        "  - \"[[raw/meetings/2026/05/m1.md]]\"\n"
        "  - \"[[raw/clippings/2026/05/c1.md]]\"\n"
        "---\nbody"
    )
    out = read_sources(p)
    assert "raw/meetings/2026/05/m1.md" in out
    assert "raw/clippings/2026/05/c1.md" in out


def test_read_sources_filters_wiki_links(tmp_path):
    p = tmp_path / "page.md"
    p.write_text(
        "---\n"
        "type: Person\n"
        "slug: a\n"
        "sources:\n"
        "  - \"[[raw/meetings/m1.md]]\"\n"
        "  - \"[[wiki/orgs/acme]]\"\n"
        "---\n"
    )
    out = read_sources(p)
    assert "raw/meetings/m1.md" in out
    assert "wiki/orgs/acme" not in out


def test_read_sources_handles_missing_field(tmp_path):
    p = tmp_path / "page.md"
    p.write_text("---\ntype: Person\nslug: a\n---\n")
    assert read_sources(p) == []


def test_read_sources_handles_no_frontmatter(tmp_path):
    p = tmp_path / "page.md"
    p.write_text("no frontmatter")
    assert read_sources(p) == []


# ── dedupe_citations ────────────────────────────────────────

def test_dedupe_citations_preserves_order():
    out = dedupe_citations(["a", "b"], ["b", "c"], ["a", "d"])
    assert out == ["a", "b", "c", "d"]


def test_dedupe_citations_empty_inputs():
    assert dedupe_citations() == []
    assert dedupe_citations([], []) == []


# ── format_inputs ───────────────────────────────────────────

def test_format_inputs_has_all_sections():
    entity = {"slug": "anthropic", "type": "Org"}
    neighbors = [
        {"slug": "x", "type": "Topic", "rel_type": "cites", "weight": 1.0, "direction": "in"},
    ]
    citations = ["raw/clippings/2026/05/c1.md"]
    qmd_hits = [{"path": "wiki/orgs/anthropic.md", "score": 85}]
    out = format_inputs(entity, neighbors, citations, qmd_hits)
    assert "## Entity" in out
    assert "anthropic" in out
    assert "## Graph 1-hop neighbours" in out
    assert "x" in out
    assert "## Citations" in out
    assert "raw/clippings/2026/05/c1.md" in out
    assert "## qmd top-10 hits" in out
    assert "85" in out
    assert "## Drafting guidance" in out


def test_format_inputs_empty_neighbours_shows_none():
    entity = {"slug": "alice", "type": "Person"}
    out = format_inputs(entity, [], [], [])
    assert "(none)" in out or "no neighbours" in out.lower()


def test_format_inputs_sorts_neighbors_by_weight():
    entity = {"slug": "alice", "type": "Person"}
    neighbors = [
        {"slug": "low", "type": "Topic", "rel_type": "mentions", "weight": 0.2, "direction": "out"},
        {"slug": "high", "type": "Org", "rel_type": "works_at", "weight": 3.0, "direction": "out"},
        {"slug": "mid", "type": "Topic", "rel_type": "related", "weight": 1.0, "direction": "out"},
    ]
    out = format_inputs(entity, neighbors, [], [])
    # high-weight should appear before low-weight in the output
    assert out.index("high") < out.index("mid") < out.index("low")
