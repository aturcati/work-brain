import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from query import find_matches, parse_qmd_output


ALIASES = {
    "by_alias": {
        "alice smith": {"slug": "alice-smith", "type": "Person"},
        "alice-smith": {"slug": "alice-smith", "type": "Person"},
        "bob jones": {"slug": "bob-jones", "type": "Person"},
        "bob-jones": {"slug": "bob-jones", "type": "Person"},
        "acme": {"slug": "acme", "type": "Org"},
        "widget pricing": {"slug": "widget-pricing", "type": "Topic"},
        "2026-05-11-status-review": {"slug": "2026-05-11-status-review", "type": "Meeting"},
    },
    "by_slug": {
        "alice-smith": "Person",
        "bob-jones": "Person",
        "acme": "Org",
        "widget-pricing": "Topic",
        "2026-05-11-status-review": "Meeting",
    },
}


def test_find_matches_single_entity():
    result = find_matches("meetings with Alice Smith", ALIASES)
    assert len(result) == 1
    assert result[0]["slug"] == "alice-smith"
    assert result[0]["type"] == "Person"


def test_find_matches_two_entities():
    result = find_matches("Alice Smith and Bob Jones", ALIASES)
    slugs = [r["slug"] for r in result]
    assert "alice-smith" in slugs
    assert "bob-jones" in slugs


def test_find_matches_multi_word_preferred():
    result = find_matches("Widget pricing analysis", ALIASES)
    assert len(result) == 1
    assert result[0]["slug"] == "widget-pricing"


def test_find_matches_no_entity():
    result = find_matches("what is the weather today", ALIASES)
    assert result == []


def test_find_matches_slug_form():
    result = find_matches("about alice-smith", ALIASES)
    assert len(result) == 1
    assert result[0]["slug"] == "alice-smith"


def test_parse_qmd_output_basic():
    stdout = (
        "qmd://wiki/people/alice-smith.md:3 #abc123\n"
        "Title: alice-smith\n"
        "Score:  87%\n"
        "\n"
        "qmd://raw/meetings/2026/05/foo.md:1 #def456\n"
        "Title: foo\n"
        "Score:  62%\n"
    )
    results = parse_qmd_output(stdout)
    assert len(results) == 2
    assert results[0]["path"] == "wiki/people/alice-smith.md"
    assert results[0]["score"] == 87
    assert results[1]["path"] == "raw/meetings/2026/05/foo.md"
    assert results[1]["score"] == 62


def test_parse_qmd_output_empty():
    assert parse_qmd_output("") == []


def test_parse_qmd_output_no_score_line():
    stdout = "qmd://wiki/people/foo.md:1 #abc\nTitle: foo\n"
    results = parse_qmd_output(stdout)
    assert len(results) == 1
    assert results[0]["score"] == 0


import io
from contextlib import redirect_stdout


def test_merge_and_print_graph_first():
    from query import merge_and_print
    entities = [{"slug": "alice-smith", "type": "Person", "phrase": "alice smith"}]
    neighbors = {"alice-smith": [
        {"slug": "2026-05-07-acme-cloud-scrum-review", "type": "Meeting", "rel_type": "attended", "weight": 1.0},
    ]}
    qmd = [
        {"path": "wiki/meetings/2026-05-07-acme-cloud-scrum-review.md", "score": 80},
        {"path": "wiki/people/alice-smith.md", "score": 70},
    ]
    out = io.StringIO()
    with redirect_stdout(out):
        merge_and_print(entities, neighbors, qmd)
    lines = out.getvalue().splitlines()
    candidate_lines = [l for l in lines if l.startswith("CANDIDATE")]
    assert len(candidate_lines) == 2
    # Graph candidate comes before qmd-only
    assert "graph:attended" in candidate_lines[0]
    assert "qmd:" in candidate_lines[1]


def test_merge_and_print_filters_tofile():
    from query import merge_and_print
    qmd = [
        {"path": "wiki/tofile/someone.md", "score": 99},
        {"path": "wiki/people/alice-smith.md", "score": 50},
    ]
    out = io.StringIO()
    with redirect_stdout(out):
        merge_and_print([], {}, qmd)
    lines = out.getvalue().splitlines()
    candidate_lines = [l for l in lines if l.startswith("CANDIDATE")]
    assert len(candidate_lines) == 1
    assert "alice-smith" in candidate_lines[0]


def test_merge_and_print_no_entity_no_crash():
    from query import merge_and_print
    out = io.StringIO()
    with redirect_stdout(out):
        merge_and_print([], {}, [{"path": "wiki/topics/foo.md", "score": 60}])
    assert "CANDIDATE wiki/topics/foo.md" in out.getvalue()
