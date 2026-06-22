import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from suggest_merges import (
    normalise,
    page_terms,
    char_3grams,
    jaccard,
    score_pair,
    find_candidates,
    format_report,
)


def _page(slug, type_, aliases=None):
    return {"slug": slug, "type": type_, "aliases": aliases or []}


def test_normalise_lowercases_and_strips():
    assert normalise("  Dave  ") == "dave"
    assert normalise('"Alice Smith"') == "alice smith"


def test_page_terms_includes_slug_and_aliases():
    p = _page("dave-miller", "Person", aliases=["Dave", "D. Miller"])
    assert page_terms(p) == {"dave-miller", "dave", "d. miller"}


def test_char_3grams_basic():
    assert "dav" in char_3grams("dave")
    assert "ave" in char_3grams("dave")


def test_jaccard_identical_returns_1():
    assert jaccard({"a", "b"}, {"a", "b"}) == 1.0


def test_jaccard_disjoint_returns_0():
    assert jaccard({"a"}, {"b"}) == 0.0


def test_score_pair_exact_alias_overlap():
    a = _page("dave", "Person", aliases=[])
    b = _page("dave-miller", "Person", aliases=["Dave"])
    score, reason = score_pair(a, b)
    assert score == 1.0
    assert "exact" in reason.lower()


def test_score_pair_first_name_match():
    a = _page("dave", "Person", aliases=[])
    b = _page("dave-miller-acme", "Person", aliases=[])
    score, reason = score_pair(a, b)
    assert score >= 0.6
    assert "first" in reason.lower()


def test_score_pair_different_type_returns_zero():
    a = _page("acme", "Org", aliases=[])
    b = _page("acme", "Project", aliases=[])
    score, _ = score_pair(a, b)
    assert score == 0.0


def test_score_pair_ngram_threshold():
    a = _page("anthropic", "Org", aliases=[])
    b = _page("anthropics", "Org", aliases=[])
    score, reason = score_pair(a, b)
    assert score >= 0.75
    assert "3-gram" in reason


def test_score_pair_unrelated_returns_zero():
    a = _page("openai", "Org", aliases=[])
    b = _page("acme", "Org", aliases=[])
    score, _ = score_pair(a, b)
    assert score == 0.0


def test_find_candidates_ranks_by_score():
    pages = [
        _page("dave", "Person", aliases=[]),
        _page("dave-miller", "Person", aliases=["Dave"]),
        _page("alice", "Person", aliases=["Alice Smith"]),
    ]
    cands = find_candidates(pages, threshold=0.6)
    assert len(cands) == 1
    a, b, score, _ = cands[0]
    assert {a, b} == {"dave", "dave-miller"}
    assert score == 1.0


def test_find_candidates_respects_threshold():
    pages = [
        _page("openai", "Org", aliases=[]),
        _page("acme", "Org", aliases=[]),
    ]
    cands = find_candidates(pages, threshold=0.6)
    assert cands == []


def test_find_candidates_empty_input():
    assert find_candidates([], threshold=0.6) == []


def test_find_candidates_single_page():
    pages = [_page("dave", "Person", aliases=[])]
    assert find_candidates(pages, threshold=0.6) == []


def test_find_candidates_low_threshold_emits_ngram_under_075():
    pages = [
        _page("anthropic", "Org", aliases=[]),
        _page("anthropics", "Org", aliases=[]),
    ]
    cands = find_candidates(pages, threshold=0.6)
    assert len(cands) == 1
    _, _, score, reason = cands[0]
    assert score >= 0.6
    assert "3-gram" in reason or "exact" in reason


def test_format_report_no_candidates():
    out = format_report([])
    assert "no" in out.lower()


def test_format_report_with_candidates():
    cands = [("dave", "dave-miller", 1.0, "exact alias overlap")]
    out = format_report(cands)
    assert "dave" in out
    assert "dave-miller" in out
    assert "1.0" in out or "1.00" in out
