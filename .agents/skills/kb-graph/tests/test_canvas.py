import sys
import json
import math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from canvas import (
    compute_layout,
    build_canvas_json,
    apply_canvas,
    CanvasError,
    TYPE_TO_DIR,
    TYPE_COLORS,
)


def _seed(slug="anthropic", type_="Org"):
    return {"slug": slug, "type": type_, "path": Path(f"wiki/{TYPE_TO_DIR[type_]}/{slug}.md")}


def _neighbor(slug, type_="Topic", rel="cites", weight=1.0, direction="out"):
    return {
        "slug": slug,
        "type": type_,
        "rel_type": rel,
        "weight": weight,
        "direction": direction,
        "path": Path(f"wiki/{TYPE_TO_DIR[type_]}/{slug}.md"),
    }


# ── compute_layout ──────────────────────────────────────────

def test_compute_layout_places_seed_at_origin():
    out = compute_layout([])
    # No neighbours → still returns empty list (seed handled by caller separately)
    assert out == []


def test_compute_layout_evenly_spaces_neighbors():
    neighbors = [_neighbor("a"), _neighbor("b"), _neighbor("c"), _neighbor("d")]
    out = compute_layout(neighbors, radius=350)
    assert len(out) == 4
    # 4 neighbours at 90-deg increments
    xs = [round(n["x"]) for n in out]
    ys = [round(n["y"]) for n in out]
    # angles: 0, 90, 180, 270 → (350,0), (0,350), (-350,0), (0,-350)
    assert 350 in xs
    assert -350 in xs
    assert 350 in ys
    assert -350 in ys


def test_compute_layout_stable_ordering():
    # Same input yields same output positions
    neighbors = [_neighbor("a", weight=1.0), _neighbor("b", weight=2.0)]
    out1 = compute_layout(neighbors)
    out2 = compute_layout(neighbors)
    assert out1 == out2


def test_compute_layout_sorts_by_weight_then_slug():
    n_a = _neighbor("alpha", weight=1.0)
    n_b = _neighbor("beta",  weight=2.0)
    n_c = _neighbor("gamma", weight=2.0)
    out = compute_layout([n_a, n_b, n_c])
    # heaviest first; ties broken alphabetically
    slugs = [n["slug"] for n in out]
    assert slugs == ["beta", "gamma", "alpha"]


# ── build_canvas_json ───────────────────────────────────────

def test_build_canvas_json_returns_nodes_and_edges():
    seed = _seed()
    n1 = _neighbor("contextual-retrieval", type_="Topic", rel="cites", direction="in")
    laid_out = compute_layout([n1])
    data = build_canvas_json(seed, laid_out)
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) == 2  # seed + 1 neighbour
    assert len(data["edges"]) == 1


def test_build_canvas_json_seed_at_origin():
    seed = _seed()
    data = build_canvas_json(seed, [])
    seed_node = data["nodes"][0]
    assert seed_node["x"] == 0
    assert seed_node["y"] == 0
    assert seed_node["file"] == "wiki/orgs/anthropic.md"
    assert seed_node["type"] == "file"


def test_build_canvas_json_node_colors_match_type():
    seed = _seed("alice", type_="Person")
    n1 = _neighbor("acme", type_="Org")
    laid_out = compute_layout([n1])
    data = build_canvas_json(seed, laid_out)
    seed_color = next(n["color"] for n in data["nodes"] if n["file"].endswith("alice.md"))
    org_color = next(n["color"] for n in data["nodes"] if n["file"].endswith("acme.md"))
    assert seed_color == TYPE_COLORS["Person"]
    assert org_color == TYPE_COLORS["Org"]


def test_build_canvas_json_edge_labelled_with_rel_type():
    seed = _seed("alice", type_="Person")
    n1 = _neighbor("acme", type_="Org", rel="works_at", direction="out")
    laid_out = compute_layout([n1])
    data = build_canvas_json(seed, laid_out)
    assert data["edges"][0]["label"] == "works_at"


def test_build_canvas_json_edge_direction_out():
    seed = _seed("alice", type_="Person")
    n1 = _neighbor("acme", type_="Org", rel="works_at", direction="out")
    laid_out = compute_layout([n1])
    data = build_canvas_json(seed, laid_out)
    edge = data["edges"][0]
    seed_node_id = next(n["id"] for n in data["nodes"] if n["x"] == 0 and n["y"] == 0)
    neighbour_id = next(n["id"] for n in data["nodes"] if n["id"] != seed_node_id)
    # out: fromNode is the seed
    assert edge["fromNode"] == seed_node_id
    assert edge["toNode"] == neighbour_id


def test_build_canvas_json_edge_direction_in():
    seed = _seed("anthropic", type_="Org")
    n1 = _neighbor("contextual-retrieval", type_="Topic", rel="cites", direction="in")
    laid_out = compute_layout([n1])
    data = build_canvas_json(seed, laid_out)
    edge = data["edges"][0]
    seed_node_id = next(n["id"] for n in data["nodes"] if n["x"] == 0 and n["y"] == 0)
    neighbour_id = next(n["id"] for n in data["nodes"] if n["id"] != seed_node_id)
    # in: fromNode is the neighbour
    assert edge["fromNode"] == neighbour_id
    assert edge["toNode"] == seed_node_id


