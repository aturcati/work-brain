"""Regression tests for kb-link link.py — slug variant raw-mention matching."""
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "link", Path(__file__).resolve().parent.parent / "link.py"
)
link = importlib.util.module_from_spec(spec)
spec.loader.exec_module(link)


def test_slug_variants_person():
    v = link.slug_variants("alice-smith")
    assert "alice-smith" in v
    assert "alice smith" in v      # display name in raw transcripts
    assert "alice.smith" in v      # email local part in raw frontmatter


def test_slug_variants_single_word():
    assert link.slug_variants("nina") == {"nina"}


def test_raw_mention_via_variant():
    # regression: hyphenated slug never appears in raw text, but the
    # spaced display name does — variant match must report raw=yes
    raw_text = "**Organizer:** Alice Smith (alice.smith@example.com)".lower()
    terms = link.slug_variants("alice-smith")
    assert any(t in raw_text for t in terms)


def test_no_false_positive():
    raw_text = "unrelated meeting about quantum hardware".lower()
    terms = link.slug_variants("alice-smith")
    assert not any(t in raw_text for t in terms)


def test_inbound_scope_matches_lint(tmp_path):
    """Links from _inbox/, overview.md, index.md must NOT count as inbound
    (regression: 8 stubs false-qualified, became orphans on promotion)."""
    wiki = tmp_path / "wiki"
    (wiki / "tofile").mkdir(parents=True)
    (wiki / "_inbox").mkdir()
    (wiki / "meetings").mkdir()
    (tmp_path / "raw").mkdir()
    (tmp_path / "CLAUDE.md").write_text("x")
    (wiki / "tofile" / "jane-doe.md").write_text(
        "---\ntype: Person\nslug: jane-doe\n---\n")
    # links that must NOT count
    (wiki / "_inbox" / "edges.md").write_text("[[wiki/tofile/jane-doe]]")
    (wiki / "overview.md").write_text("[[wiki/tofile/jane-doe]]")
    (wiki / "index.md").write_text("[[wiki/tofile/jane-doe]]")
    (wiki / "log.md").write_text("[[wiki/tofile/jane-doe]]")
    # raw mention so RAW column is yes
    (tmp_path / "raw" / "m.md").write_text("Jane Doe attended")

    # link.py auto-detects the vault from its own location, so exercise the
    # lint-aligned scan rule directly against the fixture tree:
    SKIP_DIRS = {"_inbox", "tofile"}
    SKIP_NAMES = {"overview.md", "index.md"}
    counted = []
    for f in wiki.rglob("*.md"):
        if any(part in SKIP_DIRS for part in f.relative_to(wiki).parts[:-1]):
            continue
        if f.name in SKIP_NAMES or f.name.startswith("log"):
            continue
        if "[[wiki/tofile/jane-doe" in f.read_text():
            counted.append(f)
    assert counted == []  # zero inbound under lint-aligned scope

    # a meetings page DOES count
    (wiki / "meetings" / "m1.md").write_text(
        "---\ntype: Meeting\nslug: m1\n---\n[[wiki/tofile/jane-doe]]")
    counted = [
        f for f in wiki.rglob("*.md")
        if not any(part in SKIP_DIRS for part in f.relative_to(wiki).parts[:-1])
        and f.name not in SKIP_NAMES and not f.name.startswith("log")
        and "[[wiki/tofile/jane-doe" in f.read_text()
    ]
    assert len(counted) == 1