def test_build_canvas_json_ids_stable_across_runs():
    seed = _seed()
    n1 = _neighbor("contextual-retrieval", type_="Topic")
    laid = compute_layout([n1])
    d1 = build_canvas_json(seed, laid)
    d2 = build_canvas_json(seed, laid)
    assert d1["nodes"][0]["id"] == d2["nodes"][0]["id"]
    assert d1["edges"][0]["id"] == d2["edges"][0]["id"]


# ── apply_canvas (end-to-end with stub graph) ───────────────

def test_apply_canvas_rejects_unknown_type(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    with pytest.raises(CanvasError):
        apply_canvas(tmp_path, "Unicorn", "alice", dry_run=True)


def test_apply_canvas_rejects_missing_page(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    (tmp_path / "wiki" / "people").mkdir(parents=True)
    (tmp_path / ".kb").mkdir()
    with pytest.raises(CanvasError):
        apply_canvas(tmp_path, "Person", "ghost", dry_run=True)


def test_apply_canvas_writes_canvas_file(tmp_path, monkeypatch):
    # Build minimal vault + frontmatter
    (tmp_path / "CLAUDE.md").write_text("# fake")
    (tmp_path / "wiki" / "people").mkdir(parents=True)
    (tmp_path / "wiki" / "_maps").mkdir(parents=True)
    (tmp_path / ".kb").mkdir()
    (tmp_path / "wiki" / "people" / "alice.md").write_text(
        "---\ntype: Person\nslug: alice\n---\nbody"
    )
    (tmp_path / "wiki" / "orgs").mkdir()
    (tmp_path / "wiki" / "orgs" / "acme.md").write_text(
        "---\ntype: Org\nslug: acme\n---\nbody"
    )

    # Patch graph_neighbors to return a known one-hop neighbour
    import canvas as canvas_mod
    monkeypatch.setattr(
        canvas_mod, "graph_neighbors",
        lambda db_path, ntype, slug, by_slug: [
            {"slug": "acme", "type": "Org", "rel_type": "works_at",
             "weight": 3.0, "direction": "out",
             "path": Path("wiki/orgs/acme.md")},
        ]
    )
    result = apply_canvas(tmp_path, "Person", "alice", dry_run=False)
    assert result.applied
    canvas_path = tmp_path / "wiki" / "_maps" / "alice.canvas"
    assert canvas_path.is_file()
    data = json.loads(canvas_path.read_text())
    assert any(n["file"] == "wiki/people/alice.md" for n in data["nodes"])
    assert any(n["file"] == "wiki/orgs/acme.md" for n in data["nodes"])
    assert len(data["edges"]) == 1


def test_apply_canvas_dry_run_does_not_write(tmp_path, monkeypatch):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    (tmp_path / "wiki" / "people").mkdir(parents=True)
    (tmp_path / "wiki" / "_maps").mkdir(parents=True)
    (tmp_path / ".kb").mkdir()
    (tmp_path / "wiki" / "people" / "alice.md").write_text(
        "---\ntype: Person\nslug: alice\n---\n"
    )

    import canvas as canvas_mod
    monkeypatch.setattr(canvas_mod, "graph_neighbors", lambda *a, **kw: [])
    result = apply_canvas(tmp_path, "Person", "alice", dry_run=True)
    assert not result.applied
    assert not (tmp_path / "wiki" / "_maps" / "alice.canvas").exists()


def test_apply_canvas_returns_n_neighbors(tmp_path, monkeypatch):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    (tmp_path / "wiki" / "people").mkdir(parents=True)
    (tmp_path / "wiki" / "_maps").mkdir(parents=True)
    (tmp_path / ".kb").mkdir()
    (tmp_path / "wiki" / "people" / "alice.md").write_text(
        "---\ntype: Person\nslug: alice\n---\n"
    )

    import canvas as canvas_mod
    monkeypatch.setattr(canvas_mod, "graph_neighbors", lambda *a, **kw: [
        {"slug": "a", "type": "Org", "rel_type": "works_at", "weight": 3.0, "direction": "out", "path": Path("wiki/orgs/a.md")},
        {"slug": "b", "type": "Org", "rel_type": "works_at", "weight": 3.0, "direction": "out", "path": Path("wiki/orgs/b.md")},
        {"slug": "c", "type": "Topic", "rel_type": "related", "weight": 1.0, "direction": "out", "path": Path("wiki/topics/c.md")},
    ])
    result = apply_canvas(tmp_path, "Person", "alice", dry_run=True)
    assert result.n_neighbors == 3


def test_type_colors_complete():
    # Every node type has a colour
    expected = {"Person", "Org", "Project", "Topic", "Decision", "Meeting", "Source", "Artifact", "Event"}
    assert set(TYPE_COLORS.keys()) == expected
